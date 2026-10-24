"""Behavioral integration checks. All external/agent effects are simulated."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "examples"))
from orchestration import Conflict, Store  # noqa: E402
from runtime_adapters import HandoffAdapter, NativeAdapter  # noqa: E402
from integration_fixtures import approval, approve_outputs, effective, finish, fixture, private_temp_root, progress, result, verification  # noqa: E402
from contracts import canonical_digest  # noqa: E402


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=private_temp_root())
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.store = Store(self.directory / "state.sqlite")
        self.addCleanup(lambda: self.store.close())

    def start(self, domain="services", **kwargs):
        self.state, self.definition, self.assignment = fixture(domain, **kwargs)
        self.store.create_workflow(self.state, self.definition)
        self.adapter = HandoffAdapter(self.directory / "handoffs")
        return self.dispatch(self.assignment)

    def dispatch(self, assignment):
        return self.store.dispatch(assignment, self.adapter, actor=self.state["owner"], expected_workflow_revision=self.state["revision"])

    def record(self, output):
        return self.store.record_result(output, actor=self.assignment["owner"], expected_revision=self.current()["revision"])

    def current(self):
        return self.store.execution(self.assignment["assignment_id"])

    def verify(self, output):
        return self.store.verify_result(self.assignment["assignment_id"], verification(self.assignment, output), actor=self.assignment["owner"], expected_revision=self.current()["revision"])

    def test_services_handoff_advances_only_after_workflow_gates(self):
        self.start()
        self.assertEqual(self.current()["status"], "submitted")
        self.assertFalse(self.store.mode_satisfied(self.assignment["assignment_id"]))
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        self.record(output)
        self.assertEqual(self.current()["status"], "review-pending")
        with self.assertRaisesRegex(ValueError, "unverified"):
            self.store.consume(self.assignment["assignment_id"], actor=self.state["owner"], expected_workflow_revision=1)
        self.verify(output)
        with self.assertRaisesRegex(ValueError, "missing approval"):
            self.store.consume(self.assignment["assignment_id"], actor=self.state["owner"], expected_workflow_revision=1)
        self.assertEqual(self.store.workflow(self.state["workflow_id"])[0]["stage"], "discovery")
        state = approve_outputs(self.store, self.assignment, output)
        final = self.store.consume(self.assignment["assignment_id"], actor=self.state["owner"], expected_workflow_revision=state["revision"])
        self.assertEqual(final["stage"], "proposal")
        self.assertEqual(final["workflow_status"], "active")
        self.assertTrue(self.store.mode_satisfied(self.assignment["assignment_id"]))
        self.assertNotIn("repository", self.assignment)

    def test_hiring_works_without_git_agents_or_herdr(self):
        self.start("hiring")
        progress(self.store, self.assignment)
        output = finish(self.store, self.assignment)
        state = approve_outputs(self.store, self.assignment, output)
        state = self.store.consume(self.assignment["assignment_id"], actor=state["owner"], expected_workflow_revision=state["revision"])
        self.assertEqual(state["stage"], "sourcing")

    def test_dispatch_finishes_at_useful_progress_without_closing_workflow(self):
        self.start(mode="dispatch")
        self.record(result(self.assignment, "acknowledged"))
        self.assertFalse(self.store.mode_satisfied(self.assignment["assignment_id"]))
        self.record(result(self.assignment, "progressing"))
        self.assertTrue(self.store.mode_satisfied(self.assignment["assignment_id"]))
        self.assertEqual(self.store.workflow(self.state["workflow_id"])[0]["stage"], "discovery")

    def test_live_process_is_not_progress(self):
        self.start()
        self.record(result(self.assignment, "acknowledged"))
        output = result(self.assignment, "progressing")
        output["evidence"]["work"] = []
        with self.assertRaisesRegex(ValueError, "liveness"):
            self.record(output)

    def test_duplicate_dispatch_does_not_call_adapter(self):
        self.start()
        def forbidden(_):
            self.fail("duplicate caused external submission")
        self.adapter.submit = forbidden
        with self.assertRaises(Conflict):
            self.dispatch(self.assignment)
        self.assertEqual(len(list((self.directory / "handoffs").iterdir())), 1)

    def test_stale_result_revision_duplicate_and_wrong_owner_rejected(self):
        self.start()
        output = result(self.assignment, "acknowledged")
        stale = deepcopy(output)
        stale["assignment_revision"] += 1
        with self.assertRaisesRegex(ValueError, "stale assignment"):
            self.record(stale)
        with self.assertRaises(Conflict):
            self.store.record_result(output, actor="other", expected_revision=self.current()["revision"])
        old_revision = self.current()["revision"]
        self.record(output)
        with self.assertRaises(Conflict):
            self.store.record_result(output, actor=self.assignment["owner"], expected_revision=old_revision)
        with self.assertRaisesRegex(Conflict, "duplicate result"):
            self.record(output)

    def test_partial_completion_failed_checks_and_wrong_review_block(self):
        self.start("software", endpoint="implementation")
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        output["validation"][0]["passed"] = False
        self.record(output)
        with self.assertRaisesRegex(ValueError, "failed|check"):
            self.verify(output)
        self.record(result(self.assignment, "progressing"))
        output = result(self.assignment, "completed")
        output["reviews"][0]["reviewer"] = self.assignment["owner"]
        self.record(output)
        with self.assertRaisesRegex(ValueError, "independent"):
            self.verify(output)
        self.record(result(self.assignment, "progressing"))
        output = result(self.assignment, "completed")
        output["produced_artifacts"] = []
        self.record(output)
        with self.assertRaisesRegex(ValueError, "output set"):
            self.verify(output)

    def test_merge_needs_scoped_authority_and_remote_final_revision_receipt(self):
        self.start("software", endpoint="merge")
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed", version="commit-a")
        output["external_operations"] = []
        self.record(output)
        with self.assertRaisesRegex(ValueError, "remote endpoint"):
            self.verify(output)
        self.record(result(self.assignment, "progressing"))
        output = finish(self.store, self.assignment, result(self.assignment, "completed", version="commit-a"))
        self.assertEqual(self.current()["status"], "completed")
        self.assertEqual(output["external_operations"][0]["receipt"], "SIMULATED remote readback")

    def test_runtime_permission_does_not_supply_merge_authority(self):
        self.state, self.definition, self.assignment = fixture("software", endpoint="merge")
        self.assignment["authorization"]["approval_refs"] = []
        self.assignment["runtime"]["role_config"]["permissions"] = "full-access"
        self.store.create_workflow(self.state, self.definition)
        self.adapter = HandoffAdapter(self.directory / "handoffs")
        with self.assertRaisesRegex(ValueError, "scoped authority"):
            self.dispatch(self.assignment)

    def test_native_adapter_without_herdr(self):
        self.state, self.definition, self.assignment = fixture()
        self.assignment["runtime"]["adapter"] = "native"
        self.assignment["runtime"]["required_capabilities"] = ["assign", "observe"]
        self.store.create_workflow(self.state, self.definition)
        calls = []
        def submit(assignment):
            calls.append(assignment["assignment_id"])
            return {"status": "submitted", "operation_id": "mock-native-1", "receipt": "SIMULATED native tool receipt", "effective_runtime": effective(assignment)}
        self.adapter = NativeAdapter(capabilities=["assign", "observe"], submit=submit, observe=lambda _: None)
        self.dispatch(self.assignment)
        progress(self.store, self.assignment)
        self.assertEqual(calls, [self.assignment["assignment_id"]])

    def test_crash_after_external_submission_survives_reopen_and_reuses_owner(self):
        self.state, self.definition, self.assignment = fixture()
        self.store.create_workflow(self.state, self.definition)
        class Interrupted:
            def submit(self, assignment):
                raise TimeoutError("simulated remote side effect then timeout")
        self.adapter = Interrupted()
        with self.assertRaises(TimeoutError):
            self.dispatch(self.assignment)
        self.store.close()
        self.store = Store(self.directory / "state.sqlite")
        self.assertEqual(self.current()["dispatch_state"], "uncertain")
        original = deepcopy(self.current()["assignment"])
        evidence = {"evidence": "SIMULATED live session accepts original assignment", "owner": self.assignment["owner"],
                    "accepted_assignment_digest": canonical_digest(self.assignment), "effective_runtime": effective(self.assignment), "resume": True, "owner_available": True}
        self.store.reconcile(self.assignment["assignment_id"], evidence, actor=self.assignment["owner"], expected_revision=self.current()["revision"])
        self.record(result(self.assignment, "progressing"))
        self.assertEqual(self.current()["assignment"], original)
        self.assertTrue(self.current()["failure_history"])

    def test_uncertain_remote_effect_must_be_reconciled_and_pending_preserved(self):
        self.start("software", endpoint="deploy")
        progress(self.store, self.assignment)
        output = result(self.assignment, "blocked")
        operation = {"operation_id": "deploy-123", "kind": "deploy", "status": "uncertain", "receipt": None, "revision": "sha-123"}
        output["external_operations"] = [operation]
        output["pending_actions"] = ["check deployment"]
        self.record(output)
        evidence = {"evidence": "SIMULATED original owner alive", "owner": self.assignment["owner"], "resume": True, "owner_available": True,
                    "accepted_assignment_digest": canonical_digest(self.assignment), "effective_runtime": effective(self.assignment)}
        with self.assertRaisesRegex(ValueError, "uncertain external"):
            self.store.reconcile(self.assignment["assignment_id"], evidence, actor=self.assignment["owner"], expected_revision=self.current()["revision"])
        evidence["operations"] = [{**operation, "status": "succeeded", "receipt": "SIMULATED remote revision readback"}]
        evidence["resolved_pending_actions"] = ["check deployment"]
        self.store.reconcile(self.assignment["assignment_id"], evidence, actor=self.assignment["owner"], expected_revision=self.current()["revision"])
        self.assertEqual(self.current()["operations"]["deploy-123"]["status"], "succeeded")
        self.assertEqual(self.current()["pending_actions"], [])
        self.assertEqual(self.current()["status"], "acknowledged")

    def test_intentional_stop_cannot_restart_or_accept_late_result(self):
        self.start()
        self.store.stop(self.assignment["assignment_id"], actor=self.assignment["owner"], expected_revision=self.current()["revision"], reason="user stopped", evidence="SIMULATED stop request")
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.record(result(self.assignment, "acknowledged"))
        with self.assertRaisesRegex(ValueError, "intentional stop"):
            self.store.reconcile(self.assignment["assignment_id"], {"owner": self.assignment["owner"], "evidence": "SIMULATED live owner", "resume": True}, actor=self.assignment["owner"], expected_revision=self.current()["revision"])
        self.assertIn("verify workers stopped and no relaunch", self.current()["pending_actions"])

    def test_artifact_revision_invalidates_only_related_approval(self):
        self.start()
        state, _ = self.store.workflow(self.state["workflow_id"])
        state["approvals"]["related"] = approval(self.assignment, versions=[{"artifact": "source-notes", "version": "v1"}])
        state["approvals"]["unrelated"] = approval(self.assignment, category="business")
        state = self.store.update_workflow(state, actor=state["owner"], expected_revision=state["revision"])
        state["artifact_versions"][0]["status"] = "superseded"
        state["artifact_versions"].append({"artifact": "source-notes", "version": "v2", "path": "synthetic/source-v2.md", "status": "current", "source_artifacts": [{"artifact": "source-notes", "version": "v1"}]})
        state = self.store.update_workflow(state, actor=state["owner"], expected_revision=state["revision"])
        self.assertEqual(state["approvals"]["related"]["status"], "superseded")
        self.assertEqual(state["approvals"]["related"]["revision"], 2)
        self.assertEqual(state["approvals"]["unrelated"]["status"], "approved")
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        self.record(output)
        with self.assertRaisesRegex(ValueError, "stale or missing input"):
            self.verify(output)

    def test_workflow_owner_and_revision_check_prevent_bypass(self):
        self.start()
        state, _ = self.store.workflow(self.state["workflow_id"])
        state["stage"] = "proposal"
        with self.assertRaisesRegex(ValueError, "cannot change stage"):
            self.store.update_workflow(state, actor=state["owner"], expected_revision=1)
        with self.assertRaises(Conflict):
            self.store.consume(self.assignment["assignment_id"], actor=self.assignment["owner"], expected_workflow_revision=1)

    def test_domain_checks_are_part_of_assignment_before_dispatch(self):
        self.state, self.definition, self.assignment = fixture()
        self.store.create_workflow(self.state, self.definition)
        self.adapter = HandoffAdapter(self.directory / "handoffs")
        self.assignment["required_checks"] = []
        with self.assertRaisesRegex(ValueError, "domain-required checks"):
            self.dispatch(self.assignment)
        self.assertEqual(self.store.snapshot()["executions"], [])

    def test_self_review_by_configured_author_does_not_satisfy_independence(self):
        self.start("software", endpoint="implementation")
        progress(self.store, self.assignment)
        output = result(self.assignment, "completed")
        output["reviews"][0]["reviewer"] = self.assignment["runtime"]["role_config"]["author"]
        self.record(output)
        with self.assertRaisesRegex(ValueError, "independent"):
            self.verify(output)


if __name__ == "__main__":
    unittest.main()
