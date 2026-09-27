import pytest

from mcp_rig.checks import UNKNOWN_TOOL_BASE, CheckResult, run_protocol_checks
from mcp_rig.client import CallOutcome, ToolInfo, connect


class FakeProbe:
    def __init__(
        self,
        tools: list[ToolInfo],
        *,
        outcome: CallOutcome | None = None,
        call_error: Exception | None = None,
        fail_list_on: int | None = None,
    ):
        self.tools = tools
        self.outcome = outcome or CallOutcome(True, "error", None, 1.0)
        self.call_error = call_error
        self.fail_list_on = fail_list_on
        self.list_calls = 0
        self.calls: list[tuple[str, dict, float]] = []

    async def list_tools(self) -> list[ToolInfo]:
        self.list_calls += 1
        if self.list_calls == self.fail_list_on:
            raise RuntimeError("list failed")
        return self.tools

    async def call(
        self,
        name: str,
        args: dict | None = None,
        timeout_s: float = 30.0,
    ) -> CallOutcome:
        self.calls.append((name, args or {}, timeout_s))
        if self.call_error is not None:
            raise self.call_error
        return self.outcome


def tool(name: str, input_schema: dict | None = None) -> ToolInfo:
    return ToolInfo(
        name,
        "A documented tool used by protocol tests.",
        input_schema or {"type": "object"},
    )


@pytest.mark.anyio
async def test_default_checks_pass_on_fixture(fixture_spec):
    async with connect(fixture_spec) as probe:
        results = await run_protocol_checks(probe)

    assert [result.name for result in results] == [
        "lists tools",
        "unknown tool returns an error",
        "server alive after bad calls",
    ]
    assert all(result.passed for result in results), results


@pytest.mark.anyio
async def test_unknown_tool_probe_avoids_advertised_name_collision():
    probe = FakeProbe([tool(UNKNOWN_TOOL_BASE)])

    await run_protocol_checks(probe)

    assert probe.calls[0] == (f"{UNKNOWN_TOOL_BASE}_2", {}, 10.0)


@pytest.mark.anyio
async def test_unknown_tool_probe_rejects_unexpected_success():
    probe = FakeProbe(
        [tool("echo")],
        outcome=CallOutcome(False, "unexpected", None, 1.0),
    )

    results = await run_protocol_checks(probe)

    unknown = results[1]
    assert unknown.passed is False
    assert "expected is_error=true" in unknown.detail


@pytest.mark.anyio
async def test_call_exception_fails_check_and_still_runs_liveness_probe():
    probe = FakeProbe([tool("echo")], call_error=RuntimeError("boom"))

    results = await run_protocol_checks(probe)

    assert results[1] == CheckResult(
        "unknown tool returns an error",
        False,
        "call raised RuntimeError instead of returning is_error: boom",
    )
    assert results[-1].name == "server alive after bad calls"
    assert results[-1].passed is True
    assert probe.list_calls == 2


@pytest.mark.anyio
async def test_failed_final_list_is_reported_as_liveness_failure():
    probe = FakeProbe([tool("echo")], fail_list_on=2)

    results = await run_protocol_checks(probe)

    assert results[-1].name == "server alive after bad calls"
    assert results[-1].passed is False
    assert results[-1].detail == "RuntimeError: list failed"


@pytest.mark.anyio
async def test_invalid_args_probe_covers_fixture_tools_with_required_fields(fixture_spec):
    async with connect(fixture_spec) as probe:
        default_results = await run_protocol_checks(probe)
    async with connect(fixture_spec) as probe:
        probed_results = await run_protocol_checks(probe, probe_invalid_args=True)

    assert "add: missing required args rejected" not in {result.name for result in default_results}
    names = {result.name for result in probed_results}
    assert "add: missing required args rejected" in names
    assert "get_user: missing required args rejected" in names
    assert all(result.passed for result in probed_results), probed_results


@pytest.mark.anyio
async def test_invalid_args_probe_skips_malformed_required_definitions():
    probe = FakeProbe(
        [
            tool("valid", {"type": "object", "required": ["value"]}),
            tool("empty", {"type": "object", "required": []}),
            tool("string", {"type": "object", "required": "value"}),
            tool("mixed", {"type": "object", "required": ["value", 1]}),
        ]
    )

    await run_protocol_checks(probe, probe_invalid_args=True)

    assert [name for name, _, _ in probe.calls] == [UNKNOWN_TOOL_BASE, "valid"]
