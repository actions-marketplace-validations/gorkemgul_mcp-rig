"""Render MCP Rig suite results for humans."""

from __future__ import annotations

from mcp_rig.runner import SuiteResult

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def render_suite(title: str, result: SuiteResult, color: bool = False) -> str:
    lines = [f"MCP Rig — {title}", ""]
    for item in result.results:
        mark = _paint("✓", GREEN, color) if item.passed else _paint("✗", RED, color)
        lines.append(f"{mark} {item.name} ({item.outcome.latency_ms:.0f} ms)")
        lines.extend(f"    {failure}" for failure in item.failures)
    lines.extend(["", f"{result.passed} passed, {result.failed} failed"])
    return "\n".join(lines)
