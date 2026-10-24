"""Independent adversarial review regressions; all effects and receipts are synthetic."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "examples"))
from contracts import canonical_digest  # noqa: E402
from integration_fixtures import approval, effective, finish, fixture, private_temp_root, progress, result, verification  # noqa: E402
from orchestration import Conflict, Store  # noqa: E402
from runtime_adapters import HandoffAdapter  # noqa: E402


class OrchestrationReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=private_temp_root())
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.store = Store(self.directory / "review.sqlite")
        self.addCleanup(self.store.close)
        self.adapter = HandoffAdapter(self.directory / "handoffs")

    def setup_workflow(self, domain="services", *, endpoint="task", tracks=1, concurrency=1):
        self.state, self.definition, self.assignment = fixture(domain, endpoint=endpoint)
        self.assignment["authorization"]["scope"] = self.assignment["scope"]
        for existing in self.state["approvals"].values():
            existing["scope"] = self.assignment["scope"]
        self.assignment["runtime"]["limits"]["max_concurrency"] = concurrency
        for index in range(1, tracks):
            lane = deepcopy(self.state["active_tracks"][0])
            lane["track_id"] = f"track-{index}"
            self.state["active_tracks"].append(lane)
        self.store.create_workflow(self.state, self.definition)

    def dispatch(self, assignment=None):
        assignment = assignment or self.assignment
        return self.store.dispatch(
            assignment, self.adapter, actor=self.state["owner"], expected_workflow_revision=self.state["revision"]
        )

    def current(self):
        return self.store.execution(self.assignment["assignment_id"])

    def record(self, output):
        return self.store.record_result(
            output, actor=self.assignment["owner"], expected_revision=self.current()["revision"]
        )

    def verify(self, output):
        return self.store.verify_result(
            self.assignment["assignment_id"], verification(self.assignment, output),
            actor=self.assignment["owner"], expected_revision=self.current()["revision"],
        )

    def recovery_evidence(self):
        return {
            "owner": self.assignment["owner"], "evidence": "SIMULATED live owner receipt",
            "accepted_assignment_digest": canonical_digest(self.assignment),
            "effective_runtime": effective(self.assignment), "resume": True, "owner_available": True,
        }

    def attach_input_approval(self):
        state, _ = self.store.workflow(self.state["workflow_id"])
        state["approvals"]["artifact_acceptance"] = approval(
            self.assignment, versions=deepcopy(self.assignment["input_artifacts"])
        )
        self.state = self.store.update_workflow(state, actor=state["owner"], expected_revision=state["revision"])
        self.assignment["workflow_revision"] = self.state["revision"]
        self.assignment["authorization"]["approval_refs"].append({"approval_id": "artifact_acceptance", "revision": 1})

    def test_assignment_scope_cannot_expand_referenced_authority(self):
        self.setup_workflow()
        self.assignment["scope"] = "Also commit the client to an unrelated commercial agreement"
        with self.assertRaisesRegex(ValueError, "scope"):
            self.dispatch()
        self.assertEqual(self.store.snapshot()["executions"], [])

    def test_run_limit_cannot_be_raised_by_a_later_assignment(self):
        self.setup_workflow(tracks=2)
        self.dispatch()
        next_assignment = deepcopy(self.assignment)
        next_assignment.update(assignment_id="second", track_id="track-1")
        next_assignment["runtime"]["limits"]["max_concurrency"] = 99
        with self.assertRaisesRegex(ValueError, "limit|concurrency"):
            self.dispatch(next_assignment)
        self.assertEqual(len(self.store.snapshot()["executions"]), 1)

    def test_original_authorization_window_is_pinned_across_run(self):
        self.setup_workflow(tracks=2, concurrency=2)
        self.dispatch()
        next_assignment = deepcopy(self.assignment)
        next_assignment.update(assignment_id="second", track_id="track-1")
        next_assignment["authorization"]["expires_at"] = "2100-12-31T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "authorization|cutoff|expir"):
            self.dispatch(next_assignment)

    def test_recovery_cannot_exceed_run_concurrency_after_another_track_starts(self):
        self.setup_workflow(tracks=2)
        self.dispatch()
        progress(self.store, self.assignment)
        self.record(result(self.assignment, "failed"))
        next_assignment = deepcopy(self.assignment)
        next_assignment.update(assignment_id="second", track_id="track-1")
        self.dispatch(next_assignment)
        with self.assertRaisesRegex(ValueError, "concurrency|limit"):
            self.store.reconcile(
                self.assignment["assignment_id"], self.recovery_evidence(), actor=self.assignment["owner"],
                expected_revision=self.current()["revision"],
            )
        self.assertEqual(self.current()["status"], "failed")

    def test_merge_and_deployment_keep_separate_narrow_authority(self):
        self.state, self.definition, self.assignment = fixture("software", endpoint="deploy")
        self.assignment["authorization"]["scope"] = self.assignment["scope"]
        self.state["approvals"]["endpoint-authority"]["scope"] = self.assignment["scope"]
        merge = approval(self.assignment, category="merge")
        merge["permits"] = ["merge"]
        self.state["approvals"]["merge-authority"] = merge
        self.assignment["authorization"]["approval_refs"].append({"approval_id": "merge-authority", "revision": 1})
        self.store.create_workflow(self.state, self.definition)
        self.dispatch()
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        output["external_operations"].append({
            "operation_id": "prior-merge", "kind": "merge", "status": "succeeded",
            "receipt": "SIMULATED merge authority readback", "revision": "v1",
        })
        finish(self.store, self.assignment, output)
        self.assertEqual(self.current()["status"], "completed")

    def test_completed_but_unconsumed_result_retains_track_ownership(self):
        self.setup_workflow()
        self.dispatch()
        progress(self.store, self.assignment)
        finish(self.store, self.assignment)
        self.assertFalse(self.current()["consumed"])
        next_assignment = deepcopy(self.assignment)
        next_assignment.update(assignment_id="second", run_id="second-run")
        with self.assertRaisesRegex(Conflict, "track|owner|unconsumed"):
            self.dispatch(next_assignment)

    def test_concurrent_dispatch_reserves_track_once_before_external_effect(self):
        self.setup_workflow()
        barrier = threading.Barrier(2)
        calls = []
        calls_lock = threading.Lock()

        class MockAdapter:
            def submit(inner_self, assignment):
                with calls_lock:
                    calls.append(assignment["assignment_id"])
                return {"status": "submitted", "receipt": "SIMULATED send receipt"}

        def attempt(index):
            local_store = Store(self.directory / "review.sqlite")
            try:
                assignment = deepcopy(self.assignment)
                assignment["assignment_id"] = f"concurrent-{index}"
                barrier.wait(timeout=5)
                try:
                    local_store.dispatch(assignment, MockAdapter(), actor=self.state["owner"], expected_workflow_revision=1)
                    return "submitted"
                except Conflict:
                    return "conflict"
            finally:
                local_store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, (1, 2)))
        self.assertCountEqual(outcomes, ["submitted", "conflict"])
        self.assertEqual(len(calls), 1)

    def test_fast_acknowledgement_preserves_returned_submission_receipt(self):
        self.setup_workflow()
        store = self.store

        class FastAdapter:
            def submit(inner_self, assignment):
                store.record_result(result(assignment, "acknowledged"), actor=assignment["owner"], expected_revision=1)
                return {"status": "submitted", "operation_id": "fast-send", "receipt": "SIMULATED fast submit receipt"}

        self.adapter = FastAdapter()
        self.dispatch()
        saved = self.current()
        self.assertEqual(saved["status"], "acknowledged")
        self.assertEqual(saved["dispatch_state"], "acknowledged")
        self.assertEqual(saved["submission"]["receipt"], "SIMULATED fast submit receipt")
        self.assertEqual(saved["failure_history"], [])

    def test_stop_during_send_preserves_receipt_and_stop_intent(self):
        self.setup_workflow()
        store = self.store

        class StoppedAdapter:
            def submit(inner_self, assignment):
                store.stop(
                    assignment["assignment_id"], actor=assignment["owner"], expected_revision=1,
                    reason="SIMULATED stop during in-flight submit", evidence="SIMULATED operator receipt",
                )
                return {"status": "submitted", "operation_id": "in-flight-send", "receipt": "SIMULATED in-flight receipt"}

        self.adapter = StoppedAdapter()
        self.dispatch()
        saved = self.current()
        self.assertTrue(saved["intentional_stop"])
        self.assertEqual(saved["status"], "stopped")
        self.assertEqual(saved["submission"]["receipt"], "SIMULATED in-flight receipt")
        self.assertIn("verify workers stopped and no relaunch", saved["pending_actions"])

    def test_successful_effect_requires_receipt_even_for_non_remote_endpoint(self):
        self.setup_workflow()
        self.dispatch()
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        output["external_operations"] = [{
            "operation_id": "missing-receipt", "kind": "task", "status": "succeeded", "receipt": None, "revision": "v1",
        }]
        self.record(output)
        with self.assertRaisesRegex(ValueError, "receipt|evidence"):
            self.verify(output)

    def test_extra_external_effect_cannot_gain_authority_from_task_endpoint(self):
        self.setup_workflow()
        self.dispatch()
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        output["external_operations"] = [{
            "operation_id": "unrequested-merge", "kind": "merge", "status": "succeeded",
            "receipt": "SIMULATED unrequested merge", "revision": "v1",
        }]
        self.record(output)
        with self.assertRaisesRegex(ValueError, "author|scope|endpoint|permit"):
            self.verify(output)

    def test_definitive_failed_attempt_survives_successful_recovery(self):
        self.setup_workflow("software", endpoint="deploy")
        self.dispatch()
        progress(self.store, self.assignment)
        failed = result(self.assignment, "failed")
        failed["external_operations"] = [{
            "operation_id": "failed-deploy", "kind": "deploy", "status": "failed",
            "receipt": "SIMULATED server rejects request before deployment", "revision": "v1",
        }]
        self.record(failed)
        self.store.reconcile(
            self.assignment["assignment_id"], self.recovery_evidence(), actor=self.assignment["owner"],
            expected_revision=self.current()["revision"],
        )
        self.record(result(self.assignment, "progressing"))
        finish(self.store, self.assignment)
        saved = self.current()
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["operations"]["failed-deploy"]["status"], "failed")
        self.assertTrue(saved["failure_history"])
        self.assertEqual(saved["assignment"]["runtime"]["deadline"], self.assignment["runtime"]["deadline"])

    def test_revised_input_output_can_receive_approval_before_transition(self):
        self.setup_workflow()
        self.assignment["expected_outputs"][0]["artifact"] = "source-notes"
        self.dispatch()
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed", version="v2")
        output["produced_artifacts"][0]["artifact"] = "source-notes"
        versions = [{"artifact": "source-notes", "version": "v2"}]
        for check in output["validation"]:
            check["artifact_versions"] = deepcopy(versions)
        finish(self.store, self.assignment, output)
        staged, _ = self.store.workflow(self.state["workflow_id"])
        staged["artifact_versions"][0]["status"] = "superseded"
        staged["artifact_versions"].append({**deepcopy(output["produced_artifacts"][0]), "status": "current"})
        staged["approvals"]["artifact_acceptance"] = approval(self.assignment, versions=versions)
        staged = self.store.update_workflow(staged, actor=staged["owner"], expected_revision=staged["revision"])
        self.assertEqual(staged["stage"], "discovery")
        consumed = self.store.consume(
            self.assignment["assignment_id"], actor=staged["owner"], expected_workflow_revision=staged["revision"],
        )
        self.assertEqual(consumed["stage"], "proposal")
        self.assertEqual(self.current()["assignment"]["input_artifacts"], [{"artifact": "source-notes", "version": "v1"}])

    def test_coordinator_reapproval_preserves_original_assignment_authority(self):
        self.setup_workflow()
        self.assignment["expected_outputs"][0]["artifact"] = "source-notes"
        self.attach_input_approval()
        original_assignment = deepcopy(self.assignment)
        self.dispatch()
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed", version="v2")
        output["produced_artifacts"][0]["artifact"] = "source-notes"
        versions = [{"artifact": "source-notes", "version": "v2"}]
        for check in output["validation"]:
            check["artifact_versions"] = deepcopy(versions)
        finish(self.store, self.assignment, output)
        staged, _ = self.store.workflow(self.state["workflow_id"])
        staged["artifact_versions"][0]["status"] = "superseded"
        staged["artifact_versions"].append({**deepcopy(output["produced_artifacts"][0]), "status": "current"})
        reapproval = approval(self.assignment, versions=versions)
        reapproval["revision"] = 2
        staged["approvals"]["artifact_acceptance"] = reapproval
        staged = self.store.update_workflow(staged, actor=staged["owner"], expected_revision=staged["revision"])
        self.assertEqual(staged["stage"], "discovery")
        consumed = self.store.consume(
            self.assignment["assignment_id"], actor=staged["owner"], expected_workflow_revision=staged["revision"],
        )
        self.assertEqual(consumed["stage"], "proposal")
        self.assertEqual(self.current()["assignment"], original_assignment)
        self.assertEqual(consumed["approval_history"][0]["revision"], 1)
        self.assertEqual(consumed["approvals"]["artifact_acceptance"]["revision"], 2)

    def test_runtime_permissions_do_not_reauthorize_stale_approval_before_verification(self):
        self.setup_workflow()
        self.assignment["runtime"]["role_config"]["permissions"] = "full-access"
        self.attach_input_approval()
        self.dispatch()
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        self.record(output)
        state, _ = self.store.workflow(self.state["workflow_id"])
        state["approvals"]["artifact_acceptance"]["revision"] = 2
        state["approvals"]["artifact_acceptance"]["provenance"] = "SIMULATED revised approval requiring fresh acceptance"
        self.store.update_workflow(state, actor=state["owner"], expected_revision=state["revision"])
        with self.assertRaisesRegex(ValueError, "stale approval"):
            self.verify(output)
        self.assertEqual(self.current()["status"], "review-pending")

    def test_future_and_older_observations_cannot_establish_progress(self):
        self.setup_workflow()
        self.dispatch()
        future = result(self.assignment, "acknowledged")
        future["observed_at"] = "2099-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future"):
            self.record(future)
        self.record(result(self.assignment, "acknowledged"))
        stale = result(self.assignment, "progressing")
        stale["observed_at"] = "2000-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "stale|older"):
            self.record(stale)

    def test_result_cannot_replace_observed_native_identity(self):
        self.setup_workflow()
        self.dispatch()
        first = result(self.assignment, "acknowledged")
        first["evidence"]["effective_runtime"]["native_session_id"] = "existing-session"
        first["evidence"]["effective_runtime"]["native_goal_id"] = "existing-accounting"
        self.record(first)
        changed = result(self.assignment, "progressing")
        changed["evidence"]["effective_runtime"]["native_session_id"] = "replacement-session"
        changed["evidence"]["effective_runtime"]["native_goal_id"] = "replacement-accounting"
        with self.assertRaisesRegex(ValueError, "ownership|native|session"):
            self.record(changed)

    def test_expired_original_authorization_prevents_dispatch(self):
        self.setup_workflow()
        self.assignment["authorization"]["expires_at"] = "2000-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "authorization expired"):
            self.dispatch()
        self.assertEqual(self.store.snapshot()["executions"], [])

    def test_intentional_stop_survives_reopen_and_reconciliation(self):
        self.setup_workflow()
        self.dispatch()
        progress(self.store, self.assignment)
        self.store.stop(
            self.assignment["assignment_id"], actor=self.assignment["owner"], expected_revision=self.current()["revision"],
            reason="SIMULATED operator stop", evidence="SIMULATED stop receipt",
        )
        with StoreContext(self.directory / "review.sqlite") as reopened:
            saved = reopened.execution(self.assignment["assignment_id"])
            with self.assertRaisesRegex(ValueError, "intentional stop|completion"):
                reopened.reconcile(
                    self.assignment["assignment_id"], self.recovery_evidence(), actor=self.assignment["owner"],
                    expected_revision=saved["revision"],
                )
            self.assertEqual(reopened.execution(self.assignment["assignment_id"])["status"], "stopped")


class StoreContext:
    def __init__(self, path):
        self.store = Store(path)

    def __enter__(self):
        return self.store

    def __exit__(self, *_):
        self.store.close()


if __name__ == "__main__":
    unittest.main()
