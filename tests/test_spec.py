from pathlib import Path

import pytest

from mcp_rig.spec import SpecError, load_suite


def write_suite(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "suite.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_string_server_and_defaults(tmp_path):
    suite = load_suite(
        write_suite(
            tmp_path,
            """
server: python server.py
tests:
  - name: adds
    call: add
    args: {a: 1, b: 2}
    expect: {contains: "3"}
""",
        )
    )

    assert suite.path == tmp_path / "suite.yaml"
    assert suite.server.command == "python"
    assert suite.server.args == ["server.py"]
    assert suite.server.cwd == str(tmp_path.resolve())
    assert suite.cases[0].args == {"a": 1, "b": 2}


def test_loads_mapping_server_and_resolves_relative_cwd(tmp_path):
    suite = load_suite(
        write_suite(
            tmp_path,
            """
server:
  command: python -u
  args: [server.py]
  env: {MODE: test}
  cwd: fixtures
tests:
  - name: pings
    call: ping
""",
        )
    )

    assert suite.server.command == "python"
    assert suite.server.args == ["-u", "server.py"]
    assert suite.server.env == {"MODE": "test"}
    assert suite.server.cwd == str((tmp_path / "fixtures").resolve())
    assert suite.cases[0].args == {}
    assert suite.cases[0].expect == {}


def test_loads_advanced_expectations(tmp_path):
    suite = load_suite(
        write_suite(
            tmp_path,
            r"""
server: python server.py
tests:
  - name: validates user
    call: get_user
    expect:
      not_contains: [password, secret]
      matches: 'user #[0-9]+'
      max_latency_ms: 500.5
      json_path:
        user.name: Ada
        user.roles.0: admin
      schema:
        type: object
        required: [user]
""",
        )
    )

    assert suite.cases[0].expect == {
        "not_contains": ["password", "secret"],
        "matches": r"user #[0-9]+",
        "max_latency_ms": 500.5,
        "json_path": {"user.name": "Ada", "user.roles.0": "admin"},
        "schema": {"type": "object", "required": ["user"]},
    }


def test_loads_schema_with_local_reference(tmp_path):
    suite = load_suite(
        write_suite(
            tmp_path,
            """
server: python server.py
tests:
  - name: validates identifier
    call: get_user
    expect:
      schema:
        $defs:
          identifier: {type: integer}
        $ref: '#/$defs/identifier'
""",
        )
    )

    assert suite.cases[0].expect["schema"]["$ref"] == "#/$defs/identifier"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("- not-a-mapping", "top level must be a mapping"),
        ("tests: []", "'server'"),
        ("server: python server.py", "'tests' must be a non-empty list"),
        ("server: python server.py\ntests: []", "'tests' must be a non-empty list"),
        ("server: python server.py\ntests: [{call: ping}]", "'name'"),
        ("server: python server.py\ntests: [{name: ping}]", "'call'"),
        ("server: python server.py\ntests: [{name: ping, call: ping, args: []}]", "'args'"),
        ("server: python server.py\ntests: [{name: ping, call: ping, expect: {other: true}}]", "unknown expect keys"),
        ("server: python server.py\ntests: [{name: ping, call: ping, expect: {is_error: nope}}]", "'is_error'"),
        ("server: python server.py\ntests: [{name: ping, call: ping, expect: {contains: []}}]", "'contains'"),
        ("server: {command: true}\ntests: [{name: ping, call: ping}]", "server.command"),
        ("server: '\"\"'\ntests: [{name: ping, call: ping}]", "server command is empty"),
        ("server: {command: '\"\"'}\ntests: [{name: ping, call: ping}]", "server command is empty"),
        ("server: {command: python, args: [server.py, 3]}\ntests: [{name: ping, call: ping}]", "server.args"),
        ("server: {command: python, env: {PORT: 3}}\ntests: [{name: ping, call: ping}]", "server.env"),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {not_contains: []}}]",
            "'not_contains' must be a string or non-empty list of strings",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {not_contains: [ok, 3]}}]",
            "'not_contains' must be a string or non-empty list of strings",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {matches: 3}}]",
            "'matches' must be a string",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {matches: '[unclosed'}}]",
            "invalid 'matches' regular expression",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {max_latency_ms: true}}]",
            "'max_latency_ms' must be a positive number",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {max_latency_ms: 0}}]",
            "'max_latency_ms' must be a positive number",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {max_latency_ms: .nan}}]",
            "'max_latency_ms' must be a positive number",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {max_latency_ms: .inf}}]",
            "'max_latency_ms' must be a positive number",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {json_path: {}}}]",
            "'json_path' must be a non-empty mapping with non-empty string keys",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {json_path: {1: value}}}]",
            "'json_path' must be a non-empty mapping with non-empty string keys",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {json_path: {'': value}}}]",
            "'json_path' must be a non-empty mapping with non-empty string keys",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {schema: []}}]",
            "'schema' must be a mapping",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {schema: {type: not-a-json-type}}}]",
            "invalid 'schema'",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {schema: {$ref: '#/$defs/missing'}}}]",
            "invalid 'schema' reference",
        ),
        (
            "server: python server.py\ntests: [{name: ping, call: ping, expect: {schema: {$ref: 'https://example.invalid/schema'}}}]",
            "external 'schema' references are not supported",
        ),
        ("server: [unclosed", "invalid YAML"),
    ],
)
def test_rejects_invalid_suites(tmp_path, body, message):
    with pytest.raises(SpecError, match=message):
        load_suite(write_suite(tmp_path, body))


def test_missing_file_is_a_spec_error(tmp_path):
    with pytest.raises(SpecError, match="could not read"):
        load_suite(tmp_path / "missing.yaml")
