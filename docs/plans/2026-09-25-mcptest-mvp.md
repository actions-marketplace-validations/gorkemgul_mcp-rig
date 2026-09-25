# mcptest 0.1 Uygulama Planı

> **Codex ile kullanım:** Her gün Codex'e sadece o günün task'ını ver, ör. *"`docs/plans/2026-09-25-mcptest-mvp.md` dosyasındaki Task 3'ü uygula. Adımları sırayla izle, testler geçmeden commit atma."* Adımlar `- [ ]` checkbox'larıyla takip edilir. Her task sonunda diff'i kendin oku, sonra commit'i sen at.

**Hedef:** MCP server'larını otomatik ve CI'da koşabilir şekilde test eden, PyPI'da `mcptest` adıyla yayınlanan bir CLI.

**Mimari:** `mcptest` gerçek bir MCP client'ı gibi davranır. Server'ı stdio üzerinden alt süreç olarak başlatır, resmi Python SDK'nın `ClientSession`'ıyla tool'ları çağırır ve cevapları YAML'daki beklentilerle karşılaştırır. Ayrıca test dosyası gerektirmeyen bir `check` komutu var: protokol kontrolleri ve tool tanımları için lint.

**Teknoloji:** Python ≥3.11, `mcp` 2.x SDK, PyYAML, jsonschema, argparse, pytest + anyio, ruff, hatchling.

## Genel Kısıtlar

- Paket adı: `mcptest` (PyPI'da boş olduğu 2026-09-25'te kontrol edildi). CLI komutu: `mcptest`.
- Python `>=3.11` (`BaseExceptionGroup` builtin olduğu için).
- Bağımlılıklar sadece `mcp>=2.2,<3`, `pyyaml>=6`, `jsonschema>=4`. Yeni runtime bağımlılığı eklenmez.
- **MCP SDK 2.x kullanılıyor, 1.x değil.** Server tarafında `from mcp.server.mcpserver import MCPServer` (eski `FastMCP` 2.x'te yok). Tip alanları snake_case: `is_error`, `structured_content`, `input_schema`, `server_info`. İnternetteki örneklerin çoğu 1.x'e göre, onları kopyalama.
- Çıkış kodları: `0` her şey geçti, `1` test ya da check başarısız, `2` kullanım hatası (bozuk YAML, server başlamadı).
- Kod ve README İngilizce, commit mesajları Conventional Commits formatında (`feat:`, `test:`, `docs:`, `chore:`).
- Her commit öncesi `pytest -q` ve `ruff check src tests` temiz olmalı.

## SDK davranışları (2026-09-25'te `mcp` 2.2.0 ile ölçüldü)

Testler bu davranışlara dayanıyor; SDK güncellenince bir şey kırılırsa ilk bakılacak yer burası:

| Durum | Sonuç |
|---|---|
| Tool `ToolError("msg")` fırlatır | `is_error=True`, text `"Error executing tool X: msg"` |
| Tool başka bir exception fırlatır | `is_error=True`, text `"Error executing tool X"` (**mesaj kaybolur**) |
| Olmayan tool çağrılır | `is_error=True`, text `"Unknown tool: X"` (exception değil) |
| Eksik/yanlış tipte argüman | `is_error=True`, pydantic validation mesajı |
| `int` döndüren tool | text `"5"`, `structured_content={"result": 5}` |
| `dict` döndüren tool | text JSON string, `structured_content=None` |
| Docstring'siz tool | `description == ""` |
| Hatalı çağrılardan sonra | Server ayakta kalır |

## Dosya Yapısı

```
mcptest/
├── pyproject.toml            # paket, bağımlılıklar, pytest ve ruff ayarları
├── AGENTS.md                 # Codex için proje kuralları
├── README.md
├── LICENSE
├── .gitignore
├── .github/workflows/ci.yml  # Gün 5
├── examples/fixture.yaml     # Gün 3, README'deki örnek
├── src/mcptest/
│   ├── __init__.py           # sürüm
│   ├── client.py             # ServerSpec, ToolInfo, CallOutcome, Probe, connect()
│   ├── spec.py               # YAML → Suite/Case, SpecError
│   ├── assertions.py         # check(expect, outcome) -> list[str]
│   ├── runner.py             # run_suite() -> SuiteResult
│   ├── report.py             # render_suite(), render_check()
│   ├── junit.py              # write_junit()
│   ├── checks.py             # run_protocol_checks()
│   ├── lint.py               # lint_tools()
│   └── cli.py                # mcptest run / mcptest check
└── tests/
    ├── conftest.py           # anyio backend, fixture_spec
    ├── fixtures/fixture_server.py  # kasıtlı kusurlu test server'ı
    └── test_*.py             # modül başına bir dosya
```

Her modülün tek bir sorumluluğu var. `assertions`, `lint`, `report` ve `junit` saf fonksiyonlar, server'a ihtiyaç duymadan test edilir. Sadece `client`, `runner`, `checks` ve `cli` testleri fixture server'ı başlatır.

## Takvim

| Gün | Task'lar | Günün sonunda |
|---|---|---|
| 1 | 1, 2 | Server'a bağlanıp tool listesi çekiliyor |
| 2 | 3, 4 | YAML okunuyor, tüm assertion tipleri çalışıyor |
| 3 | 5, 6, 7 | `mcptest run examples/fixture.yaml` uçtan uca çalışıyor |
| 4 | 8, 9, 10 | `mcptest check "python server.py"` çalışıyor |
| 5 | 11, 12 | CI yeşil, README hazır, PyPI'da 0.1.0 |

Her gün 2–4 commit çıkıyor. Bir gün yetişmezse task'ı ertesi güne kaydır, task'ı bölme.

---

## Gün 1

### Task 1: Proje iskeleti ve fixture server

**Dosyalar:**
- Oluştur: `pyproject.toml`, `AGENTS.md`, `README.md`, `LICENSE`, `.gitignore`, `src/mcptest/__init__.py`, `tests/conftest.py`, `tests/fixtures/fixture_server.py`

**Arayüzler:**
- Kullanır: yok
- Üretir: `tests/conftest.py` içinde `fixture_spec` fixture'ı (`ServerSpec` döner, Task 2'de tanımlanıyor) ve `anyio_backend`. `fixture_server.py` şu tool'ları sunar: `add(a:int,b:int)->int`, `echo(text:str)->str`, `get_user(user_id:int)->dict` (sadece id=1 var, diğerlerinde `ToolError("user N not found")`), `slow(seconds:float)->str`, `undocumented(x:str)` (docstring yok), `read_file(path)` ve `get_file(path)` (kasıtlı olarak neredeyse aynı açıklamalar).

- [ ] **Adım 1: Repo ve sanal ortam**

```bash
mkdir -p ~/Projects/mcptest && cd ~/Projects/mcptest
git init -b main
python3 -m venv .venv && source .venv/bin/activate
mkdir -p src/mcptest tests/fixtures examples docs/plans
```

- [ ] **Adım 2: `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mcptest"
version = "0.1.0"
description = "Automated, CI-friendly tests for MCP servers"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
dependencies = ["mcp>=2.2,<3", "pyyaml>=6", "jsonschema>=4"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[project.scripts]
mcptest = "mcptest.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/mcptest"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 120
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- [ ] **Adım 3: `src/mcptest/__init__.py`**

```python
"""Automated, CI-friendly tests for MCP servers."""

__version__ = "0.1.0"
```

- [ ] **Adım 4: `.gitignore`, geçici `README.md` ve `LICENSE`**

```bash
printf '.venv/\n__pycache__/\n*.egg-info/\ndist/\nbuild/\n.pytest_cache/\n.ruff_cache/\nreport.xml\n' > .gitignore
printf '# mcptest\n\nAutomated, CI-friendly tests for MCP servers. Work in progress.\n' > README.md
cat > LICENSE <<EOF
MIT License

Copyright (c) 2026 $(git config user.name)

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
EOF
head -3 LICENSE
```

Beklenen: `MIT License` ve `Copyright (c) 2026 <adın>`. İsim boş çıkarsa `LICENSE`'ı elle düzelt.

- [ ] **Adım 5: `AGENTS.md` (Codex bunu her oturumda okur)**

```markdown
# mcptest — agent notes

CLI that tests MCP servers: starts the server over stdio, calls tools, checks results.

## Commands
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Test: `pytest -q`
- Lint: `ruff check src tests`

## Rules
- The implementation plan lives in `docs/plans/`. Do exactly one task per request, in step order.
- Write the test first, watch it fail, then implement. Never commit with failing tests or lint errors.
- MCP Python SDK is **2.x**: server class is `mcp.server.mcpserver.MCPServer` (not `FastMCP`),
  result/tool fields are snake_case (`is_error`, `structured_content`, `input_schema`).
- Do not add runtime dependencies beyond `mcp`, `pyyaml`, `jsonschema`.
- Tests that need a live server use the `fixture_spec` fixture and `@pytest.mark.anyio`.
- Exit codes: 0 pass, 1 test/check failure, 2 usage error.
```

- [ ] **Adım 6: Fixture server `tests/fixtures/fixture_server.py`**

```python
"""Deliberately imperfect MCP server that mcptest's own tests run against."""

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("fixture")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return their sum."""
    return a + b


@server.tool()
def echo(text: str) -> str:
    """Return the given text unchanged, useful for round-trip checks."""
    return text


@server.tool()
def get_user(user_id: int) -> dict:
    """Look up a user by numeric id and return their profile."""
    if user_id != 1:
        raise ToolError(f"user {user_id} not found")
    return {"id": 1, "name": "Ada", "roles": ["admin"]}


@server.tool()
async def slow(seconds: float) -> str:
    """Sleep for the given number of seconds, then return done."""
    await anyio.sleep(seconds)
    return "done"


@server.tool()
def undocumented(x: str) -> str:
    return x


@server.tool()
def read_file(path: str) -> str:
    """Read a text file from disk and return its contents."""
    return ""


@server.tool()
def get_file(path: str) -> str:
    """Read a text file from the disk and return its content."""
    return ""


if __name__ == "__main__":
    server.run()
```

- [ ] **Adım 7: `tests/conftest.py`**

`mcptest.client` Task 2'de yazılacak. Bu dosya o yüzden şimdilik import hatası verir; bu beklenen bir durum.

```python
import sys
from pathlib import Path

import pytest

from mcptest.client import ServerSpec

FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "fixture_server.py"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fixture_spec() -> ServerSpec:
    return ServerSpec(command=sys.executable, args=[str(FIXTURE_SERVER)])
```

- [ ] **Adım 8: Kurulum ve fixture server'ın çalıştığını doğrula**

```bash
pip install -e ".[dev]"
python -c "import mcptest; print(mcptest.__version__)"
python tests/fixtures/fixture_server.py < /dev/null; echo "exit=$?"
```

Beklenen: `0.1.0`, sonra server stdin kapanınca hatasız çıkar (`exit=0`).

- [ ] **Adım 9: Commit**

```bash
git add .
git commit -m "chore: scaffold mcptest package and fixture MCP server"
```

---

### Task 2: MCP client katmanı

**Dosyalar:**
- Oluştur: `src/mcptest/client.py`
- Test: `tests/test_client.py`

**Arayüzler:**
- Kullanır: Task 1'deki `fixture_spec`, fixture server
- Üretir:
  - `ServerSpec(command: str, args: list[str] = [], env: dict[str, str] | None = None, cwd: str | None = None)` ve `ServerSpec.from_command_line(command_line: str) -> ServerSpec` (boş komutta `ValueError`)
  - `ToolInfo(name: str, description: str, input_schema: dict)`; açıklama yoksa `description == ""`
  - `CallOutcome(is_error: bool, text: str, structured: Any, latency_ms: float)` ve `.json() -> Any` (önce `structured`, yoksa `text`'i JSON parse eder, olmazsa `ValueError`)
  - `Probe.list_tools() -> list[ToolInfo]`, `Probe.call(name, args=None, timeout_s=30.0) -> CallOutcome` (tool hataları exception değil `is_error=True` olarak döner)
  - `connect(spec: ServerSpec, show_server_logs: bool = False)` → `async with connect(spec) as probe:`

- [ ] **Adım 1: Failing testleri yaz `tests/test_client.py`**

```python
import pytest

from mcptest.client import ServerSpec, connect

FIXTURE_TOOLS = {"add", "echo", "get_user", "slow", "undocumented", "read_file", "get_file"}


def test_spec_from_command_line_splits_like_a_shell():
    spec = ServerSpec.from_command_line('python server.py --name "my server"')
    assert spec.command == "python"
    assert spec.args == ["server.py", "--name", "my server"]


def test_spec_from_empty_command_line_is_rejected():
    with pytest.raises(ValueError):
        ServerSpec.from_command_line("   ")


@pytest.mark.anyio
async def test_lists_fixture_tools(fixture_spec):
    async with connect(fixture_spec) as probe:
        tools = await probe.list_tools()
    assert FIXTURE_TOOLS <= {t.name for t in tools}
    undocumented = next(t for t in tools if t.name == "undocumented")
    assert undocumented.description == ""


@pytest.mark.anyio
async def test_successful_call_returns_text_and_latency(fixture_spec):
    async with connect(fixture_spec) as probe:
        out = await probe.call("add", {"a": 2, "b": 3})
    assert out.is_error is False
    assert out.text == "5"
    assert out.latency_ms > 0


@pytest.mark.anyio
async def test_tool_error_is_returned_not_raised(fixture_spec):
    async with connect(fixture_spec) as probe:
        out = await probe.call("get_user", {"user_id": 99})
    assert out.is_error is True
    assert "user 99 not found" in out.text


@pytest.mark.anyio
async def test_json_parses_text_payload(fixture_spec):
    async with connect(fixture_spec) as probe:
        out = await probe.call("get_user", {"user_id": 1})
    assert out.json()["roles"] == ["admin"]
```

- [ ] **Adım 2: Testlerin patladığını gör**

Çalıştır: `pytest tests/test_client.py -q`
Beklenen: `ModuleNotFoundError: No module named 'mcptest.client'` (conftest yüzünden collection hatası).

- [ ] **Adım 3: `src/mcptest/client.py`**

```python
"""Connect to an MCP server over stdio and call its tools."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class ServerSpec:
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


@dataclass
class ToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class CallOutcome:
    is_error: bool
    text: str
    structured: Any
    latency_ms: float

    def json(self) -> Any:
        """Structured content if the server sent it, else the text parsed as JSON.

        Raises ValueError when the text is not JSON.
        """
        if self.structured is not None:
            return self.structured
        return json.loads(self.text)


class Probe:
    """Thin wrapper over an initialized ClientSession."""

    def __init__(self, session: ClientSession):
        self._session = session

    async def list_tools(self) -> list[ToolInfo]:
        result = await self._session.list_tools()
        return [
            ToolInfo(name=t.name, description=t.description or "", input_schema=dict(t.input_schema))
            for t in result.tools
        ]

    async def call(self, name: str, args: dict[str, Any] | None = None, timeout_s: float = 30.0) -> CallOutcome:
        start = time.perf_counter()
        result = await self._session.call_tool(name, arguments=args or {}, read_timeout_seconds=timeout_s)
        latency_ms = (time.perf_counter() - start) * 1000
        content = getattr(result, "content", None) or []
        text = "\n".join(c.text for c in content if getattr(c, "type", None) == "text")
        return CallOutcome(
            is_error=bool(getattr(result, "is_error", False)),
            text=text,
            structured=getattr(result, "structured_content", None),
            latency_ms=latency_ms,
        )


@asynccontextmanager
async def connect(spec: ServerSpec, show_server_logs: bool = False) -> AsyncIterator[Probe]:
    params = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env, cwd=spec.cwd)
    with open(os.devnull, "w") as devnull:
        errlog = sys.stderr if show_server_logs else devnull
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield Probe(session)
```

Neden böyle:
- Server'ın stderr'i varsayılan olarak `/dev/null`'a gidiyor; yoksa her tool hatasında SDK logları rapora karışıyor.
- `getattr` kullanımı bilinçli: SDK 2.x'te `call_tool` bazı durumlarda `CallToolResult` dışında bir tip (`InputRequiredResult`) dönebiliyor.

- [ ] **Adım 4: Testlerin geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `6 passed`, `All checks passed!`

- [ ] **Adım 5: Commit**

```bash
git add src/mcptest/client.py tests/test_client.py
git commit -m "feat: add stdio MCP client wrapper with timed tool calls"
```

---

## Gün 2

### Task 3: YAML test dosyası okuyucu

**Dosyalar:**
- Oluştur: `src/mcptest/spec.py`
- Test: `tests/test_spec.py`

**Arayüzler:**
- Kullanır: `ServerSpec`, `ServerSpec.from_command_line` (Task 2)
- Üretir:
  - `KNOWN_EXPECT_KEYS = {"is_error", "contains", "not_contains", "matches", "max_latency_ms", "json_path", "schema"}`
  - `class SpecError(ValueError)`
  - `Case(name: str, call: str, args: dict = {}, expect: dict = {}, timeout_s: float = 30.0)`
  - `Suite(server: ServerSpec, cases: list[Case])`
  - `load_suite(path: str | Path) -> Suite`
- İsim notu: sınıflar bilerek `TestCase`/`TestSuite` değil. `Test` ile başlayan sınıfları pytest test sınıfı sanıp toplamaya çalışıyor.

YAML formatı:

```yaml
server: python server.py          # ya da mapping: {command, args, env, cwd}
tests:
  - name: ...                     # opsiyonel, yoksa "test #N"
    call: tool_name               # zorunlu
    args: {...}                   # opsiyonel
    timeout_s: 10                 # opsiyonel, varsayılan 30
    expect: {...}                 # opsiyonel; boşsa sadece "hata dönmesin" demek
```

`cwd` verilmezse YAML dosyasının klasörü olur; böylece `server:` içindeki göreli yollar dosyaya göre çözülür.

- [ ] **Adım 1: Failing testler `tests/test_spec.py`**

```python
import pytest

from mcptest.spec import SpecError, load_suite


def write(tmp_path, text):
    path = tmp_path / "suite.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_string_server_and_cases(tmp_path):
    suite = load_suite(write(tmp_path, """
server: python server.py
tests:
  - name: adds
    call: add
    args: {a: 1, b: 2}
    expect: {contains: "3"}
  - call: echo
"""))
    assert suite.server.command == "python"
    assert suite.server.args == ["server.py"]
    assert suite.server.cwd == str(tmp_path.resolve())
    assert [c.name for c in suite.cases] == ["adds", "test #2"]
    assert suite.cases[0].args == {"a": 1, "b": 2}
    assert suite.cases[1].expect == {}


def test_loads_mapping_server(tmp_path):
    suite = load_suite(write(tmp_path, """
server:
  command: node
  args: [dist/index.js, --verbose]
  env: {API_KEY: test}
tests:
  - call: ping
"""))
    assert suite.server.command == "node"
    assert suite.server.args == ["dist/index.js", "--verbose"]
    assert suite.server.env == {"API_KEY": "test"}


@pytest.mark.parametrize("body, message", [
    ("tests: [{call: x}]", "'server'"),
    ("server: python s.py", "'tests'"),
    ("server: python s.py\ntests: [{name: no call}]", "'call'"),
    ("server: python s.py\ntests: [{call: x, expect: {contain: y}}]", "unknown expect keys: contain"),
    ("server: [unclosed", "invalid YAML"),
])
def test_rejects_malformed_suites(tmp_path, body, message):
    with pytest.raises(SpecError, match=message):
        load_suite(write(tmp_path, body))
```

- [ ] **Adım 2: Patladığını gör**

Çalıştır: `pytest tests/test_spec.py -q`
Beklenen: `ModuleNotFoundError: No module named 'mcptest.spec'`

- [ ] **Adım 3: `src/mcptest/spec.py`**

```python
"""Load YAML test suites."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mcptest.client import ServerSpec

KNOWN_EXPECT_KEYS = {"is_error", "contains", "not_contains", "matches", "max_latency_ms", "json_path", "schema"}


class SpecError(ValueError):
    """Raised when a test file is malformed."""


@dataclass
class Case:
    name: str
    call: str
    args: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 30.0


@dataclass
class Suite:
    server: ServerSpec
    cases: list[Case]


def load_suite(path: str | Path) -> Suite:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{path}: top level must be a mapping")
    server = _parse_server(data.get("server"), path)
    raw_cases = data.get("tests")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SpecError(f"{path}: 'tests' must be a non-empty list")
    return Suite(server=server, cases=[_parse_case(raw, i, path) for i, raw in enumerate(raw_cases)])


def _parse_server(raw: Any, path: Path) -> ServerSpec:
    if isinstance(raw, str) and raw.strip():
        spec = ServerSpec.from_command_line(raw)
    elif isinstance(raw, dict) and isinstance(raw.get("command"), str) and raw["command"].strip():
        spec = ServerSpec.from_command_line(raw["command"])
        spec.args += [str(a) for a in raw.get("args") or []]
        spec.env = raw.get("env")
        spec.cwd = raw.get("cwd")
    else:
        raise SpecError(f"{path}: 'server' must be a command string or a mapping with 'command'")
    if spec.cwd is None:
        # Relative paths in the server command resolve against the YAML file's folder.
        spec.cwd = str(path.parent.resolve())
    return spec


def _parse_case(raw: Any, index: int, path: Path) -> Case:
    where = f"{path}: tests[{index}]"
    if not isinstance(raw, dict):
        raise SpecError(f"{where} must be a mapping")
    name = str(raw.get("name") or f"test #{index + 1}")
    call = raw.get("call")
    if not isinstance(call, str) or not call:
        raise SpecError(f"{where} ({name}): 'call' must be a tool name")
    args = raw.get("args") or {}
    if not isinstance(args, dict):
        raise SpecError(f"{where} ({name}): 'args' must be a mapping")
    expect = raw.get("expect") or {}
    if not isinstance(expect, dict):
        raise SpecError(f"{where} ({name}): 'expect' must be a mapping")
    unknown = set(expect) - KNOWN_EXPECT_KEYS
    if unknown:
        raise SpecError(f"{where} ({name}): unknown expect keys: {', '.join(sorted(unknown))}")
    return Case(name=name, call=call, args=args, expect=expect, timeout_s=float(raw.get("timeout_s", 30.0)))
```

- [ ] **Adım 4: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `13 passed`

- [ ] **Adım 5: Commit**

```bash
git add src/mcptest/spec.py tests/test_spec.py
git commit -m "feat: load YAML test suites with validation errors"
```

---

### Task 4: Assertion motoru

**Dosyalar:**
- Oluştur: `src/mcptest/assertions.py`
- Test: `tests/test_assertions.py`

**Arayüzler:**
- Kullanır: `CallOutcome` (Task 2)
- Üretir: `check(expect: dict, outcome: CallOutcome) -> list[str]`. Her başarısız beklenti için bir mesaj döner, boş liste geçti demek.

Kurallar:
- `is_error` verilmezse `False` kabul edilir; yani her test, aksi söylenmedikçe başarı bekler.
- `contains` / `not_contains` tek string ya da liste alır.
- `matches` `re.search` kullanır (tüm metne değil, herhangi bir yere uyması yeterli).
- `json_path` noktalı yol alır, liste elemanına indeksle erişilir: `user.roles.0`.
- `json_path` ve `schema`, önce `structured_content`'e, yoksa JSON parse edilmiş text'e bakar.
- Mesajlarda uzun text 80 karakterden kesilir.

- [ ] **Adım 1: Failing testler `tests/test_assertions.py`**

```python
from mcptest.assertions import check
from mcptest.client import CallOutcome


def outcome(text="", is_error=False, structured=None, latency_ms=10.0):
    return CallOutcome(is_error=is_error, text=text, structured=structured, latency_ms=latency_ms)


def test_empty_expect_passes_on_success():
    assert check({}, outcome("ok")) == []


def test_empty_expect_fails_on_error():
    [failure] = check({}, outcome("boom", is_error=True))
    assert failure.startswith("is_error: expected False, got True")


def test_expected_error_passes():
    assert check({"is_error": True}, outcome("boom", is_error=True)) == []


def test_contains_accepts_string_or_list():
    assert check({"contains": "°C"}, outcome("21°C sunny")) == []
    failures = check({"contains": ["21", "rain"]}, outcome("21°C sunny"))
    assert failures == ["contains: 'rain' not found in '21°C sunny'"]


def test_not_contains():
    assert check({"not_contains": "null"}, outcome("Weather: null")) == [
        "not_contains: 'null' found in 'Weather: null'"
    ]


def test_matches_uses_regex_search():
    assert check({"matches": r"\d+°C"}, outcome("now 21°C")) == []
    assert len(check({"matches": r"^\d+$"}, outcome("now 21"))) == 1


def test_max_latency():
    assert check({"max_latency_ms": 100}, outcome(latency_ms=50)) == []
    assert check({"max_latency_ms": 100}, outcome(latency_ms=250)) == [
        "max_latency_ms: took 250 ms, limit 100 ms"
    ]


def test_json_path_reads_text_json_and_list_indexes():
    out = outcome('{"user": {"name": "Ada", "roles": ["admin"]}}')
    assert check({"json_path": {"user.name": "Ada", "user.roles.0": "admin"}}, out) == []
    assert check({"json_path": {"user.age": 3}}, out) == ["json_path user.age: missing"]
    assert check({"json_path": {"user.name": "Bob"}}, out) == ["json_path user.name: expected 'Bob', got 'Ada'"]


def test_json_path_prefers_structured_content():
    assert check({"json_path": {"result": 5}}, outcome("5", structured={"result": 5})) == []


def test_json_expectation_on_non_json_text():
    assert check({"json_path": {"a": 1}}, outcome("hello")) == ["json: response is not JSON: 'hello'"]


def test_schema():
    schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
    assert check({"schema": schema}, outcome('{"id": 1}')) == []
    [failure] = check({"schema": schema}, outcome('{"id": "x"}'))
    assert failure.startswith("schema: 'x' is not of type 'integer'")


def test_long_text_is_shortened_in_messages():
    [failure] = check({"contains": "zzz"}, outcome("a" * 200))
    assert "…" in failure and len(failure) < 150
```

- [ ] **Adım 2: Patladığını gör**

Çalıştır: `pytest tests/test_assertions.py -q`
Beklenen: `ModuleNotFoundError: No module named 'mcptest.assertions'`

- [ ] **Adım 3: `src/mcptest/assertions.py`**

```python
"""Compare a tool call outcome against a test's `expect` block."""

from __future__ import annotations

import re
from typing import Any

import jsonschema

from mcptest.client import CallOutcome

_MISSING = object()


def check(expect: dict[str, Any], outcome: CallOutcome) -> list[str]:
    """Return one human-readable message per failed expectation; empty means pass."""
    failures: list[str] = []

    # Every test expects success unless it says otherwise.
    expected_error = bool(expect.get("is_error", False))
    if outcome.is_error != expected_error:
        failures.append(f"is_error: expected {expected_error}, got {outcome.is_error} (text: {_short(outcome.text)})")

    for needle in _as_list(expect.get("contains")):
        if needle not in outcome.text:
            failures.append(f"contains: {needle!r} not found in {_short(outcome.text)}")

    for needle in _as_list(expect.get("not_contains")):
        if needle in outcome.text:
            failures.append(f"not_contains: {needle!r} found in {_short(outcome.text)}")

    if "matches" in expect and re.search(expect["matches"], outcome.text) is None:
        failures.append(f"matches: /{expect['matches']}/ did not match {_short(outcome.text)}")

    if "max_latency_ms" in expect:
        limit = float(expect["max_latency_ms"])
        if outcome.latency_ms > limit:
            failures.append(f"max_latency_ms: took {outcome.latency_ms:.0f} ms, limit {limit:.0f} ms")

    if "json_path" in expect or "schema" in expect:
        try:
            payload = outcome.json()
        except ValueError:
            failures.append(f"json: response is not JSON: {_short(outcome.text)}")
        else:
            failures += _check_json(expect, payload)

    return failures


def _check_json(expect: dict[str, Any], payload: Any) -> list[str]:
    failures = []
    for path, wanted in (expect.get("json_path") or {}).items():
        actual = _resolve(payload, str(path))
        if actual is _MISSING:
            failures.append(f"json_path {path}: missing")
        elif actual != wanted:
            failures.append(f"json_path {path}: expected {wanted!r}, got {actual!r}")
    if "schema" in expect:
        try:
            jsonschema.validate(payload, expect["schema"])
        except jsonschema.ValidationError as exc:
            failures.append(f"schema: {exc.message}")
    return failures


def _resolve(payload: Any, path: str) -> Any:
    """Follow a dotted path like 'user.roles.0'; list items are addressed by index."""
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _short(text: str, limit: int = 80) -> str:
    return repr(text if len(text) <= limit else text[:limit] + "…")
```

- [ ] **Adım 4: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `25 passed`

- [ ] **Adım 5: Commit**

```bash
git add src/mcptest/assertions.py tests/test_assertions.py
git commit -m "feat: add assertions for errors, text, regex, latency, JSON path and schema"
```

---

## Gün 3

### Task 5: Runner ve terminal raporu

**Dosyalar:**
- Oluştur: `src/mcptest/runner.py`, `src/mcptest/report.py`
- Test: `tests/test_runner.py`, `tests/test_report.py`

**Arayüzler:**
- Kullanır: `connect`, `Probe` (Task 2), `Case`, `Suite` (Task 3), `check` (Task 4)
- Üretir:
  - `CaseResult(name: str, passed: bool, failures: list[str], latency_ms: float | None)`; çağrı exception fırlatırsa `latency_ms=None`
  - `SuiteResult(results: list[CaseResult])` ve property'leri: `.passed: int`, `.failed: int`, `.ok: bool`
  - `async run_suite(suite: Suite, show_server_logs: bool = False) -> SuiteResult`: tek server süreci, case'ler sırayla
  - `report.paint(text, code, color) -> str`, sabitler `GREEN`, `RED`, `RESET`
  - `report.render_suite(title: str, result: SuiteResult, color: bool = False) -> str`

- [ ] **Adım 1: Failing testler `tests/test_runner.py`**

```python
import pytest

from mcptest.runner import run_suite
from mcptest.spec import Case, Suite


@pytest.mark.anyio
async def test_runs_cases_in_order_and_reports_each(fixture_spec):
    suite = Suite(server=fixture_spec, cases=[
        Case(name="adds", call="add", args={"a": 2, "b": 2}, expect={"contains": "4"}),
        Case(name="missing user", call="get_user", args={"user_id": 7},
             expect={"is_error": True, "matches": "not found"}),
        Case(name="wrong on purpose", call="echo", args={"text": "hi"}, expect={"contains": "bye"}),
        Case(name="too slow", call="slow", args={"seconds": 0.3}, expect={"max_latency_ms": 100}),
    ])
    result = await run_suite(suite)
    assert [r.name for r in result.results] == ["adds", "missing user", "wrong on purpose", "too slow"]
    assert [r.passed for r in result.results] == [True, True, False, False]
    assert (result.passed, result.failed, result.ok) == (2, 2, False)
    assert result.results[2].failures == ["contains: 'bye' not found in 'hi'"]
```

- [ ] **Adım 2: Failing testler `tests/test_report.py`**

```python
from mcptest.report import render_suite
from mcptest.runner import CaseResult, SuiteResult


def test_render_suite_plain():
    result = SuiteResult([
        CaseResult("adds", True, [], 12.4),
        CaseResult("breaks", False, ["contains: 'x' not found in 'y'"], None),
    ])
    assert render_suite("suite.yaml", result) == "\n".join([
        "suite.yaml",
        "  ✓ adds (12 ms)",
        "  ✗ breaks",
        "      contains: 'x' not found in 'y'",
        "  1 passed, 1 failed",
    ])


def test_render_suite_color_wraps_marks():
    text = render_suite("s", SuiteResult([CaseResult("a", True, [], 1.0)]), color=True)
    assert "\033[32m✓\033[0m" in text
```

- [ ] **Adım 3: Patladığını gör**

Çalıştır: `pytest tests/test_runner.py tests/test_report.py -q`
Beklenen: `ModuleNotFoundError` (`mcptest.runner`)

- [ ] **Adım 4: `src/mcptest/runner.py`**

```python
"""Run a suite's cases against one server process."""

from __future__ import annotations

from dataclasses import dataclass

from mcptest.assertions import check
from mcptest.client import Probe, connect
from mcptest.spec import Case, Suite


@dataclass
class CaseResult:
    name: str
    passed: bool
    failures: list[str]
    latency_ms: float | None


@dataclass
class SuiteResult:
    results: list[CaseResult]

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def failed(self) -> int:
        return len(self.results) - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0


async def run_suite(suite: Suite, show_server_logs: bool = False) -> SuiteResult:
    async with connect(suite.server, show_server_logs=show_server_logs) as probe:
        return SuiteResult([await _run_case(probe, case) for case in suite.cases])


async def _run_case(probe: Probe, case: Case) -> CaseResult:
    try:
        outcome = await probe.call(case.call, case.args, timeout_s=case.timeout_s)
    except Exception as exc:  # noqa: BLE001 - a broken call is a failed test, not a crash
        return CaseResult(case.name, False, [f"call raised {type(exc).__name__}: {exc}"], None)
    failures = check(case.expect, outcome)
    return CaseResult(case.name, not failures, failures, outcome.latency_ms)
```

- [ ] **Adım 5: `src/mcptest/report.py`**

```python
"""Render results for humans."""

from __future__ import annotations

from mcptest.runner import SuiteResult

GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"


def paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def render_suite(title: str, result: SuiteResult, color: bool = False) -> str:
    lines = [title]
    for r in result.results:
        mark = paint("✓", GREEN, color) if r.passed else paint("✗", RED, color)
        latency = f" ({r.latency_ms:.0f} ms)" if r.latency_ms is not None else ""
        lines.append(f"  {mark} {r.name}{latency}")
        lines += [f"      {failure}" for failure in r.failures]
    lines.append(f"  {result.passed} passed, {result.failed} failed")
    return "\n".join(lines)
```

- [ ] **Adım 6: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `28 passed`

- [ ] **Adım 7: Commit**

```bash
git add src/mcptest/runner.py src/mcptest/report.py tests/test_runner.py tests/test_report.py
git commit -m "feat: run suites against one server process and render results"
```

---

### Task 6: JUnit XML çıktısı

**Dosyalar:**
- Oluştur: `src/mcptest/junit.py`
- Test: `tests/test_junit.py`

**Arayüzler:**
- Kullanır: `CaseResult`, `SuiteResult` (Task 5)
- Üretir: `write_junit(path: str | Path, suites: list[tuple[str, SuiteResult]]) -> None`. Her YAML dosyası bir `<testsuite>`; başarısız case'te `<failure message="ilk hata">` ve body'de tüm hatalar.

- [ ] **Adım 1: Failing test `tests/test_junit.py`**

```python
import xml.etree.ElementTree as ET

from mcptest.junit import write_junit
from mcptest.runner import CaseResult, SuiteResult


def test_write_junit(tmp_path):
    out = tmp_path / "report.xml"
    write_junit(out, [("weather.yaml", SuiteResult([
        CaseResult("ok", True, [], 1500.0),
        CaseResult("bad", False, ["first problem", "second problem"], None),
    ]))])
    suite = ET.parse(out).getroot().find("testsuite")
    assert suite.attrib == {"name": "weather.yaml", "tests": "2", "failures": "1"}
    ok, bad = suite.findall("testcase")
    assert ok.attrib["time"] == "1.500" and ok.find("failure") is None
    failure = bad.find("failure")
    assert failure.attrib["message"] == "first problem"
    assert failure.text == "first problem\nsecond problem"
```

- [ ] **Adım 2: Patladığını gör**

Çalıştır: `pytest tests/test_junit.py -q`
Beklenen: `ModuleNotFoundError: No module named 'mcptest.junit'`

- [ ] **Adım 3: `src/mcptest/junit.py`**

```python
"""JUnit XML output so CI systems can show per-test results."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from mcptest.runner import SuiteResult


def write_junit(path: str | Path, suites: list[tuple[str, SuiteResult]]) -> None:
    root = ET.Element("testsuites")
    for suite_name, result in suites:
        suite_el = ET.SubElement(root, "testsuite", name=suite_name,
                                 tests=str(len(result.results)), failures=str(result.failed))
        for r in result.results:
            case_el = ET.SubElement(suite_el, "testcase", classname=suite_name, name=r.name,
                                    time=f"{(r.latency_ms or 0) / 1000:.3f}")
            if not r.passed:
                failure = ET.SubElement(case_el, "failure", message=r.failures[0])
                failure.text = "\n".join(r.failures)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
```

- [ ] **Adım 4: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `29 passed`

- [ ] **Adım 5: Commit**

```bash
git add src/mcptest/junit.py tests/test_junit.py
git commit -m "feat: write JUnit XML reports"
```

---

### Task 7: `mcptest run` komutu ve örnek suite

**Dosyalar:**
- Oluştur: `src/mcptest/cli.py`, `examples/fixture.yaml`
- Test: `tests/test_cli.py`

**Arayüzler:**
- Kullanır: `load_suite`, `SpecError` (Task 3), `run_suite`, `SuiteResult` (Task 5), `render_suite` (Task 5), `write_junit` (Task 6)
- Üretir: `main(argv: list[str] | None = None) -> int` (`pyproject.toml`'daki `mcptest = "mcptest.cli:main"` bunu çağırıyor), `EXIT_OK=0`, `EXIT_FAILED=1`, `EXIT_USAGE=2`, `_describe(exc) -> str`. Task 10 bu dosyaya `check` alt komutunu ekleyecek.

- [ ] **Adım 1: Failing testler `tests/test_cli.py`**

```python
import shlex
import xml.etree.ElementTree as ET

from mcptest.cli import main


def server_command(spec):
    return shlex.join([spec.command, *spec.args])


def write_suite(tmp_path, spec, tests_yaml):
    path = tmp_path / "suite.yaml"
    path.write_text(f"server: {server_command(spec)!r}\ntests:\n{tests_yaml}", encoding="utf-8")
    return path


PASSING = """\
  - name: adds
    call: add
    args: {a: 1, b: 1}
    expect: {contains: "2"}
"""

FAILING = PASSING + """\
  - name: wrong
    call: echo
    args: {text: hi}
    expect: {contains: bye}
"""


def test_run_passing_suite_exits_0(tmp_path, fixture_spec, capsys):
    assert main(["run", str(write_suite(tmp_path, fixture_spec, PASSING))]) == 0
    out = capsys.readouterr().out
    assert "✓ adds" in out and "1 passed, 0 failed" in out


def test_run_failing_suite_exits_1_and_writes_junit(tmp_path, fixture_spec, capsys):
    junit = tmp_path / "report.xml"
    assert main(["run", str(write_suite(tmp_path, fixture_spec, FAILING)), "--junit", str(junit)]) == 1
    assert "✗ wrong" in capsys.readouterr().out
    assert ET.parse(junit).getroot().find("testsuite").attrib["failures"] == "1"


def test_run_malformed_suite_exits_2(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("tests: []", encoding="utf-8")
    assert main(["run", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


def test_run_unstartable_server_exits_2(tmp_path, capsys):
    path = tmp_path / "suite.yaml"
    path.write_text("server: definitely-not-a-real-command-xyz\ntests:\n" + PASSING, encoding="utf-8")
    assert main(["run", str(path)]) == 2
    assert "could not run server" in capsys.readouterr().err
```

- [ ] **Adım 2: Patladığını gör**

Çalıştır: `pytest tests/test_cli.py -q`
Beklenen: `ModuleNotFoundError: No module named 'mcptest.cli'`

- [ ] **Adım 3: `src/mcptest/cli.py`**

```python
"""Command line entry point: `mcptest run`."""

from __future__ import annotations

import argparse
import sys

import anyio

from mcptest.junit import write_junit
from mcptest.report import render_suite
from mcptest.runner import SuiteResult, run_suite
from mcptest.spec import SpecError, load_suite

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcptest", description="Automated tests for MCP servers.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run YAML test suites")
    run_p.add_argument("files", nargs="+", help="YAML suite files")
    run_p.add_argument("--junit", metavar="PATH", help="also write a JUnit XML report")
    run_p.add_argument("--server-logs", action="store_true", help="show the server's stderr")

    args = parser.parse_args(argv)
    color = sys.stdout.isatty()
    return _cmd_run(args, color)


def _cmd_run(args: argparse.Namespace, color: bool) -> int:
    collected: list[tuple[str, SuiteResult]] = []
    for file in args.files:
        try:
            suite = load_suite(file)
            result = anyio.run(run_suite, suite, args.server_logs)
        except SpecError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        except Exception as exc:  # noqa: BLE001 - usually the server failed to start
            print(f"error: {file}: could not run server: {_describe(exc)}", file=sys.stderr)
            return EXIT_USAGE
        print(render_suite(file, result, color=color))
        collected.append((file, result))
    if args.junit:
        write_junit(args.junit, collected)
    return EXIT_OK if all(result.ok for _, result in collected) else EXIT_FAILED


def _describe(exc: BaseException) -> str:
    # anyio wraps errors in ExceptionGroups; show the innermost one.
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"
```

`_describe` neden var: server başlamazsa anyio hatayı iç içe `ExceptionGroup`'lar içinde fırlatıyor. Kullanıcıya en içteki gerçek hatayı göstermek için lazım.

- [ ] **Adım 4: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `33 passed`

- [ ] **Adım 5: Örnek suite `examples/fixture.yaml`**

```yaml
# Run from the repo root: mcptest run examples/fixture.yaml
# Relative paths in `server` resolve against this file's folder.
server: python ../tests/fixtures/fixture_server.py

tests:
  - name: adds two numbers
    call: add
    args: {a: 2, b: 3}
    expect:
      contains: "5"
      json_path: {result: 5}
      max_latency_ms: 2000

  - name: returns a user profile
    call: get_user
    args: {user_id: 1}
    expect:
      json_path: {name: Ada, roles.0: admin}
      schema:
        type: object
        required: [id, name]

  - name: unknown user is an error
    call: get_user
    args: {user_id: 42}
    expect:
      is_error: true
      matches: "not found"

  - name: missing argument is rejected
    call: add
    args: {a: 1}
    expect:
      is_error: true
```

- [ ] **Adım 6: Gerçek komutu elle dene**

```bash
mcptest run examples/fixture.yaml; echo "exit=$?"
```

Beklenen:

```
examples/fixture.yaml
  ✓ adds two numbers (4 ms)
  ✓ returns a user profile (1 ms)
  ✓ unknown user is an error (1 ms)
  ✓ missing argument is rejected (1 ms)
  4 passed, 0 failed
exit=0
```

Bir beklentiyi bilerek boz (ör. `contains: "6"`), `✗` ve `exit=1` gör, sonra geri al.

- [ ] **Adım 7: Commit**

```bash
git add src/mcptest/cli.py tests/test_cli.py examples/fixture.yaml
git commit -m "feat: add mcptest run command with JUnit option and example suite"
```

---

## Gün 4

### Task 8: Protokol kontrolleri

**Dosyalar:**
- Oluştur: `src/mcptest/checks.py`
- Test: `tests/test_checks.py`

**Arayüzler:**
- Kullanır: `Probe` (Task 2)
- Üretir: `CheckResult(name: str, passed: bool, detail: str = "")`, `UNKNOWN_TOOL = "__mcptest_unknown_tool__"`, `async run_protocol_checks(probe: Probe, probe_invalid_args: bool = False) -> list[CheckResult]`

Kontroller, sırayla:
1. `lists tools`: en az bir tool var mı
2. `unknown tool returns an error`: olmayan tool exception değil `is_error=True` dönmeli
3. (sadece `probe_invalid_args=True` ise) zorunlu parametresi olan her tool, `{}` ile çağrıldığında reddedilmeli
4. `server alive after bad calls`: sonrasında `tools/list` hâlâ çalışıyor mu

Madde 3 neden opt-in: argüman doğrulaması yapmayan bir server tool'u gerçekten çalıştırır (ör. `delete_file({})`). Bu yüzden sadece dev/test server'larında açılmalı.

- [ ] **Adım 1: Failing testler `tests/test_checks.py`**

```python
import pytest

from mcptest.checks import run_protocol_checks
from mcptest.client import connect


@pytest.mark.anyio
async def test_default_checks_pass_on_fixture(fixture_spec):
    async with connect(fixture_spec) as probe:
        results = await run_protocol_checks(probe)
    assert [r.name for r in results] == [
        "lists tools",
        "unknown tool returns an error",
        "server alive after bad calls",
    ]
    assert all(r.passed for r in results), results


@pytest.mark.anyio
async def test_invalid_args_probe_covers_tools_with_required_params(fixture_spec):
    async with connect(fixture_spec) as probe:
        results = await run_protocol_checks(probe, probe_invalid_args=True)
    names = {r.name for r in results}
    assert "add: missing required args rejected" in names
    assert "get_user: missing required args rejected" in names
    assert all(r.passed for r in results), results
```

- [ ] **Adım 2: Patladığını gör**

Çalıştır: `pytest tests/test_checks.py -q`
Beklenen: `ModuleNotFoundError: No module named 'mcptest.checks'`

- [ ] **Adım 3: `src/mcptest/checks.py`**

```python
"""Protocol checks that need no test file."""

from __future__ import annotations

from dataclasses import dataclass

from mcptest.client import Probe

UNKNOWN_TOOL = "__mcptest_unknown_tool__"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


async def run_protocol_checks(probe: Probe, probe_invalid_args: bool = False) -> list[CheckResult]:
    tools = await probe.list_tools()
    results = [CheckResult("lists tools", bool(tools), "" if tools else "tools/list returned no tools")]
    results.append(await _expect_error(probe, "unknown tool returns an error", UNKNOWN_TOOL))
    if probe_invalid_args:
        # Opt-in: a server that skips validation would really run these tools.
        for tool in tools:
            if tool.input_schema.get("required"):
                results.append(await _expect_error(probe, f"{tool.name}: missing required args rejected", tool.name))
    try:
        await probe.list_tools()
        results.append(CheckResult("server alive after bad calls", True))
    except Exception as exc:  # noqa: BLE001
        results.append(CheckResult("server alive after bad calls", False, f"{type(exc).__name__}: {exc}"))
    return results


async def _expect_error(probe: Probe, name: str, tool: str) -> CheckResult:
    try:
        out = await probe.call(tool, {}, timeout_s=10)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name, False, f"call raised {type(exc).__name__} instead of returning is_error: {exc}")
    if out.is_error:
        return CheckResult(name, True)
    return CheckResult(name, False, f"expected is_error=true, got success: {out.text[:80]!r}")
```

- [ ] **Adım 4: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `35 passed`

- [ ] **Adım 5: Commit**

```bash
git add src/mcptest/checks.py tests/test_checks.py
git commit -m "feat: add protocol checks for unknown tools and invalid args"
```

---

### Task 9: Tool tanımları için lint

**Dosyalar:**
- Oluştur: `src/mcptest/lint.py`
- Test: `tests/test_lint.py`

**Arayüzler:**
- Kullanır: `ToolInfo`, `connect` (Task 2)
- Üretir: `LintWarning(tool: str, code: str, message: str)`, `MIN_DESCRIPTION_WORDS = 5`, `SIMILARITY_THRESHOLD = 0.85`, `lint_tools(tools: list[ToolInfo]) -> list[LintWarning]`

Uyarı kodları:

| Kod | Ne zaman |
|---|---|
| `no-description` | Açıklama boş |
| `short-description` | 5 kelimeden kısa |
| `invalid-schema` | `input_schema` geçerli bir JSON Schema (2020-12) değil |
| `param-no-description` | Bir parametrenin `description`'ı yok |
| `similar-tools` | İki tool'un açıklaması en az %85 benzer (`tool` alanı `a/b` formatında) |

Sıralama: önce tool başına (açıklama, sonra şema), en sonda benzerlik çiftleri.

- [ ] **Adım 1: Failing testler `tests/test_lint.py`**

```python
import pytest

from mcptest.client import ToolInfo, connect
from mcptest.lint import lint_tools

GOOD_SCHEMA = {"type": "object", "properties": {"city": {"type": "string", "description": "City name"}}}


def tool(name, description="Return the current weather for a city.", schema=None):
    return ToolInfo(name=name, description=description, input_schema=schema or GOOD_SCHEMA)


def codes(warnings):
    return [(w.tool, w.code) for w in warnings]


def test_clean_tool_has_no_warnings():
    assert lint_tools([tool("weather")]) == []


def test_missing_and_short_descriptions():
    warnings = lint_tools([tool("a", description=""), tool("b", description="Gets it.")])
    assert codes(warnings) == [("a", "no-description"), ("b", "short-description")]
    assert warnings[1].message == "description has 2 words (min 5)"


def test_param_without_description():
    schema = {"type": "object", "properties": {"city": {"type": "string"}}}
    assert codes(lint_tools([tool("weather", schema=schema)])) == [("weather", "param-no-description")]


def test_invalid_schema():
    assert codes(lint_tools([tool("weather", schema={"type": "not-a-type"})])) == [("weather", "invalid-schema")]


def test_similar_descriptions():
    warnings = lint_tools([
        tool("read_file", "Read a text file from disk and return its contents."),
        tool("get_file", "Read a text file from the disk and return its content."),
        tool("weather"),
    ])
    assert codes(warnings) == [("read_file/get_file", "similar-tools")]


@pytest.mark.anyio
async def test_fixture_server_warnings(fixture_spec):
    async with connect(fixture_spec) as probe:
        warnings = lint_tools(await probe.list_tools())
    found = set(codes(warnings))
    assert ("undocumented", "no-description") in found
    assert ("read_file/get_file", "similar-tools") in found
    assert ("add", "param-no-description") in found
```

- [ ] **Adım 2: Patladığını gör**

Çalıştır: `pytest tests/test_lint.py -q`
Beklenen: `ModuleNotFoundError: No module named 'mcptest.lint'`

- [ ] **Adım 3: `src/mcptest/lint.py`**

```python
"""Static quality checks on tool definitions."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

import jsonschema

from mcptest.client import ToolInfo

MIN_DESCRIPTION_WORDS = 5
SIMILARITY_THRESHOLD = 0.85


@dataclass
class LintWarning:
    tool: str
    code: str
    message: str


def lint_tools(tools: list[ToolInfo]) -> list[LintWarning]:
    warnings: list[LintWarning] = []
    for tool in tools:
        warnings += _lint_description(tool)
        warnings += _lint_schema(tool)
    warnings += _lint_similar(tools)
    return warnings


def _lint_description(tool: ToolInfo) -> list[LintWarning]:
    words = tool.description.split()
    if not words:
        return [LintWarning(tool.name, "no-description", "tool has no description")]
    if len(words) < MIN_DESCRIPTION_WORDS:
        return [LintWarning(tool.name, "short-description",
                            f"description has {len(words)} words (min {MIN_DESCRIPTION_WORDS})")]
    return []


def _lint_schema(tool: ToolInfo) -> list[LintWarning]:
    try:
        jsonschema.Draft202012Validator.check_schema(tool.input_schema)
    except jsonschema.SchemaError as exc:
        return [LintWarning(tool.name, "invalid-schema", exc.message)]
    return [
        LintWarning(tool.name, "param-no-description", f"parameter '{name}' has no description")
        for name, prop in (tool.input_schema.get("properties") or {}).items()
        if isinstance(prop, dict) and not prop.get("description")
    ]


def _lint_similar(tools: list[ToolInfo]) -> list[LintWarning]:
    documented = [t for t in tools if t.description.strip()]
    warnings = []
    for i, a in enumerate(documented):
        for b in documented[i + 1:]:
            ratio = difflib.SequenceMatcher(None, a.description.lower(), b.description.lower()).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                warnings.append(LintWarning(f"{a.name}/{b.name}", "similar-tools",
                                            f"descriptions are {ratio:.0%} similar; models may confuse them"))
    return warnings
```

- [ ] **Adım 4: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `41 passed`

- [ ] **Adım 5: Commit**

```bash
git add src/mcptest/lint.py tests/test_lint.py
git commit -m "feat: lint tool descriptions, schemas and look-alike tools"
```

---

### Task 10: `mcptest check` komutu

**Dosyalar:**
- Değiştir: `src/mcptest/report.py` (tamamı aşağıda), `src/mcptest/cli.py` (tamamı aşağıda)
- Test: `tests/test_report.py` ve `tests/test_cli.py` dosyalarının sonuna ekleme

**Arayüzler:**
- Kullanır: `run_protocol_checks`, `CheckResult` (Task 8), `lint_tools`, `LintWarning` (Task 9), `ServerSpec`, `connect` (Task 2)
- Üretir: `report.render_check(checks: list[CheckResult], warnings: list[LintWarning], color: bool = False) -> str`, `YELLOW` sabiti ve CLI'da `mcptest check "<server komutu>" [--probe-invalid-args] [--strict] [--server-logs]`. Çıkış kodu: check başarısızsa `1`, `--strict` ile lint uyarısı varsa da `1`.

- [ ] **Adım 1: `tests/test_report.py` sonuna ekle**

```python
def test_render_check():
    from mcptest.checks import CheckResult
    from mcptest.lint import LintWarning
    from mcptest.report import render_check

    text = render_check(
        [CheckResult("lists tools", True), CheckResult("unknown tool returns an error", False, "got success")],
        [LintWarning("undocumented", "no-description", "tool has no description")],
    )
    assert text == "\n".join([
        "Protocol checks",
        "  ✓ lists tools",
        "  ✗ unknown tool returns an error",
        "      got success",
        "Lint",
        "  ⚠ undocumented [no-description] tool has no description",
        "1/2 checks passed, 1 lint warnings",
    ])
```

- [ ] **Adım 2: `tests/test_cli.py` sonuna ekle**

```python
def test_check_passes_without_strict(fixture_spec, capsys):
    assert main(["check", server_command(fixture_spec)]) == 0
    out = capsys.readouterr().out
    assert "✓ unknown tool returns an error" in out
    assert "undocumented [no-description]" in out


def test_check_strict_fails_on_lint_warnings(fixture_spec):
    assert main(["check", server_command(fixture_spec), "--strict"]) == 1
```

- [ ] **Adım 3: Patladığını gör**

Çalıştır: `pytest tests/test_report.py tests/test_cli.py -q`
Beklenen: `ImportError: cannot import name 'render_check'` ve CLI testlerinde `invalid choice: 'check'` (argparse, `SystemExit: 2`).

- [ ] **Adım 4: `src/mcptest/report.py` dosyasını bununla değiştir**

```python
"""Render results for humans."""

from __future__ import annotations

from mcptest.checks import CheckResult
from mcptest.lint import LintWarning
from mcptest.runner import SuiteResult

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def render_suite(title: str, result: SuiteResult, color: bool = False) -> str:
    lines = [title]
    for r in result.results:
        mark = paint("✓", GREEN, color) if r.passed else paint("✗", RED, color)
        latency = f" ({r.latency_ms:.0f} ms)" if r.latency_ms is not None else ""
        lines.append(f"  {mark} {r.name}{latency}")
        lines += [f"      {failure}" for failure in r.failures]
    lines.append(f"  {result.passed} passed, {result.failed} failed")
    return "\n".join(lines)


def render_check(checks: list[CheckResult], warnings: list[LintWarning], color: bool = False) -> str:
    lines = ["Protocol checks"]
    for c in checks:
        mark = paint("✓", GREEN, color) if c.passed else paint("✗", RED, color)
        lines.append(f"  {mark} {c.name}")
        if c.detail:
            lines.append(f"      {c.detail}")
    lines.append("Lint")
    if not warnings:
        lines.append("  no warnings")
    for w in warnings:
        lines.append(f"  {paint('⚠', YELLOW, color)} {w.tool} [{w.code}] {w.message}")
    passed = sum(c.passed for c in checks)
    lines.append(f"{passed}/{len(checks)} checks passed, {len(warnings)} lint warnings")
    return "\n".join(lines)
```

- [ ] **Adım 5: `src/mcptest/cli.py` dosyasını bununla değiştir**

```python
"""Command line entry point: `mcptest run` and `mcptest check`."""

from __future__ import annotations

import argparse
import sys

import anyio

from mcptest.checks import run_protocol_checks
from mcptest.client import ServerSpec, connect
from mcptest.junit import write_junit
from mcptest.lint import lint_tools
from mcptest.report import render_check, render_suite
from mcptest.runner import SuiteResult, run_suite
from mcptest.spec import SpecError, load_suite

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcptest", description="Automated tests for MCP servers.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run YAML test suites")
    run_p.add_argument("files", nargs="+", help="YAML suite files")
    run_p.add_argument("--junit", metavar="PATH", help="also write a JUnit XML report")
    run_p.add_argument("--server-logs", action="store_true", help="show the server's stderr")

    check_p = sub.add_parser("check", help="protocol checks and lint, no test file needed")
    check_p.add_argument("server", help='server command, e.g. "python server.py"')
    check_p.add_argument("--probe-invalid-args", action="store_true",
                         help="call every tool with empty args; only use against dev servers")
    check_p.add_argument("--strict", action="store_true", help="fail on lint warnings too")
    check_p.add_argument("--server-logs", action="store_true", help="show the server's stderr")

    args = parser.parse_args(argv)
    color = sys.stdout.isatty()
    if args.command == "run":
        return _cmd_run(args, color)
    return _cmd_check(args, color)


def _cmd_run(args: argparse.Namespace, color: bool) -> int:
    collected: list[tuple[str, SuiteResult]] = []
    for file in args.files:
        try:
            suite = load_suite(file)
            result = anyio.run(run_suite, suite, args.server_logs)
        except SpecError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        except Exception as exc:  # noqa: BLE001 - usually the server failed to start
            print(f"error: {file}: could not run server: {_describe(exc)}", file=sys.stderr)
            return EXIT_USAGE
        print(render_suite(file, result, color=color))
        collected.append((file, result))
    if args.junit:
        write_junit(args.junit, collected)
    return EXIT_OK if all(result.ok for _, result in collected) else EXIT_FAILED


def _cmd_check(args: argparse.Namespace, color: bool) -> int:
    try:
        spec = ServerSpec.from_command_line(args.server)
        checks, warnings = anyio.run(_check, spec, args.probe_invalid_args, args.server_logs)
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not run server: {_describe(exc)}", file=sys.stderr)
        return EXIT_USAGE
    print(render_check(checks, warnings, color=color))
    failed = not all(c.passed for c in checks) or (args.strict and warnings)
    return EXIT_FAILED if failed else EXIT_OK


async def _check(spec: ServerSpec, probe_invalid_args: bool, show_server_logs: bool):
    async with connect(spec, show_server_logs=show_server_logs) as probe:
        tools = await probe.list_tools()
        checks = await run_protocol_checks(probe, probe_invalid_args=probe_invalid_args)
    return checks, lint_tools(tools)


def _describe(exc: BaseException) -> str:
    # anyio wraps errors in ExceptionGroups; show the innermost one.
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"
```

- [ ] **Adım 6: Geçtiğini gör**

Çalıştır: `pytest -q && ruff check src tests`
Beklenen: `44 passed`

- [ ] **Adım 7: Elle dene**

```bash
mcptest check "python tests/fixtures/fixture_server.py"; echo "exit=$?"
```

Beklenen: 3 check `✓`, 10 lint uyarısı (`undocumented [no-description]`, `read_file/get_file [similar-tools]` dahil) ve `exit=0`. `--strict` eklenince `exit=1`.

- [ ] **Adım 8: Commit**

```bash
git add src/mcptest/report.py src/mcptest/cli.py tests/test_report.py tests/test_cli.py
git commit -m "feat: add mcptest check command for protocol checks and lint"
```

---

## Gün 5

### Task 11: CI

**Dosyalar:**
- Oluştur: `.github/workflows/ci.yml`

**Arayüzler:**
- Kullanır: tüm test paketi ve `examples/fixture.yaml` (Task 7)
- Üretir: her push ve PR'da 3.11 / 3.12 / 3.13 matrisi; mcptest'in kendini kendi CLI'ı ile test etmesi (dogfooding)

- [ ] **Adım 1: `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: pytest -q
      - run: mcptest run examples/fixture.yaml --junit report.xml
      - run: mcptest check "python tests/fixtures/fixture_server.py"
```

- [ ] **Adım 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: test on Python 3.11-3.13 and dogfood the CLI"
```

- [ ] **Adım 3: GitHub'da repo aç ve push et (bunu kendin yap, repo public olacak)**

```bash
gh repo create mcptest --public --source . --push
```

- [ ] **Adım 4: CI'ın yeşil olduğunu kontrol et**

```bash
gh run watch
```

Beklenen: üç Python sürümünde de tüm adımlar başarılı. Kırmızıysa `gh run view --log-failed` ile loga bak, düzelt, commit at, `git push`.

---

### Task 12: README ve 0.1.0 yayını

**Dosyalar:**
- Değiştir: `README.md` (tamamı)

**Arayüzler:**
- Kullanır: tüm CLI davranışı
- Üretir: PyPI'da `mcptest 0.1.0`, GitHub'da `v0.1.0` tag'i

- [ ] **Adım 1: `README.md`**

````markdown
# mcptest

Automated, CI-friendly tests for [MCP](https://modelcontextprotocol.io) servers.

MCP Inspector is great for poking at a server by hand. `mcptest` is for the other half:
repeatable tests that run on every commit.

```bash
pip install mcptest
```

## Write a test

```yaml
# weather.yaml
server: python weather_server.py

tests:
  - name: returns the temperature
    call: get_weather
    args: {city: Istanbul}
    expect:
      contains: "°C"
      max_latency_ms: 2000

  - name: unknown city is an error
    call: get_weather
    args: {city: Xyzabc}
    expect:
      is_error: true
      matches: "not found"
```

```bash
mcptest run weather.yaml
```

Every test expects the call to succeed unless it sets `is_error: true`.

| `expect` key | Passes when |
|---|---|
| `is_error` | the result's error flag matches |
| `contains` / `not_contains` | the text contains / lacks a string (or every string in a list) |
| `matches` | a regex matches anywhere in the text |
| `max_latency_ms` | the call finished in time |
| `json_path` | `{path: value}` pairs match, e.g. `user.roles.0: admin` |
| `schema` | the JSON result validates against a JSON Schema |

`server` can also be a mapping with `command`, `args`, `env` and `cwd`.
Relative paths resolve against the YAML file's folder.

## Check a server without writing tests

```bash
mcptest check "python server.py"
```

Runs protocol checks (unknown tools must return an error, the server must survive bad calls)
and lints tool definitions: missing or short descriptions, parameters without descriptions,
invalid schemas, and tools whose descriptions are so similar that a model may confuse them.

- `--strict` fails on lint warnings too.
- `--probe-invalid-args` also calls every tool with empty arguments to confirm they are rejected.
  Only use it against development servers: a server that skips validation will run the tool.

## CI

```yaml
- run: pip install mcptest
- run: mcptest run tests/mcp/*.yaml --junit mcptest.xml
```

Exit codes: `0` all passed, `1` a test or check failed, `2` bad test file or the server did not start.

## Status

Early. Stdio servers only. Planned: HTTP transport, snapshot tests, a pytest plugin,
and LLM-in-the-loop tests that check whether models pick the right tool.

## License

MIT
````

- [ ] **Adım 2: Paketi derle ve kontrol et**

```bash
pip install build twine
python -m build
twine check dist/*
```

Beklenen: `dist/mcptest-0.1.0.tar.gz` ve `dist/mcptest-0.1.0-py3-none-any.whl`, `twine check` → `PASSED`.

- [ ] **Adım 3: Temiz ortamda wheel'i dene**

```bash
python3 -m venv /tmp/mcptest-smoke && /tmp/mcptest-smoke/bin/pip install -q dist/mcptest-0.1.0-py3-none-any.whl
PATH=/tmp/mcptest-smoke/bin:$PATH mcptest check "python tests/fixtures/fixture_server.py"; echo "exit=$?"
```

Beklenen: `3/3 checks passed`, `exit=0`.

- [ ] **Adım 4: Commit, tag, push**

```bash
git add README.md
git commit -m "docs: write README for 0.1.0"
git tag v0.1.0
git push && git push --tags
```

- [ ] **Adım 5: PyPI'a yükle (bunu kendin yap)**

PyPI hesabı ve API token gerekiyor, Codex'e yaptırma.

```bash
twine upload dist/*
```

Sonra `pip install mcptest` ile doğrula ve `gh release create v0.1.0 --generate-notes` ile GitHub release'i aç.

---

## 0.1 sonrası (bu planın dışında)

Sırayla, her biri kendi planına değer:
1. **HTTP transport:** `server: {url: http://localhost:8000/mcp}` (`mcp.client.streamable_http`)
2. **Snapshot testleri:** `expect: {snapshot: true}`, ilk koşuda kaydet, sonra farkı göster
3. **pytest eklentisi:** `mcp` fixture'ı ile Python'da test yazma
4. **LLM testleri:** prompt ver, doğru tool'u doğru argümanla seçiyor mu (çoklu model)
5. Resources ve prompts için de testler (şu an sadece tools)
