"""Load and validate MCP Rig YAML suites."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from mcp_rig.client import ServerSpec
from mcp_rig.selection import validate_tag

KNOWN_EXPECT_KEYS = {
    "is_error",
    "contains",
    "not_contains",
    "matches",
    "max_latency_ms",
    "json_path",
    "schema",
}
_MISSING = object()


class SpecError(ValueError):
    """Raised when a suite file cannot be loaded as valid configuration."""


@dataclass(frozen=True)
class Case:
    name: str
    call: str
    args: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 30.0
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Suite:
    path: Path
    server: ServerSpec
    cases: list[Case]
    tags: frozenset[str] = field(default_factory=frozenset)


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
    tags = _parse_tags(data.get("tags", _MISSING), f"{suite_path}")
    return Suite(path=suite_path, server=server, cases=cases, tags=tags)


def _parse_server(raw: Any, path: Path) -> ServerSpec:
    if isinstance(raw, str) and raw.strip():
        try:
            spec = ServerSpec.from_command_line(raw)
        except ValueError as exc:
            raise SpecError(f"{path}: invalid 'server': {exc}") from exc
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

    if not spec.command:
        raise SpecError(f"{path}: invalid 'server': server command is empty")

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
    timeout_s = raw.get("timeout_s", 30.0)
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or not math.isfinite(timeout_s)
        or timeout_s <= 0
    ):
        raise SpecError(f"{where} ({name}): 'timeout_s' must be a positive number")
    unknown = set(expect) - KNOWN_EXPECT_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise SpecError(f"{where} ({name}): unknown expect keys: {names}")
    if "is_error" in expect and not isinstance(expect["is_error"], bool):
        raise SpecError(f"{where} ({name}): 'is_error' must be a boolean")
    if "contains" in expect:
        contains = expect["contains"]
        if not _is_string_or_non_empty_string_list(contains):
            raise SpecError(f"{where} ({name}): 'contains' must be a string or non-empty list of strings")
    if "not_contains" in expect:
        not_contains = expect["not_contains"]
        if not _is_string_or_non_empty_string_list(not_contains):
            raise SpecError(f"{where} ({name}): 'not_contains' must be a string or non-empty list of strings")
    if "matches" in expect:
        matches = expect["matches"]
        if not isinstance(matches, str):
            raise SpecError(f"{where} ({name}): 'matches' must be a string")
        try:
            re.compile(matches)
        except re.error as exc:
            raise SpecError(f"{where} ({name}): invalid 'matches' regular expression: {exc}") from exc
    if "max_latency_ms" in expect:
        limit = expect["max_latency_ms"]
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not math.isfinite(limit)
            or limit <= 0
        ):
            raise SpecError(f"{where} ({name}): 'max_latency_ms' must be a positive number")
    if "json_path" in expect:
        paths = expect["json_path"]
        valid_paths = (
            isinstance(paths, dict)
            and bool(paths)
            and all(isinstance(key, str) and bool(key.strip()) for key in paths)
        )
        if not valid_paths:
            raise SpecError(f"{where} ({name}): 'json_path' must be a non-empty mapping with non-empty string keys")
    if "schema" in expect:
        schema = expect["schema"]
        if not isinstance(schema, dict):
            raise SpecError(f"{where} ({name}): 'schema' must be a mapping")
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            raise SpecError(f"{where} ({name}): invalid 'schema': {exc.message}") from exc
        _validate_schema_references(schema, where, name)
    tags = _parse_tags(raw.get("tags", _MISSING), f"{where} ({name})")
    return Case(
        name=name,
        call=call,
        args=args,
        expect=expect,
        timeout_s=float(timeout_s),
        tags=tags,
    )


def _parse_tags(raw: Any, where: str) -> frozenset[str]:
    if raw is _MISSING:
        return frozenset()
    if not isinstance(raw, list):
        raise SpecError(f"{where}: 'tags' must be a list")
    try:
        return frozenset(validate_tag(value) for value in raw)
    except ValueError as exc:
        raise SpecError(f"{where}: 'tags' values {exc}") from exc


def _is_string_or_non_empty_string_list(value: Any) -> bool:
    return isinstance(value, str) or (
        isinstance(value, list) and bool(value) and all(isinstance(item, str) for item in value)
    )


def _validate_schema_references(schema: dict[str, Any], where: str, name: str) -> None:
    root = Resource.from_contents(schema, default_specification=DRAFT202012)
    root_uri = root.id() or "urn:mcp-rig:inline-schema"
    registry = Registry().with_resource(root_uri, root).crawl()

    def visit(resource: Resource, resolver) -> None:
        resolver = resolver.in_subresource(resource)
        contents = resource.contents
        if isinstance(contents, dict) and "$ref" in contents:
            reference = contents["$ref"]
            if not reference.startswith("#"):
                raise SpecError(f"{where} ({name}): external 'schema' references are not supported")
            try:
                resolver.lookup(reference)
            except Unresolvable as exc:
                raise SpecError(f"{where} ({name}): invalid 'schema' reference: {reference}") from exc
        for child in resource.subresources():
            visit(child, resolver)

    visit(root, registry.resolver(root_uri))
