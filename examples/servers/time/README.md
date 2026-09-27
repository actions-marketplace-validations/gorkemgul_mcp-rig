# Time MCP Server

This suite starts the official Time MCP server and checks deterministic timezone conversions.
It avoids `get_current_time` because its output changes on every run.

Requirements:

- `uv` and `uvx`
- Network access for the pinned Python package

Run it from the repository root:

```bash
mcp-rig run examples/servers/time/suite.yaml
```

The server package is pinned in `suite.yaml`. Review upstream release notes and run the suite
before updating that version.
