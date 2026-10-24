"""Validate local execution contracts without resolving schemas over the network.

The JSON Schema documents are authoritative for shape and types. The small
semantic checks here reject ambiguous duplicate identities within a contract;
workflow authorization, evidence trust, and state transitions belong to the
coordinator and execution supervisor.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "references"
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _timestamp(value: Any) -> bool:
    """Validate timestamps even when jsonschema's optional format extras are absent."""
    if not isinstance(value, str):
        return True  # The schema's type assertion reports this separately.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        return False
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None


def canonical_digest(data: Any) -> str:
    """Return a stable SHA-256 digest of a JSON value, rejecting non-JSON data."""
    try:
        encoded = json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"contract must contain only JSON values: {exc}") from exc
    _check_json_types(data)
    return hashlib.sha256(encoded).hexdigest()


def _check_json_types(value: Any) -> None:
    # json.dumps also accepts tuples and integer object keys. Reject those so a
    # Python-only value cannot acquire the same identity as a different contract.
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("contract JSON object keys must be strings")
            _check_json_types(child)
    elif isinstance(value, list):
        for child in value:
            _check_json_types(child)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"contract must contain only JSON values, found {type(value).__name__}")


@lru_cache(maxsize=2)
def _validator(kind: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_ROOT / f"{kind}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def _validate(kind: str, data: Any) -> None:
    canonical_digest(data)
    errors = sorted(
        _validator(kind).iter_errors(data),
        key=lambda error: "/".join(str(part) for part in error.absolute_path),
    )
    if errors:
        details = []
        for error in errors[:5]:
            path = "/" + "/".join(str(part) for part in error.absolute_path)
            details.append(f"{path}: {error.message}")
        raise ValueError(f"invalid {kind}: " + "; ".join(details))


def _unique(records: list[dict[str, Any]], field: str, path: str) -> None:
    seen = set()
    for record in records:
        value = record[field]
        if value in seen:
            raise ValueError(f"{path}: duplicate {field} {value!r}")
        seen.add(value)


def validate_assignment(data: Any) -> None:
    """Raise ValueError for a malformed or internally ambiguous assignment."""
    _validate("assignment", data)
    _unique(data["input_artifacts"], "artifact", "/input_artifacts")
    _unique(data["expected_outputs"], "artifact", "/expected_outputs")
    _unique(data["authorization"]["approval_refs"], "approval_id", "/authorization/approval_refs")
    if data["assignment_id"] in data["dependencies"]:
        raise ValueError("/dependencies: an assignment cannot depend on itself")


def validate_result(data: Any) -> None:
    """Validate an observation's shape; completion must still pass coordinator gates."""
    _validate("result", data)
    _unique(data["produced_artifacts"], "artifact", "/produced_artifacts")
    _unique(data["validation"], "criterion", "/validation")
    _unique(data["external_operations"], "operation_id", "/external_operations")
    for index, artifact in enumerate(data["produced_artifacts"]):
        _unique(artifact["source_artifacts"], "artifact", f"/produced_artifacts/{index}/source_artifacts")
    for collection in ("validation", "reviews"):
        for index, evidence in enumerate(data[collection]):
            _unique(evidence["artifact_versions"], "artifact", f"/{collection}/{index}/artifact_versions")
