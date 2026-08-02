---
name: crawl-platform
description: 当用户要从小红书/抖音/快手/B站/微博/贴吧/知乎爬取内容（关键词搜索、帖子/视频详情、创作者主页、抖音个人点赞与收藏）时使用。指导选择正确的 crawl_* 工具、填写参数、处理登录态。
---

# 平台爬取技能

通过 MCP 工具 `crawl_<平台代号>` 爬取 7 大社媒平台内容。不确定平台支持什么模式时，先调用 `list_platforms`。

## 平台与模式

| 平台 | 代号 | 工具 | 可用 crawler_type |
| --- | --- | --- | --- |
| 小红书 | xhs | crawl_xhs | search / detail / creator |
| 抖音 | dy | crawl_dy | search / detail / creator / liked / collected |
| 快手 | ks | crawl_ks | search / detail / creator |
| B站 | bili | crawl_bili | search / detail / creator |
| 微博 | wb | crawl_wb | search / detail / creator |
| 贴吧 | tieba | crawl_tieba | search / detail / creator |
| 知乎 | zhihu | crawl_zhihu | search / detail / creator |

## 三种通用模式的必填参数

- `search`（关键词搜索）：`keywords` 必填，多个关键词用逗号分隔。
- `detail`（指定内容详情）：`specified_id` 必填，内容 ID 或 URL，多个用逗号分隔。
- `creator`（创作者主页）：`creator_id` 必填，创作者 ID 或主页 URL，多个用逗号分隔。

## 抖音个人模式（仅 dy）

- `liked`：当前登录账号点赞的作品。
- `collected`：当前登录账号收藏的作品。
- 这两种模式**不需要** keywords/specified_id/creator_id，**默认不抓评论**；确有需要显式传 `get_comment=true`。

## 常用参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| login_type | qrcode | qrcode / phone / cookie |
| cookies | 空 | cookie 登录时用；优先复用 browser_data 登录态，不建议直接传敏感 Cookie（会进入客户端/模型日志） |
| get_comment | 普通模式 True，抖音个人模式 False | 是否抓评论 |
| get_sub_comment | False | 是否抓二级评论 |
| max_notes_count | 15 | 单次上限 1000，按页数扩展超时 |
| headless | False | 有头浏览器更不易被风控 |
| download_media | False | 下载图片/视频 |
| transcribe_media | False | 异步转写视频（开启后自动下载视频），详见 media-transcribe 技能 |
| save_data_option | jsonl | jsonl/json/csv/excel/sqlite/db/mongodb/postgres |
| return_data | False | 为 true 时把本次数据内联返回（仅 jsonl/json/csv/excel） |

## 登录态处理（关键）

1. 优先复用 `browser_data/` 中已保存的登录态（二维码登录一次即可）。
2. 若工具返回登录失败，引导用户在项目根目录手动执行（以 xhs 为例）：

   ```bash
   uv run main.py --platform xhs --lt qrcode --type search --keywords test --headless false
   ```

   扫码后登录态自动保存，再重试 MCP 调用。
3. 不要在对话里索取或打印用户的 Cookie 明文。

## 调用后必做

- 记录返回 JSON 中的 `crawl_run_id`（格式 `crawl_` + 32 位十六进制），后续回读数据、查媒体资产都要用它。
- 返回结果含 `log_tail`/`stderr_tail`，失败时先读这两段定位原因（登录失效、风控、参数错误）。
- 数据文件在 `data/mcp_runs/<crawl_run_id>/` 下，回读请用 read-crawl-data 技能。

## 注意事项

- 单次爬取是子进程执行，耗时与 max_notes_count、是否抓评论正相关；量大时先小批量试跑。
- 遵守目标平台 robots 与频率限制，不要大规模并发爬取（LICENSE 禁止商用与大规模爬取）。
