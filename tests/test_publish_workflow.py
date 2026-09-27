import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "publish.yml"

APPROVED_ACTIONS = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
}


def load_workflow() -> tuple[dict[str, object], str]:
    raw = WORKFLOW_PATH.read_text()
    return yaml.load(raw, Loader=yaml.BaseLoader), raw


def test_release_publication_is_the_only_trigger() -> None:
    workflow, _ = load_workflow()

    assert workflow["on"] == {"release": {"types": ["published"]}}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "publish-${{ github.event.release.tag_name }}",
        "cancel-in-progress": "false",
    }


def test_prereleases_cannot_run_either_job() -> None:
    workflow, _ = load_workflow()

    expected_condition = "${{ github.event.release.prerelease == false }}"
    assert workflow["jobs"]["build"]["if"] == expected_condition
    assert workflow["jobs"]["publish"]["if"] == expected_condition


def test_publish_job_has_only_oidc_and_distribution_handoff() -> None:
    workflow, _ = load_workflow()
    publish = workflow["jobs"]["publish"]

    assert publish["needs"] == "build"
    assert publish["environment"] == {
        "name": "pypi",
        "url": "https://pypi.org/p/mcp-rig",
    }
    assert publish["permissions"] == {"id-token": "write"}
    assert len(publish["steps"]) == 2
    assert [step["uses"].split("@", 1)[0] for step in publish["steps"]] == [
        "actions/download-artifact",
        "pypa/gh-action-pypi-publish",
    ]
    assert all("run" not in step for step in publish["steps"])


def test_every_action_is_approved_and_immutably_pinned() -> None:
    workflow, _ = load_workflow()
    uses = {
        step["uses"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    }

    assert uses == APPROVED_ACTIONS
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)


def test_build_checks_out_the_release_tag_without_credentials() -> None:
    workflow, _ = load_workflow()
    checkout = workflow["jobs"]["build"]["steps"][0]

    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {
        "ref": "${{ github.event.release.tag_name }}",
        "persist-credentials": "false",
    }


def test_build_validates_tag_and_uploads_only_distributions() -> None:
    workflow, _ = load_workflow()
    steps = {step["name"]: step for step in workflow["jobs"]["build"]["steps"]}

    assert steps["Validate release tag"]["env"] == {
        "RELEASE_TAG": "${{ github.event.release.tag_name }}"
    }
    assert steps["Validate release tag"]["run"] == 'python scripts/check_release_tag.py "$RELEASE_TAG"'
    assert steps["Upload distributions"]["with"] == {
        "name": "python-package-distributions",
        "path": "dist/",
        "retention-days": "1",
        "if-no-files-found": "error",
    }


def test_workflow_contains_no_credential_or_bypass_path() -> None:
    _, raw = load_workflow()
    lowered = raw.lower()

    for forbidden in (
        "secrets.",
        "password",
        "api-token",
        "pull_request",
        "workflow_dispatch",
        "schedule",
        "twine upload",
        "test.pypi",
        "skip-existing",
        "attestations: false",
    ):
        assert forbidden not in lowered
