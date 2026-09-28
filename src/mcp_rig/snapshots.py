"""Load, compare, and update MCP Rig snapshot sidecars."""

from __future__ import annotations

import difflib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from mcp_rig.client import CallOutcome

SNAPSHOT_SUFFIX = ".snap.yaml"
SUITE_SUFFIXES = {".yaml", ".yml"}


class SnapshotError(ValueError):
    """Raised when snapshot configuration or storage is invalid."""


class SnapshotKind(StrEnum):
    STRUCTURED = "structured"
    TEXT = "text"


@dataclass(frozen=True)
class SnapshotEntry:
    is_error: bool
    kind: SnapshotKind
    value: Any


@dataclass(frozen=True)
class SnapshotChanges:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0

    def __add__(self, other: SnapshotChanges) -> SnapshotChanges:
        return SnapshotChanges(
            added=self.added + other.added,
            updated=self.updated + other.updated,
            unchanged=self.unchanged + other.unchanged,
            removed=self.removed + other.removed,
        )


class SnapshotSession:
    """Compare outcomes with one suite's snapshot sidecar."""

    def __init__(
        self,
        path: Path,
        entries: dict[str, SnapshotEntry],
        *,
        update: bool,
    ):
        self._path = path
        self._entries = entries
        self._update = update
        self._observed: dict[str, SnapshotEntry] = {}

    @classmethod
    def open(cls, suite_path: Path, *, update: bool) -> SnapshotSession:
        path = snapshot_path(suite_path)
        return cls(path, _load_entries(path), update=update)

    def evaluate(self, case_name: str, outcome: CallOutcome) -> list[str]:
        actual = snapshot_entry(outcome)
        if self._update:
            self._observed[case_name] = actual
            return []

        expected = self._entries.get(case_name)
        if expected is None:
            return [f"snapshot: missing entry for {case_name!r}"]
        if expected == actual:
            return []
        return [
            f"snapshot: mismatch for {case_name!r}\n{_entry_diff(expected, actual)}"
        ]

    def finalize(
        self,
        declared_names: Sequence[str],
        *,
        prune: bool,
    ) -> SnapshotChanges:
        if not self._update:
            return SnapshotChanges()

        added = sum(name not in self._entries for name in self._observed)
        updated = sum(
            name in self._entries and self._entries[name] != entry
            for name, entry in self._observed.items()
        )
        unchanged = sum(
            name in self._entries and self._entries[name] == entry
            for name, entry in self._observed.items()
        )
        declared = list(dict.fromkeys(declared_names))
        declared_set = set(declared)
        removed = (
            sum(name not in declared_set for name in self._entries)
            if prune
            else 0
        )
        changes = SnapshotChanges(added, updated, unchanged, removed)

        merged = {**self._entries, **self._observed}
        ordered: dict[str, SnapshotEntry] = {}
        for name in declared:
            if name in merged:
                ordered[name] = merged[name]
        if not prune:
            for name, entry in merged.items():
                if name not in ordered:
                    ordered[name] = entry

        if not ordered:
            if self._path.exists():
                try:
                    self._path.unlink()
                except OSError as exc:
                    raise SnapshotError(
                        f"{self._path}: could not delete snapshot file: {exc}"
                    ) from exc
            return changes
        if added == 0 and updated == 0 and removed == 0:
            return changes
        _write_entries(self._path, ordered)
        return changes


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


def snapshot_entry(outcome: CallOutcome) -> SnapshotEntry:
    if outcome.structured is not None:
        value = _canonical_json(outcome.structured)
        kind = SnapshotKind.STRUCTURED
    else:
        value = outcome.text
        kind = SnapshotKind.TEXT
    return SnapshotEntry(is_error=outcome.is_error, kind=kind, value=value)


def _load_entries(path: Path) -> dict[str, SnapshotEntry]:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SnapshotError(f"{path}: could not read snapshot file: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"version", "snapshots"}:
        raise SnapshotError(f"{path}: snapshot file must contain only 'version' and 'snapshots'")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise SnapshotError(f"{path}: 'version' must be the integer 1")
    snapshots = raw["snapshots"]
    if not isinstance(snapshots, dict):
        raise SnapshotError(f"{path}: 'snapshots' must be a mapping")
    entries: dict[str, SnapshotEntry] = {}
    for name, entry in snapshots.items():
        if not isinstance(name, str) or not name:
            raise SnapshotError(f"{path}: snapshot names must be non-empty strings")
        entries[name] = _parse_entry(path, name, entry)
    return entries


def _parse_entry(path: Path, name: str, raw: Any) -> SnapshotEntry:
    where = f"{path}: snapshots[{name!r}]"
    if not isinstance(raw, dict) or set(raw) != {"is_error", "kind", "value"}:
        raise SnapshotError(f"{where} must contain only 'is_error', 'kind', and 'value'")
    if not isinstance(raw["is_error"], bool):
        raise SnapshotError(f"{where}: 'is_error' must be a boolean")
    try:
        kind = SnapshotKind(raw["kind"])
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"{where}: 'kind' must be 'structured' or 'text'") from exc
    value = raw["value"]
    if kind is SnapshotKind.TEXT:
        if not isinstance(value, str):
            raise SnapshotError(f"{where}: text 'value' must be a string")
    else:
        value = _canonical_json(value)
    return SnapshotEntry(is_error=raw["is_error"], kind=kind, value=value)


def _canonical_json(value: Any) -> Any:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
        )
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"structured result is not JSON-compatible: {exc}") from exc


def _entry_data(entry: SnapshotEntry) -> dict[str, Any]:
    return {
        "is_error": entry.is_error,
        "kind": entry.kind.value,
        "value": entry.value,
    }


def _entry_diff(expected: SnapshotEntry, actual: SnapshotEntry) -> str:
    expected_yaml = yaml.safe_dump(
        {"snapshot": _entry_data(expected)},
        sort_keys=False,
        allow_unicode=True,
    ).splitlines()
    actual_yaml = yaml.safe_dump(
        {"snapshot": _entry_data(actual)},
        sort_keys=False,
        allow_unicode=True,
    ).splitlines()
    return "\n".join(
        difflib.unified_diff(
            expected_yaml,
            actual_yaml,
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )


def _write_entries(path: Path, entries: dict[str, SnapshotEntry]) -> None:
    data = {
        "version": 1,
        "snapshots": {name: _entry_data(entry) for name, entry in entries.items()},
    }
    rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise SnapshotError(f"{path}: could not write snapshot file: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
