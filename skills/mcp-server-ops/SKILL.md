---
name: mcp-server-ops
description: 当用户要启动、停止、重启 MediaCrawler MCP 服务、查看服务状态与日志、配置 HTTP/局域网监听、排查 MCP 连接失败时使用。覆盖 stdio 与 streamable-http 两种传输方式。
---

# MCP 服务运维技能

MediaCrawler MCP 服务支持两种运行方式：

- `stdio`：默认方式，Claude Code / Codex 等客户端以子进程方式启动，无需手动运维。
- `streamable-http`：HTTP 网络调用，默认监听 `127.0.0.1:8765`，端点 `/mcp`。

## 启动与停止（Windows 一键脚本）

项目根目录提供：

```powershell
.\start_mcp_server.bat    # 后台启动 HTTP 服务，等待健康检查通过
.\stop_mcp_server.bat     # 停止本项目的 MCP 服务及其子进程
```

- 重复执行启动脚本不会重复创建服务；停止脚本只停当前项目虚拟环境里的服务。
- PID 状态写入 `data/runtime/mcp_server.json`。
- 日志：`logs/mcp_server.stdout.log`、`logs/mcp_server.stderr.log`。
- 对应 PowerShell 脚本：`scripts/start_mcp_server.ps1`、`scripts/stop_mcp_server.ps1`。

## 手动启动

```bash
# stdio（调试用）
uv run python -m mcp_server

# 本机 HTTP
uv run python -m mcp_server --transport streamable-http

# 监听局域网（必须显式指定 allowed-host）
uv run python -m mcp_server --transport streamable-http --host 0.0.0.0 --port 8765 --allowed-host "192.168.1.10:*"
```

健康检查地址：`http://127.0.0.1:8765/health`。

## 环境变量

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| MEDIACRAWLER_MCP_TRANSPORT | stdio | stdio 或 streamable-http |
| MEDIACRAWLER_MCP_HOST | 127.0.0.1 | HTTP 监听地址 |
| MEDIACRAWLER_MCP_PORT | 8765 | HTTP 监听端口 |
| MEDIACRAWLER_MCP_PATH | /mcp | MCP HTTP 路径 |
| MEDIACRAWLER_MCP_ALLOWED_HOSTS | 自动 | 逗号分隔 Host 白名单 |
| MEDIACRAWLER_MCP_ALLOWED_ORIGINS | 空 | 逗号分隔 Origin 白名单（浏览器客户端需要） |

服务启用了 MCP SDK 的 DNS 重绑定保护：监听 `0.0.0.0` 或 `::` 时**必须**配置
`--allowed-host`，否则请求会被拒绝。

## 安全须知

服务本身**不做应用层鉴权**：任何能访问该端口的客户端都能调用爬虫工具。
- 只监听可信网络；公网部署必须由 Nginx/Caddy/API Gateway 提供 HTTPS 和认证。
- 用防火墙/VPN 限制访问来源。

## 故障排查

| 症状 | 排查路径 |
| --- | --- |
| 客户端连不上 stdio 服务 | 在项目根手动跑 `uv run python -m mcp_server`，看启动报错（依赖缺失/端口占用/环境变量错误） |
| HTTP 健康检查失败 | 查 `logs/mcp_server.stderr.log`；确认端口 8765 未被占用；确认 allowed-host 配置 |
| 插件加载后工具不可见 | 确认 `.mcp.json` 中 `uv` 在 PATH；查看 MCP 客户端日志里的 stdio 输出 |
| 工具调用报登录失败 | 不是服务问题——按 crawl-platform 技能的登录流程先扫码登录 |
