from pathlib import Path

import pytest
import yaml

from mcp_rig.client import CallOutcome
from mcp_rig.snapshots import (
    SnapshotChanges,
    SnapshotEntry,
    SnapshotError,
    SnapshotKind,
    SnapshotSession,
    snapshot_entry,
    snapshot_path,
)


def text_outcome(text: str, *, is_error: bool = False) -> CallOutcome:
    return CallOutcome(is_error, text, None, 42)


def write_snapshot_file(tmp_path: Path, snapshots: dict) -> Path:
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite", encoding="utf-8")
    (tmp_path / "suite.snap.yaml").write_text(
        yaml.safe_dump(
            {"version": 1, "snapshots": snapshots},
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return suite


def test_snapshot_path_is_canonical_and_replaces_suite_suffix(tmp_path: Path):
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite", encoding="utf-8")
    alias = tmp_path / "alias.yml"
    alias.symlink_to(suite)

    assert snapshot_path(suite) == tmp_path / "suite.snap.yaml"
    assert snapshot_path(alias) == tmp_path / "suite.snap.yaml"


def test_snapshot_path_rejects_yaml_yml_stem_collision(tmp_path: Path):
    yaml_path = tmp_path / "suite.yaml"
    yml_path = tmp_path / "suite.yml"
    yaml_path.write_text("suite", encoding="utf-8")
    yml_path.write_text("suite", encoding="utf-8")

    with pytest.raises(SnapshotError, match="same snapshot sidecar"):
        snapshot_path(yaml_path)


def test_structured_content_wins_and_mapping_keys_are_canonical():
    entry = snapshot_entry(
        CallOutcome(
            False,
            "ignored",
            {"z": 1, "nested": {"b": 2, "a": 1}},
            42,
        )
    )

    assert entry == SnapshotEntry(
        is_error=False,
        kind=SnapshotKind.STRUCTURED,
        value={"nested": {"a": 1, "b": 2}, "z": 1},
    )


def test_missing_and_changed_snapshots_return_deterministic_failures(tmp_path: Path):
    missing = SnapshotSession.open(tmp_path / "missing.yaml", update=False)
    assert missing.evaluate("case", text_outcome("actual")) == [
        "snapshot: missing entry for 'case'"
    ]

    suite = write_snapshot_file(
        tmp_path,
        {
            "case": {
                "is_error": False,
                "kind": "text",
                "value": "expected",
            }
        },
    )
    changed = SnapshotSession.open(suite, update=False)
    failure = changed.evaluate("case", text_outcome("actual"))[0]

    assert failure.startswith(
        "snapshot: mismatch for 'case'\n--- expected\n+++ actual\n"
    )
    assert "-  value: expected" in failure
    assert "+  value: actual" in failure


def test_equal_snapshot_has_no_failure(tmp_path: Path):
    suite = write_snapshot_file(
        tmp_path,
        {"case": {"is_error": False, "kind": "text", "value": "same"}},
    )

    session = SnapshotSession.open(suite, update=False)

    assert session.evaluate("case", text_outcome("same")) == []


@pytest.mark.parametrize(
    ("expected", "outcome"),
    [
        (
            {"is_error": False, "kind": "text", "value": "same"},
            text_outcome("same", is_error=True),
        ),
        (
            {"is_error": False, "kind": "text", "value": '{"ok": true}'},
            CallOutcome(False, '{"ok": true}', {"ok": True}, 42),
        ),
    ],
)
def test_error_state_and_kind_changes_are_mismatches(tmp_path: Path, expected, outcome):
    suite = write_snapshot_file(tmp_path, {"case": expected})

    failure = SnapshotSession.open(suite, update=False).evaluate("case", outcome)

    assert len(failure) == 1
    assert failure[0].startswith("snapshot: mismatch for 'case'")


def test_text_comparison_is_exact_for_whitespace_unicode_and_crlf(tmp_path: Path):
    value = "héllo\r\n  world\n"
    suite = write_snapshot_file(
        tmp_path,
        {"case": {"is_error": False, "kind": "text", "value": value}},
    )
    session = SnapshotSession.open(suite, update=False)

    assert session.evaluate("case", text_outcome(value)) == []
    assert session.evaluate("case", text_outcome(value.replace("  ", " ")))


@pytest.mark.parametrize("structured", [{"value": float("nan")}, {"value": {1, 2}}])
def test_rejects_non_json_compatible_structured_content(structured):
    with pytest.raises(SnapshotError, match="not JSON-compatible"):
        snapshot_entry(CallOutcome(False, "", structured, 42))


def test_snapshot_changes_add_component_counts():
    assert SnapshotChanges(added=1, unchanged=2) + SnapshotChanges(
        updated=3,
        removed=4,
    ) == SnapshotChanges(added=1, updated=3, unchanged=2, removed=4)


def test_filtered_finalize_updates_selected_and_preserves_other_entries(tmp_path: Path):
    suite = write_snapshot_file(
        tmp_path,
        {
            "selected": {"is_error": False, "kind": "text", "value": "old"},
            "unselected": {"is_error": False, "kind": "text", "value": "old"},
        },
    )
    session = SnapshotSession.open(suite, update=True)
    session.evaluate("selected", text_outcome("new"))

    changes = session.finalize(["selected", "unselected"], prune=False)
    data = yaml.safe_load((tmp_path / "suite.snap.yaml").read_text(encoding="utf-8"))

    assert changes == SnapshotChanges(updated=1)
    assert {name: entry["value"] for name, entry in data["snapshots"].items()} == {
        "selected": "new",
        "unselected": "old",
    }


def test_complete_finalize_prunes_stale_entries_and_deletes_empty_file(tmp_path: Path):
    suite = write_snapshot_file(
        tmp_path,
        {
            "keep": {"is_error": False, "kind": "text", "value": "same"},
            "stale": {"is_error": False, "kind": "text", "value": "old"},
        },
    )
    sidecar = tmp_path / "suite.snap.yaml"
    session = SnapshotSession.open(suite, update=True)
    session.evaluate("keep", text_outcome("same"))

    assert session.finalize(["keep"], prune=True) == SnapshotChanges(
        unchanged=1,
        removed=1,
    )
    assert list(yaml.safe_load(sidecar.read_text(encoding="utf-8"))["snapshots"]) == [
        "keep"
    ]

    emptying = SnapshotSession.open(suite, update=True)
    assert emptying.finalize([], prune=True) == SnapshotChanges(removed=1)
    assert sidecar.exists() is False


def test_replace_failure_preserves_original_and_removes_temporary_file(
    tmp_path: Path,
    monkeypatch,
):
    suite = write_snapshot_file(
        tmp_path,
        {"case": {"is_error": False, "kind": "text", "value": "old"}},
    )
    sidecar = tmp_path / "suite.snap.yaml"
    original = sidecar.read_text(encoding="utf-8")
    session = SnapshotSession.open(suite, update=True)
    session.evaluate("case", text_outcome("new"))

    def raising_replace(source, destination):
        raise OSError("replace denied")

    monkeypatch.setattr("mcp_rig.snapshots.os.replace", raising_replace)

    with pytest.raises(SnapshotError, match="could not write"):
        session.finalize(["case"], prune=True)

    assert sidecar.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".*.tmp")) == []


def test_ordinary_mode_never_writes_snapshot_files(tmp_path: Path):
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite", encoding="utf-8")
    session = SnapshotSession.open(suite, update=False)

    assert session.evaluate("case", text_outcome("actual"))
    assert session.finalize(["case"], prune=True) == SnapshotChanges()
    assert (tmp_path / "suite.snap.yaml").exists() is False


def test_missing_update_file_is_created_only_when_finalized(tmp_path: Path):
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite", encoding="utf-8")
    sidecar = tmp_path / "suite.snap.yaml"
    session = SnapshotSession.open(suite, update=True)

    assert session.evaluate("case", text_outcome("actual")) == []
    assert sidecar.exists() is False
    assert session.finalize(["case"], prune=True) == SnapshotChanges(added=1)
    assert sidecar.exists()


def test_finalize_counts_changes_and_writes_declaration_order(tmp_path: Path):
    suite = write_snapshot_file(
        tmp_path,
        {
            "a": {"is_error": False, "kind": "text", "value": "same"},
            "b": {"is_error": False, "kind": "text", "value": "old"},
        },
    )
    session = SnapshotSession.open(suite, update=True)
    session.evaluate("b", text_outcome("new"))
    session.evaluate("a", text_outcome("same"))
    session.evaluate("c", text_outcome("added"))

    changes = session.finalize(["c", "a", "b"], prune=True)
    snapshots = yaml.safe_load(
        (tmp_path / "suite.snap.yaml").read_text(encoding="utf-8")
    )["snapshots"]

    assert changes == SnapshotChanges(added=1, updated=1, unchanged=1)
    assert list(snapshots) == ["c", "a", "b"]


@pytest.mark.parametrize(
    "body",
    [
        "version: true\nsnapshots: {}\n",
        "version: 1\nsnapshots: {}\nunknown: value\n",
        "version: 1\nsnapshots:\n  case:\n    is_error: false\n    kind: text\n    value: ok\n    unknown: value\n",
    ],
)
def test_rejects_non_integer_version_and_unknown_schema_fields(tmp_path: Path, body):
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite", encoding="utf-8")
    (tmp_path / "suite.snap.yaml").write_text(body, encoding="utf-8")

    with pytest.raises(SnapshotError):
        SnapshotSession.open(suite, update=False)


def test_unicode_and_crlf_text_round_trip_through_persistence(tmp_path: Path):
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite", encoding="utf-8")
    value = "héllo\r\n  world\n"
    updating = SnapshotSession.open(suite, update=True)
    updating.evaluate("case", text_outcome(value))

    assert updating.finalize(["case"], prune=True) == SnapshotChanges(added=1)
    checking = SnapshotSession.open(suite, update=False)
    assert checking.evaluate("case", text_outcome(value)) == []
