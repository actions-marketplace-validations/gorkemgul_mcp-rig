from contextlib import asynccontextmanager

import pytest

from mcp_rig.client import CallOutcome, ServerSpec
from mcp_rig.runner import CaseStatus, ErrorCategory, run_suite
from mcp_rig.spec import Case, Suite


@pytest.mark.anyio
async def test_runs_all_cases_in_order_after_an_assertion_failure(fixture_spec, tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=fixture_spec,
        cases=[
            Case("adds", "add", {"a": 2, "b": 2}, {"contains": "4"}),
            Case("wrong on purpose", "echo", {"text": "hi"}, {"contains": "bye"}),
            Case("still runs", "echo", {"text": "after"}, {"contains": "after"}),
        ],
    )

    result = await run_suite(suite)

    assert [item.name for item in result.results] == ["adds", "wrong on purpose", "still runs"]
    assert [item.status for item in result.results] == [CaseStatus.PASSED, CaseStatus.FAILED, CaseStatus.PASSED]
    assert result.results[1].failures == ["contains: 'bye' not found in 'hi'"]
    assert (result.passed, result.failed, result.ok) == (2, 1, False)
    assert all(item.outcome is not None for item in result.results)


@pytest.mark.anyio
async def test_tool_error_can_be_an_expected_passing_result(fixture_spec, tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=fixture_spec,
        cases=[Case("missing user", "get_user", {"user_id": 99}, {"is_error": True, "contains": "not found"})],
    )

    result = await run_suite(suite)

    assert result.ok is True
    assert result.results[0].outcome.is_error is True


@pytest.mark.anyio
async def test_transport_timeout_aborts_later_cases_and_preserves_earlier_failure(monkeypatch, tmp_path):
    calls = []

    class FakeProbe:
        async def call(self, name, args, timeout_s):
            calls.append((name, args, timeout_s))
            if name == "times-out":
                raise ExceptionGroup("call", [RuntimeError("side"), TimeoutError()])
            return CallOutcome(False, "hi", None, 1.0)

    @asynccontextmanager
    async def fake_connect(spec, show_server_logs=False):
        yield FakeProbe()

    monkeypatch.setattr("mcp_rig.runner.connect", fake_connect)
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=ServerSpec("unused"),
        cases=[
            Case("fails", "echo", {}, {"contains": "bye"}, timeout_s=1.5),
            Case("times out", "times-out", timeout_s=0.25),
            Case("never runs", "never"),
        ],
    )

    result = await run_suite(suite)

    assert [item.status for item in result.results] == [
        CaseStatus.FAILED,
        CaseStatus.ERROR,
        CaseStatus.SKIPPED,
    ]
    assert (result.passed, result.failed, result.errors, result.skipped) == (0, 1, 1, 1)
    assert result.results[1].error.category is ErrorCategory.TIMEOUT
    assert result.results[1].error.exception_type == "TimeoutError"
    assert result.results[1].error.message == "operation timed out"
    assert calls == [("echo", {}, 1.5), ("times-out", {}, 0.25)]


@pytest.mark.anyio
async def test_live_timeout_marks_active_case_error_and_later_case_skipped(fixture_spec, tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=fixture_spec,
        cases=[
            Case("too slow", "slow", {"seconds": 0.2}, timeout_s=0.01),
            Case("never runs", "echo", {"text": "after"}),
        ],
    )

    result = await run_suite(suite)

    assert [item.status for item in result.results] == [CaseStatus.ERROR, CaseStatus.SKIPPED]
    assert result.results[0].error.category is ErrorCategory.TIMEOUT
    assert result.results[0].elapsed_ms >= 0


@pytest.mark.anyio
async def test_base_exception_from_probe_propagates(monkeypatch, tmp_path):
    class InterruptingProbe:
        async def call(self, name, args, timeout_s):
            raise KeyboardInterrupt

    @asynccontextmanager
    async def fake_connect(spec, show_server_logs=False):
        yield InterruptingProbe()

    monkeypatch.setattr("mcp_rig.runner.connect", fake_connect)
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=ServerSpec("unused"),
        cases=[Case("interrupts", "stop")],
    )

    with pytest.raises(KeyboardInterrupt):
        await run_suite(suite)


@pytest.mark.anyio
async def test_infrastructure_failure_propagates(tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=ServerSpec("/definitely/missing/mcp-rig-server"),
        cases=[Case("never runs", "echo")],
    )

    with pytest.raises(OSError):
        await run_suite(suite)
