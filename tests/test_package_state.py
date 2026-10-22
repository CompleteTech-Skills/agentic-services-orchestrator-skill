"""Synthetic project_state checks for scripts/validate_state.py; no specialist code is executed."""
import copy
import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_state", ROOT / "scripts/validate_state.py")
assert SPEC and SPEC.loader
state_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state_check)

try:
    import yaml
except ImportError:  # the package-contract job runs without PyYAML
    yaml = None

WORKFLOW = {
    "workflow_type": "demo",
    "stages": [{"id": "draft"}, {"id": "review"}, {"id": "done"}],
    "allowed_transitions": [
        {"from": "draft", "to": "review", "when": "ready"},
        {"from": "review", "to": "done", "when": "signed", "requires_gates": ["signoff"]},
    ],
    "gates": [{"gate_id": "signoff"}, {"gate_id": "send", "approval_field": "external_send"}],
    "gated_actions": [{"action": "external_send", "requires_gates": ["send"]}],
    "approval_states": ["unknown", "draft", "requested", "partial", "approved", "rejected", "expired",
                        "superseded", "blocked", "conditional"],
    "specialist_owners": {"security_review": "reviewer"},
    "terminal_states": [{"id": "closed", "allows_open_blockers": False}],
}


def approval(status="unknown", by="TBD", at="TBD", permits=()):
    return {"status": status, "approved_by": by, "approved_at": at, "permits": list(permits)}


def base_state():
    return {
        "workflow_type": "demo",
        "approvals": {"signoff": approval(), "external_send": approval()},
        "state_transitions": [{"from": "draft", "to": "review", "when": "ready"}],
        "active_tracks": [{"track_id": "T1", "stage": "security_review", "status": "active", "owner": "TBD"}],
        "artifact_versions": [{"artifact_id": "A1", "version": "v1", "source_artifacts": []}],
    }


def rules(violations):
    return sorted(set(re.findall(r"^VIOLATION \[(\w+)\]", "\n".join(violations), re.M)))


class StateValidatorTests(unittest.TestCase):
    def check(self, state, actions=()):
        return state_check.validate_state(state, WORKFLOW, list(actions))[0]

    def test_valid_state(self):
        self.assertEqual(self.check(base_state()), [])

    def test_disallowed_transition(self):
        state = base_state()
        state["state_transitions"].append({"from": "draft", "to": "security_review", "when": "risk"})
        self.assertEqual(rules(self.check(state)), ["invalid_transition"])

    def test_gated_transition_needs_attributed_approval(self):
        state = base_state()
        state["state_transitions"].append({"from": "review", "to": "done", "when": "signed"})
        self.assertEqual(rules(self.check(state)), ["gate_not_satisfied"])
        state["approvals"]["signoff"] = approval("approved", "Signer", "TBD")
        self.assertEqual(rules(self.check(state)), ["approval_without_attribution", "gate_not_satisfied"])
        state["approvals"]["signoff"] = approval("approved", "Signer", "2026-06-01")
        self.assertEqual(self.check(state), [])

    def test_stale_approvals_do_not_authorize(self):
        for status in ("expired", "superseded", "rejected", "blocked", "requested"):
            with self.subTest(status=status):
                state = base_state()
                state["approvals"]["external_send"] = approval(status, "Sender", "2026-06-01")
                self.assertEqual(rules(self.check(state, ["external_send"])), ["external_action_without_approval_evidence"])

    def test_conditional_approval_needs_action_in_permits(self):
        state = base_state()
        state["approvals"]["external_send"] = approval("conditional", "Sender", "2026-06-01", ["draft only"])
        self.assertTrue(self.check(state, ["external_send"]))
        state["approvals"]["external_send"]["permits"].append("external_send")
        self.assertEqual(self.check(state, ["external_send"]), [])

    def test_missing_unknown_and_invalid_records(self):
        state = base_state()
        del state["approvals"]["signoff"]
        state["approvals"]["billing"] = approval()
        state["approvals"]["external_send"]["status"] = "maybe"
        self.assertEqual(rules(self.check(state)), ["invalid_approval", "missing_approval_record", "unknown_approval"])

    def test_unknown_action_tracks_artifacts_and_terminal(self):
        state = base_state()
        state["active_tracks"][0].update(stage="nowhere", status="paused")
        del state["active_tracks"][0]["owner"]
        state["artifact_versions"][0] = {"artifact_id": "A1"}
        state.update(workflow_status="closed", blockers=["open item"], workflow_type="other")
        self.assertEqual(rules(self.check(state, ["launch"])), [
            "artifact_without_source_or_version", "invalid_track_stage", "invalid_track_status", "missing_owner",
            "terminal_state_with_open_blockers", "unknown_action", "workflow_type_mismatch"])

    def test_cli_exit_codes_with_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflow, state = Path(tmp) / "workflow.json", Path(tmp) / "state.json"
            workflow.write_text(json.dumps(WORKFLOW), encoding="utf-8")
            state.write_text(json.dumps({"project_state": base_state()}), encoding="utf-8")
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(state_check.main([str(state), "--workflow", str(workflow)]), 0)
                self.assertEqual(state_check.main([str(state), "--workflow", str(workflow), "--action", "external_send"]), 1)
                self.assertEqual(state_check.main([str(Path(tmp) / "missing.json"), "--workflow", str(workflow)]), 2)
            self.assertIn("VIOLATION [external_action_without_approval_evidence]", output.getvalue())


@unittest.skipIf(yaml is None, "PyYAML not installed")
class BundledExampleTests(unittest.TestCase):
    def load(self, name):
        return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))

    def test_example_state_is_consistent_with_default_adapter(self):
        state = state_check.extract_state(self.load("references/full-workflow-variables.yaml"))
        workflow = self.load("references/completetech-services-workflow.yaml")
        self.assertEqual(state_check.validate_state(state, workflow)[0], [])
        blocked = state_check.validate_state(state, workflow, ["external_send", "issue_invoice", "production_launch"])[0]
        self.assertEqual(len(blocked), 3)

    def test_every_gate_and_gated_action_resolves(self):
        for name in ("references/completetech-services-workflow.yaml", "references/hiring-pipeline-workflow.yaml"):
            workflow = self.load(name)
            gates = {g["gate_id"] for g in workflow["gates"]}
            needed = [g for item in workflow.get("gated_actions", []) + workflow["allowed_transitions"]
                      for g in item.get("requires_gates", [])]
            self.assertTrue(set(needed) <= gates, name)

    def test_markdown_copy_matches_yaml_example(self):
        text = (ROOT / "references/full-workflow-variables.md").read_text(encoding="utf-8")
        block = re.search(r"## Canonical Workflow Variables\s+```yaml\n(.*?)```", text, re.S)
        assert block
        self.assertEqual(yaml.safe_load(block.group(1)), self.load("references/full-workflow-variables.yaml"))

    def test_mutated_example_is_rejected(self):
        state = state_check.extract_state(self.load("references/full-workflow-variables.yaml"))
        workflow = self.load("references/completetech-services-workflow.yaml")
        bad = copy.deepcopy(state)
        bad["state_transitions"].append({"from": "delivery", "to": "security_review", "when": "risk"})
        bad["approvals"]["public_proof"]["approved_at"] = "TBD"
        del bad["approvals"]["billing"]
        self.assertEqual(rules(state_check.validate_state(bad, workflow)[0]),
                         ["approval_without_attribution", "invalid_transition", "missing_approval_record"])


if __name__ == "__main__":
    unittest.main()
