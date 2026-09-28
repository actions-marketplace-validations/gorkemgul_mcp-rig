"""Discover MCP Rig suite files from explicit files and directories."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

SUITE_SUFFIXES = {".yaml", ".yml"}


@dataclass(frozen=True)
class DiscoveryError:
    target: Path
    exception_type: str
    message: str


@dataclass(frozen=True)
class DiscoveryResult:
    paths: list[Path]
    errors: list[DiscoveryError]


def discover_suites(targets: Sequence[str | Path]) -> DiscoveryResult:
    paths: set[Path] = set()
    errors: list[DiscoveryError] = []

    for raw_target in targets:
        target = Path(raw_target)
        try:
            if target.is_file():
                if target.suffix not in SUITE_SUFFIXES:
                    errors.append(_error(target, ValueError("must be a .yaml or .yml file")))
                else:
                    paths.add(target.resolve())
                continue

            if target.is_dir():
                found_in_target = False
                error_count_before = len(errors)

                def onerror(exc: OSError, error_target: Path = target) -> None:
                    errors.append(_error(error_target, exc))

                for root, directories, files in os.walk(
                    target,
                    onerror=onerror,
                    followlinks=False,
                ):
                    directories.sort()
                    for filename in sorted(files):
                        candidate = Path(root) / filename
                        if candidate.suffix in SUITE_SUFFIXES:
                            found_in_target = True
                            paths.add(candidate.resolve())
                if not found_in_target and len(errors) == error_count_before:
                    errors.append(
                        _error(
                            target,
                            ValueError("contains no .yaml or .yml suite files"),
                        )
                    )
                continue

            if not target.exists():
                errors.append(_error(target, FileNotFoundError(f"{target}: does not exist")))
            else:
                errors.append(_error(target, ValueError("must be a .yaml or .yml file or a directory")))
        except OSError as exc:
            errors.append(_error(target, exc))

    return DiscoveryResult(paths=sorted(paths, key=str), errors=errors)


def _error(target: Path, exc: Exception) -> DiscoveryError:
    return DiscoveryError(
        target=target,
        exception_type=type(exc).__name__,
        message=str(exc),
    )
