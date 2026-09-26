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
```

Each case expects a successful tool call unless it declares
`is_error: true`. Supported expectations are:

- `contains` / `not_contains`: require or forbid one string or a list of strings.
- `matches`: search response text with a Python regular expression.
- `max_latency_ms`: enforce an inclusive response-time limit.
- `json_path`: compare exact values through dotted mapping keys and numeric list indexes.
- `schema`: validate structured results with JSON Schema Draft 2020-12.

JSON checks prefer MCP structured content and otherwise parse response text as
JSON. Invalid expectation configuration exits with code `2` before the server
starts. Add `--server-logs` to expose the MCP server's stderr while diagnosing
startup or tool behavior.

This release supports local stdio servers and tools only. Timeout handling,
JUnit output, protocol checks, and PyPI publication arrive in later increments.
