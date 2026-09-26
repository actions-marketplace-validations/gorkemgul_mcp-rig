from mcp_rig.client import CallOutcome
from mcp_rig.report import render_suite
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
