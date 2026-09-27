# MCP Rig

Deterministic, CI-friendly testing for Model Context Protocol servers.

MCP Rig currently launches local MCP servers over stdio and runs declarative
tool suites in YAML.

## Installation

Install MCP Rig as an isolated command-line tool with
[pipx](https://pipx.pypa.io/):

```bash
pipx install mcp-rig
```

Or install it into the active Python environment with pip:

```bash
pip install mcp-rig
```

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
source .venv/bin/activate
```

## Run a suite

```bash
mcp-rig run examples/fixture.yaml
mcp-rig run examples/fixture.yaml --junit results.xml
```

Each case expects a successful tool call unless it declares
`is_error: true`. Supported expectations are:

- `contains` / `not_contains`: require or forbid one string or a list of strings.
- `matches`: search response text with a Python regular expression.
- `max_latency_ms`: enforce an inclusive response-time limit.
- `json_path`: compare exact values through dotted mapping keys and numeric list indexes.
- `schema`: validate structured results with JSON Schema Draft 2020-12;
  document-local `#...` references are supported, while external references
  are rejected to keep evaluation offline.

JSON checks prefer MCP structured content and otherwise parse response text as
JSON. Each case may set a positive, finite `timeout_s`; the default is 30
seconds. A timeout is an infrastructure error, aborts further calls on the
shared session, and marks later cases as skipped.

Terminal and JUnit reports distinguish four states:

- passed: the call completed and every expectation matched;
- failed: the call completed but one or more expectations did not match;
- error: MCP Rig could not execute the call or suite reliably; and
- skipped: the case was not started after an infrastructure error.

`--junit PATH` writes CI-readable XML without creating missing parent
directories. Invalid configuration exits before the server starts and does not
write a JUnit report. Exit codes are `0` for success, `1` for assertion
failures only, and `2` for configuration or infrastructure failures. Add
`--server-logs` to expose the MCP server's stderr while diagnosing startup or
tool behavior.

## Check a server without a suite

Run protocol checks and inspect tool-definition quality without writing YAML:

```bash
mcp-rig check "python path/to/server.py"
```

The command verifies that the server lists tools, returns an MCP tool error for
an unknown tool, and remains responsive after the negative call. It also warns
about missing or short descriptions, invalid input schemas, undocumented
parameters, and tool descriptions that are likely to be confused with each
other.

Lint warnings are advisory by default. Use `--strict` to make them fail CI:

```bash
mcp-rig check "python path/to/server.py" --strict
```

`--probe-invalid-args` calls every tool that declares required parameters with
an empty argument object and checks that the call is rejected. Use this option
only with development or test servers: a server that does not enforce its
declared schema could execute the tool body.

```bash
mcp-rig check "python path/to/server.py" --probe-invalid-args
```

Server stderr is hidden by default. Add `--server-logs` while diagnosing the
server:

```bash
mcp-rig check "python path/to/server.py" --server-logs
```

For `check`, exit code `0` means all protocol checks passed, `1` means a
protocol check failed or strict lint found warnings, and `2` means the command,
server process, connection, or teardown failed.

This release supports local stdio servers and tools only.

Repository CI tests Python 3.11 through 3.13 and validates both wheel and
source distributions without publishing them.
