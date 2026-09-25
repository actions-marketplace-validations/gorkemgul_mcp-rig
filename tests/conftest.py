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
