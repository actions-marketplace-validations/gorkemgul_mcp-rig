import os
from pathlib import Path

from mcp_rig.discovery import discover_suites


def test_discovers_yaml_recursively_in_canonical_sorted_order(tmp_path):
    first = tmp_path / "a.yml"
    second = tmp_path / "nested" / "b.yaml"
    ignored = tmp_path / "nested" / "notes.txt"
    second.parent.mkdir()
    first.write_text("suite", encoding="utf-8")
    second.write_text("suite", encoding="utf-8")
    ignored.write_text("not a suite", encoding="utf-8")

    result = discover_suites([tmp_path])

    assert result.paths == [first.resolve(), second.resolve()]
    assert result.errors == []


def test_ignores_snapshot_sidecars_but_rejects_explicit_sidecar_target(tmp_path):
    suite = tmp_path / "suite.yaml"
    sidecar = tmp_path / "suite.snap.yaml"
    suite.write_text("suite", encoding="utf-8")
    sidecar.write_text("version: 1\nsnapshots: {}\n", encoding="utf-8")

    discovered = discover_suites([tmp_path])
    explicit = discover_suites([sidecar])

    assert discovered.paths == [suite.resolve()]
    assert discovered.errors == []
    assert explicit.paths == []
    assert len(explicit.errors) == 1
    assert "snapshot sidecar" in explicit.errors[0].message


def test_deduplicates_relative_absolute_directory_and_symlink_targets(
    tmp_path, monkeypatch
):
    suite = tmp_path / "suite.yaml"
    alias = tmp_path / "alias.yml"
    suite.write_text("suite", encoding="utf-8")
    alias.symlink_to(suite)
    monkeypatch.chdir(tmp_path)

    result = discover_suites(
        [Path("suite.yaml"), suite.resolve(), tmp_path, alias]
    )

    assert result.paths == [suite.resolve()]
    assert result.errors == []


def test_keeps_valid_paths_while_reporting_missing_unsupported_and_empty_targets(
    tmp_path,
):
    valid = tmp_path / "valid.yaml"
    missing = tmp_path / "missing.yaml"
    unsupported = tmp_path / "notes.txt"
    empty = tmp_path / "empty"
    valid.write_text("suite", encoding="utf-8")
    unsupported.write_text("notes", encoding="utf-8")
    empty.mkdir()

    result = discover_suites([missing, valid, unsupported, empty])

    assert result.paths == [valid.resolve()]
    assert [(error.target, error.exception_type) for error in result.errors] == [
        (missing, "FileNotFoundError"),
        (unsupported, "ValueError"),
        (empty, "ValueError"),
    ]
    assert "does not exist" in result.errors[0].message
    assert "must be a .yaml or .yml file" in result.errors[1].message
    assert "contains no .yaml or .yml suite files" in result.errors[2].message


def test_keeps_other_targets_when_directory_traversal_fails(tmp_path, monkeypatch):
    valid = tmp_path / "valid.yaml"
    blocked = tmp_path / "blocked"
    valid.write_text("suite", encoding="utf-8")
    blocked.mkdir()
    real_walk = os.walk

    def failing_walk(top, *args, **kwargs):
        if Path(top) == blocked:
            error = PermissionError(13, "permission denied", str(blocked))
            kwargs["onerror"](error)
            return iter(())
        return real_walk(top, *args, **kwargs)

    monkeypatch.setattr("mcp_rig.discovery.os.walk", failing_walk)

    result = discover_suites([blocked, valid])

    assert result.paths == [valid.resolve()]
    assert len(result.errors) == 1
    assert result.errors[0].target == blocked
    assert result.errors[0].exception_type == "PermissionError"
    assert "permission denied" in result.errors[0].message


def test_keeps_other_targets_when_target_metadata_access_fails(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked.yaml"
    valid = tmp_path / "valid.yaml"
    blocked.write_text("suite", encoding="utf-8")
    valid.write_text("suite", encoding="utf-8")
    real_is_file = Path.is_file

    def failing_is_file(path):
        if path == blocked:
            raise PermissionError(13, "permission denied", str(blocked))
        return real_is_file(path)

    monkeypatch.setattr(Path, "is_file", failing_is_file)

    result = discover_suites([blocked, valid])

    assert result.paths == [valid.resolve()]
    assert len(result.errors) == 1
    assert result.errors[0].target == blocked
    assert result.errors[0].exception_type == "PermissionError"
    assert "permission denied" in result.errors[0].message
