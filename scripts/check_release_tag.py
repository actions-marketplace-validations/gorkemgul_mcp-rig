from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path


def expected_tag(pyproject_path: Path) -> str:
    with pyproject_path.open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]

    version = project["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("project version must be a non-empty string")
    return f"v{version}"


def validate_release_tag(tag: str, pyproject_path: Path) -> None:
    expected = expected_tag(pyproject_path)
    if tag != expected:
        raise ValueError(f"release tag mismatch: expected {expected}, received {tag}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a release tag against pyproject.toml")
    parser.add_argument("tag", help="GitHub Release tag to validate")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args(argv)

    try:
        validate_release_tag(args.tag, args.pyproject)
    except (KeyError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"release tag accepted: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
