from pathlib import Path

import pytest

from mcp_rig.batch import (
    BatchFailure,
    BatchFailureCategory,
    BatchResult,
    SuiteRun,
    run_batch,
)
from mcp_rig.client import ServerSpec
from mcp_rig.discovery import DiscoveryError, DiscoveryResult
from mcp_rig.runner import (
    CaseResult,
    CaseStatus,
    ErrorCategory,
    InfrastructureError,
    SuiteResult,
)
from mcp_rig.selection import SelectionFilter
from mcp_rig.spec import Case, SpecError, Suite


def passing_result(name: str = "passes") -> SuiteResult:
    return SuiteResult([CaseResult(name=name, status=CaseStatus.PASSED)])


def suite_at(path: Path) -> Suite:
    return Suite(path=path, server=ServerSpec("unused"), cases=[Case("case", "echo")])


def test_batch_counts_suite_and_case_outcomes_with_discovery_errors():
    passed = SuiteResult(
        [
            CaseResult(name="one", status=CaseStatus.PASSED),
            CaseResult(name="two", status=CaseStatus.PASSED),
        ]
    )
    failed = SuiteResult(
        [
            CaseResult(name="three", status=CaseStatus.PASSED),
            CaseResult(name="four", status=CaseStatus.FAILED, failures=["wrong"]),
        ]
    )
    errored = SuiteResult(
        [
            CaseResult(name="five", status=CaseStatus.FAILED, failures=["wrong"]),
            CaseResult(
                name="six",
                status=CaseStatus.ERROR,
                error=InfrastructureError(
                    ErrorCategory.TRANSPORT,
                    "BrokenPipeError",
                    "connection lost",
                ),
            ),
            CaseResult(
                name="seven",
                status=CaseStatus.SKIPPED,
                skip_reason="session unavailable",
            ),
        ]
    )
    result = BatchResult(
        suites=[
            SuiteRun(Path("passed.yaml"), result=passed),
            SuiteRun(Path("failed.yaml"), result=failed),
            SuiteRun(Path("errored.yaml"), result=errored),
            SuiteRun(
                Path("invalid.yaml"),
                error=BatchFailure(
                    BatchFailureCategory.CONFIGURATION,
                    "SpecError",
                    "invalid suite",
                ),
            ),
        ],
        discovery_errors=[
            DiscoveryError(Path("missing.yaml"), "FileNotFoundError", "missing")
        ],
    )

    assert (result.suite_passed, result.suite_failed, result.suite_errors) == (1, 1, 3)
    assert (
        result.case_passed,
        result.case_failed,
        result.case_errors,
        result.case_skipped,
    ) == (3, 2, 1, 1)
    assert result.has_failures is True
    assert result.has_errors is True


@pytest.mark.anyio
async def test_batch_runs_paths_sequentially_and_forwards_server_logs(
    monkeypatch, tmp_path
):
    paths = [tmp_path / "a.yaml", tmp_path / "b.yaml"]
    calls = []

    def fake_load(path):
        calls.append(("load", path))
        return suite_at(path)

    async def fake_run(suite, show_server_logs=False):
        calls.append(("run", suite.path, show_server_logs))
        return passing_result(suite.path.stem)

    monkeypatch.setattr("mcp_rig.batch.load_suite", fake_load)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(DiscoveryResult(paths, []), show_server_logs=True)

    assert calls == [
        ("load", paths[0]),
        ("run", paths[0], True),
        ("load", paths[1]),
        ("run", paths[1], True),
    ]
    assert [item.path for item in result.suites] == paths
    assert result.suite_passed == 2
    assert result.selection_active is False
    assert (result.selected_cases, result.filtered_out_cases) == (2, 0)


@pytest.mark.anyio
async def test_batch_filters_before_running_and_aggregates_selection_counts(
    monkeypatch, tmp_path
):
    partial = tmp_path / "partial.yaml"
    empty = tmp_path / "empty.yaml"
    suites = {
        partial: Suite(
            partial,
            ServerSpec("unused"),
            [
                Case("keep", "echo", tags=frozenset({"smoke"})),
                Case("remove", "echo", tags=frozenset({"slow"})),
            ],
        ),
        empty: Suite(
            empty,
            ServerSpec("unused"),
            [Case("also remove", "echo", tags=frozenset({"regression"}))],
        ),
    }
    executed = []

    async def fake_run(suite, show_server_logs=False):
        executed.append(suite)
        return passing_result(suite.cases[0].name)

    monkeypatch.setattr("mcp_rig.batch.load_suite", suites.__getitem__)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([partial, empty], []),
        selection=SelectionFilter(required_tags=frozenset({"smoke"})),
    )

    assert [suite.path for suite in executed] == [partial]
    assert [case.name for case in executed[0].cases] == ["keep"]
    assert [item.path for item in result.suites] == [partial]
    assert result.selection_active is True
    assert (result.selected_cases, result.filtered_out_cases) == (1, 2)


@pytest.mark.anyio
async def test_batch_does_not_run_any_suite_when_selection_matches_nothing(
    monkeypatch, tmp_path
):
    path = tmp_path / "suite.yaml"
    suite = Suite(
        path,
        ServerSpec("unused"),
        [Case("one", "echo"), Case("two", "echo")],
    )

    async def fail_if_run(suite, show_server_logs=False):
        pytest.fail("runner must not start for an empty selection")

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda _: suite)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fail_if_run)

    result = await run_batch(
        DiscoveryResult([path], []),
        selection=SelectionFilter(required_tags=frozenset({"smoke"})),
    )

    assert result.suites == []
    assert (result.selected_cases, result.filtered_out_cases) == (0, 2)


@pytest.mark.anyio
async def test_batch_still_reports_load_errors_when_other_cases_are_selected(
    monkeypatch, tmp_path
):
    invalid = tmp_path / "invalid.yaml"
    valid = tmp_path / "valid.yaml"

    def fake_load(path):
        if path == invalid:
            raise SpecError("invalid suite")
        return Suite(
            valid,
            ServerSpec("unused"),
            [Case("keep", "echo", tags=frozenset({"smoke"}))],
        )

    async def fake_run(suite, show_server_logs=False):
        return passing_result()

    monkeypatch.setattr("mcp_rig.batch.load_suite", fake_load)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([invalid, valid], []),
        selection=SelectionFilter(required_tags=frozenset({"smoke"})),
    )

    assert [item.path for item in result.suites] == [invalid, valid]
    assert result.suites[0].error == BatchFailure(
        BatchFailureCategory.CONFIGURATION,
        "SpecError",
        "invalid suite",
    )
    assert result.suites[1].result is not None
    assert (result.selected_cases, result.filtered_out_cases) == (1, 0)


@pytest.mark.anyio
async def test_filtered_cases_are_not_runtime_skips_after_selected_infrastructure_error(
    monkeypatch, tmp_path
):
    path = tmp_path / "suite.yaml"
    suite = Suite(
        path,
        ServerSpec("unused"),
        [
            Case("breaks", "echo", tags=frozenset({"smoke"})),
            Case("selected later", "echo", tags=frozenset({"smoke"})),
            Case("filtered", "echo", tags=frozenset({"slow"})),
        ],
    )

    async def fake_run(selected, show_server_logs=False):
        assert [case.name for case in selected.cases] == ["breaks", "selected later"]
        return SuiteResult(
            [
                CaseResult(
                    name="breaks",
                    status=CaseStatus.ERROR,
                    error=InfrastructureError(
                        ErrorCategory.TRANSPORT,
                        "BrokenPipeError",
                        "connection lost",
                    ),
                ),
                CaseResult(
                    name="selected later",
                    status=CaseStatus.SKIPPED,
                    skip_reason="session unavailable",
                ),
            ]
        )

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda _: suite)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([path], []),
        selection=SelectionFilter(required_tags=frozenset({"smoke"})),
    )

    assert result.case_skipped == 1
    assert (result.selected_cases, result.filtered_out_cases) == (2, 1)


@pytest.mark.anyio
async def test_batch_continues_after_parse_and_execution_errors(monkeypatch, tmp_path):
    invalid = tmp_path / "invalid.yaml"
    crashes = tmp_path / "crashes.yaml"
    passes = tmp_path / "passes.yaml"
    executed = []

    def fake_load(path):
        if path == invalid:
            raise SpecError("invalid suite")
        return suite_at(path)

    async def fake_run(suite, show_server_logs=False):
        executed.append(suite.path)
        if suite.path == crashes:
            raise RuntimeError("runner crashed")
        return passing_result()

    monkeypatch.setattr("mcp_rig.batch.load_suite", fake_load)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(DiscoveryResult([invalid, crashes, passes], []))

    assert executed == [crashes, passes]
    assert [item.path for item in result.suites] == [invalid, crashes, passes]
    assert result.suites[0].error == BatchFailure(
        BatchFailureCategory.CONFIGURATION,
        "SpecError",
        "invalid suite",
    )
    assert result.suites[1].error == BatchFailure(
        BatchFailureCategory.EXECUTION,
        "RuntimeError",
        "runner crashed",
    )
    assert result.suites[2].result is not None
    assert (result.suite_passed, result.suite_errors) == (1, 2)


@pytest.mark.anyio
async def test_batch_continues_after_unexpected_suite_load_error(monkeypatch, tmp_path):
    invalid = tmp_path / "invalid.yaml"
    passes = tmp_path / "passes.yaml"

    def fake_load(path):
        if path == invalid:
            raise TypeError("malformed expectation key")
        return suite_at(path)

    async def fake_run(suite, show_server_logs=False):
        return passing_result()

    monkeypatch.setattr("mcp_rig.batch.load_suite", fake_load)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(DiscoveryResult([invalid, passes], []))

    assert result.suites[0].error == BatchFailure(
        BatchFailureCategory.CONFIGURATION,
        "TypeError",
        "malformed expectation key",
    )
    assert result.suites[1].result is not None
    assert (result.suite_passed, result.suite_errors) == (1, 1)


@pytest.mark.anyio
async def test_batch_propagates_keyboard_interrupt(monkeypatch, tmp_path):
    path = tmp_path / "suite.yaml"

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda path: suite_at(path))

    async def interrupt(suite, show_server_logs=False):
        raise KeyboardInterrupt

    monkeypatch.setattr("mcp_rig.batch.run_suite", interrupt)

    with pytest.raises(KeyboardInterrupt):
        await run_batch(DiscoveryResult([path], []))
