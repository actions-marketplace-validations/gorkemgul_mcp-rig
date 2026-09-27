# MCP Everything Server

This suite starts the official MCP reference server and exercises two deterministic tools:
echoing text and adding numbers. It does not call the server's long-running, sampling, or
environment-inspection tools.

Requirements:

- Node.js and `npx`
- Network access for the pinned npm package

Run it from the repository root:

```bash
mcp-rig run examples/servers/server-everything/suite.yaml
```

The server package is pinned in `suite.yaml`. Review upstream release notes and run the suite
before updating that version.
