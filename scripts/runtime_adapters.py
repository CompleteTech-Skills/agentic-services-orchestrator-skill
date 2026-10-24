"""Small runtime bridges. Persistence/authority belong to the calling coordinator.

No adapter launches an agent implicitly. Native callbacks are explicitly supplied
trusted host bindings; file handoffs and the optional legacy bridge work offline.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

from contracts import canonical_digest


IDENTITY = ("workflow_id", "track_id", "run_id", "assignment_id", "revision")
OBSERVED_STATES = {
    "submitted", "acknowledged", "progressing", "review-pending", "blocked",
    "stopped", "failed", "completed",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _identity(assignment: dict) -> dict:
    return {key: assignment[key] for key in IDENTITY}


def _selected(assignment: dict, adapter: str) -> None:
    _require(assignment["runtime"]["adapter"] == adapter, "runtime adapter was not explicitly selected")


def _subset(requested: dict, actual: dict, path: str) -> None:
    _require(isinstance(actual, dict), path + " must be an observed object")
    for key, value in requested.items():
        _require(key in actual, path + "." + key + " was not observed")
        if isinstance(value, dict):
            _subset(value, actual[key], path + "." + key)
        else:
            _require(type(actual[key]) is type(value) and actual[key] == value,
                     path + "." + key + " differs from the requested configuration")


def validate_observation(assignment: dict, observed: dict) -> dict:
    """Validate reported actual configuration; never interpret it as authority.

The trusted binding/operator must acquire the observation. This structural check
cannot prove the truth of a caller-supplied receipt or perform runtime inspection.
"""
    _require(isinstance(observed, dict), "effective_runtime must be an object")
    for key in ("capabilities", "role_config", "limits", "owner", "native_session_id", "native_goal_id", "evidence"):
        _require(key in observed, "effective_runtime missing " + key)
    capabilities = observed["capabilities"]
    _require(isinstance(capabilities, list) and all(_text(item) for item in capabilities),
             "observed capabilities must be text values")
    _require(set(assignment["runtime"]["required_capabilities"]) <= set(capabilities),
             "required runtime capability was not observed")
    _require(observed["owner"] == assignment["owner"], "observed execution owner differs")
    _require(_text(observed["evidence"]), "actual runtime observation evidence is required")
    _subset(assignment["runtime"]["role_config"], observed["role_config"], "role_config")
    limits = observed["limits"]
    _require(isinstance(limits, dict), "observed limits must be an object")
    for key, ceiling in assignment["runtime"]["limits"].items():
        value = limits.get(key)
        numeric = type(value) in (int, float) if key == "max_cost" else type(value) is int
        _require(numeric and math.isfinite(value) and 0 <= value <= ceiling,
                 "observed resource limit exceeds or omits " + key)
        if key in ("max_concurrency", "max_tokens"):
            _require(value >= 1, "observed " + key + " must be positive")
    for key in ("native_session_id", "native_goal_id"):
        actual, pinned = observed[key], assignment["runtime"][key]
        _require(actual is None or _text(actual), "invalid observed " + key)
        _require(pinned is None or actual == pinned, "existing " + key + " must be preserved")
    return copy.deepcopy(observed)


def _utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0), "deadline must be UTC")
    return parsed


def _recoverable(assignment: dict, evidence: dict) -> None:
    for key, value in _identity(assignment).items():
        _require(evidence.get(key) == value, "recovery observation identity/revision differs")
    now = dt.datetime.now(dt.timezone.utc)
    _require(_utc(assignment["runtime"]["deadline"]) > now, "original runtime deadline expired")
    _require(_utc(assignment["authorization"]["expires_at"]) > now, "original authorization expired")
    _require(evidence.get("reconciled") is True, "saved/live reconciliation is required before recovery")
    _require(evidence.get("uncertain_operations") == [], "uncertain external operations must be reconciled")
    _require(evidence.get("intentional_stop") is False, "intentional or unknown stop cannot be recovered")
    _require(evidence.get("status") in {"submitted", "acknowledged", "progressing", "review-pending", "blocked", "failed"},
             "terminal or unknown observation cannot be recovered")
    observed = validate_observation(assignment, evidence.get("effective_runtime"))
    _require(_text(observed["native_session_id"]), "recovery requires an existing native session")
    _require(evidence.get("existing_owner_recoverable") is True, "existing owner must be recoverable")


class NativeAdapter:
    """Bindings to supported native tools supplied by the supervising host.

    The coordinator must persist dispatch intent before submit. Never retry an
    exception blindly: the callback may have completed an external side effect.
    """

    def __init__(self, *, capabilities: list[str], submit: Callable, observe: Callable,
                 recover: Callable | None = None):
        _require(isinstance(capabilities, list) and all(_text(item) for item in capabilities),
                 "declared native capabilities must be text values")
        self.capabilities = set(capabilities)
        self._submit, self._observe, self._recover = submit, observe, recover

    def _check(self, assignment: dict) -> None:
        _selected(assignment, "native")
        _require(set(assignment["runtime"]["required_capabilities"]) <= self.capabilities,
                 "binding does not declare every required capability")

    def submit(self, assignment: dict) -> dict:
        self._check(assignment)
        receipt = self._submit(copy.deepcopy(assignment))
        _require(isinstance(receipt, dict) and receipt.get("status") == "submitted",
                 "native submit must return submission evidence only")
        _require(_text(receipt.get("operation_id")) and _text(receipt.get("receipt")),
                 "native submission requires an operation ID and receipt")
        for key, value in _identity(assignment).items():
            _require(key not in receipt or receipt[key] == value, "submission receipt identity differs")
        observed = validate_observation(assignment, receipt.get("effective_runtime"))
        return {**copy.deepcopy(receipt), **_identity(assignment), "effective_runtime": observed,
                "acceptance_verified": False}

    def observe(self, assignment: dict) -> dict:
        self._check(assignment)
        evidence = self._observe(copy.deepcopy(assignment))
        _require(isinstance(evidence, dict) and evidence.get("status") in OBSERVED_STATES,
                 "native observation requires a distinguishable execution status")
        for key, value in _identity(assignment).items():
            _require(key in evidence and evidence[key] == value, "observation identity/revision differs")
        evidence = copy.deepcopy(evidence)
        evidence["effective_runtime"] = validate_observation(assignment, evidence.get("effective_runtime"))
        return evidence

    def recover(self, assignment: dict, evidence: dict) -> dict:
        self._check(assignment)
        _recoverable(assignment, evidence)
        _require(self._recover is not None, "no native recovery binding; hand off to the existing owner")
        # Pass the reconciled native identity to the callback, never call submit.
        result = self._recover(copy.deepcopy(assignment), copy.deepcopy(evidence))
        _require(isinstance(result, dict) and result.get("action") == "reused-existing-owner",
                 "native recovery must reuse the existing owner")
        actual = validate_observation(assignment, result.get("effective_runtime"))
        prior = evidence["effective_runtime"]
        for key in ("native_session_id", "native_goal_id"):
            _require(actual[key] == prior[key], "recovery replaced existing native identity")
        _require(_text(result.get("receipt")), "recovery receipt is required")
        return {**copy.deepcopy(result), **_identity(assignment), "effective_runtime": actual}


def _private_root(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    package = Path(__file__).resolve().parents[1]
    _require(not path.is_relative_to(package), "runtime handoff directory must be outside this skill checkout")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _directory(root: Path, assignment: dict) -> Path:
    return root / ("assignment-" + canonical_digest(_identity(assignment)))


def _write(path: Path, value: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _read_assignment(directory: Path, assignment: dict) -> dict:
    path = directory / "assignment.json"
    _require(not path.is_symlink(), "handoff assignment cannot be a symlink")
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(canonical_digest(data) == canonical_digest(assignment),
             "same assignment revision has different bytes; reconcile instead of redispatching")
    return data


class HandoffAdapter:
    """Prepare an immutable operator handoff when direct agent control is absent."""

    def __init__(self, private_directory: Path):
        self.root = _private_root(private_directory)

    def submit(self, assignment: dict) -> dict:
        _selected(assignment, "handoff")
        directory = _directory(self.root, assignment)
        duplicate = directory.exists()
        if duplicate:
            _read_assignment(directory, assignment)
        else:
            directory.mkdir(mode=0o700)
            _write(directory / "assignment.json", assignment)
        return {**_identity(assignment), "status": "submitted", "transport": "local-handoff",
                "operation_id": directory.name, "receipt": str(directory / "assignment.json"),
                "assignment_sha256": canonical_digest(assignment), "duplicate": duplicate,
                "acceptance_verified": False, "runtime_verified": False}

    def observe(self, assignment: dict) -> dict:
        _selected(assignment, "handoff")
        directory = _directory(self.root, assignment)
        _read_assignment(directory, assignment)
        return {**_identity(assignment), "status": "submitted", "receipt": str(directory / "assignment.json"),
                "acceptance_verified": False, "runtime_verified": False,
                "pending_actions": ["Existing owner must acknowledge this assignment and return work evidence."]}

    def recover(self, assignment: dict, evidence: dict) -> dict:
        _selected(assignment, "handoff")
        self.observe(assignment)
        return {**_identity(assignment), "status": "blocked", "action": "manual-reconciliation",
                "pending_actions": ["Reconcile with the existing owner; do not submit another assignment."]}


class HerdrAdapter:
    """Optional offline bridge to the unchanged Herdr v1 preparation helper.

    The explicit helper path is executable, trusted operator input. This bridge
    never invokes a Herdr CLI, connects to a host, or dispatches the prepared run.
    """

    def __init__(self, helper_path: Path | None = None, config: dict | None = None,
                 private_directory: Path | None = None):
        _require(isinstance(config, dict) and private_directory is not None,
                 "Herdr preparation requires explicit configuration and a private directory")
        bundled = Path(__file__).resolve().parents[1] / "adapters" / "herdr" / "scripts" / "prepare_run.py"
        self.helper = Path(helper_path or bundled).resolve(strict=True)
        _require(self.helper.is_file(), "legacy helper must be a file")
        self.config = copy.deepcopy(config)
        self.root = _private_root(private_directory)
        _require(not self.root.is_relative_to(self.helper.parent.parent),
                 "runtime handoff directory must be outside the Herdr skill checkout")

    def _run(self, *arguments: str) -> dict:
        command = [sys.executable, str(self.helper), *arguments]
        completed = subprocess.run(command, shell=False, capture_output=True, encoding="utf-8", timeout=30)
        _require(completed.returncode == 0, "legacy helper rejected preparation; inspect its local configuration")
        return json.loads(completed.stdout)

    def _configuration(self, assignment: dict) -> dict:
        """Map representable requested controls, rejecting contradictory v1 input."""
        config = copy.deepcopy(self.config)
        roles = assignment["runtime"]["role_config"]
        models = config.setdefault("models", {})
        requested = copy.deepcopy(roles.get("models", {}))
        _require(isinstance(requested, dict), "role_config.models must be an object for the Herdr bridge")
        for role in ("coordinator", "worker", "fallback_worker", "reviewer"):
            values = roles.get(role)
            if isinstance(values, dict):
                if "model" in values:
                    _require(role not in requested or requested[role] == values["model"],
                             "requested role models conflict")
                    requested[role] = values["model"]
                for setting in ("effort", "tier"):
                    if setting in values:
                        _require(setting not in requested or requested[setting] == values[setting],
                                 "Herdr v1 cannot represent different per-role " + setting)
                        requested[setting] = values[setting]
        for setting in ("effort", "tier", "fallback_when"):
            if setting in roles:
                _require(setting not in requested or requested[setting] == roles[setting],
                         "requested " + setting + " conflicts")
                requested[setting] = roles[setting]
        for key, value in requested.items():
            _require(key not in models or models[key] == value, "legacy model setting differs: " + key)
            models[key] = value
        permissions = roles.get("permissions", roles.get("permission"))
        if permissions is not None:
            modes = {"inherit": "inherit", "workspace": "workspace", "workspace-write": "workspace",
                     "yolo": "yolo", "full-access": "yolo", "danger-full-access": "yolo"}
            _require(isinstance(permissions, str) and permissions in modes,
                     "Herdr v1 cannot represent requested runtime permissions")
            mode = modes[permissions]
            _require("permission" not in config or config["permission"] == mode, "legacy runtime permissions differ")
            config["permission"] = mode
        ceilings = assignment["runtime"]["limits"]
        workers = models.setdefault("max_workers", min(ceilings["max_concurrency"], 16))
        _require(type(workers) is int and 1 <= workers <= ceilings["max_concurrency"],
                 "legacy concurrency exceeds assignment limit")
        # Shared depth counts edges from the outer owner; legacy levels include it.
        levels = models.setdefault("levels", min(ceilings["max_delegation_depth"] + 1, 3))
        _require(type(levels) is int and 2 <= levels <= 3 and levels - 1 <= ceilings["max_delegation_depth"],
                 "legacy delegation depth cannot satisfy the assignment limit")
        limits = config.setdefault("limits", {})
        _require(limits.get("original_cutoff_utc") in (None, assignment["runtime"]["deadline"]),
                 "legacy original cutoff differs; preserve and reconcile the existing deadline")
        limits["original_cutoff_utc"] = assignment["runtime"]["deadline"]
        target = config.setdefault("target", {})
        for shared, legacy in (("native_session_id", "native_session_uuid"), ("native_goal_id", "goal_id")):
            pinned = assignment["runtime"][shared]
            if pinned is not None:
                _require(target.get(legacy) in (None, pinned), "legacy " + legacy + " differs from the existing owner")
                target[legacy] = pinned
        return config

    def submit(self, assignment: dict) -> dict:
        _selected(assignment, "herdr")
        _require(assignment["endpoint"] in {"implementation", "pr", "merge", "deploy"},
                 "Herdr v1 bridge supports software delivery endpoints only")
        _require(self.config.get("delivery", "implementation") == assignment["endpoint"], "legacy endpoint differs")
        _require(self.config.get("control", "dispatch") == assignment["mode"], "legacy control mode differs")
        _require(self.config.get("scope") == assignment["scope"], "legacy scope differs")
        directory = _directory(self.root, assignment)
        duplicate = directory.exists()
        config = self._configuration(assignment)
        config["scope"] += (
            "\nShared workflow assignment: " + str(directory / "assignment.json") +
            ". Read that complete contract before acting. Its workflow approval references, authorization, "
            "native identity, role configuration, and limits remain authoritative. Reconcile any legacy "
            "configuration discrepancy before live control. Return execution evidence to the workflow "
            "coordinator; do not advance business stages or grant approvals."
        )
        if duplicate:
            _read_assignment(directory, assignment)
            stored_config = json.loads((directory / "legacy-config.json").read_text(encoding="utf-8"))
            _require(stored_config == config, "legacy configuration changed for the same assignment revision")
            link = json.loads((directory / "workflow-link.json").read_text(encoding="utf-8"))
        else:
            directory.mkdir(mode=0o700)
            _write(directory / "assignment.json", assignment)
            _write(directory / "legacy-config.json", config)
            self._run("validate", "--config", str(directory / "legacy-config.json"))
            rendered = self._run("render", "--config", str(directory / "legacy-config.json"),
                                 "--out", str(directory / "legacy-run"))
            link = {**_identity(assignment), "assignment_sha256": canonical_digest(assignment),
                    "authorization": copy.deepcopy(assignment["authorization"]),
                    "legacy_contract_id": rendered["contract_id"],
                    "legacy_prompt_sha256": rendered["prompt_sha256"],
                    "helper_sha256": hashlib.sha256(self.helper.read_bytes()).hexdigest()}
            _write(directory / "workflow-link.json", link)
        _require(link["helper_sha256"] == hashlib.sha256(self.helper.read_bytes()).hexdigest(),
                 "legacy helper changed; reconcile the prepared handoff")
        verified = self._run("verify", "--run", str(directory / "legacy-run"),
                             "--expected-prompt-sha256", link["legacy_prompt_sha256"])
        _require(verified.get("artifacts_verified") is True and verified.get("runtime_verified") is False,
                 "legacy verification did not verify prepared artifacts")
        return {**_identity(assignment), "status": "prepared", "transport": "herdr-preparation",
                "operation_id": link["legacy_contract_id"], "receipt": str(directory / "workflow-link.json"),
                "assignment_sha256": link["assignment_sha256"], "duplicate": duplicate,
                "acceptance_verified": False, "runtime_verified": False}

    def observe(self, assignment: dict) -> dict:
        _selected(assignment, "herdr")
        directory = _directory(self.root, assignment)
        _read_assignment(directory, assignment)
        link = json.loads((directory / "workflow-link.json").read_text(encoding="utf-8"))
        verified = self._run("verify", "--run", str(directory / "legacy-run"),
                             "--expected-prompt-sha256", link["legacy_prompt_sha256"])
        _require(verified.get("artifacts_verified") is True, "prepared legacy artifacts changed")
        return {**_identity(assignment), "status": "prepared", "runtime_verified": False,
                "pending_actions": ["Use verified Herdr session controls and return live assignment evidence."]}

    def recover(self, assignment: dict, evidence: dict) -> dict:
        self.observe(assignment)
        return {**_identity(assignment), "status": "blocked", "action": "manual-reconciliation",
                "pending_actions": ["Recover the existing native owner using the Herdr recovery procedure."]}
