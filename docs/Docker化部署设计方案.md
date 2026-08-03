# MediaCrawler Docker 化部署设计方案

> 设计日期:2026-08-03
> 方案:单容器一体化(方案 A)+ Xvfb 有头浏览器 + 全套服务容器化
> 状态:待用户确认后实施

---

## 一、背景与目标

项目当前重度依赖本地环境:本地真实 Chrome(CDP 模式)、本地弹窗扫码登录、本地 user-data-dir 登录态。本方案目标是打出一个**自包含的 Docker 镜像**,让整套系统(爬虫 + MCP 服务 + API + WebUI)能在无 GUI 的 Linux 环境中运行,同时**宿主机现有使用方式零影响**。

### 三个关键技术约束(已查证)

1. **CDP 连接地址写死 `localhost`** —— `tools/cdp_browser.py:296`(`http://localhost:{port}/json/version`)和 `:322`(`ws://localhost:{port}`),配置项 `CDP_DEBUG_PORT` 只有端口没有主机。结论:本方案浏览器与爬虫同容器,localhost 可继续用;跨容器是方案 B 的事。
2. **扫码登录是本地弹图片** —— `tools/crawler_util.py:100` 用 PIL `Image.show()` 弹窗,容器内无 GUI 会失败。结论:Docker 模式下改为落文件。
3. **登录态在 `browser_data/` 的 Chrome profile 目录** —— 必须做成 volume 持久化,否则容器重建后需重新扫码。

### 一个有利的既有事实(已查证)

WebUI 生产构建产物输出到 `api/webui/`,由 FastAPI 在 8080 端口直接托管(README:196-209)。因此 **API 与 WebUI 天然同进程**,容器内不需要单独的前端服务器。

---

## 二、容器内服务拓扑

```
┌──────────────────────────────────────────────────┐
│  容器 mediacrawler(supervisord 管理进程)          │
│                                                  │
│  Xvfb :99  ── 虚拟显示(有头模式的屏幕)            │
│       │                                          │
│  Chrome(CDP 有头, DISPLAY=:99, 9222 端口)         │
│       │                                          │
│  ├── MCP 服务      :8765  (mcp_server)           │
│  ├── API + WebUI   :8080  (uvicorn api.main:app) │
│  └── 爬虫 main.py  按需 docker exec 触发          │
│        └── CDP 连 localhost:9222(同容器,不用改)  │
└──────────────────────────────────────────────────┘
  volume: browser_data/  ← 登录态持久化(关键!)
  volume: data/          ← 爬取结果 + 二维码
  volume: logs/          ← 日志
  port: 8765(MCP) 8080(API+WebUI)
```

---

## 三、代码改动(共 3 处,均小且向后兼容)

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 1 | `config/base_config.py` | 新增配置 | `DOCKER_MODE`(默认 False,环境变量 `MEDIACRAWLER_DOCKER=true` 覆盖)、`QRCODE_OUTPUT_DIR = "data/qrcode"` |
| 2 | `tools/crawler_util.py` `show_qrcode()` | 加分支 | Docker 模式下把带边框二维码 png 写到 `data/qrcode/login_<platform>_<ts>.png` 并 `logger.info` 路径;非 Docker 模式保持原 `Image.show()` 弹窗不变。**7 个平台共用此函数,一处改动全平台生效** |
| 3 | `tools/cdp_browser.py` | `localhost` 抽配置 | 新增 `CDP_DEBUG_HOST = "localhost"`,替换 `:296`、`:322` 两处硬编码。本方案用不上,为方案 B 留口子 |

**核心保证:宿主机非 Docker 使用方式完全不受影响**,只有 `DOCKER_MODE=true` 才走新分支。

---

## 四、新增文件

### 4.1 `Dockerfile`(多阶段)

```
阶段1 (frontend): node:20-alpine
  → webui/ npm ci + npm run build
  → 产物在 api/webui/

阶段2 (runtime): mcr.microsoft.com/playwright/python:v1.61.0-jammy
  → 自带浏览器系统依赖
  → apt 安装: xvfb、google-chrome-stable(CDP 用真实 Chrome)、supervisord
  → 装 uv, uv sync(锁定依赖)
  → COPY 项目代码 + 阶段1的 api/webui/ 产物
  → EXPOSE 8765 8080
  → CMD supervisord
```

镜像要点:
- 基础镜像自带 playwright 依赖,省去大量 apt 调试
- Xvfb 提供虚拟显示,Chrome 跑有头模式(反检测最接近本地)
- google-chrome-stable 是 CDP 模式用的真实浏览器,非 playwright 自带 chromium

### 4.2 `.dockerignore`

排除 `.venv/`、`node_modules/`、`data/`、`browser_data/`、`logs/`、`docs/`、`.git/`、`*.pyc` 等,控制镜像体积与上下文。

### 4.3 `docker/supervisord.conf`

管理 3 个常驻程序:
- `xvfb`:`Xvfb :99 -screen 0 1920x1080x24`
- `mcp`:`uv run python -m mcp_server`(8765)
- `api`:`uv run uvicorn api.main:app --host 0.0.0.0 --port 8080`

Chrome 不由 supervisord 管,由爬虫进程经 CDP 按需拉起(`tools/browser_launcher.py` 现有逻辑),`DISPLAY=:99` 通过环境变量注入。

### 4.4 `docker-compose.yml`(可选便利层)

```yaml
services:
  mediacrawler:
    build: .
    environment:
      MEDIACRAWLER_DOCKER: "true"
      DISPLAY: :99
    volumes:
      - ./browser_data:/app/browser_data
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8765:8765"
      - "8080:8080"
    shm_size: 2gb    # Chrome 必需,防 /dev/shm 不足崩溃
```

---

## 五、运行与登录流程

### 构建与启动
```bash
docker compose up -d --build
# 或纯 docker:docker build -t mediacrawler . && docker run ...
```

### 首次扫码登录(以小红书为例)
```bash
docker exec -it mc uv run main.py --platform xhs --lt qrcode --type search --keywords 测试
```
1. 日志提示:`二维码已保存到 data/qrcode/login_xhs_<ts>.png`
2. 宿主机直接打开挂载目录里的该文件扫码
3. 登录态自动写入 `browser_data` volume,后续爬取免登录

### 日常爬取
- MCP 客户端(Claude Code)连 `http://127.0.0.1:8765/mcp` 调 `crawl_*` 工具
- 或浏览器访问 `http://127.0.0.1:8080` 用 WebUI

---

## 六、明确的取舍(必须知晓)

| 事项 | 说明 |
|------|------|
| 反检测 | Xvfb 有头已最接近本地,但容器是 Linux + 干净 Chrome profile,指纹仍与本地真实 Chrome 有差异。小红书/抖音风控最严,仍可能需要首次手动过滑块(可通过挂 VNC 或首次本地登录后把 browser_data 拷进去解决) |
| 首次登录 | 必须人工扫码一次,之后靠 volume 续命 |
| shm | Chrome 在容器里必须给足 `shm_size`,否则渲染大页面会崩 |
| 方案 B 口子 | 已预留 `CDP_DEBUG_HOST`,未来可平滑升级到浏览器独立容器 |
| 镜像体积 | 预计 2.5~3.5GB(playwright 基础镜像 + Chrome + Python 依赖),属正常水平 |

---

## 七、验证标准(实施完成后逐项过)

1. **宿主机回归**:非 Docker 模式 `main.py` 扫码弹窗行为不变
2. **镜像构建**:`docker build` 零错误
3. **服务健康**:容器启动后 8765(MCP `/health`)与 8080(API)均通
4. **扫码登录**:容器内跑 login,二维码正确落文件,扫码后登录态写入 volume
5. **端到端爬取**:容器内完成一次爬取,数据落到挂载的 `data/`
6. **登录态复用**:删除容器重建(不删 volume),免二次扫码

---

## 八、改动范围评估

- **直接改动**:`config/base_config.py`(新增配置)、`tools/crawler_util.py`(show_qrcode 分支)、`tools/cdp_browser.py`(抽 CDP_DEBUG_HOST)
- **新增文件**:`Dockerfile`、`.dockerignore`、`docker/supervisord.conf`、`docker-compose.yml`
- **调用链影响**:`show_qrcode` 被 7 个平台 login.py 调用,改动向后兼容;CDP host 默认值不变
- **跨模块影响**:无 API/DB schema 变更;新增环境变量 `MEDIACRAWLER_DOCKER`、`DISPLAY`
- **风险等级:中**(涉及配置/工具/CDP 模块,但全部向后兼容,宿主机零回归是硬要求)
