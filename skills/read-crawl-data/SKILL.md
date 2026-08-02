---
name: read-crawl-data
description: 当用户要读取、查看、统计或分析之前 crawl_* 工具爬取到的数据（帖子、视频、评论等）时使用。指导用 crawl_run_id 正确回读 JSONL/JSON/CSV/Excel 数据，避免读到旧任务数据。
---

# 数据回读技能

通过 MCP 工具 `read_crawl_data` 读取之前爬取产生的数据文件。

## 推荐用法：按 crawl_run_id 回读

每次 `crawl_*` 调用都返回唯一 `crawl_run_id`，数据保存在独立运行目录
`data/mcp_runs/<crawl_run_id>/`。回读时**优先只传 crawl_run_id**：

```text
read_crawl_data(crawl_run_id="crawl_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
```

- 传入 `crawl_run_id` 后，`platform`、`crawler_type`、`file_type` 都可省略（自动从运行清单读取）。
- 这样即使本次列表为空，也不会回读到同日旧任务的数据。
- 抖音 liked/collected 模式**禁止省略** crawl_run_id，否则工具直接报错。
- 只有状态为 `completed` 的运行可以读取。

## 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| crawl_run_id | 空 | crawl_* 返回的运行 ID（推荐必填） |
| platform | 空 | 平台代号；有 crawl_run_id 时可省略 |
| crawler_type | 空 | 爬取模式；有 crawl_run_id 时可省略 |
| file_type | jsonl | jsonl / json / csv / excel |
| max_items | 200 | 每类最多返回条目数，上限 1000 |

## 文件格式与限制

- 可回读格式：`jsonl`、`json`、`csv`、`excel`。
- `sqlite`、`db`、`postgres`、`mongodb` 是共享后端，只支持写入和状态返回，**不能**把共享历史记录当本次数据内联返回——需要这些格式时先用文件格式保存。
- 损坏的 JSONL 行会跳过并保留可解析记录，返回里带 `DATA_READ_ERROR` 错误码与 `read_errors` 列表；遇到时向用户说明哪些文件有多少行损坏。
- 如果同时传了 crawl_run_id 和 platform/crawler_type/file_type，三者必须与运行清单一致，否则报错——所以最简单的做法就是只传 crawl_run_id。

## 典型流程

1. 用户说"看看刚才爬的数据" → 从对话记录找到最近的 `crawl_run_id` → 调用 read_crawl_data。
2. 用户要做统计分析 → 回读数据后直接基于返回的 JSON 条目做汇总，不要再去翻文件系统。
3. 用户问"数据文件在哪" → 告知 `data/mcp_runs/<crawl_run_id>/` 目录。

## 常见错误处理

| 错误 | 含义 | 处置 |
| --- | --- | --- |
| 找不到运行清单 | crawl_run_id 不存在或目录被清理 | 确认 ID 拼写；让用户重新爬取 |
| 运行状态非 completed | 任务失败/进行中 | 回报状态，建议查 crawl 返回的日志尾部 |
| DATA_READ_ERROR | 部分文件损坏 | 展示可用数据 + 说明损坏情况 |
| 必须提供 crawl_run_id | 抖音个人模式的强制约束 | 找到对应 crawl_dy 的 crawl_run_id 重试 |
