#!/usr/bin/env python3
"""Deterministic, read-only check of a project_state file against its workflow definition.

Checks allowed stage transitions, gate approvals required by transitions and by
requested gated actions (`--action`), approval attribution (approver and ISO
date), approval records for every gate, track stages/owners, artifact versions
and terminal-state blockers. Prints one line per violation and exits non-zero
when any are found.

This is a check the agent (or CI) runs; it is not a runtime guard. Nothing here
can stop an agent that skips the check or acts outside this skill.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = "references/completetech-services-workflow.yaml"
AUTHORIZING = ("approved", "conditional", "partial")
TRACK_STATUSES = ("draft", "active", "blocked", "waiting", "complete", "superseded")
STATE_ROOTS = ("project_state", "workflow_generation")


def load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError("PyYAML is required for YAML input; pass JSON or install pyyaml") from exc
    return yaml.safe_load(text)


def extract_state(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("project_state document must be a mapping")
    for key in STATE_ROOTS:
        if isinstance(document.get(key), dict):
            return document[key]
    return document


def unset(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().upper() in ("", "TBD"))


def iso_date(value: Any) -> bool:
    if isinstance(value, (dt.date, dt.datetime)):
        return True
    if not isinstance(value, str):
        return False
    try:
        dt.datetime.fromisoformat(value.strip())
    except ValueError:
        return False
    return True


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class Checker:
    def __init__(self, state: dict[str, Any], workflow: dict[str, Any]) -> None:
        self.state = state
        self.workflow = workflow
        self.violations: list[str] = []
        self.notes: list[str] = []
        self.gates = {g.get("gate_id"): g for g in as_list(workflow.get("gates")) if isinstance(g, dict)}
        self.field_for = {gid: g.get("approval_field") or gid for gid, g in self.gates.items()}
        self.approvals = state.get("approvals") if isinstance(state.get("approvals"), dict) else {}
        self.states = set(as_list(workflow.get("approval_states")))
        self.stages = {s.get("id") for s in as_list(workflow.get("stages")) if isinstance(s, dict)}

    def fail(self, rule: str, message: str) -> None:
        self.violations.append(f"VIOLATION [{rule}] {message}")

    def approval(self, gate_id: str) -> dict[str, Any] | None:
        record = self.approvals.get(self.field_for.get(gate_id, gate_id))
        return record if isinstance(record, dict) else None

    def check_workflow_type(self) -> None:
        declared = self.state.get("workflow_type")
        expected = self.workflow.get("workflow_type")
        if declared and declared != expected:
            self.fail("workflow_type_mismatch", f"state declares {declared!r}, definition is {expected!r}")

    def check_approvals(self) -> None:
        known = set(self.field_for.values())
        for gate_id, field in self.field_for.items():
            if field not in self.approvals:
                self.fail("missing_approval_record", f"gate {gate_id!r} has no approvals.{field} record")
        for field, record in self.approvals.items():
            if field not in known:
                self.fail("unknown_approval", f"approvals.{field} does not match any gate in the workflow definition")
                continue
            if not isinstance(record, dict):
                self.fail("invalid_approval", f"approvals.{field} must be a mapping")
                continue
            status = record.get("status")
            if status not in self.states:
                self.fail("invalid_approval", f"approvals.{field}.status {status!r} is not an approval state")
            elif status in AUTHORIZING:
                if unset(record.get("approved_by")):
                    self.fail("approval_without_attribution", f"approvals.{field} is {status} but approved_by is missing")
                if not iso_date(record.get("approved_at")):
                    self.fail("approval_without_attribution", f"approvals.{field} is {status} but approved_at is not an ISO date")

    def gate_authorizes(self, gate_id: str, action: str | None) -> str | None:
        """Return None when the gate authorizes, otherwise the reason it does not."""
        if gate_id not in self.gates:
            return f"gate {gate_id!r} is not defined"
        record = self.approval(gate_id)
        if record is None:
            return f"no approvals.{self.field_for[gate_id]} record"
        status = record.get("status")
        if status not in AUTHORIZING:
            return f"approvals.{self.field_for[gate_id]} is {status!r}"
        if unset(record.get("approved_by")) or not iso_date(record.get("approved_at")):
            return f"approvals.{self.field_for[gate_id]} lacks approver or ISO date"
        if action and status != "approved":
            if action not in as_list(record.get("permits")):
                return f"approvals.{self.field_for[gate_id]} is {status} and its permits do not list {action!r}"
        if status != "approved":
            self.notes.append(f"NOTE {gate_id} is {status}; stay within permits {as_list(record.get('permits'))}")
        return None

    def check_transitions(self) -> None:
        allowed = {(t.get("from"), t.get("to")): t for t in as_list(self.workflow.get("allowed_transitions")) if isinstance(t, dict)}
        for index, item in enumerate(as_list(self.state.get("state_transitions"))):
            if not isinstance(item, dict):
                self.fail("invalid_transition", f"state_transitions[{index}] must be a mapping")
                continue
            src, dst = item.get("from"), item.get("to")
            if unset(src) and unset(dst):
                continue  # template placeholder
            if unset(item.get("when")):
                self.fail("invalid_transition", f"state_transitions[{index}] {src} -> {dst} has no 'when'")
            rule = allowed.get((src, dst))
            if rule is None:
                self.fail("invalid_transition", f"state_transitions[{index}] {src} -> {dst} is not in allowed_transitions")
                continue
            for gate_id in as_list(rule.get("requires_gates")):
                reason = self.gate_authorizes(gate_id, None)
                if reason:
                    self.fail("gate_not_satisfied", f"transition {src} -> {dst} requires {gate_id}: {reason}")

    def check_actions(self, actions: list[str]) -> None:
        defined = {a.get("action"): a for a in as_list(self.workflow.get("gated_actions")) if isinstance(a, dict)}
        for action in actions:
            rule = defined.get(action)
            if rule is None:
                self.fail("unknown_action", f"{action!r} is not a gated action; known: {sorted(defined)}")
                continue
            for gate_id in as_list(rule.get("requires_gates")):
                reason = self.gate_authorizes(gate_id, action)
                if reason:
                    self.fail("external_action_without_approval_evidence", f"{action} requires {gate_id}: {reason}")

    def check_tracks(self) -> None:
        extra = set(as_list(self.workflow.get("support_outputs"))) | set(self.workflow.get("specialist_owners") or {})
        valid = self.stages | extra | {"support_output"}
        for track in as_list(self.state.get("active_tracks")):
            if not isinstance(track, dict):
                continue  # summary forms such as "TRACK-1: note" are not checked
            tid = track.get("track_id", "?")
            if "owner" not in track or track.get("owner") is None:
                self.fail("missing_owner", f"track {tid} has no owner (use TBD when unknown)")
            if not unset(track.get("stage")) and track.get("stage") not in valid:
                self.fail("invalid_track_stage", f"track {tid} stage {track.get('stage')!r} is not defined")
            if not unset(track.get("status")) and track.get("status") not in TRACK_STATUSES:
                self.fail("invalid_track_status", f"track {tid} status {track.get('status')!r} is not a track status")

    def check_artifacts(self) -> None:
        for item in as_list(self.state.get("artifact_versions")):
            if not isinstance(item, dict):
                continue
            name = item.get("artifact_id") or item.get("artifact") or "?"
            if unset(item.get("version")):
                self.fail("artifact_without_source_or_version", f"artifact {name} has no version")
            if not isinstance(item.get("source_artifacts"), list):
                self.fail("artifact_without_source_or_version", f"artifact {name} has no source_artifacts list")

    def check_terminal(self) -> None:
        status = self.state.get("workflow_status")
        for terminal in as_list(self.workflow.get("terminal_states")):
            if isinstance(terminal, dict) and terminal.get("id") == status:
                if not terminal.get("allows_open_blockers") and as_list(self.state.get("blockers")):
                    self.fail("terminal_state_with_open_blockers", f"workflow_status {status!r} has open blockers")

    def run(self, actions: list[str]) -> list[str]:
        self.check_workflow_type()
        self.check_approvals()
        self.check_transitions()
        self.check_actions(actions)
        self.check_tracks()
        self.check_artifacts()
        self.check_terminal()
        return self.violations


def validate_state(state: dict[str, Any], workflow: dict[str, Any], actions: list[str] | None = None) -> tuple[list[str], list[str]]:
    checker = Checker(state, workflow)
    return checker.run(actions or []), checker.notes


def resolve_workflow(state: dict[str, Any], override: Path | None) -> Path:
    if override:
        return override
    declared = state.get("workflow_definition")
    path = (ROOT / declared).resolve() if isinstance(declared, str) and not unset(declared) else ROOT / DEFAULT_WORKFLOW
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError(f"workflow definition not found inside the package: {declared}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("state", type=Path, help="project_state YAML or JSON file")
    parser.add_argument("--workflow", type=Path, help="workflow definition (default: state's workflow_definition)")
    parser.add_argument("--action", action="append", default=[], help="gated action about to run; repeatable")
    args = parser.parse_args(argv)
    try:
        state = extract_state(load_document(args.state))
        workflow_path = resolve_workflow(state, args.workflow)
        workflow = load_document(workflow_path)
        if not isinstance(workflow, dict):
            raise ValueError("workflow definition must be a mapping")
        violations, notes = validate_state(state, workflow, args.action)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}")
        return 2
    for line in [*notes, *violations]:
        print(line)
    if violations:
        print(f"{len(violations)} violation(s); do not proceed with gated steps")
        return 1
    print(f"State OK against {workflow.get('workflow_type')}; checked actions: {args.action or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
