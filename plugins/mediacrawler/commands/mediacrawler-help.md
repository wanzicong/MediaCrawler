---
description: 查看 MediaCrawler 插件的使用指南：平台列表、爬取模式、登录方式、数据回读、视频转写、MCP 服务运维入口
---

# MediaCrawler 插件帮助

请向用户展示以下使用指南（根据用户当前的问题选择性展开对应章节）：

## 1. 插件能力总览

本插件通过 MCP 提供 13 个工具，配合 4 个技能使用：

| 技能 | 触发场景 |
| --- | --- |
| crawl-platform | 要爬取任何平台内容时 |
| read-crawl-data | 要读取/分析之前爬取的数据时 |
| media-transcribe | 要下载视频或把视频转成文字/字幕时 |
| mcp-server-ops | 要启动/停止/排查 MCP 服务时 |

## 2. 平台与工具对照

| 平台 | 代号 | 爬取工具 | 可用模式 |
| --- | --- | --- | --- |
| 小红书 | xhs | crawl_xhs | search / detail / creator |
| 抖音 | dy | crawl_dy | search / detail / creator / liked / collected |
| 快手 | ks | crawl_ks | search / detail / creator |
| B站 | bili | crawl_bili | search / detail / creator |
| 微博 | wb | crawl_wb | search / detail / creator |
| 贴吧 | tieba | crawl_tieba | search / detail / creator |
| 知乎 | zhihu | crawl_zhihu | search / detail / creator |

辅助工具：list_platforms（列出平台）、read_crawl_data（回读数据）、
list_media_assets / transcribe_downloaded_media / get_media_task_status /
read_media_transcript（媒体下载与转写）。

## 3. 首次使用：登录

爬虫需要平台登录态。在项目根目录执行（以小红书为例）：

```bash
uv run main.py --platform xhs --lt qrcode --type search --keywords test --headless false
```

扫码登录后，登录态保存到 `browser_data/` 目录，后续 MCP 调用自动复用。

## 4. 常用流程

1. 爬取：`crawl_<平台>(crawler_type="search", keywords="关键词", ...)`，记录返回的 `crawl_run_id`。
2. 回读：`read_crawl_data(crawl_run_id="crawl_...")`。
3. 转写：爬取时带 `transcribe_media=true`，或事后 `transcribe_downloaded_media(platform, content_id)`。

## 5. 服务运维

- 启动 HTTP 服务：`start_mcp_server.bat`（Windows）或 `uv run python -m mcp_server --transport streamable-http`
- 停止：`stop_mcp_server.bat`
- 健康检查：`http://127.0.0.1:8765/health`
- 日志：`logs/mcp_server.stdout.log`、`logs/mcp_server.stderr.log`

更详细说明见 `mcp_server/README.md`。
