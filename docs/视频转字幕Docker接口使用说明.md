# 视频转字幕 Docker 接口使用说明

本文记录 MediaCrawler 当前用于音频、视频转字幕的独立 Docker 服务，包括
已验证的运行环境、容器启动方式、HTTP 接口调用方式、测试结果和运维命令。

> 当前阶段统一采用 `hwdsl2/whisper-server`。其他 Whisper Web UI、云端
> 语音识别或自建 Python API 方案暂不引入，避免同时维护多套实现。

## 1. 服务用途

该服务使用 Faster-Whisper 对音频或视频中的语音进行识别，并通过 HTTP
接口返回以下格式：

- `srt`：通用字幕文件，当前主要使用格式。
- `vtt`：适合网页播放器的字幕格式。
- `text`：纯文字。
- `json`：纯文字 JSON 响应。
- `verbose_json`：包含分段时间戳等信息的详细 JSON。

视频文件可以直接上传，不需要调用方预先提取音轨。服务支持 MP3、MP4、
M4A、WAV、WebM、OGG、FLAC 等常见格式。

## 2. 当前运行现状

本机当前运行的是测试服务，尚未改为 Docker Compose。MediaCrawler 已加入
该服务的 API 适配器，默认优先调用 API，调用失败时自动回退原有本地
Faster-Whisper。

| 项目 | 当前值 |
| --- | --- |
| 容器名称 | `codex-whisper-test` |
| Docker 镜像 | `hwdsl2/whisper-server:latest` |
| 访问地址 | `http://127.0.0.1:9000` |
| API 文档 | `http://127.0.0.1:9000/docs` |
| 模型 | `base` |
| 默认语言 | `auto` |
| 计算设备 | CPU |
| 计算精度 | `int8` |
| CPU 线程 | 8 |
| 模型数据卷 | `codex-whisper-test-data` |
| 部署指纹 | `base-auto-int8-v2` |
| 重启策略 | `no`，Docker 或电脑重启后不会自动启动 |
| API Key | 配置在被 Git 忽略的项目根目录 `.env`，仅用于本机测试 |
| 网络暴露范围 | 仅绑定 `127.0.0.1`，局域网和公网无法直接访问 |

项目根目录被 Git 忽略的 `.env` 已配置同一地址和测试 Key，因此当前项目可
直接调用该容器；提交到版本库的 `.env.example` 不包含真实密钥。

健康检查：

```powershell
curl.exe http://127.0.0.1:9000/health
```

正常响应：

```json
{"status":"ok","model":"base"}
```

## 3. 当前容器的启动命令

本次测试使用 `docker run` 启动，不是 Docker Compose：

```powershell
$env:WHISPER_API_KEY="<LOCAL_TEST_API_KEY>"

docker run -d `
  --name codex-whisper-test `
  --restart no `
  -p 127.0.0.1:9000:9000 `
  -e WHISPER_MODEL=base `
  -e WHISPER_LANGUAGE=auto `
  -e WHISPER_DEVICE=cpu `
  -e WHISPER_COMPUTE_TYPE=int8 `
  -e WHISPER_THREADS=8 `
  -e WHISPER_API_KEY=$env:WHISPER_API_KEY `
  -v codex-whisper-test-data:/var/lib/whisper `
  hwdsl2/whisper-server:latest
```

关键配置说明：

- `WHISPER_MODEL=base`：当前验证模型。速度较快、资源占用较低，正式环境可在
  性能测试后考虑 `small` 或 `large-v3-turbo`。
- `WHISPER_LANGUAGE=auto`：默认自动识别语言；调用方也可以显式传 `zh`。
- `WHISPER_DEVICE=cpu`：当前电脑没有检测到可用的 NVIDIA CUDA 环境。
- `WHISPER_COMPUTE_TYPE=int8`：适合 CPU 推理。
- `WHISPER_THREADS=8`：单次推理实测可占用约 8 个逻辑 CPU。
- `WHISPER_API_KEY`：接口鉴权密钥。正式环境必须替换，不能继续使用测试值。
- `127.0.0.1:9000:9000`：只允许本机访问，避免测试服务直接暴露到网络。
- 数据卷保存模型缓存，删除和重建容器不会导致模型重新下载；删除数据卷才会
  清除缓存。

## 4. Docker 和代理情况

本机 Docker Desktop 使用 WSL2 Linux 后端。Docker 引擎已经配置内部代理：

```text
HTTP Proxy:  http://docker.internal:3128
HTTPS Proxy: http://docker.internal:3128
```

已实际验证以下链路正常：

1. 从 Docker Hub 拉取 `hwdsl2/whisper-server:latest`。
2. 容器访问 Hugging Face。
3. 首次下载 Faster-Whisper `base` 模型。
4. 重启容器后复用模型缓存。

宿主机的 `8080` 端口当前由一个 Python 进程监听，未确认其为代理，因此不应
将它配置给 Docker。当前 Docker 内部 `3128` 代理已经可用，不需要额外修改。

## 5. 接口定义

转写接口：

```text
POST /v1/audio/transcriptions
Content-Type: multipart/form-data
Authorization: Bearer <API Key>
```

常用参数：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | 要识别的音频或视频文件 |
| `model` | 是 | 兼容 OpenAI 接口，传 `whisper-1`；实际使用容器启动时加载的模型 |
| `language` | 否 | 中文传 `zh`，自动识别可省略或传 `auto` |
| `response_format` | 否 | `srt`、`vtt`、`text`、`json` 或 `verbose_json` |
| `prompt` | 否 | 用于提示专有名词、上下文或输出风格 |
| `temperature` | 否 | 采样温度，默认 `0` |

## 6. 上传视频并保存 SRT

Windows PowerShell 中使用 `curl.exe`，避免调用 PowerShell 自带的
`curl` 别名：

```powershell
curl.exe http://127.0.0.1:9000/v1/audio/transcriptions `
  -H "Authorization: Bearer $env:WHISPER_API_KEY" `
  -F "file=@D:\videos\example.mp4" `
  -F "model=whisper-1" `
  -F "language=zh" `
  -F "response_format=srt" `
  -o "D:\videos\example.srt"
```

接口成功时返回 HTTP 200，字幕内容直接写入 `example.srt`。

## 7. 上传音频并保存 VTT

```powershell
curl.exe http://127.0.0.1:9000/v1/audio/transcriptions `
  -H "Authorization: Bearer $env:WHISPER_API_KEY" `
  -F "file=@D:\audio\meeting.m4a" `
  -F "model=whisper-1" `
  -F "language=zh" `
  -F "response_format=vtt" `
  -o "D:\audio\meeting.vtt"
```

## 8. 获取 JSON 结果

基础 JSON：

```powershell
curl.exe http://127.0.0.1:9000/v1/audio/transcriptions `
  -H "Authorization: Bearer $env:WHISPER_API_KEY" `
  -F "file=@D:\audio\meeting.mp3" `
  -F "model=whisper-1" `
  -F "language=zh" `
  -F "response_format=json"
```

需要分段时间戳时：

```powershell
curl.exe http://127.0.0.1:9000/v1/audio/transcriptions `
  -H "Authorization: Bearer $env:WHISPER_API_KEY" `
  -F "file=@D:\audio\meeting.mp3" `
  -F "model=whisper-1" `
  -F "language=zh" `
  -F "response_format=verbose_json"
```

## 9. 已完成测试

### 9.1 基础功能

- 9.45 秒中文 WAV：约 1.04 秒生成 SRT。
- 9.47 秒中文 MP4：约 0.91 秒生成 SRT。
- 音频和视频输出内容一致。
- SRT 时间轴正确。
- UTF-8 中文无乱码。
- 容器重启后模型缓存可正常复用。

测试识别结果：

```srt
1
00:00:00,000 --> 00:00:02,560
这是一个字幕生成测试。

2
00:00:03,080 --> 00:00:08,960
今天天气不错,我们正在验证音频和视频转字幕功能。
```

### 9.2 长视频

项目内 `data/media/dy/7655626030958267686/source.mp4`：

| 指标 | 结果 |
| --- | --- |
| 视频时长 | 6 分 39 秒 |
| 文件大小 | 48.02 MB |
| 转写耗时 | 44.88 秒 |
| 处理速度 | 约 8.9 倍实时速度 |
| 字幕数量 | 226 条 |
| 输出大小 | 约 14.5 KB |
| HTTP 状态 | 200 |

### 9.3 并发

两个 6 分 39 秒视频同时提交：

- 第一个请求约 50.99 秒完成。
- 第二个请求约 97.62 秒完成。
- 总墙钟时间约 99.21 秒。
- 峰值 CPU 约 803%，峰值内存约 687 MiB。
- 两个请求均返回 HTTP 200，字幕内容一致。

四个 59 秒视频同时提交：

- 四个请求分别约在 5.27、10.62、16.17、21.49 秒完成。
- 总墙钟时间约 22.86 秒。
- 峰值 CPU 约 801%，峰值内存约 380 MiB。
- 四个请求均返回 HTTP 200，字幕文件哈希完全一致。

结论：单容器可以接收并发请求，但推理任务实际按队列串行处理。提高对同一
容器的请求并发数不会提高总吞吐量，只会增加后续请求的等待时间。正式接入时
应采用任务队列，并把每个容器的推理并发度设为 1；需要更高吞吐时再增加容器
副本。

### 9.4 MediaCrawler 集成回归

项目内 37.13 秒真实 MP4 通过 `TranscriptionManager` 调用当前容器：

- API 转写耗时 15.65 秒，生成 26 个分段和 187 个词级时间戳。
- 任务记录为 `requested_backend=api`、`actual_backend=api`、模型 `base`。
- TXT、JSON、SRT、VTT 全部写入任务专属目录，未残留临时文件。
- 将 API 地址故意改为不可连接端口后，23.72 秒内由原有本地 `tiny` 模型完成，
  任务记录为 `actual_backend=local`，并保存了 API 回退原因。

## 10. 日常运维命令

查看容器状态：

```powershell
docker ps --filter "name=codex-whisper-test"
```

查看日志：

```powershell
docker logs -f codex-whisper-test
```

查看 CPU 和内存：

```powershell
docker stats codex-whisper-test
```

停止：

```powershell
docker stop codex-whisper-test
```

重新启动：

```powershell
docker start codex-whisper-test
```

重启：

```powershell
docker restart codex-whisper-test
```

删除测试容器但保留模型缓存：

```powershell
docker rm -f codex-whisper-test
```

删除模型缓存属于破坏性操作。确认不再需要缓存后才执行：

```powershell
docker volume rm codex-whisper-test-data
```

## 11. MediaCrawler 接入方式

默认开启转写时使用 API：

```powershell
uv run main.py --platform dy --type detail `
  --specified_id "<视频ID或URL>" `
  --transcribe_media true `
  --whisper_backend api `
  --whisper_language zh
```

处理顺序：

```text
下载并注册视频
    → 调用 /v1/audio/transcriptions
    → 成功：统一生成 TXT/JSON/SRT/VTT
    → 失败：自动调用本地 Faster-Whisper
    → API 和本地均失败：任务标记为 failed
```

强制使用旧的本地实现：

```powershell
uv run main.py --platform dy --type detail `
  --specified_id "<视频ID或URL>" `
  --transcribe_media true `
  --whisper_backend local
```

WebUI 在开启“视频转文字”后提供“API 优先”和“仅本地模型”选项。CLI、
Web API 和 MCP 也会透传同一个后端选择。

## 12. 当前限制与后续接入原则

- 当前 API Key 是测试值，正式使用前必须更换并放入安全配置。
- API 请求出现连接、超时、非 2xx 响应或响应格式错误时都会触发本地回退；
  回退原因会写入任务记录，不会静默隐藏鉴权或配置错误。
- 当前没有 Docker Compose 文件，也没有配置开机自动启动。
- 当前为 CPU `base` 模型，准确率评估需要使用真实业务视频继续抽检。
- 单容器推理串行，项目默认把 API 转写并发限制为 1。
- 项目进程内会复用相同媒体和参数的活动任务；如果将 MediaCrawler 部署为
  多个独立 Worker，需要再增加数据库级任务认领/租约或外部任务队列。
- 如果未来开放给其他电脑访问，需要配置 HTTPS、正式鉴权、上传大小限制、
  超时、任务队列和结果存储，不能直接把测试端口暴露到公网。
- 当前只维护这一套 Docker Whisper API 方案，暂不部署 Whisper Web UI、
  Whisper ASR Webservice 或其他替代镜像。

## 13. 与项目内置转写功能的关系

项目已有基于 Faster-Whisper 的内置媒体转写流程，说明见
[`视频下载与转写指南`](视频下载与转写指南.md)。内置流程直接由
MediaCrawler 进程执行；本文记录的方案是独立 HTTP 服务。

Docker API 和本地实现已经统一到同一 `TranscriptionManager`，共用任务状态
和输出逻辑，不会由平台下载代码分别调用两套流程。任务 JSON 和 SQLite 会记录
请求后端、实际后端、实际模型和回退原因。每次任务的文件写入
`transcripts/{job_id}/` 独立目录，重试或并发任务不会互相覆盖。
