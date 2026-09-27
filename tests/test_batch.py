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
async def test_batch_propagates_keyboard_interrupt(monkeypatch, tmp_path):
    path = tmp_path / "suite.yaml"

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda path: suite_at(path))

    async def interrupt(suite, show_server_logs=False):
        raise KeyboardInterrupt

    monkeypatch.setattr("mcp_rig.batch.run_suite", interrupt)

    with pytest.raises(KeyboardInterrupt):
        await run_batch(DiscoveryResult([path], []))
