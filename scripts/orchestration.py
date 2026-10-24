#!/usr/bin/env python3
"""Local workflow coordination and execution supervision; no background or network work.

The operator is the trust boundary. Actor strings identify already authenticated
callers; this library is not an authentication service. Use a private local DB.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
import uuid

import yaml

from contracts import canonical_digest, validate_assignment, validate_result
from runtime_adapters import validate_observation


class Conflict(ValueError):
    """A stale revision, owner conflict, or duplicate assignment requires reconciliation."""


TRANSITIONS = {
    "submitted": {"acknowledged", "blocked", "stopped", "failed"},
    "acknowledged": {"progressing", "blocked", "stopped", "failed"},
    "progressing": {"review-pending", "blocked", "stopped", "failed"},
    "review-pending": {"progressing", "blocked", "stopped", "failed"},
    "blocked": set(), "failed": set(), "stopped": set(), "completed": set(),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def instant(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamps require an explicit timezone")
    return dt


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def refs(items: list[dict]) -> set[tuple[str, str]]:
    return {(a["artifact"], a["version"]) for a in items}


def current_artifacts(state: dict) -> dict[str, dict]:
    return {a["artifact"]: a for a in state["artifact_versions"] if a.get("status", "current") == "current"}


def track(state: dict, track_id: str) -> dict:
    for item in state["active_tracks"]:
        if item["track_id"] == track_id:
            return item
    raise ValueError(f"unknown track: {track_id}")


def validate_workflow(state: dict, definition: dict) -> None:
    """Validate the executable extension, preserving unrelated legacy state fields."""
    for field in ("workflow_id", "owner", "workflow_type", "stage"):
        require(isinstance(state.get(field), str) and state[field].strip() not in ("", "TBD"), f"invalid {field}")
    require(type(state.get("revision")) is int and state["revision"] >= 1, "invalid workflow revision")
    require(state["workflow_type"] == definition["workflow_type"], "workflow definition mismatch")
    stages = {s["id"] for s in definition["stages"]}
    require(state["stage"] in stages, "unknown workflow stage")
    for name, kind in (("active_tracks", list), ("artifact_versions", list), ("approvals", dict),
                       ("known_facts", dict), ("blockers", list)):
        require(isinstance(state.get(name), kind), f"{name} must be {kind.__name__}")
    ids = set()
    for item in state["active_tracks"]:
        require(item.get("track_id") and item.get("owner") not in (None, "", "TBD"), "track needs ID and owner")
        require(item["track_id"] not in ids and item.get("stage") in stages, "duplicate track or invalid stage")
        require(isinstance(item.get("blockers", []), list), "track blockers must be a list")
        ids.add(item["track_id"])
    require(ids, "at least one track required")
    versions, currents = set(), set()
    for artifact in state["artifact_versions"]:
        require(all(artifact.get(k) for k in ("artifact", "version", "path")), "artifact needs name, version, path")
        key = (artifact["artifact"], artifact["version"])
        require(key not in versions, "duplicate artifact version")
        versions.add(key)
        if artifact.get("status", "current") == "current":
            require(artifact["artifact"] not in currents, "multiple current versions of artifact")
            currents.add(artifact["artifact"])
    for key, approval in state["approvals"].items():
        require(isinstance(approval, dict), f"invalid approval: {key}")
        require(type(approval.get("revision")) is int and approval["revision"] >= 1, f"approval {key} needs revision")
        require(approval.get("category") in {"business", "artifact", "merge", "deployment"}, "invalid approval category")
        require(isinstance(approval.get("artifact_versions", []), list), "invalid approval artifact versions")
    allowed = {(t["from"], t["to"]) for t in definition["allowed_transitions"]}
    rules = set()
    for rule in definition.get("execution_rules", []):
        pair = (rule["from"], rule["to"])
        require(pair in allowed and pair not in rules, "execution rule must map a unique allowed transition")
        for key in ("required_approvals", "required_facts", "required_checks"):
            require(isinstance(rule.get(key), list) and all(isinstance(x, str) for x in rule[key]), f"invalid {key}")
        require(type(rule.get("independent_review")) is bool, "independent_review must be boolean")
        rules.add(pair)


class Store:
    """One SQLite transaction boundary, distinct authoritative business/execution records.

    SQLite locking and CAS prevent concurrent local writers. External effects are
    deliberately outside transactions; durable intent plus reconciliation handles
    the unavoidable send/crash gap. This does not provide exactly-once execution.
    """

    def __init__(self, path: str | Path):
        path = Path(path).resolve()
        require(path.parent.is_dir(), "create and secure the private state directory first")
        require(not any((parent / ".git").exists() for parent in path.parents), "private state must be outside a Git checkout")
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL, definition TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES workflows(id), revision INTEGER NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, entity TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES executions(id), digest TEXT NOT NULL);
        """)

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _event(self, entity: str, kind: str, actor: str, body: dict) -> None:
        self.db.execute("INSERT INTO events(entity,kind,actor,at,body) VALUES(?,?,?,?,?)",
                        (entity, kind, actor, now(), json.dumps(body, sort_keys=True)))

    def workflow(self, workflow_id: str) -> tuple[dict, dict]:
        row = self.db.execute("SELECT body,definition FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        require(row, f"unknown workflow: {workflow_id}")
        return json.loads(row[0]), json.loads(row[1])

    def execution(self, assignment_id: str) -> dict:
        row = self.db.execute("SELECT body FROM executions WHERE id=?", (assignment_id,)).fetchone()
        require(row, f"unknown assignment: {assignment_id}")
        return json.loads(row[0])

    def _check(self, state: dict, actor: str, revision: int, owner: str) -> None:
        if state["revision"] != revision or actor != owner:
            raise Conflict("stale revision or caller is not the authoritative owner")

    def _save_execution(self, execution: dict, actor: str, kind: str) -> dict:
        old = execution["revision"]
        execution["revision"] += 1
        changed = self.db.execute("UPDATE executions SET revision=?,body=? WHERE id=? AND revision=?",
                                 (execution["revision"], json.dumps(execution), execution["assignment"]["assignment_id"], old))
        if changed.rowcount != 1:
            raise Conflict("execution revision changed")
        self._event(execution["assignment"]["assignment_id"], kind, actor,
                    {"revision": execution["revision"], "status": execution["status"]})
        return deepcopy(execution)

    def _save_workflow(self, state: dict, actor: str, kind: str) -> None:
        old = state["revision"]
        state["revision"] += 1
        changed = self.db.execute("UPDATE workflows SET revision=?,body=? WHERE id=? AND revision=?",
                                 (state["revision"], json.dumps(state), state["workflow_id"], old))
        if changed.rowcount != 1:
            raise Conflict("workflow revision changed")
        self._event(state["workflow_id"], kind, actor, {"revision": state["revision"]})

    def create_workflow(self, state: dict, definition: dict) -> None:
        validate_workflow(state, definition)
        require(state["revision"] == 1, "new workflow starts at revision 1")
        with self.transaction():
            self.db.execute("INSERT INTO workflows VALUES(?,?,?,?)",
                            (state["workflow_id"], 1, json.dumps(state), json.dumps(definition)))
            self._event(state["workflow_id"], "workflow-created", state["owner"], {"revision": 1})

    def update_workflow(self, state: dict, *, actor: str, expected_revision: int) -> dict:
        """Coordinator updates facts/artifacts/approvals, never bypasses stage gates."""
        state = deepcopy(state)
        with self.transaction():
            old, definition = self.workflow(state["workflow_id"])
            self._check(old, actor, expected_revision, old["owner"])
            require(state["revision"] == expected_revision, "submitted workflow revision mismatch")
            for key in ("owner", "workflow_type", "stage", "workflow_status"):
                require(state.get(key) == old.get(key), f"update cannot change {key}")
            for key in ("lifecycle_stage", "events", "decision_log"):
                require(state.get(key) == old.get(key), f"update cannot rewrite {key}")
            require([(t["track_id"], t["stage"], t.get("status")) for t in state["active_tracks"]] ==
                    [(t["track_id"], t["stage"], t.get("status")) for t in old["active_tracks"]],
                    "update cannot change track topology or stages")
            old_artifacts = {(a["artifact"], a["version"]): a for a in old["artifact_versions"]}
            new_artifacts = {(a["artifact"], a["version"]): a for a in state["artifact_versions"]}
            for key, artifact in old_artifacts.items():
                require(key in new_artifacts, "artifact history cannot be removed")
                require({k: v for k, v in artifact.items() if k != "status"} ==
                        {k: v for k, v in new_artifacts[key].items() if k != "status"}, "artifact version is immutable")
            history = state.setdefault("approval_history", deepcopy(old.get("approval_history", [])))
            require(history == old.get("approval_history", []), "approval history is append-only")
            current = refs(list(current_artifacts(state).values()))
            for key, approval in old["approvals"].items():
                require(key in state["approvals"], "approval history cannot be removed")
                new = state["approvals"][key]
                if new != approval:
                    require(new["revision"] == approval["revision"] + 1, "changed approval must increment revision")
                    history.append({"approval_id": key, **approval})
            for key, approval in state["approvals"].items():
                bound = refs(approval.get("artifact_versions", []))
                if approval.get("status") in {"approved", "conditional", "partial"} and not bound <= current:
                    history.append({"approval_id": key, **deepcopy(approval)})
                    approval["status"] = "superseded"
                    approval["revision"] += 1
            validate_workflow(state, definition)
            self._save_workflow(state, actor, "workflow-updated")
            return state

    def _approval(self, state: dict, approval_id: str, assignment: dict, *, current: set | None = None) -> dict:
        approval = state["approvals"].get(approval_id)
        require(approval is not None, f"missing approval: {approval_id}")
        require(approval.get("status") in {"approved", "conditional", "partial"}, f"approval not effective: {approval_id}")
        require(approval.get("scope") == assignment["authorization"]["scope"], "approval outside assignment scope")
        require(assignment["endpoint"] in approval.get("permits", []), "approval does not permit endpoint")
        require(approval.get("provenance") and approval.get("approved_by"), "approval needs provenance and approver")
        require(not approval.get("remaining_blockers"), "approval has remaining blockers")
        require(not approval.get("expires_at") or instant(approval["expires_at"]) > instant(now()), "approval expired")
        bound = refs(approval.get("artifact_versions", []))
        require(bound <= (current if current is not None else refs(list(current_artifacts(state).values()))), "approval binds stale artifact")
        if approval["category"] == "artifact":
            require(bound, "artifact approval must bind exact artifact versions")
        return approval

    def _authorization(self, state: dict, assignment: dict, *, accepted_result: dict | None = None) -> None:
        require(assignment["scope"] == assignment["authorization"]["scope"], "assignment scope differs from authorized scope")
        require(instant(assignment["authorization"]["expires_at"]) > instant(now()), "authorization expired")
        require(instant(assignment["runtime"]["deadline"]) > instant(now()), "original deadline expired")
        require(assignment["authorization"]["provenance"].strip(), "authorization provenance required")
        categories = set()
        for ref in assignment["authorization"]["approval_refs"]:
            category = state["approvals"].get(ref["approval_id"], {}).get("category")
            operation = {"merge": "merge", "deployment": "deploy"}.get(category, assignment["endpoint"])
            allowed = {"task": {"task"}, "implementation": {"implementation"}, "pr": {"pr"}, "merge": {"pr", "merge"}, "deploy": {"pr", "merge", "deploy"}}
            require(operation in allowed[assignment["endpoint"]], "approval belongs to an operation outside requested endpoint")
            approval = self._approval(state, ref["approval_id"], {**assignment, "endpoint": operation})
            if ref["revision"] != approval["revision"]:
                previous = next((p for p in state.get("approval_history", []) if p["approval_id"] == ref["approval_id"] and p["revision"] == ref["revision"]), None)
                reapproved = accepted_result and previous and refs(previous.get("artifact_versions", [])) and \
                    refs(previous["artifact_versions"]) <= refs(assignment["input_artifacts"]) and \
                    refs(approval.get("artifact_versions", [])) and \
                    refs(approval["artifact_versions"]) <= refs(accepted_result["produced_artifacts"]) and \
                    all(previous.get(key) == approval.get(key) for key in ("scope", "category", "permits"))
                require(reapproved, "stale approval reference; exact verified output needs scoped coordinator reapproval")
            categories.add(approval["category"])
        needed = {"merge": "merge", "deploy": "deployment"}.get(assignment["endpoint"])
        require(not needed or needed in categories, f"{assignment['endpoint']} requires its scoped authority reference")

    def _inputs(self, state: dict, assignment: dict, *, accepted_result: dict | None = None) -> None:
        current = refs(list(current_artifacts(state).values()))
        required = refs(assignment["input_artifacts"])
        # A coordinator may register a verified revision before requesting its
        # approval. Only that exact output may supersede this assignment's input.
        if accepted_result:
            produced = accepted_result["produced_artifacts"]
            superseded = {a["artifact"] for a in produced if (a["artifact"], a["version"]) in current and
                          all(next((old for old in state["artifact_versions"] if old["artifact"] == a["artifact"] and old["version"] == a["version"]), {}).get(k) == v for k, v in a.items())}
            historical = refs(state["artifact_versions"])
            required = {(name, version) for name, version in required if name not in superseded or (name, version) not in historical}
        require(required <= current, "stale or missing input artifact")
        lane = track(state, assignment["track_id"])
        require(not state["blockers"] and not state.get("conflicts") and not lane.get("blockers"), "workflow or track blocked")

    def dispatch(self, assignment: dict, adapter: Any, *, actor: str, expected_workflow_revision: int) -> dict:
        """Reserve durable intent before any adapter call. Existing IDs never resend."""
        validate_assignment(assignment)
        assignment = deepcopy(assignment)
        with self.transaction():
            state, definition = self.workflow(assignment["workflow_id"])
            self._check(state, actor, expected_workflow_revision, state["owner"])
            require(assignment["workflow_revision"] == state["revision"], "assignment workflow revision is stale")
            self._authorization(state, assignment)
            self._inputs(state, assignment)
            if assignment["proposed_transition"]:
                transition = assignment["proposed_transition"]
                rule = next((r for r in definition.get("execution_rules", []) if r["from"] == transition["from"] and r["to"] == transition["to"]), None)
                require(rule and track(state, assignment["track_id"])["stage"] == transition["from"], "assignment transition lacks current executable policy")
                require(set(rule["required_checks"]) <= set(assignment["required_checks"]), "assignment omits domain-required checks")
                require(not rule["independent_review"] or assignment["independent_review"], "assignment omits domain-required independent review")
            require(assignment["revision"] == 1, "new assignment starts at revision 1; in-place amendments are unsupported")
            existing = self.db.execute("SELECT body FROM executions WHERE workflow_id=?", (state["workflow_id"],)).fetchall()
            for row in existing:
                other = json.loads(row[0])
                previous = other["assignment"]
                if previous["assignment_id"] == assignment["assignment_id"]:
                    raise Conflict("duplicate assignment: reconcile saved intent; do not redispatch")
                if previous["track_id"] == assignment["track_id"] and not other["consumed"]:
                    raise Conflict("track already has an owner; reconcile it before assigning another")
                if previous["run_id"] == assignment["run_id"]:
                    require(previous["runtime"]["deadline"] == assignment["runtime"]["deadline"], "run deadline cannot be extended")
                    require(previous["runtime"]["native_goal_id"] == assignment["runtime"]["native_goal_id"], "native goal accounting changed")
                    require(previous["runtime"]["limits"] == assignment["runtime"]["limits"], "run resource limits cannot change")
                    require(previous["authorization"]["expires_at"] == assignment["authorization"]["expires_at"], "original run authorization cutoff cannot change")
            for dependency in assignment["dependencies"]:
                dep = self.execution(dependency)
                require(dep["status"] == "completed" and dep["assignment"]["workflow_id"] == state["workflow_id"], "dependency incomplete or foreign")
            run_active = [json.loads(r[0]) for r in existing if json.loads(r[0])["status"] not in {"completed", "stopped", "failed"}]
            run_active = [e for e in run_active if e["assignment"]["run_id"] == assignment["run_id"]]
            require(len(run_active) < assignment["runtime"]["limits"]["max_concurrency"], "run concurrency limit reached")
            execution = {"revision": 1, "assignment": assignment, "assignment_digest": canonical_digest(assignment),
                         "status": "submitted", "dispatch_state": "uncertain", "submission": None, "results": [],
                         "operations": {}, "pending_actions": [], "failure_history": [], "reconciliations": [],
                         "intentional_stop": False, "verified_result_id": None, "verification": None, "consumed": False,
                         "effective_runtime": None, "created_at": now()}
            self.db.execute("INSERT INTO executions VALUES(?,?,?,?)", (assignment["assignment_id"], state["workflow_id"], 1, json.dumps(execution)))
            self._event(assignment["assignment_id"], "dispatch-intent", actor, {"assignment_digest": execution["assignment_digest"]})
        try:
            receipt = adapter.submit(deepcopy(assignment))
            require(isinstance(receipt, dict) and receipt.get("receipt"), "adapter did not return a submission receipt")
            with self.transaction():
                execution = self.execution(assignment["assignment_id"])
                require(execution["assignment_digest"] == canonical_digest(assignment), "dispatch contract changed during submission")
                execution["submission"] = receipt
                if execution["dispatch_state"] != "acknowledged":
                    execution["dispatch_state"] = "prepared" if receipt.get("status") == "prepared" else "submitted"
                return self._save_execution(execution, actor, "submission-recorded")
        except Exception as exc:
            with self.transaction():
                execution = self.execution(assignment["assignment_id"])
                execution["failure_history"].append({"at": now(), "kind": "dispatch-uncertain", "error_type": type(exc).__name__})
                self._save_execution(execution, actor, "dispatch-uncertain")
            raise

    def record_result(self, result: dict, *, actor: str, expected_revision: int) -> dict:
        validate_result(result)
        with self.transaction():
            execution = self.execution(result["assignment_id"])
            assignment = execution["assignment"]
            self._check(execution, actor, expected_revision, assignment["owner"])
            require(not execution["intentional_stop"] and execution["status"] != "completed", "terminal execution rejects late results")
            for field in ("workflow_id", "track_id", "run_id", "assignment_id", "owner"):
                require(result[field] == assignment[field], f"result {field} mismatch")
            require(result["assignment_revision"] == assignment["revision"], "stale assignment result")
            prior = self.db.execute("SELECT digest FROM results WHERE id=?", (result["result_id"],)).fetchone()
            if prior:
                raise Conflict("duplicate result ID; saved result is authoritative")
            observed = instant(result["observed_at"])
            require(observed <= instant(now()), "future observation cannot establish evidence")
            if execution["results"]:
                require(observed >= instant(execution["results"][-1]["observed_at"]), "stale observed result")
            status = result["observed_status"]
            target = "review-pending" if status == "completed" else status
            require(target == execution["status"] or target in TRANSITIONS[execution["status"]], "invalid execution transition")
            if status in {"acknowledged", "progressing", "review-pending", "completed"}:
                require(result["evidence"]["accepted_assignment_digest"] == execution["assignment_digest"], "assignment acceptance digest missing/mismatched")
                effective = validate_observation(assignment, result["evidence"]["effective_runtime"])
                if execution["effective_runtime"]:
                    for key in ("owner", "native_session_id", "native_goal_id"):
                        require(effective.get(key) == execution["effective_runtime"].get(key), "native ownership changed without reconciliation")
                execution["effective_runtime"] = effective
                execution["dispatch_state"] = "acknowledged"
            if status in {"progressing", "review-pending", "completed"}:
                require(result["evidence"]["work"], "liveness is not useful progress")
            if status in {"blocked", "failed"}:
                require(result["blockers"], "blocked/failed result needs precise blocker")
            if status == "stopped":
                require(result["stop_reason"], "stop reason required")
                execution["intentional_stop"] = True
            for operation in result["external_operations"]:
                old = execution["operations"].get(operation["operation_id"])
                if old and old != operation:
                    require(old["status"] == "planned" and operation["status"] == "uncertain", "operation outcome changes require reconciliation")
                execution["operations"][operation["operation_id"]] = deepcopy(operation)
            if status in {"failed", "blocked"}:
                execution["failure_history"].append({"at": now(), "result_id": result["result_id"], "status": status, "blockers": result["blockers"]})
            execution["pending_actions"] = sorted(set(execution["pending_actions"]) | set(result["pending_actions"]))
            execution["status"] = target
            execution["results"].append(deepcopy(result))
            execution["verified_result_id"] = None
            self.db.execute("INSERT INTO results VALUES(?,?,?)", (result["result_id"], assignment["assignment_id"], canonical_digest(result)))
            return self._save_execution(execution, actor, "result-recorded")

    def _completion(self, execution: dict, *, rule: dict | None = None) -> dict:
        assignment = execution["assignment"]
        require(execution["results"], "no result")
        result = execution["results"][-1]
        require(result["observed_status"] == "completed", "latest result is partial")
        require(not result["blockers"] and not result["pending_actions"] and not execution["pending_actions"], "completion has blockers or pending actions")
        require(all(op["status"] in {"succeeded", "failed", "not-performed"} for op in execution["operations"].values()), "external action outcome unresolved")
        state, _ = self.workflow(assignment["workflow_id"])
        for op in execution["operations"].values():
            require(op["receipt"], "every resolved external action requires a receipt")
            if op["status"] == "not-performed":
                continue
            if op["kind"] in {"pr", "merge", "deploy"}:
                allowed = {"pr": {"pr"}, "merge": {"pr", "merge"}, "deploy": {"pr", "merge", "deploy"}}.get(assignment["endpoint"], set())
                require(op["kind"] in allowed, "external operation exceeds requested endpoint")
                if op["kind"] in {"merge", "deploy"}:
                    needed = "merge" if op["kind"] == "merge" else "deployment"
                    authority = {**assignment, "endpoint": op["kind"]}
                    require(any(self._approval(state, ref["approval_id"], authority)["category"] == needed
                                for ref in assignment["authorization"]["approval_refs"]
                                if state["approvals"].get(ref["approval_id"], {}).get("category") == needed), "external operation lacks scoped authority")
            else:
                require(op["kind"] in assignment["runtime"]["required_capabilities"], "external operation capability not selected")
                authority = {**assignment, "endpoint": op["kind"]}
                require(any(op["kind"] in state["approvals"].get(ref["approval_id"], {}).get("permits", []) and
                            self._approval(state, ref["approval_id"], authority)
                            for ref in assignment["authorization"]["approval_refs"]), "external operation lacks scoped authority")
        produced = refs(result["produced_artifacts"])
        require({a["artifact"] for a in result["produced_artifacts"]} == {a["artifact"] for a in assignment["expected_outputs"]}, "expected output set incomplete or outside scope")
        criteria = set(assignment["acceptance_criteria"]) | set(assignment["required_checks"])
        criteria |= {c for a in assignment["expected_outputs"] for c in a["acceptance_criteria"]}
        if rule:
            criteria |= set(rule["required_checks"])
        for criterion in criteria:
            matches = [v for v in result["validation"] if v["criterion"] == criterion]
            require(matches and all(v["passed"] and v["evidence"] and refs(v["artifact_versions"]) == produced for v in matches), f"missing, failed, or stale check: {criterion}")
        require(all(v["passed"] for v in result["validation"]), "failed validation remains")
        if assignment["independent_review"] or (rule and rule["independent_review"]):
            require(result["reviews"] and all(r["passed"] for r in result["reviews"]), "independent review failed/missing")
            author = assignment["runtime"]["role_config"].get("author", assignment["owner"])
            if isinstance(author, dict):
                author = author.get("identity", assignment["owner"])
            reviewer = assignment["runtime"]["role_config"].get("reviewer")
            if isinstance(reviewer, dict):
                reviewer = reviewer.get("identity")
            require(any(r["independent"] and r["reviewer"] not in {assignment["owner"], author} and r["evidence"] and
                        (not reviewer or r["reviewer"] == reviewer) and
                        refs(r["artifact_versions"]) == produced for r in result["reviews"]), "review is not independent or for final artifacts")
        endpoint = result["evidence"]["endpoint"]
        require(endpoint and endpoint["kind"] == assignment["endpoint"] and endpoint["verified"] and endpoint["receipt"], "requested endpoint not verified")
        require(endpoint["revision"] in {version for _, version in produced}, "endpoint revision does not match output")
        if assignment["endpoint"] in {"pr", "merge", "deploy"}:
            require(any(op["kind"] == assignment["endpoint"] and op["status"] == "succeeded" and
                        op["revision"] == endpoint["revision"] and op["receipt"] for op in execution["operations"].values()), "remote endpoint receipt missing")
        return result

    def verify_result(self, assignment_id: str, verification: dict, *, actor: str, expected_revision: int) -> dict:
        """Supervisor supplies readback from actual artifacts/tools, not a worker verdict."""
        with self.transaction():
            execution = self.execution(assignment_id)
            assignment = execution["assignment"]
            self._check(execution, actor, expected_revision, assignment["owner"])
            require(execution["status"] == "review-pending" and not execution["intentional_stop"], "result not awaiting verification")
            state, _ = self.workflow(assignment["workflow_id"])
            self._authorization(state, assignment)
            self._inputs(state, assignment)
            result = self._completion(execution)
            require(verification.get("result_id") == result["result_id"] and verification.get("result_digest") == canonical_digest(result), "verification does not bind exact result")
            require(verification.get("verifier") == actor and verification.get("evidence"), "supervisor readback evidence required")
            require(refs(verification.get("artifact_versions", [])) == refs(result["produced_artifacts"]), "supervisor must read back final artifacts")
            require(verification.get("endpoint") == result["evidence"]["endpoint"], "supervisor endpoint readback mismatch")
            execution["verification"] = deepcopy(verification)
            execution["verified_result_id"] = result["result_id"]
            execution["status"] = "completed"
            return self._save_execution(execution, actor, "completion-verified")

    def consume(self, assignment_id: str, *, actor: str, expected_workflow_revision: int) -> dict:
        """Coordinator alone imports versions and advances this track after current gates."""
        with self.transaction():
            execution = self.execution(assignment_id)
            assignment = execution["assignment"]
            state, definition = self.workflow(assignment["workflow_id"])
            self._check(state, actor, expected_workflow_revision, state["owner"])
            require(execution["status"] == "completed" and not execution["consumed"], "execution unverified or already consumed")
            result = execution["results"][-1]
            self._authorization(state, assignment, accepted_result=result)
            self._inputs(state, assignment, accepted_result=result)
            require(execution["verified_result_id"] == result["result_id"], "verification stale")
            proposal = result["proposed_transition"]
            require(proposal == assignment["proposed_transition"], "result cannot expand requested transition")
            lane = track(state, assignment["track_id"])
            rule = None
            if proposal:
                require(lane["stage"] == proposal["from"], "track stage changed")
                rule = next((r for r in definition.get("execution_rules", []) if r["from"] == proposal["from"] and r["to"] == proposal["to"]), None)
                require(rule, "transition has no executable gate rule; coordinator must map policy explicitly")
                for fact in rule["required_facts"]:
                    value = state["known_facts"]
                    for part in fact.split("."):
                        value = value.get(part) if isinstance(value, dict) else None
                    require(value is True, f"required verified fact missing: {fact}")
            self._completion(execution, rule=rule)
            current = current_artifacts(state)
            for produced in result["produced_artifacts"]:
                require(refs(produced["source_artifacts"]) <= refs(assignment["input_artifacts"]), "output source outside assigned inputs")
                existing = next((a for a in state["artifact_versions"] if (a["artifact"], a["version"]) == (produced["artifact"], produced["version"])), None)
                if existing:
                    require(all(existing.get(k) == v for k, v in produced.items()), "artifact version content changed")
                else:
                    if produced["artifact"] in current:
                        current[produced["artifact"]]["status"] = "superseded"
                    state["artifact_versions"].append({**produced, "status": "current"})
            available = refs(list(current_artifacts(state).values()))
            for key, approval in state["approvals"].items():
                if approval.get("status") in {"approved", "partial", "conditional"} and not refs(approval.get("artifact_versions", [])) <= available:
                    state.setdefault("approval_history", []).append({"approval_id": key, **deepcopy(approval)})
                    approval["status"] = "superseded"
                    approval["revision"] += 1
            if rule:
                for approval_id in rule["required_approvals"]:
                    self._approval(state, approval_id, assignment, current=available)
                lane["stage"] = proposal["to"]
                lane["status"] = "active"
                # Global stage is meaningful only when all tracks agree; status never closes implicitly.
                stages = {t["stage"] for t in state["active_tracks"]}
                if len(stages) == 1:
                    state["stage"] = next(iter(stages))
                    if "lifecycle_stage" in state:
                        state["lifecycle_stage"] = state["stage"]
            decision = {"event_id": str(uuid.uuid4()), "type": "execution_result_accepted", "actor": actor,
                        "timestamp": now(), "assignment_id": assignment_id, "assignment_revision": assignment["revision"],
                        "result_id": result["result_id"], "result_digest": canonical_digest(result), "transition": proposal}
            decision["approval_refs"] = [{"approval_id": ref["approval_id"], "revision": state["approvals"][ref["approval_id"]]["revision"]}
                                         for ref in assignment["authorization"]["approval_refs"]]
            state.setdefault("events", []).append(decision)
            validate_workflow(state, definition)
            self._save_workflow(state, actor, "execution-consumed")
            execution["consumed"] = True
            self._save_execution(execution, actor, "workflow-accepted-result")
            return state

    def reconcile(self, assignment_id: str, evidence: dict, *, actor: str, expected_revision: int) -> dict:
        """Persist live evidence before recovery or repeating any uncertain effect.

        This never sends work. It may return the same owner to acknowledged state
        after a proven interruption; caller resumes through a supported adapter.
        """
        with self.transaction():
            execution = self.execution(assignment_id)
            assignment = execution["assignment"]
            self._check(execution, actor, expected_revision, assignment["owner"])
            require(evidence.get("evidence") and evidence.get("owner") == assignment["owner"], "reconciliation needs live owner evidence")
            execution["reconciliations"].append({"at": now(), **deepcopy(evidence)})
            for op in evidence.get("operations", []):
                old = execution["operations"].get(op["operation_id"])
                require(old and old["status"] in {"uncertain", "planned"}, "operation not awaiting reconciliation")
                require(op["status"] in {"succeeded", "failed", "not-performed"} and op.get("receipt"), "operation needs definitive external readback")
                require(old["kind"] == op["kind"] and old["revision"] == op["revision"], "operation identity changed")
                execution["operations"][op["operation_id"]] = deepcopy(op)
            resolved = evidence.get("resolved_pending_actions", [])
            require(all(item in execution["pending_actions"] for item in resolved), "unknown pending action")
            execution["pending_actions"] = [p for p in execution["pending_actions"] if p not in resolved]
            if evidence.get("accepted_assignment_digest"):
                require(evidence["accepted_assignment_digest"] == execution["assignment_digest"], "reconciled assignment digest mismatch")
                effective = validate_observation(assignment, evidence["effective_runtime"])
                if execution["effective_runtime"]:
                    require(all(effective.get(k) == execution["effective_runtime"].get(k) for k in ("owner", "native_session_id", "native_goal_id")), "cannot replace existing native owner")
                execution["effective_runtime"] = effective
                execution["dispatch_state"] = "acknowledged"
            if evidence.get("resume"):
                require(not execution["intentional_stop"] and execution["status"] not in {"completed", "stopped"}, "intentional stop/completion cannot be resumed")
                state, _ = self.workflow(assignment["workflow_id"])
                self._authorization(state, assignment)
                self._inputs(state, assignment)
                require(execution["dispatch_state"] == "acknowledged", "uncertain submission requires receiver readback")
                require(evidence.get("accepted_assignment_digest") and evidence.get("owner_available") is True, "recovery must reuse observed owner")
                require(all(op["status"] not in {"uncertain", "planned"} for op in execution["operations"].values()), "uncertain external operations block resume")
                require(execution["status"] in {"blocked", "failed", "submitted"}, "live execution needs no recovery")
                others = [json.loads(row[0]) for row in self.db.execute("SELECT body FROM executions WHERE workflow_id=? AND id<>?", (assignment["workflow_id"], assignment_id))]
                active = [e for e in others if e["assignment"]["run_id"] == assignment["run_id"] and e["status"] not in {"completed", "stopped", "failed"}]
                require(len(active) < assignment["runtime"]["limits"]["max_concurrency"], "run concurrency limit prevents recovery")
                execution["status"] = "acknowledged"
            return self._save_execution(execution, actor, "reconciled")

    def stop(self, assignment_id: str, *, actor: str, expected_revision: int, reason: str, evidence: str) -> dict:
        """Record intent immediately; caller still reconciles workers and wake mechanisms."""
        require(reason and evidence, "stop requires reason and evidence")
        with self.transaction():
            execution = self.execution(assignment_id)
            self._check(execution, actor, expected_revision, execution["assignment"]["owner"])
            require(execution["status"] != "completed", "completed run cannot be stopped")
            execution["intentional_stop"] = True
            execution["status"] = "stopped"
            execution["stop"] = {"reason": reason, "evidence": evidence, "at": now()}
            execution["pending_actions"] = sorted(set(execution["pending_actions"]) | {"verify workers stopped and no relaunch"})
            return self._save_execution(execution, actor, "intentional-stop")

    def mode_satisfied(self, assignment_id: str) -> bool:
        execution = self.execution(assignment_id)
        if execution["assignment"]["mode"] == "supervise":
            return execution["status"] == "completed"
        return execution["dispatch_state"] == "acknowledged" and execution["status"] in {"progressing", "review-pending", "completed"} and any(r["evidence"]["work"] for r in execution["results"])

    def snapshot(self) -> dict:
        return {"workflows": [json.loads(r[0]) for r in self.db.execute("SELECT body FROM workflows ORDER BY id")],
                "executions": [json.loads(r[0]) for r in self.db.execute("SELECT body FROM executions ORDER BY id")]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate", "init", "handoff", "record", "verify", "consume", "reconcile", "stop", "update", "inspect"])
    parser.add_argument("--db", type=Path)
    parser.add_argument("--file", type=Path, help="JSON input (workflow, assignment, result, verification or reconciliation)")
    parser.add_argument("--kind", choices=["assignment", "result"])
    parser.add_argument("--definition", type=Path)
    parser.add_argument("--assignment-id")
    parser.add_argument("--actor")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    store = None
    try:
        data = json.loads(args.file.read_text(encoding="utf-8")) if args.file else None
        if args.action == "validate":
            require(args.kind and data, "validate needs --kind and --file")
            (validate_assignment if args.kind == "assignment" else validate_result)(data)
            print("Contract valid")
            return 0
        require(args.db, "--db required")
        store = Store(args.db)
        if args.action == "init":
            require(data and args.definition, "init requires --file and --definition")
            store.create_workflow(data, yaml.safe_load(args.definition.read_text(encoding="utf-8")))
            output = {"created": data["workflow_id"]}
        elif args.action == "inspect":
            output = store.snapshot()
        else:
            require(args.actor and args.expected_revision is not None, "mutation needs --actor and --expected-revision")
            kwargs = {"actor": args.actor, "expected_revision": args.expected_revision}
            if args.action == "handoff":
                from runtime_adapters import HandoffAdapter
                require(data and args.out, "handoff requires --file assignment and --out private directory")
                output = store.dispatch(data, HandoffAdapter(args.out), actor=args.actor, expected_workflow_revision=args.expected_revision)
            elif args.action == "record":
                output = store.record_result(data, **kwargs)
            elif args.action == "update":
                output = store.update_workflow(data, **kwargs)
            elif args.action == "verify":
                output = store.verify_result(args.assignment_id, data, **kwargs)
            elif args.action == "consume":
                output = store.consume(args.assignment_id, actor=args.actor, expected_workflow_revision=args.expected_revision)
            elif args.action == "reconcile":
                output = store.reconcile(args.assignment_id, data, **kwargs)
            else:
                output = store.stop(args.assignment_id, reason=data["reason"], evidence=data["evidence"], **kwargs)
        print(json.dumps(output, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"{exc}\n")
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
