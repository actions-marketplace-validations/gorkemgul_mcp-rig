"""Load, compare, and update MCP Rig snapshot sidecars."""

from __future__ import annotations

from pathlib import Path

SNAPSHOT_SUFFIX = ".snap.yaml"
SUITE_SUFFIXES = {".yaml", ".yml"}


class SnapshotError(ValueError):
    """Raised when snapshot configuration or storage is invalid."""


def is_snapshot_sidecar(path: str | Path) -> bool:
    return Path(path).name.endswith(SNAPSHOT_SUFFIX)


def snapshot_path(suite_path: str | Path) -> Path:
    resolved = Path(suite_path).resolve()
    if resolved.suffix not in SUITE_SUFFIXES or is_snapshot_sidecar(resolved):
        raise SnapshotError(f"{resolved}: snapshot owner must be a .yaml or .yml suite")

    alternate_suffix = ".yml" if resolved.suffix == ".yaml" else ".yaml"
    alternate = resolved.with_suffix(alternate_suffix)
    if alternate.exists():
        raise SnapshotError(
            f"{resolved} and {alternate} would use the same snapshot sidecar"
        )
    return resolved.with_suffix(SNAPSHOT_SUFFIX)
