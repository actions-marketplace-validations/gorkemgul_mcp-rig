# MCP Rig agent notes

MCP Rig launches MCP servers over stdio, calls tools, and verifies behavior.

## Commands

- Setup: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- Test: `.venv/bin/python -m pytest -q`
- Lint: `.venv/bin/ruff check src tests`

## Rules

- Follow the approved design in `docs/superpowers/specs/` and the active phase plan in `docs/superpowers/plans/`.
- Implement only the active phase; do not start the next phase automatically.
- Write a failing test before production behavior.
- Use MCP Python SDK 2.x public APIs and the first-class `Client`.
- Keep runtime dependencies limited to `mcp`, `pyyaml`, and `jsonschema`.
- Preserve exit-code semantics from the design when the CLI is introduced.
