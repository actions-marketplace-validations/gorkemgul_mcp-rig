"""Protocol checks that do not require a test suite."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_rig.client import Probe

UNKNOWN_TOOL_BASE = "__mcp_rig_unknown_tool__"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one protocol behavior check."""

    name: str
    passed: bool
    detail: str = ""


async def run_protocol_checks(
    probe: Probe,
    probe_invalid_args: bool = False,
) -> list[CheckResult]:
    """Run deterministic protocol checks against a connected server."""
    tools = await probe.list_tools()
    results = [
        CheckResult(
            "lists tools",
            bool(tools),
            "" if tools else "tools/list returned no tools",
        )
    ]
    results.append(
        await _expect_error(
            probe,
            "unknown tool returns an error",
            _unknown_tool_name({tool.name for tool in tools}),
        )
    )
    if probe_invalid_args:
        for tool in tools:
            if _has_required_args(tool.input_schema):
                results.append(
                    await _expect_error(
                        probe,
                        f"{tool.name}: missing required args rejected",
                        tool.name,
                    )
                )
    try:
        await probe.list_tools()
    except Exception as exc:  # noqa: BLE001 - the failed check records SDK errors
        results.append(
            CheckResult(
                "server alive after bad calls",
                False,
                f"{type(exc).__name__}: {exc}",
            )
        )
    else:
        results.append(CheckResult("server alive after bad calls", True))
    return results


async def _expect_error(probe: Probe, name: str, tool: str) -> CheckResult:
    try:
        outcome = await probe.call(tool, {}, timeout_s=10.0)
    except Exception as exc:  # noqa: BLE001 - the failed check records SDK errors
        return CheckResult(
            name,
            False,
            f"call raised {type(exc).__name__} instead of returning is_error: {exc}",
        )
    if outcome.is_error:
        return CheckResult(name, True)
    return CheckResult(
        name,
        False,
        f"expected is_error=true, got success: {outcome.text[:80]!r}",
    )


def _unknown_tool_name(advertised_names: set[str]) -> str:
    candidate = UNKNOWN_TOOL_BASE
    suffix = 2
    while candidate in advertised_names:
        candidate = f"{UNKNOWN_TOOL_BASE}_{suffix}"
        suffix += 1
    return candidate


def _has_required_args(input_schema: dict) -> bool:
    required = input_schema.get("required")
    return bool(required) and isinstance(required, list) and all(
        isinstance(name, str) for name in required
    )
