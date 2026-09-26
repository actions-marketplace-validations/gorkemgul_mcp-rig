import pytest

from mcp_rig.client import ServerSpec
from mcp_rig.runner import run_suite
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
    assert [item.passed for item in result.results] == [True, False, True]
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
async def test_infrastructure_failure_propagates(tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=ServerSpec("/definitely/missing/mcp-rig-server"),
        cases=[Case("never runs", "echo")],
    )

    with pytest.raises(OSError):
        await run_suite(suite)
