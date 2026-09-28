from pathlib import Path

from mcp_rig.batch import BatchFailure, BatchFailureCategory, BatchResult, SuiteRun
from mcp_rig.checks import CheckResult
from mcp_rig.client import CallOutcome
from mcp_rig.discovery import DiscoveryError
from mcp_rig.lint import LintWarning
from mcp_rig.report import render_batch, render_batch_errors, render_check, render_suite
from mcp_rig.runner import CaseResult, CaseStatus, ErrorCategory, InfrastructureError, SuiteResult


def completed_result(name, status, failures, elapsed_ms):
    return CaseResult(
        name=name,
        status=status,
        elapsed_ms=elapsed_ms,
        failures=failures,
        outcome=CallOutcome(False, "", None, elapsed_ms),
    )


def test_render_suite_plain_text_for_every_case_status():
    suite_result = SuiteResult(
        [
            completed_result("adds", CaseStatus.PASSED, [], 12.4),
            completed_result("breaks", CaseStatus.FAILED, ["contains: 'x' not found in 'y'"], 2.2),
            CaseResult(
                name="times out",
                status=CaseStatus.ERROR,
                elapsed_ms=10.6,
                error=InfrastructureError(ErrorCategory.TIMEOUT, "MCPError", "Request 'tools/call' timed out"),
            ),
            CaseResult(
                name="never runs",
                status=CaseStatus.SKIPPED,
                skip_reason="not run after infrastructure error in 'times out'",
            ),
        ]
    )

    assert render_suite("suite.yaml", suite_result) == "\n".join(
        [
            "MCP Rig — suite.yaml",
            "",
            "✓ adds (12 ms)",
            "✗ breaks (2 ms)",
            "    contains: 'x' not found in 'y'",
            "! times out (11 ms)",
            "    timeout: MCPError: Request 'tools/call' timed out",
            "- never runs",
            "    not run after infrastructure error in 'times out'",
            "",
            "1 passed, 1 failed, 1 error, 1 skipped",
        ]
    )


def test_render_suite_color_wraps_only_status_marks():
    suite_result = SuiteResult(
        [
            completed_result("adds", CaseStatus.PASSED, [], 1.0),
            completed_result("breaks", CaseStatus.FAILED, ["bad"], 1.0),
            CaseResult(
                name="times out",
                status=CaseStatus.ERROR,
                elapsed_ms=1.0,
                error=InfrastructureError(ErrorCategory.TIMEOUT, "TimeoutError", "operation timed out"),
            ),
            CaseResult(name="later", status=CaseStatus.SKIPPED, skip_reason="not run"),
        ]
    )

    text = render_suite("suite.yaml", suite_result, color=True)

    assert "\033[32m✓\033[0m adds" in text
    assert "\033[31m✗\033[0m breaks" in text
    assert "\033[31m!\033[0m times out" in text
    assert "\033[" not in text.split("- later", maxsplit=1)[1]
    assert "MCP Rig — suite.yaml" in text


def test_render_suite_setup_error_separately_from_skipped_cases():
    suite_result = SuiteResult(
        [CaseResult(name="never runs", status=CaseStatus.SKIPPED, skip_reason="suite could not start")],
        suite_error=InfrastructureError(ErrorCategory.SETUP, "FileNotFoundError", "missing server"),
    )

    text = render_suite("suite.yaml", suite_result)

    assert "! suite setup: FileNotFoundError: missing server" in text
    assert "- never runs\n    suite could not start" in text
    assert "0 passed, 0 failed, 1 error, 1 skipped" in text


def test_render_suite_teardown_error_without_rewriting_completed_case():
    suite_result = SuiteResult(
        [completed_result("completed", CaseStatus.PASSED, [], 2.0)],
        suite_error=InfrastructureError(ErrorCategory.TEARDOWN, "RuntimeError", "close failed"),
    )

    text = render_suite("suite.yaml", suite_result)

    assert "✓ completed (2 ms)" in text
    assert "! suite teardown: RuntimeError: close failed" in text
    assert "1 passed, 0 failed, 1 error, 0 skipped" in text


def test_render_batch_preserves_single_successful_suite_output():
    result = SuiteResult([completed_result("passes", CaseStatus.PASSED, [], 2.0)])
    batch = BatchResult([SuiteRun(Path("suite.yaml"), result=result)], [])

    assert render_batch(batch) == render_suite("suite.yaml", result)


def test_render_batch_reports_each_suite_then_literal_aggregate_counts():
    passed = SuiteResult(
        [
            completed_result("one", CaseStatus.PASSED, [], 1.0),
            completed_result("two", CaseStatus.PASSED, [], 2.0),
        ]
    )
    failed = SuiteResult(
        [
            completed_result("three", CaseStatus.PASSED, [], 3.0),
            completed_result("four", CaseStatus.FAILED, ["wrong"], 4.0),
        ]
    )
    errored = SuiteResult(
        [
            CaseResult(
                name="five",
                status=CaseStatus.ERROR,
                elapsed_ms=5.0,
                error=InfrastructureError(
                    ErrorCategory.TRANSPORT,
                    "BrokenPipeError",
                    "connection lost",
                ),
            ),
            CaseResult(
                name="six",
                status=CaseStatus.SKIPPED,
                skip_reason="session unavailable",
            ),
        ]
    )
    batch = BatchResult(
        [
            SuiteRun(Path("a.yaml"), result=passed),
            SuiteRun(Path("b.yaml"), result=failed),
            SuiteRun(Path("c.yaml"), result=errored),
            SuiteRun(
                Path("d.yaml"),
                error=BatchFailure(
                    BatchFailureCategory.CONFIGURATION,
                    "SpecError",
                    "invalid suite",
                ),
            ),
        ],
        [],
    )

    text = render_batch(batch)

    assert text.index("MCP Rig — a.yaml") < text.index("MCP Rig — b.yaml")
    assert text.index("MCP Rig — b.yaml") < text.index("MCP Rig — c.yaml")
    assert text.endswith(
        "Suites: 1 passed, 1 failed, 2 errors\n"
        "Cases: 3 passed, 1 failed, 1 error, 1 skipped"
    )


def test_render_batch_errors_identifies_target_and_suite_sources():
    batch = BatchResult(
        [
            SuiteRun(
                Path("invalid.yaml"),
                error=BatchFailure(
                    BatchFailureCategory.CONFIGURATION,
                    "SpecError",
                    "invalid suite",
                ),
            ),
            SuiteRun(
                Path("crashed.yaml"),
                error=BatchFailure(
                    BatchFailureCategory.EXECUTION,
                    "RuntimeError",
                    "runner crashed",
                ),
            ),
        ],
        [DiscoveryError(Path("missing.yaml"), "FileNotFoundError", "missing")],
    )

    assert render_batch_errors(batch) == "\n".join(
        [
            "! target missing.yaml: FileNotFoundError: missing",
            "! suite invalid.yaml configuration: SpecError: invalid suite",
            "! suite crashed.yaml execution: RuntimeError: runner crashed",
        ]
    )


def test_render_batch_colors_only_status_marks():
    passed = SuiteResult([completed_result("passes", CaseStatus.PASSED, [], 1.0)])
    failed = SuiteResult(
        [completed_result("fails", CaseStatus.FAILED, ["wrong"], 1.0)]
    )
    batch = BatchResult(
        [
            SuiteRun(Path("a.yaml"), result=passed),
            SuiteRun(Path("b.yaml"), result=failed),
        ],
        [],
    )

    text = render_batch(batch, color=True)

    assert "\033[32m✓\033[0m passes" in text
    assert "\033[31m✗\033[0m fails" in text
    assert "\033[" not in text.split("Suites:", maxsplit=1)[1]


def test_render_check_plain_text_with_failure_and_lint_warning():
    text = render_check(
        [
            CheckResult("lists tools", True),
            CheckResult("unknown tool returns an error", False, "got success"),
        ],
        [LintWarning("undocumented", "no-description", "tool has no description")],
    )

    assert text == "\n".join(
        [
            "Protocol checks",
            "  ✓ lists tools",
            "  ✗ unknown tool returns an error",
            "      got success",
            "Lint",
            "  ⚠ undocumented [no-description] tool has no description",
            "1/2 checks passed, 1 lint warning",
        ]
    )


def test_render_check_shows_empty_lint_section_and_plural_summary():
    text = render_check([CheckResult("lists tools", True)], [])

    assert text == "\n".join(
        [
            "Protocol checks",
            "  ✓ lists tools",
            "Lint",
            "  no warnings",
            "1/1 checks passed, 0 lint warnings",
        ]
    )


def test_render_check_color_wraps_only_status_symbols():
    text = render_check(
        [
            CheckResult("lists tools", True),
            CheckResult("unknown tool returns an error", False, "got success"),
        ],
        [LintWarning("undocumented", "no-description", "tool has no description")],
        color=True,
    )

    assert "\033[32m✓\033[0m lists tools" in text
    assert "\033[31m✗\033[0m unknown tool returns an error" in text
    assert "\033[33m⚠\033[0m undocumented" in text
    lines = text.splitlines()
    assert "Protocol checks" in lines
    assert "      got success" in lines
    assert "Lint" in lines
    assert "1/2 checks passed, 1 lint warning" in lines
