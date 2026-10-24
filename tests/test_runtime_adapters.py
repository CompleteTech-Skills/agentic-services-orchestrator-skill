"""Offline runtime boundary tests; callback and Herdr effects are simulated."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from runtime_adapters import HandoffAdapter, HerdrAdapter, NativeAdapter, validate_observation  # noqa: E402


def assignment(adapter="native"):
    return {
        "schema_version": 1, "workflow_id": "services-demo", "workflow_revision": 1,
        "track_id": "discovery", "run_id": "run-1", "assignment_id": "brief", "revision": 1,
        "owner": "discovery-specialist", "scope": "Prepare the approved discovery brief; do not send it.",
        "dependencies": [], "input_artifacts": [], "expected_outputs": [], "acceptance_criteria": [],
        "authorization": {"scope": "draft discovery brief", "provenance": "Synthetic fixture instruction",
                          "approval_refs": [], "expires_at": "2099-01-01T00:00:00Z"},
        "runtime": {"adapter": adapter, "required_capabilities": ["file-work"],
                    "role_config": {"worker": {"model": "fixture-model", "effort": "normal"}},
                    "limits": {"max_concurrency": 2, "max_delegation_depth": 1},
                    "deadline": "2099-01-01T00:00:00Z", "native_session_id": "session-1",
                    "native_goal_id": "goal-1"},
        "mode": "dispatch", "endpoint": "task", "independent_review": False,
        "required_checks": [], "stopping_conditions": ["Do not send any client communication."],
    }


def observed(task):
    return {
        "capabilities": ["file-work"], "role_config": copy.deepcopy(task["runtime"]["role_config"]),
        "limits": copy.deepcopy(task["runtime"]["limits"]), "owner": task["owner"],
        "native_session_id": task["runtime"]["native_session_id"],
        "native_goal_id": task["runtime"]["native_goal_id"], "evidence": "Simulated native status receipt",
    }


def identity(task):
    return {key: task[key] for key in ("workflow_id", "track_id", "run_id", "assignment_id", "revision")}


class RuntimeAdapterTests(unittest.TestCase):
    def native(self, task, **overrides):
        arguments = {
            "capabilities": ["file-work"],
            "submit": lambda item: {"status": "submitted", "operation_id": "op-1", "receipt": "fixture submission",
                                    "effective_runtime": observed(item)},
            "observe": lambda item: {**identity(item), "status": "submitted", "effective_runtime": observed(item)},
            "recover": lambda item, evidence: {"action": "reused-existing-owner", "receipt": "fixture recovery",
                                                "effective_runtime": observed(item)},
        }
        arguments.update(overrides)
        return NativeAdapter(**arguments)

    def test_native_submit_does_not_claim_acceptance_or_progress(self):
        task = assignment()
        receipt = self.native(task).submit(task)
        self.assertEqual(receipt["status"], "submitted")
        self.assertFalse(receipt["acceptance_verified"])
        self.assertEqual(receipt["assignment_id"], task["assignment_id"])
        self.assertEqual(self.native(task).observe(task)["status"], "submitted")

    def test_missing_declared_capability_prevents_submit(self):
        called = []
        with self.assertRaisesRegex(ValueError, "declare"):
            self.native(assignment(), capabilities=[], submit=lambda item: called.append(item)).submit(assignment())
        self.assertEqual(called, [])

    def test_observation_cannot_substitute_requested_settings(self):
        task = assignment()
        mutations = [
            lambda item: item.update(capabilities=[]),
            lambda item: item["role_config"]["worker"].update(model="different"),
            lambda item: item["limits"].update(max_concurrency=3),
            lambda item: item.update(owner="other-owner"),
            lambda item: item.update(native_session_id="new-session"),
            lambda item: item.update(native_goal_id="new-goal"),
            lambda item: item.update(evidence=""),
        ]
        for mutate in mutations:
            actual = observed(task)
            mutate(actual)
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                validate_observation(task, actual)

    def test_stricter_limits_are_valid(self):
        task = assignment()
        actual = observed(task)
        actual["limits"] = {"max_concurrency": 1, "max_delegation_depth": 0}
        self.assertEqual(validate_observation(task, actual), actual)

    def test_fractional_cost_limit_and_invalid_numeric_values(self):
        task = assignment()
        task["runtime"]["limits"]["max_cost"] = 0.5
        actual = observed(task)
        actual["limits"]["max_cost"] = 0.25
        self.assertEqual(validate_observation(task, actual), actual)
        for invalid in (True, float("inf"), float("nan"), 0.6, -0.1):
            actual["limits"]["max_cost"] = invalid
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                validate_observation(task, actual)

    def test_native_rejects_stale_observation_and_false_completion_receipt(self):
        task = assignment()
        with self.assertRaisesRegex(ValueError, "identity"):
            self.native(task, observe=lambda item: {**identity(item), "revision": 0, "status": "progressing",
                                                   "effective_runtime": observed(item)}).observe(task)
        with self.assertRaisesRegex(ValueError, "submission evidence"):
            self.native(task, submit=lambda item: {"status": "completed"}).submit(task)

    def test_recovery_preserves_existing_session_and_never_submits(self):
        task = assignment()
        evidence = {**identity(task), "status": "failed", "reconciled": True,
                    "uncertain_operations": [], "intentional_stop": False,
                    "existing_owner_recoverable": True, "effective_runtime": observed(task)}
        adapter = self.native(task, submit=lambda _: self.fail("recovery must not submit"))
        receipt = adapter.recover(task, evidence)
        self.assertEqual(receipt["effective_runtime"]["native_session_id"], "session-1")
        for key, value in (("reconciled", False), ("uncertain_operations", ["unknown-op"]),
                           ("intentional_stop", True), ("status", "completed"), ("revision", 0),
                           ("existing_owner_recoverable", False)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                adapter.recover(task, {**evidence, key: value})
        for field in ("deadline", "expires_at"):
            expired = copy.deepcopy(task)
            expired["runtime" if field == "deadline" else "authorization"][field] = "2000-01-01T00:00:00Z"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "expired"):
                adapter.recover(expired, evidence)

    def test_recovery_detects_unpinned_session_replacement(self):
        task = assignment()
        task["runtime"]["native_session_id"] = None
        evidence = {**identity(task), "status": "failed", "reconciled": True, "uncertain_operations": [],
                    "intentional_stop": False, "existing_owner_recoverable": True,
                    "effective_runtime": {**observed(task), "native_session_id": "existing-session"}}
        with self.assertRaisesRegex(ValueError, "replaced"):
            self.native(task).recover(task, evidence)

    def test_handoff_works_without_herdr_git_or_coding_requirements(self):
        task = assignment("handoff")
        task["scope"] += " Preserve café 🦊 and literal $(do-not-execute)."
        with tempfile.TemporaryDirectory() as temp:
            adapter = HandoffAdapter(Path(temp))
            receipt = adapter.submit(task)
            before = Path(receipt["receipt"]).read_bytes()
            self.assertEqual(json.loads(before), task)
            self.assertFalse(receipt["acceptance_verified"])
            self.assertTrue(adapter.submit(task)["duplicate"])
            self.assertEqual(Path(receipt["receipt"]).read_bytes(), before)
            self.assertEqual(adapter.observe(task)["status"], "submitted")
            self.assertEqual(adapter.recover(task, {})["action"], "manual-reconciliation")
            changed = {**task, "scope": "Different scope"}
            with self.assertRaisesRegex(ValueError, "different bytes"):
                adapter.submit(changed)

    def test_handoffs_reject_paths_inside_skill_checkout(self):
        with self.assertRaisesRegex(ValueError, "outside this skill"):
            HandoffAdapter(Path(__file__).resolve().parents[1] / "private")

    def test_explicit_adapter_selection_is_required(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, "explicitly selected"):
            HandoffAdapter(Path(temp)).submit(assignment())

    def test_optional_herdr_bridge_prepares_full_assignment_without_launching(self):
        task = assignment("herdr")
        task["endpoint"] = "implementation"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / "legacy" / "scripts" / "trusted helper.py"
            helper.parent.mkdir(parents=True)
            helper.write_text("# Trusted fake CLI; all effects mocked in this test.\n", encoding="utf-8")
            config = {"repository": "fixture/project", "scope": task["scope"], "delivery": "implementation",
                      "authority": {"implementation": "Synthetic instruction"}}
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                self.assertFalse(kwargs["shell"])
                self.assertEqual(command[:2], [sys.executable, str(helper.resolve())])
                action = command[2]
                result = {"valid": True}
                if action == "render":
                    result = {"contract_id": "legacy-1", "prompt_sha256": "a" * 64}
                if action == "verify":
                    result = {"artifacts_verified": True, "runtime_verified": False}
                return type("Process", (), {"returncode": 0, "stdout": json.dumps(result)})()

            with patch("runtime_adapters.subprocess.run", side_effect=fake_run):
                adapter = HerdrAdapter(helper, config, root / "private")
                receipt = adapter.submit(task)
                self.assertEqual(receipt["status"], "prepared")
                self.assertFalse(receipt["acceptance_verified"])
                mapping = json.loads(Path(receipt["receipt"]).read_text(encoding="utf-8"))
                self.assertEqual(mapping["authorization"], task["authorization"])
                self.assertEqual(json.loads(Path(receipt["receipt"]).with_name("assignment.json").read_text()), task)
                self.assertTrue(adapter.submit(task)["duplicate"])
                self.assertEqual(adapter.observe(task)["status"], "prepared")
                self.assertEqual(adapter.recover(task, {})["action"], "manual-reconciliation")
                self.assertEqual([command[2] for command in calls].count("render"), 1)
                self.assertTrue(all(command[2] in {"validate", "render", "verify"} for command in calls))

    def test_bundled_helper_prepares_without_separate_repository(self):
        task = assignment("herdr")
        task["endpoint"] = "implementation"
        task["runtime"]["native_session_id"] = "12345678-1234-4234-8234-123456789abc"
        config = {"repository": "fixture/project", "scope": task["scope"], "delivery": "implementation",
                  "authority": {"implementation": "Synthetic instruction for offline preparation"}}
        with tempfile.TemporaryDirectory() as temp:
            adapter = HerdrAdapter(config=config, private_directory=Path(temp))
            self.assertTrue(adapter.helper.is_relative_to(Path(__file__).resolve().parents[1]))
            receipt = adapter.submit(task)
            self.assertEqual(receipt["status"], "prepared")
            self.assertFalse(receipt["runtime_verified"])
            self.assertTrue(adapter.submit(task)["duplicate"])
            self.assertEqual(adapter.observe(task)["status"], "prepared")

    def test_herdr_bridge_rejects_original_cutoff_or_session_drift_before_helper(self):
        task = assignment("herdr")
        task["endpoint"] = "implementation"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / "legacy" / "scripts" / "prepare_run.py"
            helper.parent.mkdir(parents=True)
            helper.write_text("# Synthetic trusted helper\n", encoding="utf-8")
            for changed in ({"limits": {"original_cutoff_utc": "2098-01-01T00:00:00Z"}},
                            {"target": {"native_session_uuid": "different-session"}}):
                config = {"repository": "fixture/project", "scope": task["scope"],
                          "delivery": "implementation", **changed}
                with self.subTest(changed=changed), patch("runtime_adapters.subprocess.run") as run:
                    with self.assertRaisesRegex(ValueError, "differs"):
                        HerdrAdapter(helper, config, root / "private").submit(task)
                    run.assert_not_called()

    def test_herdr_bridge_rejects_conflicting_roles_limits_and_permissions(self):
        task = assignment("herdr")
        task["endpoint"] = "implementation"
        task["runtime"]["role_config"]["permissions"] = "workspace"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / "legacy" / "scripts" / "prepare_run.py"
            helper.parent.mkdir(parents=True)
            helper.write_text("# Synthetic trusted helper\n", encoding="utf-8")
            conflicts = [
                {"models": {"worker": "different-model"}}, {"models": {"effort": "different-effort"}},
                {"models": {"max_workers": 3}}, {"models": {"levels": 3}}, {"permission": "yolo"},
                {"target": {"goal_id": "replacement-goal"}},
            ]
            for changed in conflicts:
                config = {"repository": "fixture/project", "scope": task["scope"],
                          "delivery": "implementation", **changed}
                with self.subTest(changed=changed), patch("runtime_adapters.subprocess.run") as run:
                    with self.assertRaises(ValueError):
                        HerdrAdapter(helper, config, root / "private").submit(task)
                    run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
