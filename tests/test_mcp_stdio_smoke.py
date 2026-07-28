import sys

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_mcp_stdio_lists_media_tools_and_headed_defaults() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server"],
    )
    async with stdio_client(parameters) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            tools_by_name = {tool.name: tool for tool in tools}

            assert len(tools) == 13
            assert {
                "crawl_dy",
                "list_media_assets",
                "transcribe_downloaded_media",
                "get_media_task_status",
                "read_media_transcript",
            }.issubset(tools_by_name)

            crawl_schema = tools_by_name["crawl_dy"].inputSchema["properties"]
            assert crawl_schema["headless"]["default"] is False
            assert crawl_schema["download_media"]["default"] is False
            assert crawl_schema["transcribe_media"]["default"] is False

            result = await session.call_tool("list_media_assets", {"limit": 1})
            assert result.isError is False
