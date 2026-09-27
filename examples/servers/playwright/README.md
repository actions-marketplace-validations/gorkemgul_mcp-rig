# Playwright MCP

This suite starts the official Playwright MCP server in headless, isolated mode, opens
`https://example.com`, and verifies the accessible page snapshot.

Requirements:

- Node.js and `npx`
- Network access for the pinned npm package, browser binary, and the example page

Install the browser version used by the pinned MCP package once:

```bash
npx -y playwright@1.64.0-alpha-1789764292000 install firefox
```

Run it from the repository root:

```bash
mcp-rig run examples/servers/playwright/suite.yaml
```

The MCP server and browser installer versions are pinned together. Review upstream release
notes, update both versions when necessary, and run the suite before committing an upgrade.
