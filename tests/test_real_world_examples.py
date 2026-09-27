from pathlib import Path

import pytest
import yaml

from mcp_rig.spec import load_suite

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "servers"
WORKFLOW = ROOT / ".github" / "workflows" / "examples-smoke.yml"


@pytest.mark.parametrize(
    ("name", "command", "package"),
    [
        ("playwright", "npx", "@playwright/mcp@0.0.82"),
        (
            "server-everything",
            "npx",
            "@modelcontextprotocol/server-everything@2026.8.18",
        ),
        ("time", "uvx", "mcp-server-time==2026.8.18"),
    ],
)
def test_real_world_suite_loads_with_a_pinned_server_package(
    name: str, command: str, package: str
) -> None:
    suite = load_suite(EXAMPLES / name / "suite.yaml")

    assert suite.server.command == command
    assert package in suite.server.args
    assert len(suite.cases) >= 2
    assert all(case.expect.get("is_error") is False for case in suite.cases)


def test_external_examples_run_only_manually_or_on_the_weekly_schedule() -> None:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert workflow["on"] == {
        "workflow_dispatch": "",
        "schedule": [{"cron": "17 6 * * 1"}],
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"playwright", "server-everything", "time"}
