"""MCP server that exposes tools over two discovery pages."""

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import ListToolsResult, PaginatedRequestParams, Tool


def tool(name: str) -> Tool:
    return Tool(name=name, description=f"{name} tool", inputSchema={"type": "object"})


async def list_tools(_context, params: PaginatedRequestParams | None) -> ListToolsResult:
    if params is None or params.cursor is None:
        return ListToolsResult(tools=[tool("first")], nextCursor="page-2")
    return ListToolsResult(tools=[tool("second")])


server = Server("mcp-rig-paginated-fixture", on_list_tools=list_tools)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
