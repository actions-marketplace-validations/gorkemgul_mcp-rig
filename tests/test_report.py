from mcp_rig.client import CallOutcome
from mcp_rig.report import render_suite
from mcp_rig.runner import CaseResult, SuiteResult


def result(name, passed, failures, latency_ms):
    return CaseResult(name, passed, failures, CallOutcome(False, "", None, latency_ms))


def test_render_suite_plain_text():
    suite_result = SuiteResult(
        [
            result("adds", True, [], 12.4),
            result("breaks", False, ["contains: 'x' not found in 'y'"], 2.2),
        ]
    )

    assert render_suite("suite.yaml", suite_result) == "\n".join(
        [
            "MCP Rig — suite.yaml",
            "",
            "✓ adds (12 ms)",
            "✗ breaks (2 ms)",
            "    contains: 'x' not found in 'y'",
            "",
            "1 passed, 1 failed",
        ]
    )


def test_render_suite_color_wraps_only_status_marks():
    text = render_suite("suite.yaml", SuiteResult([result("adds", True, [], 1.0)]), color=True)

    assert "\033[32m✓\033[0m adds" in text
    assert "MCP Rig — suite.yaml" in text
