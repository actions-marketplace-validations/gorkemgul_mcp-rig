from pathlib import Path

import pytest

from mcp_rig.batch import (
    BatchFailure,
    BatchFailureCategory,
    BatchResult,
    SuiteRun,
    run_batch,
)
from mcp_rig.client import CallOutcome, ServerSpec
from mcp_rig.discovery import DiscoveryError, DiscoveryResult
from mcp_rig.runner import (
    CaseResult,
    CaseStatus,
    ErrorCategory,
    InfrastructureError,
    SuiteResult,
)
from mcp_rig.selection import SelectionFilter
from mcp_rig.snapshots import SnapshotChanges
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


@pytest.mark.anyio
async def test_batch_opens_snapshot_session_for_selected_case_and_aggregates_update(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "suite.yaml"
    suite = Suite(
        path,
        ServerSpec("unused"),
        [Case("snapshot case", "echo", expect={"snapshot": True})],
    )

    async def fake_run(selected, show_server_logs=False, snapshots=None):
        assert snapshots is not None
        assert snapshots.evaluate(
            "snapshot case",
            CallOutcome(False, "captured", None, 1),
        ) == []
        return passing_result("snapshot case")

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda _: suite)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([path], []),
        update_snapshots=True,
    )

    assert result.snapshot_update_active is True
    assert result.snapshot_changes == SnapshotChanges(added=1)
    assert (tmp_path / "suite.snap.yaml").exists()


@pytest.mark.anyio
async def test_batch_does_not_open_sidecar_for_filtered_or_non_snapshot_suite(
    monkeypatch,
    tmp_path,
):
    filtered_path = tmp_path / "filtered.yaml"
    ordinary_path = tmp_path / "ordinary.yaml"
    (tmp_path / "filtered.snap.yaml").write_text("malformed", encoding="utf-8")
    (tmp_path / "ordinary.snap.yaml").write_text("malformed", encoding="utf-8")
    suites = {
        filtered_path: Suite(
            filtered_path,
            ServerSpec("unused"),
            [
                Case(
                    "filtered snapshot",
                    "echo",
                    expect={"snapshot": True},
                    tags=frozenset({"slow"}),
                )
            ],
        ),
        ordinary_path: Suite(
            ordinary_path,
            ServerSpec("unused"),
            [Case("ordinary", "echo", tags=frozenset({"smoke"}))],
        ),
    }

    async def fake_run(selected, show_server_logs=False):
        assert selected.path == ordinary_path
        return passing_result("ordinary")

    monkeypatch.setattr("mcp_rig.batch.load_suite", suites.__getitem__)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([filtered_path, ordinary_path], []),
        selection=SelectionFilter(required_tags=frozenset({"smoke"})),
        update_snapshots=True,
    )

    assert result.has_errors is False
    assert [item.path for item in result.suites] == [ordinary_path]
    assert result.snapshot_changes == SnapshotChanges()


@pytest.mark.anyio
async def test_filtered_snapshot_update_preserves_unselected_entries(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "suite.yaml"
    (tmp_path / "suite.snap.yaml").write_text(
        "version: 1\n"
        "snapshots:\n"
        "  selected: {is_error: false, kind: text, value: old}\n"
        "  unselected: {is_error: false, kind: text, value: keep}\n",
        encoding="utf-8",
    )
    suite = Suite(
        path,
        ServerSpec("unused"),
        [
            Case(
                "selected",
                "echo",
                expect={"snapshot": True},
                tags=frozenset({"smoke"}),
            ),
            Case(
                "unselected",
                "echo",
                expect={"snapshot": True},
                tags=frozenset({"slow"}),
            ),
        ],
    )

    async def fake_run(selected, show_server_logs=False, snapshots=None):
        snapshots.evaluate("selected", CallOutcome(False, "new", None, 1))
        return passing_result("selected")

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda _: suite)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([path], []),
        selection=SelectionFilter(required_tags=frozenset({"smoke"})),
        update_snapshots=True,
    )

    contents = (tmp_path / "suite.snap.yaml").read_text(encoding="utf-8")
    assert result.snapshot_changes == SnapshotChanges(updated=1)
    assert "value: new" in contents
    assert "value: keep" in contents


@pytest.mark.anyio
async def test_complete_snapshot_update_prunes_stale_entry(monkeypatch, tmp_path):
    path = tmp_path / "suite.yaml"
    (tmp_path / "suite.snap.yaml").write_text(
        "version: 1\n"
        "snapshots:\n"
        "  case: {is_error: false, kind: text, value: same}\n"
        "  stale: {is_error: false, kind: text, value: old}\n",
        encoding="utf-8",
    )
    suite = Suite(
        path,
        ServerSpec("unused"),
        [Case("case", "echo", expect={"snapshot": True})],
    )

    async def fake_run(selected, show_server_logs=False, snapshots=None):
        snapshots.evaluate("case", CallOutcome(False, "same", None, 1))
        return passing_result("case")

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda _: suite)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([path], []),
        update_snapshots=True,
    )

    contents = (tmp_path / "suite.snap.yaml").read_text(encoding="utf-8")
    assert result.snapshot_changes == SnapshotChanges(unchanged=1, removed=1)
    assert "stale" not in contents


@pytest.mark.anyio
@pytest.mark.parametrize(
    "result",
    [
        SuiteResult(
            [
                CaseResult(
                    "case",
                    CaseStatus.ERROR,
                    error=InfrastructureError(
                        ErrorCategory.TIMEOUT,
                        "TimeoutError",
                        "timed out",
                    ),
                )
            ]
        ),
        SuiteResult(
            [CaseResult("case", CaseStatus.PASSED)],
            suite_error=InfrastructureError(
                ErrorCategory.TEARDOWN,
                "RuntimeError",
                "close failed",
            ),
        ),
    ],
)
async def test_infrastructure_error_prevents_snapshot_pruning(
    monkeypatch,
    tmp_path,
    result,
):
    path = tmp_path / "suite.yaml"
    (tmp_path / "suite.snap.yaml").write_text(
        "version: 1\n"
        "snapshots:\n"
        "  case: {is_error: false, kind: text, value: old}\n"
        "  stale: {is_error: false, kind: text, value: keep}\n",
        encoding="utf-8",
    )
    suite = Suite(
        path,
        ServerSpec("unused"),
        [Case("case", "echo", expect={"snapshot": True})],
    )

    async def fake_run(selected, show_server_logs=False, snapshots=None):
        return result

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda _: suite)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    batch = await run_batch(
        DiscoveryResult([path], []),
        update_snapshots=True,
    )

    assert batch.snapshot_changes == SnapshotChanges()
    assert "stale" in (tmp_path / "suite.snap.yaml").read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_snapshot_changes_aggregate_across_suites(monkeypatch, tmp_path):
    added_path = tmp_path / "added.yaml"
    updated_path = tmp_path / "updated.yaml"
    (tmp_path / "updated.snap.yaml").write_text(
        "version: 1\nsnapshots:\n"
        "  case: {is_error: false, kind: text, value: old}\n",
        encoding="utf-8",
    )
    suites = {
        path: Suite(
            path,
            ServerSpec("unused"),
            [Case("case", "echo", expect={"snapshot": True})],
        )
        for path in (added_path, updated_path)
    }

    async def fake_run(selected, show_server_logs=False, snapshots=None):
        snapshots.evaluate("case", CallOutcome(False, "new", None, 1))
        return passing_result("case")

    monkeypatch.setattr("mcp_rig.batch.load_suite", suites.__getitem__)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([added_path, updated_path], []),
        update_snapshots=True,
    )

    assert result.snapshot_changes == SnapshotChanges(added=1, updated=1)


@pytest.mark.anyio
async def test_malformed_snapshot_is_isolated_and_later_suite_runs(
    monkeypatch,
    tmp_path,
):
    invalid = tmp_path / "invalid.yaml"
    valid = tmp_path / "valid.yaml"
    (tmp_path / "invalid.snap.yaml").write_text("malformed", encoding="utf-8")
    suites = {
        invalid: Suite(
            invalid,
            ServerSpec("unused"),
            [Case("snapshot", "echo", expect={"snapshot": True})],
        ),
        valid: Suite(valid, ServerSpec("unused"), [Case("ordinary", "echo")]),
    }
    executed = []

    async def fake_run(selected, show_server_logs=False):
        executed.append(selected.path)
        return passing_result(selected.path.stem)

    monkeypatch.setattr("mcp_rig.batch.load_suite", suites.__getitem__)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(DiscoveryResult([invalid, valid], []))

    assert executed == [valid]
    assert result.suites[0].error.category is BatchFailureCategory.SNAPSHOT
    assert result.suites[1].result is not None


@pytest.mark.anyio
async def test_snapshot_read_oserror_is_suite_local(monkeypatch, tmp_path):
    blocked = tmp_path / "blocked.yaml"
    later = tmp_path / "later.yaml"
    sidecar = tmp_path / "blocked.snap.yaml"
    sidecar.write_text("version: 1\nsnapshots: {}\n", encoding="utf-8")
    suites = {
        blocked: Suite(
            blocked,
            ServerSpec("unused"),
            [Case("snapshot", "echo", expect={"snapshot": True})],
        ),
        later: Suite(later, ServerSpec("unused"), [Case("ordinary", "echo")]),
    }
    real_read_text = Path.read_text

    def failing_read_text(path, *args, **kwargs):
        if path == sidecar:
            raise PermissionError("read denied")
        return real_read_text(path, *args, **kwargs)

    async def fake_run(selected, show_server_logs=False):
        return passing_result(selected.path.stem)

    monkeypatch.setattr(Path, "read_text", failing_read_text)
    monkeypatch.setattr("mcp_rig.batch.load_suite", suites.__getitem__)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(DiscoveryResult([blocked, later], []))

    assert result.suites[0].error.category is BatchFailureCategory.SNAPSHOT
    assert "read denied" in result.suites[0].error.message
    assert result.suites[1].result is not None


@pytest.mark.anyio
async def test_snapshot_persistence_failure_keeps_result_and_later_suite_runs(
    monkeypatch,
    tmp_path,
):
    snapshot_path = tmp_path / "snapshot.yaml"
    later_path = tmp_path / "later.yaml"
    suites = {
        snapshot_path: Suite(
            snapshot_path,
            ServerSpec("unused"),
            [Case("snapshot", "echo", expect={"snapshot": True})],
        ),
        later_path: Suite(later_path, ServerSpec("unused"), [Case("later", "echo")]),
    }

    async def fake_run(selected, show_server_logs=False, snapshots=None):
        if snapshots is not None:
            snapshots.evaluate("snapshot", CallOutcome(False, "captured", None, 1))
        return passing_result(selected.path.stem)

    def failing_replace(source, destination):
        raise OSError("replace denied")

    monkeypatch.setattr("mcp_rig.snapshots.os.replace", failing_replace)
    monkeypatch.setattr("mcp_rig.batch.load_suite", suites.__getitem__)
    monkeypatch.setattr("mcp_rig.batch.run_suite", fake_run)

    result = await run_batch(
        DiscoveryResult([snapshot_path, later_path], []),
        update_snapshots=True,
    )

    assert result.suites[0].result is not None
    assert result.suites[0].error.category is BatchFailureCategory.SNAPSHOT
    assert result.suites[1].result is not None


@pytest.mark.anyio
async def test_snapshot_batch_still_propagates_keyboard_interrupt(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "suite.yaml"
    suite = Suite(
        path,
        ServerSpec("unused"),
        [Case("snapshot", "echo", expect={"snapshot": True})],
    )

    async def interrupt(selected, show_server_logs=False, snapshots=None):
        raise KeyboardInterrupt

    monkeypatch.setattr("mcp_rig.batch.load_suite", lambda _: suite)
    monkeypatch.setattr("mcp_rig.batch.run_suite", interrupt)

    with pytest.raises(KeyboardInterrupt):
        await run_batch(
            DiscoveryResult([path], []),
            update_snapshots=True,
        )
