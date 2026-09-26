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
`is_error: true`. The `contains` expectation accepts one string or a list of
strings. Add `--server-logs` to expose the MCP server's stderr while
diagnosing startup or tool behavior.

This release supports local stdio servers and tools only. Advanced
assertions, JUnit output, protocol checks, and PyPI publication arrive in
later increments.
