from __future__ import annotations

import argparse
import ipaddress
import os
from dataclasses import dataclass
from typing import Literal


Transport = Literal["stdio", "streamable-http"]


def _csv_env(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/":
        normalized = normalized.rstrip("/")
    if normalized == "/":
        raise ValueError("MCP HTTP 路径不能使用根路径 /")
    return normalized


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class MCPServerConfig:
    transport: Transport = "stdio"
    host: str = "127.0.0.1"
    port: int = 8765
    path: str = "/mcp"
    allowed_hosts: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()

    def validated(self) -> "MCPServerConfig":
        if not 1 <= self.port <= 65535:
            raise ValueError("MCP 端口必须在 1 到 65535 之间")
        normalized_path = _normalize_path(self.path)
        if normalized_path == "/health":
            raise ValueError("MCP HTTP 路径不能与 /health 冲突")
        if self.transport == "stdio":
            return MCPServerConfig(
                transport=self.transport,
                host=self.host,
                port=self.port,
                path=normalized_path,
                allowed_hosts=self.allowed_hosts,
                allowed_origins=self.allowed_origins,
            )

        if self.host in {"0.0.0.0", "::"} and not self.allowed_hosts:
            raise ValueError(
                "监听通配地址时必须通过 --allowed-host 或 "
                "MEDIACRAWLER_MCP_ALLOWED_HOSTS 指定客户端使用的 Host"
            )
        return MCPServerConfig(
            transport=self.transport,
            host=self.host,
            port=self.port,
            path=normalized_path,
            allowed_hosts=self.allowed_hosts,
            allowed_origins=self.allowed_origins,
        )

    def effective_allowed_hosts(self) -> list[str]:
        if self.allowed_hosts:
            return list(self.allowed_hosts)
        if is_loopback_host(self.host):
            return [
                "127.0.0.1",
                "127.0.0.1:*",
                "localhost",
                "localhost:*",
                "[::1]",
                "[::1]:*",
            ]
        return [self.host, f"{self.host}:*"]


def parse_server_config(argv: list[str] | None = None) -> MCPServerConfig:
    parser = argparse.ArgumentParser(description="MediaCrawler MCP Server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.getenv("MEDIACRAWLER_MCP_TRANSPORT", "stdio"),
        help="传输协议，默认 stdio",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MEDIACRAWLER_MCP_HOST", "127.0.0.1"),
        help="Streamable HTTP 监听地址，默认 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MEDIACRAWLER_MCP_PORT", "8765")),
        help="Streamable HTTP 监听端口，默认 8765",
    )
    parser.add_argument(
        "--path",
        default=os.getenv("MEDIACRAWLER_MCP_PATH", "/mcp"),
        help="Streamable HTTP 端点路径，默认 /mcp",
    )
    parser.add_argument(
        "--allowed-host",
        action="append",
        dest="allowed_hosts",
        default=None,
        help="DNS 重绑定保护允许的 Host，可重复传入",
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        dest="allowed_origins",
        default=None,
        help="允许的浏览器 Origin，可重复传入",
    )
    args = parser.parse_args(argv)
    return MCPServerConfig(
        transport=args.transport,
        host=args.host,
        port=args.port,
        path=args.path,
        allowed_hosts=tuple(
            args.allowed_hosts
            if args.allowed_hosts is not None
            else _csv_env("MEDIACRAWLER_MCP_ALLOWED_HOSTS")
        ),
        allowed_origins=tuple(
            args.allowed_origins
            if args.allowed_origins is not None
            else _csv_env("MEDIACRAWLER_MCP_ALLOWED_ORIGINS")
        ),
    ).validated()
