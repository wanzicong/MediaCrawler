# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests\test_mcp_stdio_smoke.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

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
            assert crawl_schema["transcription_backend"]["default"] == "api"
            transcribe_schema = tools_by_name[
                "transcribe_downloaded_media"
            ].inputSchema["properties"]
            assert transcribe_schema["backend"]["default"] == "api"

            result = await session.call_tool("list_media_assets", {"limit": 1})
            assert result.isError is False
