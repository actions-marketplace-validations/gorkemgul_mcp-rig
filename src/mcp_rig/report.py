"""Render MCP Rig suite results for humans."""

from __future__ import annotations

from mcp_rig.runner import CaseStatus, SuiteResult

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def render_suite(title: str, result: SuiteResult, color: bool = False) -> str:
    lines = [f"MCP Rig — {title}", ""]
    for item in result.results:
        if item.status is CaseStatus.PASSED:
            lines.append(f"{_paint('✓', GREEN, color)} {item.name} ({item.elapsed_ms:.0f} ms)")
        elif item.status is CaseStatus.FAILED:
            lines.append(f"{_paint('✗', RED, color)} {item.name} ({item.elapsed_ms:.0f} ms)")
            lines.extend(f"    {failure}" for failure in item.failures)
        elif item.status is CaseStatus.ERROR:
            assert item.error is not None
            lines.append(f"{_paint('!', RED, color)} {item.name} ({item.elapsed_ms:.0f} ms)")
            lines.append(f"    {item.error.category}: {item.error.exception_type}: {item.error.message}")
        else:
            assert item.skip_reason is not None
            lines.append(f"- {item.name}")
            lines.append(f"    {item.skip_reason}")
    error_label = "error" if result.errors == 1 else "errors"
    lines.extend(
        [
            "",
            f"{result.passed} passed, {result.failed} failed, "
            f"{result.errors} {error_label}, {result.skipped} skipped",
        ]
    )
    return "\n".join(lines)
