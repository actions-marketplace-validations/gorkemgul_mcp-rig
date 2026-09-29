# Examples

The examples in this directory are ready-to-run MCP Rig suites.

- [`fixture.yaml`](fixture.yaml) tests the repository's deterministic local fixture server.
- [`feature-tour`](feature-tour/) exercises every suite feature and CLI workflow locally.
- [`custom-server-template`](custom-server-template/) is a copyable starting point for your server.
- [`ci`](ci/) shows a complete GitHub Actions integration.
- [`servers/playwright`](servers/playwright/) tests browser navigation with Playwright MCP.
- [`servers/server-everything`](servers/server-everything/) tests the MCP reference server.
- [`servers/time`](servers/time/) tests timezone conversion with the Time MCP server.

The real-world server examples pin their package versions so that a passing suite does not
silently change when an upstream package publishes a new release. They make only safe,
read-only calls and require network access when their package runner downloads dependencies.

Repository CI validates every suite as part of the Python test suite. A separate scheduled
workflow runs the external servers weekly, and it can also be started manually from GitHub
Actions.
