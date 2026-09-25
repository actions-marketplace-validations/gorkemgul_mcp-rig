# MCP Rig Phase 1: Stdio Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify MCP Rig's package foundation and stdio client boundary so it can start a real MCP subprocess, list its tools, call tools, and normalize successful and tool-error results.

**Architecture:** A controlled `MCPServer` fixture runs as a subprocess over stdio. `mcp_rig.client` wraps the MCP SDK 2.x first-class `Client`, exposing MCP Rig-owned configuration and result types so later phases do not depend on raw SDK models. Phase 1 has no CLI, YAML parser, runner, assertions, reports, or release automation.

**Tech Stack:** Python 3.11+, MCP Python SDK 2.x, Hatchling, pytest with AnyIO, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-25-mcp-rig-design.md`

## Global Constraints

- Product name: MCP Rig.
- PyPI distribution and future CLI command: `mcp-rig`; Python package: `mcp_rig`.
- Python 3.11 or newer.
- MCP Python SDK 2.x, verified against its current public API during Phase 1.
- `argparse` is reserved for the CLI in Phase 2; Phase 1 does not create a CLI placeholder.
- Runtime dependencies remain `mcp>=2.2,<3`, `pyyaml>=6`, and `jsonschema>=4`; no additional runtime dependency may be added without design review.
- Hatchling handles packaging; pytest with AnyIO handles tests; Ruff handles linting.
- Only stdio and tools are in scope. HTTP, SSE, resources, prompts, snapshots, plugins, and parallel execution are out of scope.
- Development is test-first. Every task demonstrates the intended failure before adding the minimal implementation.
- `docs/plans/2026-09-25-mcptest-mvp.md` is reference material, not an API authority.
- Use the SDK 2.x first-class `Client`; do not reproduce the older manual `ClientSession` and `initialize()` nesting from the source plan.

## Review Focus

- Server configuration must reject empty commands, split quoted arguments like a shell, and avoid shared mutable defaults. Task 2 pins all three cases.
- A missing executable must remain an infrastructure exception instead of becoming a successful connection or tool outcome. Task 3 pins this boundary.
- Explicit `env` and `cwd` settings must reach the spawned server without relying on the caller's current directory. Task 3 pins both values through real tool calls.
- A server-reported `ToolError` must become `CallOutcome(is_error=True, ...)`, while a successful call must preserve text, structured content, and positive latency. Task 3 pins both paths.
- Server stderr must be suppressed by default and visible only when explicitly requested. Task 3 pins both modes.

---

## File Structure

Phase 1 creates the following files:

- `pyproject.toml`: package metadata, dependency constraints, and pytest/Ruff configuration.
- `.gitignore`: local environment, build, test, report, and graph-analysis artifacts.
- `LICENSE`: MIT license.
- `README.md`: concise project identity and current Phase 1 status.
- `AGENTS.md`: repository-local development commands and invariants.
- `src/mcp_rig/__init__.py`: package version.
- `src/mcp_rig/client.py`: MCP Rig-owned server configuration, tool metadata, normalized call outcome, probe, and stdio connection context manager.
- `tests/conftest.py`: AnyIO backend selection plus fixture server path and `ServerSpec` fixtures.
- `tests/fixtures/fixture_server.py`: deterministic MCP SDK 2.x stdio server used by integration tests.
- `tests/test_sdk_smoke.py`: direct SDK-to-fixture compatibility test.
- `tests/test_client_models.py`: pure tests for MCP Rig-owned value types.
- `tests/test_client.py`: live stdio integration tests for the public client boundary.

No other production modules are created in Phase 1.

### Task 1: Package Foundation and SDK Fixture Smoke Test

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `src/mcp_rig/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_sdk_smoke.py`
- Create: `tests/fixtures/fixture_server.py`

**Interfaces:**
- Consumes: Python 3.11+ and the MCP Python SDK 2.x public `Client`, `StdioServerParameters`, and `MCPServer` APIs.
- Produces: installable `mcp_rig` package version `0.1.0`, deterministic fixture server path fixture, and a proven SDK 2.x stdio connection.

- [ ] **Step 1: Create package and tooling configuration**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mcp-rig"
version = "0.1.0"
description = "Deterministic, CI-friendly testing for MCP servers"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
dependencies = [
  "mcp>=2.2,<3",
  "pyyaml>=6",
  "jsonschema>=4",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "ruff>=0.6",
]

[tool.hatch.build.targets.wheel]
packages = ["src/mcp_rig"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 120
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
report.xml
graphify-out/
```

Create `LICENSE`:

```text
MIT License

Copyright (c) 2026 MCP Rig contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Create `README.md`:

```markdown
# MCP Rig

Deterministic, CI-friendly testing for Model Context Protocol servers.

MCP Rig is being built in reviewed phases. Phase 1 establishes a tested stdio
client foundation. The `run` and `check` commands arrive in later phases.
```

Create `AGENTS.md`:

```markdown
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
```

Create `src/mcp_rig/__init__.py`:

```python
"""Deterministic, CI-friendly testing for MCP servers."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create the virtual environment and install the editable project**

Run:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Expected: installation completes and `.venv/bin/python -c "import mcp_rig; print(mcp_rig.__version__)"` prints `0.1.0`.

- [ ] **Step 3: Write the direct SDK smoke test before the fixture server exists**

Create `tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fixture_server_path() -> Path:
    return Path(__file__).parent / "fixtures" / "fixture_server.py"
```

Create `tests/test_sdk_smoke.py`:

```python
import sys

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters


@pytest.mark.anyio
async def test_sdk_client_can_list_and_call_fixture_tools(fixture_server_path):
    params = StdioServerParameters(command=sys.executable, args=[str(fixture_server_path)])

    async with Client(params) as client:
        listed = await client.list_tools()
        result = await client.call_tool("add", {"a": 2, "b": 3})

    assert "add" in {tool.name for tool in listed.tools}
    assert result.is_error is False
    assert result.structured_content == {"result": 5}
```

- [ ] **Step 4: Run the smoke test and verify the missing fixture fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_sdk_smoke.py -q
```

Expected: FAIL because `tests/fixtures/fixture_server.py` does not exist and the stdio subprocess cannot start successfully.

- [ ] **Step 5: Add the deterministic MCP fixture server**

Create `tests/fixtures/fixture_server.py`:

```python
"""Deterministic MCP server used by MCP Rig's stdio integration tests."""

import os
import sys

import anyio

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("mcp-rig-fixture")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return their sum."""
    return a + b


@server.tool()
def echo(text: str) -> str:
    """Return the given text unchanged."""
    return text


@server.tool()
def get_user(user_id: int) -> dict:
    """Return a deterministic user or a readable tool error."""
    if user_id != 1:
        raise ToolError(f"user {user_id} not found")
    return {"id": 1, "name": "Ada", "roles": ["admin"]}


@server.tool()
async def slow(seconds: float) -> str:
    """Wait for the requested duration and return done."""
    await anyio.sleep(seconds)
    return "done"


@server.tool()
def get_env(name: str) -> str:
    """Return one environment variable from the server process."""
    return os.environ.get(name, "")


@server.tool()
def working_directory() -> str:
    """Return the server process working directory."""
    return os.getcwd()


@server.tool()
def write_stderr(message: str) -> str:
    """Write a controlled diagnostic to stderr for log-routing tests."""
    print(message, file=sys.stderr, flush=True)
    return "written"


@server.tool()
def undocumented(value: str) -> str:
    return value


if __name__ == "__main__":
    server.run()
```

- [ ] **Step 6: Run the smoke test and lint the foundation**

Run:

```bash
.venv/bin/python -m pytest tests/test_sdk_smoke.py -q
.venv/bin/ruff check src tests
```

Expected: `1 passed` and `All checks passed!`.

- [ ] **Step 7: Commit the package foundation and SDK compatibility proof**

```bash
git add pyproject.toml .gitignore LICENSE README.md AGENTS.md src/mcp_rig/__init__.py tests/conftest.py tests/test_sdk_smoke.py tests/fixtures/fixture_server.py
git commit -m "chore: establish MCP Rig package and SDK fixture"
```

### Task 2: MCP Rig Client Value Types

**Files:**
- Create: `src/mcp_rig/client.py`
- Create: `tests/test_client_models.py`

**Interfaces:**
- Consumes: standard-library `dataclasses`, `json`, and `shlex`.
- Produces:
  - `ServerSpec(command: str, args: list[str] = [], env: dict[str, str] | None = None, cwd: str | None = None)`
  - `ServerSpec.from_command_line(command_line: str) -> ServerSpec`
  - `ToolInfo(name: str, description: str, input_schema: dict[str, Any])`
  - `CallOutcome(is_error: bool, text: str, structured: Any, latency_ms: float)`
  - `CallOutcome.json() -> Any`

- [ ] **Step 1: Write failing value-type tests**

Create `tests/test_client_models.py`:

```python
import pytest

from mcp_rig.client import CallOutcome, ServerSpec


def test_server_spec_splits_a_shell_like_command():
    spec = ServerSpec.from_command_line('python server.py --name "my server"')

    assert spec.command == "python"
    assert spec.args == ["server.py", "--name", "my server"]


def test_server_spec_rejects_an_empty_command():
    with pytest.raises(ValueError, match="server command is empty"):
        ServerSpec.from_command_line("   ")


def test_server_spec_argument_defaults_are_independent():
    first = ServerSpec("python")
    second = ServerSpec("node")

    first.args.append("server.py")

    assert second.args == []


def test_call_outcome_prefers_structured_content():
    outcome = CallOutcome(False, '{"fallback": true}', {"result": 5}, 1.0)

    assert outcome.json() == {"result": 5}


def test_call_outcome_parses_json_text_when_structured_content_is_missing():
    outcome = CallOutcome(False, '{"name": "Ada"}', None, 1.0)

    assert outcome.json() == {"name": "Ada"}


def test_call_outcome_rejects_non_json_text():
    outcome = CallOutcome(False, "plain text", None, 1.0)

    with pytest.raises(ValueError):
        outcome.json()
```

- [ ] **Step 2: Run the model tests and verify the missing module fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_client_models.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'mcp_rig.client'`.

- [ ] **Step 3: Implement the MCP Rig-owned value types**

Create `src/mcp_rig/client.py`:

```python
"""Connect to MCP servers over stdio and normalize tool results."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServerSpec:
    """A local command that launches an MCP server over stdio."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None

    @classmethod
    def from_command_line(cls, command_line: str) -> ServerSpec:
        parts = shlex.split(command_line)
        if not parts:
            raise ValueError("server command is empty")
        return cls(command=parts[0], args=parts[1:])


@dataclass(frozen=True)
class ToolInfo:
    """Tool metadata used by MCP Rig without exposing SDK model types."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class CallOutcome:
    """Normalized result of one MCP tool call."""

    is_error: bool
    text: str
    structured: Any
    latency_ms: float

    def json(self) -> Any:
        if self.structured is not None:
            return self.structured
        return json.loads(self.text)
```

- [ ] **Step 4: Run the value-type tests and full lint**

Run:

```bash
.venv/bin/python -m pytest tests/test_client_models.py -q
.venv/bin/ruff check src tests
```

Expected: `6 passed` and `All checks passed!`.

- [ ] **Step 5: Commit the client value types**

```bash
git add src/mcp_rig/client.py tests/test_client_models.py
git commit -m "feat: define MCP Rig client value types"
```

### Task 3: Live Stdio Client Boundary

**Files:**
- Modify: `src/mcp_rig/client.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_client.py`

**Interfaces:**
- Consumes: `ServerSpec`, MCP SDK `Client`, `StdioServerParameters`, `stdio_client`, and SDK `TextContent` result blocks.
- Produces:
  - `Probe.list_tools() -> list[ToolInfo]`
  - `Probe.call(name: str, args: dict[str, Any] | None = None, timeout_s: float = 30.0) -> CallOutcome`
  - `connect(spec: ServerSpec, show_server_logs: bool = False) -> AsyncContextManager[Probe]`
- Preserves: missing executables, protocol validation failures, connection loss, and timeout exceptions propagate as infrastructure failures for later CLI handling.

- [ ] **Step 1: Add the reusable `fixture_spec` test fixture**

Replace `tests/conftest.py` with:

```python
import sys
from pathlib import Path

import pytest

from mcp_rig.client import ServerSpec


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fixture_server_path() -> Path:
    return Path(__file__).parent / "fixtures" / "fixture_server.py"


@pytest.fixture
def fixture_spec(fixture_server_path: Path) -> ServerSpec:
    return ServerSpec(command=sys.executable, args=[str(fixture_server_path)])
```

- [ ] **Step 2: Write failing live-client tests**

Create `tests/test_client.py`:

```python
import sys
from pathlib import Path

import pytest

from mcp_rig.client import ServerSpec, connect

FIXTURE_TOOLS = {
    "add",
    "echo",
    "get_user",
    "slow",
    "get_env",
    "working_directory",
    "write_stderr",
    "undocumented",
}


@pytest.mark.anyio
async def test_connect_lists_normalized_fixture_tools(fixture_spec):
    async with connect(fixture_spec) as probe:
        tools = await probe.list_tools()

    assert FIXTURE_TOOLS == {tool.name for tool in tools}
    undocumented = next(tool for tool in tools if tool.name == "undocumented")
    assert undocumented.description == ""
    assert undocumented.input_schema["type"] == "object"


@pytest.mark.anyio
async def test_successful_call_preserves_text_structure_and_latency(fixture_spec):
    async with connect(fixture_spec) as probe:
        outcome = await probe.call("add", {"a": 2, "b": 3})

    assert outcome.is_error is False
    assert outcome.text == "5"
    assert outcome.structured == {"result": 5}
    assert outcome.latency_ms > 0


@pytest.mark.anyio
async def test_tool_error_is_a_normalized_outcome(fixture_spec):
    async with connect(fixture_spec) as probe:
        outcome = await probe.call("get_user", {"user_id": 99})

    assert outcome.is_error is True
    assert "user 99 not found" in outcome.text


@pytest.mark.anyio
async def test_explicit_environment_and_working_directory_reach_server(fixture_server_path, tmp_path):
    spec = ServerSpec(
        command=sys.executable,
        args=[str(fixture_server_path)],
        env={"MCP_RIG_TEST_VALUE": "visible"},
        cwd=str(tmp_path),
    )

    async with connect(spec) as probe:
        env_outcome = await probe.call("get_env", {"name": "MCP_RIG_TEST_VALUE"})
        cwd_outcome = await probe.call("working_directory")

    assert env_outcome.text == "visible"
    assert Path(cwd_outcome.text) == tmp_path


@pytest.mark.anyio
async def test_missing_executable_remains_an_infrastructure_error():
    spec = ServerSpec(command="/definitely/missing/mcp-rig-server")

    with pytest.raises(OSError):
        async with connect(spec):
            pass


@pytest.mark.anyio
async def test_omitted_arguments_are_sent_as_an_empty_mapping(fixture_spec):
    async with connect(fixture_spec) as probe:
        outcome = await probe.call("working_directory")

    assert outcome.is_error is False
    assert outcome.text


@pytest.mark.anyio
async def test_server_logs_are_hidden_by_default_and_opt_in(fixture_spec, capsys):
    hidden_message = "mcp-rig-hidden-server-log"
    async with connect(fixture_spec) as probe:
        await probe.call("write_stderr", {"message": hidden_message})

    assert hidden_message not in capsys.readouterr().err

    visible_message = "mcp-rig-visible-server-log"
    async with connect(fixture_spec, show_server_logs=True) as probe:
        await probe.call("write_stderr", {"message": visible_message})

    assert visible_message in capsys.readouterr().err
```

- [ ] **Step 3: Run the integration tests and verify the missing public functions fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_client.py -q
```

Expected: FAIL during collection because `connect` does not exist in `mcp_rig.client`.

- [ ] **Step 4: Implement the stdio probe and connection context manager**

Replace `src/mcp_rig/client.py` with:

```python
"""Connect to MCP servers over stdio and normalize tool results."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent


@dataclass
class ServerSpec:
    """A local command that launches an MCP server over stdio."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None

    @classmethod
    def from_command_line(cls, command_line: str) -> ServerSpec:
        parts = shlex.split(command_line)
        if not parts:
            raise ValueError("server command is empty")
        return cls(command=parts[0], args=parts[1:])


@dataclass(frozen=True)
class ToolInfo:
    """Tool metadata used by MCP Rig without exposing SDK model types."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class CallOutcome:
    """Normalized result of one MCP tool call."""

    is_error: bool
    text: str
    structured: Any
    latency_ms: float

    def json(self) -> Any:
        if self.structured is not None:
            return self.structured
        return json.loads(self.text)


class Probe:
    """MCP Rig's narrow interface over a connected SDK client."""

    def __init__(self, client: Client):
        self._client = client

    async def list_tools(self) -> list[ToolInfo]:
        listed = await self._client.list_tools()
        return [
            ToolInfo(
                name=tool.name,
                description=tool.description or "",
                input_schema=dict(tool.input_schema),
            )
            for tool in listed.tools
        ]

    async def call(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
    ) -> CallOutcome:
        started = time.perf_counter()
        result = await self._client.call_tool(
            name,
            arguments=args or {},
            read_timeout_seconds=timeout_s,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        return CallOutcome(
            is_error=bool(result.is_error),
            text=text,
            structured=result.structured_content,
            latency_ms=latency_ms,
        )


@asynccontextmanager
async def connect(spec: ServerSpec, show_server_logs: bool = False) -> AsyncIterator[Probe]:
    """Start one stdio server and yield an initialized MCP Rig probe."""
    params = StdioServerParameters(
        command=spec.command,
        args=spec.args,
        env=spec.env,
        cwd=spec.cwd,
    )
    log_context = (
        nullcontext(sys.stderr)
        if show_server_logs
        else open(os.devnull, "w", encoding="utf-8")
    )
    with log_context as errlog:
        transport = stdio_client(params, errlog=errlog)
        async with Client(transport) as client:
            yield Probe(client)
```

- [ ] **Step 5: Run focused integration and model tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_client.py tests/test_client_models.py tests/test_sdk_smoke.py -q
```

Expected: `14 passed`.

- [ ] **Step 6: Run the complete Phase 1 verification gate**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: `14 passed` and `All checks passed!`.

Manually verify the public imports:

```bash
.venv/bin/python -c "from mcp_rig.client import CallOutcome, Probe, ServerSpec, ToolInfo, connect; print('phase-1 imports ok')"
```

Expected: `phase-1 imports ok`.

- [ ] **Step 7: Commit the live stdio client boundary**

```bash
git add src/mcp_rig/client.py tests/conftest.py tests/test_client.py
git commit -m "feat: add tested stdio MCP client boundary"
```

## Phase 1 Completion Review

After Task 3, review the complete diff against the Phase 1 section of the design spec. Confirm all of the following before declaring the phase complete:

- The implementation uses `from mcp import Client` and does not manually create or initialize `ClientSession`.
- The fixture is a real stdio subprocess using `from mcp.server import MCPServer`.
- MCP SDK result models do not escape `mcp_rig.client`; later layers receive `ToolInfo` and `CallOutcome`.
- Tool errors remain normal outcomes, while missing executables and connection failures remain exceptions.
- Explicit environment variables and working directories reach the subprocess.
- Server stderr is suppressed by default and can be routed to the caller's stderr with `show_server_logs=True`.
- No Phase 2 modules or CLI placeholders were added.
- The complete pytest and Ruff gates pass from a clean checkout with the editable package installed.

Stop after this review and present the Phase 1 result to the user. Do not begin Phase 2 without explicit approval.
