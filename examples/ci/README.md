# GitHub Actions

Install MCP Rig, run every suite recursively, and upload JUnit even when tests
fail:

```yaml
name: MCP server tests

on: [push, pull_request]

jobs:
  test-mcp-server:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install mcp-rig
      - run: mcp-rig check "python -m my_mcp_server" --strict
      - run: mcp-rig run tests/mcp/ --junit mcp-rig-results.xml
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: mcp-rig-results
          path: mcp-rig-results.xml
```

Install your server package before the `check` step when it is not part of the
same Python project. Commit snapshot sidecars beside their suites; do not use
`--update-snapshots` in CI.
