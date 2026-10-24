#!/usr/bin/env python3
"""Run offline integration examples. Agent actions and remote receipts are SIMULATED."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from contracts import canonical_digest  # noqa: E402
from orchestration import Conflict, Store  # noqa: E402
from runtime_adapters import HandoffAdapter  # noqa: E402
from integration_fixtures import approve_outputs, effective, finish, fixture, progress, result  # noqa: E402


def run(directory: Path) -> dict:
    directory = directory.resolve()
    if directory.exists():
        raise ValueError("choose a new private demonstration directory")
    if any((p / ".git").exists() for p in (directory, *directory.parents)):
        raise ValueError("demonstration directory must be outside Git")
    directory.mkdir(parents=True, mode=0o700)
    store = Store(directory / "state.sqlite")
    report = {"validation": "OFFLINE SYNTHETIC: no real agents, GitHub operations, client workflows, or deployments", "scenarios": []}
    try:
        for domain in ("services", "hiring", "software"):
            state, definition, assignment = fixture(domain, endpoint="implementation" if domain == "software" else "task")
            assignment["assignment_id"] = domain + "-assignment"
            assignment["run_id"] = domain + "-run"
            store.create_workflow(state, definition)
            adapter = HandoffAdapter(directory / "handoffs")
            store.dispatch(assignment, adapter, actor=state["owner"], expected_workflow_revision=1)
            try:
                store.dispatch(assignment, adapter, actor=state["owner"], expected_workflow_revision=1)
            except Conflict:
                duplicate_blocked = True
            else:
                raise AssertionError("duplicate dispatch accepted")
            progress(store, assignment)
            completed = finish(store, assignment)
            before = store.workflow(state["workflow_id"])[0]["stage"]
            if domain != "software":
                try:
                    store.consume(assignment["assignment_id"], actor=state["owner"], expected_workflow_revision=1)
                except ValueError as exc:
                    gate_blocker = str(exc)
                else:
                    raise AssertionError("missing business approval allowed transition")
                state = approve_outputs(store, assignment, completed)
            else:
                gate_blocker = None
            state = store.consume(assignment["assignment_id"], actor=state["owner"], expected_workflow_revision=state["revision"])
            report["scenarios"].append({"domain": domain, "duplicate_blocked": duplicate_blocked, "initial_gate_blocker": gate_blocker,
                                        "before": before, "after": state["stage"], "workflow_status": state["workflow_status"], "external_effects": "none"})
            if domain == "software":
                # Versioned reports bind each review and delivery check to its exact output.
                prior_version = "v1"
                for stage, target, endpoint, check in (("review", "checks", "implementation", "local_checks"), ("checks", "delivery", "pr", "delivery_checks")):
                    next_assignment = deepcopy(assignment)
                    next_assignment.update(assignment_id="software-" + stage, workflow_revision=state["revision"],
                                           endpoint=endpoint, proposed_transition={"from": stage, "to": target}, required_checks=[check])
                    next_assignment["dependencies"] = [assignment["assignment_id"]]
                    next_assignment["input_artifacts"] = [{"artifact": "deliverable", "version": prior_version}]
                    store.dispatch(next_assignment, adapter, actor=state["owner"], expected_workflow_revision=state["revision"])
                    progress(store, next_assignment)
                    version = "review-v1" if stage == "review" else "pr-v1"
                    completed = finish(store, next_assignment, result(next_assignment, "completed", version=version))
                    current = approve_outputs(store, next_assignment, completed)
                    state = store.consume(next_assignment["assignment_id"], actor=state["owner"], expected_workflow_revision=current["revision"])
                    report["scenarios"].append({"domain": "software", "before": stage, "after": state["stage"], "endpoint": endpoint,
                                                "review": "SIMULATED independent review", "remote": "SIMULATED PR readback" if endpoint == "pr" else None,
                                                "workflow_status": state["workflow_status"]})
                    assignment = next_assignment
                    prior_version = version

        state, definition, assignment = fixture("services")
        state["workflow_id"] = assignment["workflow_id"] = "interruption-example"
        assignment["assignment_id"] = "interrupted-assignment"
        store.create_workflow(state, definition)
        class Interrupted:
            def submit(self, _assignment):
                raise TimeoutError("SIMULATED interruption after send")
        try:
            store.dispatch(assignment, Interrupted(), actor=state["owner"], expected_workflow_revision=1)
        except TimeoutError:
            pass
        original = deepcopy(store.execution(assignment["assignment_id"])["assignment"])
        store.close()
        store = Store(directory / "state.sqlite")
        execution = store.execution(assignment["assignment_id"])
        store.reconcile(assignment["assignment_id"], {"evidence": "SIMULATED existing owner readback", "owner": assignment["owner"],
                        "accepted_assignment_digest": canonical_digest(assignment), "effective_runtime": effective(assignment), "resume": True, "owner_available": True},
                        actor=assignment["owner"], expected_revision=execution["revision"])
        store.record_result(result(assignment, "progressing"), actor=assignment["owner"], expected_revision=store.execution(assignment["assignment_id"])["revision"])
        assert store.execution(assignment["assignment_id"])["assignment"] == original
        store.stop(assignment["assignment_id"], actor=assignment["owner"], expected_revision=store.execution(assignment["assignment_id"])["revision"],
                   reason="SIMULATED intentional stop", evidence="SIMULATED user request")
        report["scenarios"].append({"domain": "recovery", "original_identity_and_cutoff_preserved": True, "progress_after_reopen": True,
                                    "final_status": store.execution(assignment["assignment_id"])["status"], "stop_followup": "pending worker/no-relaunch verification"})
        (directory / "snapshot.json").write_text(json.dumps(store.snapshot(), indent=2) + "\n", encoding="utf-8")
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().out), indent=2))
