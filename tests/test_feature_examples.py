import os
import sys
from pathlib import Path

from mcp_rig.cli import main
from mcp_rig.spec import KNOWN_EXPECT_KEYS, load_suite

ROOT = Path(__file__).resolve().parents[1]
FEATURE_TOUR = ROOT / "examples" / "feature-tour"


def activate_test_python(monkeypatch) -> None:
    executable_directory = str(Path(sys.executable).parent)
    monkeypatch.setenv(
        "PATH",
        executable_directory + os.pathsep + os.environ.get("PATH", ""),
    )


def test_feature_tour_runs_end_to_end(capsys, monkeypatch) -> None:
    activate_test_python(monkeypatch)
    assert main(["run", str(FEATURE_TOUR)]) == 0

    output = capsys.readouterr().out
    assert "validates a complete user payload" in output
    assert "inherits suite and case tags" in output
    assert "captures a stable tool response" in output
    assert "reads configured environment" in output


def test_feature_tour_covers_the_complete_suite_contract() -> None:
    suite_paths = sorted(
        path
        for path in FEATURE_TOUR.glob("*.yaml")
        if not path.name.endswith(".snap.yaml")
    )
    suites = [load_suite(path) for path in suite_paths]
    cases = [case for suite in suites for case in suite.cases]

    covered_expectations = {
        key for case in cases for key in case.expect if key in KNOWN_EXPECT_KEYS
    }
    assert covered_expectations == KNOWN_EXPECT_KEYS
    assert any(case.timeout_s != 30 for case in cases)
    assert any(suite.tags for suite in suites)
    assert any(case.tags for case in cases)

    configured = next(suite for suite in suites if suite.path.name == "server-config.yaml")
    assert configured.server.args
    assert configured.server.cwd is not None
    assert configured.server.env == {"MCP_RIG_EXAMPLE": "configured"}


def test_feature_tour_filters_real_cases(capsys, monkeypatch) -> None:
    activate_test_python(monkeypatch)
    suite = FEATURE_TOUR / "filtering.yaml"

    assert main(["run", str(suite), "--tag", "smoke", "--exclude-tag", "slow"]) == 0

    output = capsys.readouterr().out
    assert "inherits suite and case tags" in output
    assert "slow case can be excluded" not in output
    assert "Selection: 1 selected, 1 filtered out" in output
