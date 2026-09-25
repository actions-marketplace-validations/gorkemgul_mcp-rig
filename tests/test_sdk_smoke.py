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
