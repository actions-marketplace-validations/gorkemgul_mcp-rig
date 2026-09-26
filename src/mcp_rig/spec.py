"""Load and validate MCP Rig YAML suites."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mcp_rig.client import ServerSpec

KNOWN_EXPECT_KEYS = {"is_error", "contains"}


class SpecError(ValueError):
    """Raised when a suite file cannot be loaded as valid configuration."""


@dataclass(frozen=True)
class Case:
    name: str
    call: str
    args: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Suite:
    path: Path
    server: ServerSpec
    cases: list[Case]


def load_suite(path: str | Path) -> Suite:
    suite_path = Path(path)
    try:
        text = suite_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"{suite_path}: could not read suite: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"{suite_path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{suite_path}: top level must be a mapping")

    server = _parse_server(data.get("server"), suite_path)
    raw_cases = data.get("tests")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SpecError(f"{suite_path}: 'tests' must be a non-empty list")
    cases = [_parse_case(raw, index, suite_path) for index, raw in enumerate(raw_cases)]
    return Suite(path=suite_path, server=server, cases=cases)


def _parse_server(raw: Any, path: Path) -> ServerSpec:
    if isinstance(raw, str) and raw.strip():
        try:
            spec = ServerSpec.from_command_line(raw)
        except ValueError as exc:
            raise SpecError(f"{path}: invalid 'server': {exc}") from exc
        if not spec.command:
            raise SpecError(f"{path}: invalid 'server': server command is empty")
    elif isinstance(raw, dict):
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            raise SpecError(f"{path}: 'server.command' must be a non-empty string")
        args = raw.get("args", [])
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
            raise SpecError(f"{path}: 'server.args' must be a list of strings")
        env = raw.get("env")
        if env is not None and (
            not isinstance(env, dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items())
        ):
            raise SpecError(f"{path}: 'server.env' must map strings to strings")
        cwd = raw.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise SpecError(f"{path}: 'server.cwd' must be a string")
        try:
            spec = ServerSpec.from_command_line(command)
        except ValueError as exc:
            raise SpecError(f"{path}: invalid 'server.command': {exc}") from exc
        spec.args.extend(args)
        spec.env = env
        spec.cwd = cwd
    else:
        raise SpecError(f"{path}: 'server' must be a command string or mapping")

    base = path.parent.resolve()
    if spec.cwd is None:
        spec.cwd = str(base)
    else:
        cwd_path = Path(spec.cwd)
        spec.cwd = str(cwd_path if cwd_path.is_absolute() else (base / cwd_path).resolve())
    return spec


def _parse_case(raw: Any, index: int, path: Path) -> Case:
    where = f"{path}: tests[{index}]"
    if not isinstance(raw, dict):
        raise SpecError(f"{where} must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SpecError(f"{where}: 'name' must be a non-empty string")
    call = raw.get("call")
    if not isinstance(call, str) or not call.strip():
        raise SpecError(f"{where} ({name}): 'call' must be a non-empty string")
    args = raw.get("args", {})
    if not isinstance(args, dict):
        raise SpecError(f"{where} ({name}): 'args' must be a mapping")
    expect = raw.get("expect", {})
    if not isinstance(expect, dict):
        raise SpecError(f"{where} ({name}): 'expect' must be a mapping")
    unknown = set(expect) - KNOWN_EXPECT_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise SpecError(f"{where} ({name}): unknown expect keys: {names}")
    if "is_error" in expect and not isinstance(expect["is_error"], bool):
        raise SpecError(f"{where} ({name}): 'is_error' must be a boolean")
    if "contains" in expect:
        contains = expect["contains"]
        valid = isinstance(contains, str) or (
            isinstance(contains, list)
            and bool(contains)
            and all(isinstance(value, str) for value in contains)
        )
        if not valid:
            raise SpecError(f"{where} ({name}): 'contains' must be a string or non-empty list of strings")
    return Case(name=name, call=call, args=args, expect=expect)
