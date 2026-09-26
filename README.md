# MCP Rig

Deterministic, CI-friendly testing for Model Context Protocol servers.

MCP Rig currently launches local MCP servers over stdio and runs declarative
tool suites in YAML.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run a suite

```bash
.venv/bin/mcp-rig run examples/fixture.yaml
.venv/bin/mcp-rig run examples/fixture.yaml --junit results.xml
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

This release supports local stdio servers and tools only. Protocol checks and
PyPI publication arrive in later increments.
