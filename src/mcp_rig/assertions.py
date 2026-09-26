"""Compare normalized tool outcomes with suite expectations."""

from __future__ import annotations

from typing import Any

from mcp_rig.client import CallOutcome


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
    return failures


def _needles(value: Any) -> list[str]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _short(text: str, limit: int = 80) -> str:
    shortened = text if len(text) <= limit else text[:limit] + "…"
    return repr(shortened)
