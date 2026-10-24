"""Synthetic schema regressions; these tests do not dispatch work or contact services."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from contracts import canonical_digest, validate_assignment, validate_result  # noqa: E402


def assignment_fixture():
    return {
        "schema_version": 1,
        "workflow_id": "synthetic-services",
        "workflow_revision": 1,
        "track_id": "discovery",
        "run_id": "run-001",
        "assignment_id": "assignment-001",
        "revision": 1,
        "owner": "discovery-specialist",
        "scope": "Draft a readiness brief from the supplied synthetic notes.",
        "dependencies": [],
        "input_artifacts": [{"artifact": "interview-notes", "version": "v1"}],
        "expected_outputs": [{"artifact": "readiness-brief", "acceptance_criteria": ["Sources are attributed"]}],
        "acceptance_criteria": ["Sources are attributed"],
        "authorization": {
            "scope": "Draft a readiness brief from the supplied synthetic notes.",
            "provenance": "Synthetic operator request fixture.",
            "approval_refs": [{"approval_id": "scope-approval", "revision": 1}],
            "expires_at": "2099-12-31T23:59:59Z",
        },
        "runtime": {
            "adapter": "handoff",
            "required_capabilities": [],
            "role_config": {"specialist": "discovery", "fallback": "handoff"},
            "limits": {"max_concurrency": 1, "max_delegation_depth": 0},
            "deadline": "2099-12-30T23:59:59Z",
            "native_session_id": None,
            "native_goal_id": None,
        },
        "endpoint": "task",
        "mode": "dispatch",
        "stopping_conditions": ["Stop if requested scope changes"],
        "independent_review": False,
        "required_checks": [],
        "proposed_transition": {"from": "discovery", "to": "proposal"},
    }


def result_fixture():
    return {
        "schema_version": 1,
        "workflow_id": "synthetic-services",
        "track_id": "discovery",
        "run_id": "run-001",
        "assignment_id": "assignment-001",
        "assignment_revision": 1,
        "result_id": "observation-001",
        "observed_status": "acknowledged",
        "owner": "discovery-specialist",
        "observed_at": "2099-12-01T12:00:00Z",
        "produced_artifacts": [],
        "validation": [],
        "reviews": [],
        "external_operations": [],
        "blockers": [],
        "pending_actions": ["Draft readiness brief"],
        "proposed_transition": None,
        "evidence": {
            "accepted_assignment_digest": canonical_digest(assignment_fixture()),
            "work": [],
            "effective_runtime": {"adapter": "handoff", "capabilities": []},
            "endpoint": None,
        },
        "stop_reason": None,
    }


class ContractTests(unittest.TestCase):
    def test_valid_services_contract_without_git_or_agents(self):
        validate_assignment(assignment_fixture())
        validate_result(result_fixture())

    def test_schemas_are_valid_and_only_use_local_fragment_references(self):
        for name in ("assignment", "result"):
            with self.subTest(name=name):
                schema = json.loads((ROOT / "references" / f"{name}.schema.json").read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)

                def visit(value):
                    if isinstance(value, dict):
                        if "$ref" in value:
                            self.assertTrue(value["$ref"].startswith("#/"))
                        for child in value.values():
                            visit(child)
                    elif isinstance(value, list):
                        for child in value:
                            visit(child)

                visit(schema)

    def test_every_assignment_field_is_required(self):
        for name in assignment_fixture():
            data = assignment_fixture()
            del data[name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "required property"):
                validate_assignment(data)

    def test_every_result_field_is_required(self):
        for name in result_fixture():
            data = result_fixture()
            del data[name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "required property"):
                validate_result(data)

    def test_invalid_assignment_types_and_limits(self):
        for name, value in (
            ("schema_version", True), ("revision", 0), ("workflow_revision", "1"),
            ("owner", "  "), ("scope", ""), ("dependencies", "other"),
            ("expected_outputs", []), ("acceptance_criteria", []),
            ("independent_review", "yes"), ("mode", "run"), ("endpoint", "any"),
            ("stopping_conditions", []), ("required_checks", [""]),
        ):
            data = assignment_fixture()
            data[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_assignment(data)
        for name, value in (("max_concurrency", 0), ("max_delegation_depth", -1), ("max_tokens", 0)):
            data = assignment_fixture()
            data["runtime"]["limits"][name] = value
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                validate_assignment(data)

    def test_structural_unknown_fields_do_not_grant_authority(self):
        for path in ((), ("authorization",), ("runtime",), ("runtime", "limits")):
            data = assignment_fixture()
            target = data
            for component in path:
                target = target[component]
            target["business_approved"] = True
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Additional properties"):
                validate_assignment(data)
        for path in ((), ("evidence",)):
            data = result_fixture()
            target = data
            for component in path:
                target = target[component]
            target["grant_approval"] = True
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Additional properties"):
                validate_result(data)

    def test_configurable_roles_and_effective_runtime(self):
        data = assignment_fixture()
        data["runtime"]["adapter"] = "native"
        data["runtime"]["required_capabilities"] = ["assign", "observe"]
        data["runtime"]["role_config"] = {
            "implementer": {"model": "operator-selected", "effort": "operator-selected"},
            "reviewer": {"model": "another-selection", "independent": True},
            "fallback": {"policy": "explicit-handoff"},
        }
        data["runtime"]["limits"].update(max_concurrency=3, max_delegation_depth=2, max_tokens=1000)
        data["runtime"]["native_session_id"] = "existing-session"
        data["runtime"]["native_goal_id"] = "existing-goal"
        validate_assignment(data)
        result = result_fixture()
        result["evidence"]["effective_runtime"] = {"model_verified": False, "unknown_settings": ["model"]}
        validate_result(result)

    def test_utc_timestamps_are_validated_not_just_strings(self):
        for value in ("tomorrow", "2099-02-30T12:00:00Z", "2099-12-01T12:00:00", "2099-12-01T12:00:00-05:00"):
            assignment = assignment_fixture()
            assignment["runtime"]["deadline"] = value
            result = result_fixture()
            result["observed_at"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_assignment(assignment)
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_result(result)
        assignment = assignment_fixture()
        assignment["authorization"]["expires_at"] = "2099-12-31T23:59:59+00:00"
        validate_assignment(assignment)

    def test_duplicate_assignment_identities_are_rejected(self):
        for field, record in (
            ("input_artifacts", {"artifact": "interview-notes", "version": "v2"}),
            ("expected_outputs", {"artifact": "readiness-brief", "acceptance_criteria": ["Another criterion"]}),
        ):
            data = assignment_fixture()
            data[field].append(record)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "duplicate artifact"):
                validate_assignment(data)
        data = assignment_fixture()
        data["authorization"]["approval_refs"].append({"approval_id": "scope-approval", "revision": 2})
        with self.assertRaisesRegex(ValueError, "duplicate approval_id"):
            validate_assignment(data)
        data = assignment_fixture()
        data["dependencies"] = [data["assignment_id"]]
        with self.assertRaisesRegex(ValueError, "depend on itself"):
            validate_assignment(data)
        data["dependencies"] = ["other", "other"]
        with self.assertRaises(ValueError):
            validate_assignment(data)

    def test_duplicate_result_identities_are_rejected(self):
        examples = {
            "produced_artifacts": {"artifact": "brief", "version": "v1", "path": "brief.md", "source_artifacts": []},
            "validation": {"criterion": "Sources", "passed": True, "evidence": "Synthetic check", "artifact_versions": []},
            "external_operations": {"operation_id": "op-1", "kind": "pr", "status": "uncertain", "receipt": None, "revision": "abc"},
        }
        for field, example in examples.items():
            data = result_fixture()
            second = copy.deepcopy(example)
            if field == "produced_artifacts":
                second["version"] = "v2"
            elif field == "validation":
                second["passed"] = False
            else:
                second["status"] = "planned"
            data[field] = [example, second]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "duplicate"):
                validate_result(data)

    def test_conflicting_artifact_versions_in_evidence_are_rejected(self):
        for collection in ("validation", "reviews"):
            data = result_fixture()
            entry = {
                "passed": True, "evidence": "Synthetic review",
                "artifact_versions": [{"artifact": "brief", "version": "v1"}, {"artifact": "brief", "version": "v2"}],
            }
            if collection == "validation":
                entry["criterion"] = "Sources"
            else:
                entry.update(reviewer="independent-specialist", independent=True)
            data[collection] = [entry]
            with self.subTest(collection=collection), self.assertRaisesRegex(ValueError, "duplicate artifact"):
                validate_result(data)

    def test_statuses_and_uncertain_operations_remain_distinct(self):
        for status in (
            "submitted", "acknowledged", "progressing", "review-pending", "blocked", "stopped", "failed", "completed",
        ):
            data = result_fixture()
            data["observed_status"] = status
            data["external_operations"] = [{
                "operation_id": "op-1", "kind": "synthetic-effect", "status": "uncertain",
                "receipt": None, "revision": None,
            }]
            # A structurally valid observation is not validated completion or authority.
            with self.subTest(status=status):
                validate_result(data)
        data["observed_status"] = "success"
        with self.assertRaisesRegex(ValueError, "observed_status"):
            validate_result(data)

    def test_digest_is_stable_and_changes_with_assignment_revision(self):
        data = assignment_fixture()
        digest = canonical_digest(data)
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, canonical_digest(dict(reversed(list(data.items())))))
        self.assertEqual(digest, canonical_digest(json.loads(json.dumps(data, indent=2))))
        data["revision"] = 2
        self.assertNotEqual(digest, canonical_digest(data))

    def test_non_json_values_and_invalid_digests_are_rejected(self):
        for value in (float("nan"), float("inf"), {"set"}, ("tuple",), {1: "non-string key"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_digest(value)
        data = result_fixture()
        data["evidence"]["accepted_assignment_digest"] = "agent says accepted"
        with self.assertRaisesRegex(ValueError, "accepted_assignment_digest"):
            validate_result(data)


if __name__ == "__main__":
    unittest.main()
