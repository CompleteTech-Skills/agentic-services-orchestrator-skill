"""Synthetic inputs for offline demonstrations and tests; never client authority."""
from copy import deepcopy
from pathlib import Path
import os
import sys
import tempfile
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from contracts import canonical_digest  # noqa: E402
from orchestration import now  # noqa: E402


def private_temp_root():
    """The Windows user home can itself be a Git workspace; choose a private temp root outside it."""
    candidates = [Path(tempfile.gettempdir())]
    if os.name == "nt":
        candidates.append(Path(os.environ.get("SystemRoot", "C:/Windows")) / "Temp")
    for candidate in candidates:
        if candidate.is_dir() and not any((p / ".git").exists() for p in (candidate, *candidate.parents)):
            return candidate
    raise RuntimeError("Set TMPDIR/TEMP to a writable temporary directory outside Git before running examples/tests")


def fixture(domain="services", *, endpoint="task", mode="supervise"):
    names = {"services": "completetech-services", "hiring": "hiring-pipeline", "software": "software-delivery"}
    definition = yaml.safe_load((ROOT / "references" / f"{names[domain]}-workflow.yaml").read_text(encoding="utf-8"))
    start = definition["stages"][0]["id"]
    target = definition["stages"][1]["id"]
    rule = definition["execution_rules"][0]
    workflow = {
        "workflow_id": "synthetic-" + domain, "revision": 1, "workflow_type": definition["workflow_type"],
        "owner": "workflow-coordinator", "stage": start, "workflow_status": "active",
        "active_tracks": [{"track_id": "main", "stage": start, "owner": "domain-specialist", "status": "active", "blockers": []}],
        "artifact_versions": [{"artifact": "source-notes", "version": "v1", "path": "synthetic/source.md", "status": "current", "source_artifacts": []}],
        "approvals": {}, "known_facts": {"discovery": {"ready_for_proposal": True}, "role": {"ready_for_sourcing": True}},
        "blockers": [], "events": [],
    }
    assignment = {
        "schema_version": 1, "workflow_id": workflow["workflow_id"], "workflow_revision": 1, "track_id": "main",
        "run_id": "synthetic-run", "assignment_id": "synthetic-assignment", "revision": 1, "owner": "execution-supervisor",
        "scope": "synthetic-scope", "dependencies": [],
        "input_artifacts": [{"artifact": "source-notes", "version": "v1"}],
        "expected_outputs": [{"artifact": "deliverable", "acceptance_criteria": ["acceptance"]}], "acceptance_criteria": ["acceptance"],
        "authorization": {"scope": "synthetic-scope", "provenance": "SIMULATED operator authorization; fixture only",
                          "approval_refs": [], "expires_at": "2099-12-31T00:00:00Z"},
        "runtime": {"adapter": "handoff", "required_capabilities": [],
                    "role_config": {"author": "domain-specialist", "reviewer": "independent-reviewer", "fallback": "explicit-handoff"},
                    "limits": {"max_concurrency": 1, "max_delegation_depth": 0}, "deadline": "2099-12-30T00:00:00Z",
                    "native_session_id": None, "native_goal_id": None},
        "endpoint": endpoint, "mode": mode, "stopping_conditions": ["Stop on scope changes or unresolved authority"],
        "independent_review": domain == "software", "required_checks": rule["required_checks"],
        "proposed_transition": {"from": start, "to": target},
    }
    if endpoint in {"merge", "deploy"}:
        category = "merge" if endpoint == "merge" else "deployment"
        workflow["approvals"]["endpoint-authority"] = approval(assignment, category=category)
        assignment["authorization"]["approval_refs"].append({"approval_id": "endpoint-authority", "revision": 1})
    return workflow, definition, assignment


def approval(assignment, *, category="artifact", versions=None):
    return {"revision": 1, "category": category, "status": "approved", "scope": assignment["authorization"]["scope"],
            "permits": [assignment["endpoint"]], "provenance": "SIMULATED approver receipt", "approved_by": "synthetic-domain-owner",
            "artifact_versions": versions if versions is not None else [], "remaining_blockers": []}


def effective(assignment):
    return {"capabilities": assignment["runtime"]["required_capabilities"], "role_config": deepcopy(assignment["runtime"]["role_config"]),
            "limits": deepcopy(assignment["runtime"]["limits"]), "owner": assignment["owner"],
            "native_session_id": assignment["runtime"]["native_session_id"], "native_goal_id": assignment["runtime"]["native_goal_id"],
            "evidence": "SIMULATED capability observation; no real agent launched"}


def result(assignment, status, *, version="v1"):
    done = status == "completed"
    versions = [{"artifact": "deliverable", "version": version}]
    output = {
        "schema_version": 1, **{k: assignment[k] for k in ("workflow_id", "track_id", "run_id", "assignment_id", "owner")},
        "assignment_revision": assignment["revision"], "result_id": str(uuid.uuid4()), "observed_status": status, "observed_at": now(),
        "produced_artifacts": [{"artifact": "deliverable", "version": version, "path": "synthetic/deliverable.md", "source_artifacts": deepcopy(assignment["input_artifacts"])}] if done else [],
        "validation": [{"criterion": c, "passed": True, "evidence": "SIMULATED check receipt", "artifact_versions": versions}
                       for c in sorted(set(assignment["acceptance_criteria"] + assignment["required_checks"]))] if done else [],
        "reviews": [{"reviewer": "independent-reviewer", "independent": True, "passed": True, "evidence": "SIMULATED review receipt", "artifact_versions": versions}] if done and assignment["independent_review"] else [],
        "external_operations": [], "blockers": [], "pending_actions": [], "proposed_transition": deepcopy(assignment["proposed_transition"]) if done else None,
        "evidence": {"accepted_assignment_digest": canonical_digest(assignment),
                     "work": ["SIMULATED work: synthetic deliverable sections drafted"] if status in {"progressing", "review-pending", "completed"} else [],
                     "effective_runtime": effective(assignment),
                     "endpoint": {"kind": assignment["endpoint"], "verified": True, "revision": version, "receipt": "SIMULATED endpoint readback"} if done else None},
        "stop_reason": None,
    }
    if done and assignment["endpoint"] in {"pr", "merge", "deploy"}:
        output["external_operations"] = [{"operation_id": "synthetic-remote-operation", "kind": assignment["endpoint"], "status": "succeeded", "receipt": "SIMULATED remote readback", "revision": version}]
    if status in {"blocked", "failed"}:
        output["blockers"] = ["SIMULATED interruption: existing session unavailable"]
    if status == "stopped":
        output["stop_reason"] = "SIMULATED intentional user stop"
    return output


def verification(assignment, output):
    return {"result_id": output["result_id"], "result_digest": canonical_digest(output), "verifier": assignment["owner"],
            "evidence": "SIMULATED supervisor independently read artifact/check/review/remote receipts",
            "artifact_versions": [{"artifact": a["artifact"], "version": a["version"]} for a in output["produced_artifacts"]],
            "endpoint": deepcopy(output["evidence"]["endpoint"])}


def progress(store, assignment):
    for status in ("acknowledged", "progressing"):
        store.record_result(result(assignment, status), actor=assignment["owner"], expected_revision=store.execution(assignment["assignment_id"])["revision"])


def finish(store, assignment, output=None):
    output = output or result(assignment, "completed")
    store.record_result(output, actor=assignment["owner"], expected_revision=store.execution(assignment["assignment_id"])["revision"])
    store.verify_result(assignment["assignment_id"], verification(assignment, output), actor=assignment["owner"], expected_revision=store.execution(assignment["assignment_id"])["revision"])
    return output


def approve_outputs(store, assignment, output):
    state, definition = store.workflow(assignment["workflow_id"])
    for item in output["produced_artifacts"]:
        for old in state["artifact_versions"]:
            if old["artifact"] == item["artifact"] and old.get("status", "current") == "current":
                old["status"] = "superseded"
        state["artifact_versions"].append({**deepcopy(item), "status": "current"})
    rule = next(r for r in definition["execution_rules"] if r["from"] == assignment["proposed_transition"]["from"] and r["to"] == assignment["proposed_transition"]["to"])
    for approval_id in rule["required_approvals"]:
        revision = state["approvals"].get(approval_id, {}).get("revision", 0) + 1
        state["approvals"][approval_id] = approval(assignment, versions=[{"artifact": x["artifact"], "version": x["version"]} for x in output["produced_artifacts"]])
        state["approvals"][approval_id]["revision"] = revision
    return store.update_workflow(state, actor=state["owner"], expected_revision=state["revision"])
