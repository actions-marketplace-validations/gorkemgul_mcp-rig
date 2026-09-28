from pathlib import Path

import pytest

from mcp_rig.snapshots import SnapshotError, snapshot_path


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
