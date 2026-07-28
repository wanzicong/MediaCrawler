import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcp_server.runtime import MCPServerConfig, parse_server_config


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_network_config_defaults_to_local_streamable_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "MEDIACRAWLER_MCP_TRANSPORT",
        "MEDIACRAWLER_MCP_HOST",
        "MEDIACRAWLER_MCP_PORT",
        "MEDIACRAWLER_MCP_PATH",
        "MEDIACRAWLER_MCP_ALLOWED_HOSTS",
        "MEDIACRAWLER_MCP_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = parse_server_config(["--transport", "streamable-http"])

    assert config.host == "127.0.0.1"
    assert config.port == 8765
    assert config.path == "/mcp"
    assert "127.0.0.1:*" in config.effective_allowed_hosts()


def test_network_config_allows_non_loopback_without_authentication() -> None:
    config = MCPServerConfig(
        transport="streamable-http",
        host="192.168.1.10",
    ).validated()

    assert config.host == "192.168.1.10"
    assert config.effective_allowed_hosts() == [
        "192.168.1.10",
        "192.168.1.10:*",
    ]


def test_wildcard_bind_requires_explicit_allowed_host() -> None:
    with pytest.raises(ValueError, match="allowed-host"):
        parse_server_config(
            [
                "--transport",
                "streamable-http",
                "--host",
                "0.0.0.0",
            ]
        )


@pytest.mark.asyncio
async def test_streamable_http_network_transport_without_authentication() -> None:
    port = _free_local_port()
    endpoint = f"http://127.0.0.1:{port}/mcp"
    environment = os.environ.copy()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mcp_server",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=os.fspath(os.path.dirname(os.path.dirname(__file__))),
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"网络 MCP 服务提前退出，返回码 {process.returncode}")
            try:
                response = httpx.get(
                    f"http://127.0.0.1:{port}/health",
                    timeout=1,
                )
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("网络 MCP 服务未在 15 秒内启动")

        async with streamablehttp_client(endpoint) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                names = {tool.name for tool in tools}
                assert len(tools) == 13
                assert "crawl_dy" in names
                assert "transcribe_downloaded_media" in names
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
