# MediaCrawler MCP Server

MCP 服务支持两种运行方式：

- `stdio`：默认方式，供 Codex、Claude Desktop 等客户端以子进程方式启动。
- `streamable-http`：通过 HTTP 网络调用，端点默认为 `/mcp`。

## stdio

```shell
uv run python -m mcp_server
```

## 本机 HTTP

默认只监听 `127.0.0.1:8765`：

```shell
uv run python -m mcp_server --transport streamable-http
```

MCP 地址为 `http://127.0.0.1:8765/mcp`，健康检查地址为
`http://127.0.0.1:8765/health`。

## 局域网或公网

监听非本机地址时默认强制要求 Bearer Token。Token 只通过环境变量传入，
避免出现在命令行和进程列表中。

PowerShell 示例：

```powershell
$env:MEDIACRAWLER_MCP_TOKEN = "<使用随机生成的长字符串>"
uv run python -m mcp_server `
  --transport streamable-http `
  --host 0.0.0.0 `
  --port 8765 `
  --allowed-host "192.168.1.10:*"
```

Linux/macOS 示例：

```shell
MEDIACRAWLER_MCP_TOKEN='<使用随机生成的长字符串>' \
uv run python -m mcp_server \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8765 \
  --allowed-host '192.168.1.10:*'
```

客户端请求需携带：

```text
Authorization: Bearer <同一个 Token>
```

若通过域名访问，应把域名加入 `--allowed-host`。浏览器客户端还需通过
`--allowed-origin` 指定允许的 Origin。公网部署应在 Nginx、Caddy 等反向
代理后启用 HTTPS，不建议直接暴露明文 HTTP。

## 环境变量

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MEDIACRAWLER_MCP_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `MEDIACRAWLER_MCP_HOST` | `127.0.0.1` | HTTP 监听地址 |
| `MEDIACRAWLER_MCP_PORT` | `8765` | HTTP 监听端口 |
| `MEDIACRAWLER_MCP_PATH` | `/mcp` | MCP HTTP 路径 |
| `MEDIACRAWLER_MCP_TOKEN` | 空 | Bearer Token |
| `MEDIACRAWLER_MCP_ALLOWED_HOSTS` | 自动 | 逗号分隔的 Host 白名单 |
| `MEDIACRAWLER_MCP_ALLOWED_ORIGINS` | 空 | 逗号分隔的 Origin 白名单 |

服务还会启用 MCP SDK 的 DNS 重绑定保护。只有显式使用
`--allow-insecure-network` 才能在非本机地址上无 Token 运行，不建议在生产
环境使用该参数。
