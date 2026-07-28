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

### Windows 一键启动与停止

项目根目录提供了可直接运行的脚本：

```powershell
.\start_mcp_server.bat
.\stop_mcp_server.bat
```

启动脚本会在后台运行服务，等待健康检查通过，并把 PID 状态写入
`data/runtime/mcp_server.json`。日志保存在：

```text
logs/mcp_server.stdout.log
logs/mcp_server.stderr.log
```

监听局域网的示例：

```powershell
.\start_mcp_server.bat `
  -ListenHost 0.0.0.0 `
  -AllowedHost "192.168.1.10:*"
```

重复执行启动脚本不会重复创建服务；停止脚本只会停止当前项目虚拟环境中运行
的 MCP 服务及其子进程。

## 局域网或公网

PowerShell 示例：

```powershell
uv run python -m mcp_server `
  --transport streamable-http `
  --host 0.0.0.0 `
  --port 8765 `
  --allowed-host "192.168.1.10:*"
```

Linux/macOS 示例：

```shell
uv run python -m mcp_server \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8765 \
  --allowed-host '192.168.1.10:*'
```

若通过域名访问，应把域名加入 `--allowed-host`。浏览器客户端还需通过
`--allowed-origin` 指定允许的 Origin。

服务本身不进行应用层身份鉴权。任何能够访问该端口的客户端都可以调用爬虫
工具，因此应通过防火墙、可信局域网、VPN 或反向代理限制访问。公网部署时，
应由 Nginx、Caddy、API Gateway 等上游服务提供 HTTPS 和身份认证。

## 环境变量

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MEDIACRAWLER_MCP_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `MEDIACRAWLER_MCP_HOST` | `127.0.0.1` | HTTP 监听地址 |
| `MEDIACRAWLER_MCP_PORT` | `8765` | HTTP 监听端口 |
| `MEDIACRAWLER_MCP_PATH` | `/mcp` | MCP HTTP 路径 |
| `MEDIACRAWLER_MCP_ALLOWED_HOSTS` | 自动 | 逗号分隔的 Host 白名单 |
| `MEDIACRAWLER_MCP_ALLOWED_ORIGINS` | 空 | 逗号分隔的 Origin 白名单 |

服务仍会启用 MCP SDK 的 DNS 重绑定保护。监听 `0.0.0.0` 或 `::` 时必须
显式配置客户端将使用的 `--allowed-host`。
