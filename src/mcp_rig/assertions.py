"""Compare normalized tool outcomes with suite expectations."""

from __future__ import annotations

import re
from typing import Any

import jsonschema

from mcp_rig.client import CallOutcome

_MISSING = object()


def check(expect: dict[str, Any], outcome: CallOutcome) -> list[str]:
    failures: list[str] = []
    expected_error = expect.get("is_error", False)
    if outcome.is_error != expected_error:
        failures.append(
            f"is_error: expected {expected_error}, got {outcome.is_error} "
            f"(text: {_short(outcome.text)})"
        )
    for needle in _needles(expect.get("contains")):
        if needle not in outcome.text:
            failures.append(f"contains: {needle!r} not found in {_short(outcome.text)}")
    for needle in _needles(expect.get("not_contains")):
        if needle in outcome.text:
            failures.append(f"not_contains: {needle!r} found in {_short(outcome.text)}")
    if "matches" in expect and re.search(expect["matches"], outcome.text) is None:
        failures.append(f"matches: /{expect['matches']}/ did not match {_short(outcome.text)}")
    if "max_latency_ms" in expect:
        limit = float(expect["max_latency_ms"])
        if outcome.latency_ms > limit:
            failures.append(f"max_latency_ms: took {outcome.latency_ms:.0f} ms, limit {limit:.0f} ms")
    if "json_path" in expect or "schema" in expect:
        try:
            payload = outcome.json()
        except ValueError:
            failures.append(f"json: response is not JSON: {_short(outcome.text)}")
        else:
            failures.extend(_check_json(expect, payload))
    return failures


def _check_json(expect: dict[str, Any], payload: Any) -> list[str]:
    failures: list[str] = []
    for path, wanted in expect.get("json_path", {}).items():
        actual = _resolve(payload, path)
        if actual is _MISSING:
            failures.append(f"json_path {path}: missing")
        elif actual != wanted:
            failures.append(f"json_path {path}: expected {wanted!r}, got {actual!r}")
    if "schema" in expect:
        validator = jsonschema.Draft202012Validator(expect["schema"])
        errors = sorted(
            validator.iter_errors(payload),
            key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
        )
        failures.extend(f"schema: {error.message}" for error in errors)
    return failures


def _resolve(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdecimal() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current


def _needles(value: Any) -> list[str]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _short(text: str, limit: int = 80) -> str:
    shortened = text if len(text) <= limit else text[:limit] + "…"
    return repr(shortened)
