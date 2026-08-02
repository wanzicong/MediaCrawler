---
name: media-transcribe
description: 当用户要下载视频/图片、把视频语音转成文字或字幕（SRT/VTT）、查询转写任务进度时使用。覆盖 list_media_assets、transcribe_downloaded_media、get_media_task_status、read_media_transcript 四个 MCP 工具的完整流水线。
---

# 视频下载与转写技能

媒体流水线：爬取（下载媒体）→ 查询媒体资产 → 创建转写任务 → 查询任务状态 → 读取转写结果。

## 两条入口路径

**路径 A：爬取时一步完成**
`crawl_*` 调用时传 `download_media=true` + `transcribe_media=true`，工具会自动下载视频并批量创建转写任务，返回里带 `media_run_id`、`media_assets` 和 `transcription_jobs`。

可选转写参数：`transcription_backend`（api/local，默认 api，失败自动回退本地）、
`transcription_model`（faster-whisper 模型，默认 small）、
`transcription_device`（auto/cpu/cuda）、`transcription_compute_type`（auto/int8/float16/int8_float16）、
`transcription_language`（语言代码或 auto）、`word_timestamps`（词级时间戳，默认 false）。

**路径 B：事后补转写**
对已下载的媒体资产调用 `transcribe_downloaded_media(platform, content_id)`。

## 工具用法

### 1. list_media_assets — 查询媒体资产

```text
list_media_assets(platform="dy", content_id="", media_run_id="", status="", limit=100)
```

- 全部参数可选，按平台/内容 ID/运行 ID/状态过滤。
- 返回资产元数据和本地路径；转写前先用它确认资产 `status` 为 `downloaded` 且 `has_audio` 为 true。

### 2. transcribe_downloaded_media — 创建转写任务

```text
transcribe_downloaded_media(platform="dy", content_id="7xxx", backend="api", model="small", wait=false)
```

- `platform`、`content_id` 必填；找不到资产会报"未找到已下载的媒体资产"。
- `wait=false`（默认）异步执行，立即返回任务；`wait=true` 等待完成。
- 返回的 `job.id` 即任务 ID，查状态和读结果要用。

### 3. get_media_task_status — 查询任务状态

```text
get_media_task_status(task_id="<job.id>")
```

- 异步任务轮询用；状态变为 `completed` 后才能读结果。

### 4. read_media_transcript — 读取转写结果

```text
read_media_transcript(platform="dy", content_id="7xxx", output_format="srt")
```

- `output_format`：json（全文+分段，默认）/ text（纯文本）/ srt / vtt（字幕文件内容）。
- 可选 `task_id` 读取指定版本；不传则读该资产最新一次转写。
- 任务未完成时返回"转写尚未完成"并附带 job 状态——先轮询 get_media_task_status。

## 典型对话流程

1. 用户："把刚才爬的抖音视频转成文字" → 从对话记录找到 platform + content_id（或用 list_media_assets 按 media_run_id 查）→ transcribe_downloaded_media → 告知任务 ID → 轮询 get_media_task_status → read_media_transcript 输出 text。
2. 用户："给我字幕文件" → 同上，output_format 用 srt 或 vtt。
3. 用户："转写失败了" → get_media_task_status 看 job 的 error_message；backend 默认 api 失败会自动回退 local，仍失败则检查本地模型环境。

## 注意事项

- 转写耗时与视频时长、模型大小正相关；本地 backend 在 CPU 上明显慢于 GPU。
- 只有 `has_audio=true` 的资产才能转写（图片资产会被跳过）。
- 字幕文件保存在媒体资产同目录（transcript.srt / transcript.vtt）。
