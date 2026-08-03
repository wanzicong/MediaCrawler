# MediaCrawler 一体化镜像:爬虫 + MCP 服务 + API/WebUI + Xvfb 有头 Chrome
# 构建:docker build -t mediacrawler .
# 运行:见 docker-compose.yml 或 docs/Docker化部署设计方案.md

# ---------- 阶段 1:构建 WebUI 前端 ----------
FROM node:20-alpine AS frontend
WORKDIR /build/webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci
COPY webui/ ./
# 产物输出到 api/webui/(由 vite 配置决定),供 FastAPI 托管
RUN npm run build

# ---------- 阶段 2:运行时 ----------
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

# 构建期代理(仅构建时生效,通过 --build-arg 注入;不带值则空,不影响无代理环境)
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY="localhost,127.0.0.1"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    DISPLAY=:99 \
    MEDIACRAWLER_DOCKER=true

# 系统依赖:Xvfb(虚拟显示)、真实 Chrome(CDP 用)、supervisord(进程管理)、中文字体
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        supervisor \
        wget \
        gnupg \
        ca-certificates \
        fonts-noto-cjk \
        curl \
    && wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20(抖音/快手等平台的 execjs JS 签名运行时需要)。
# 用 NodeSource 官方源,单包可靠;不走 ubuntu 自带的旧版 nodejs/npm 依赖链。
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv(项目用 uv 管理依赖)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 先拷贝依赖声明,利用构建缓存
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# 安装与 uv 锁定 playwright 版本匹配的 chromium(标准模式 launch_persistent_context 需要;
# 基础镜像自带的浏览器对应旧版 playwright,uv sync 升级后会因版本不匹配报 "Executable doesn't exist")。
# 用 npmmirror 国内镜像加速;--with-deps 不需要(系统依赖基础镜像 playwright 已带齐)。
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
RUN uv run playwright install chromium

# 拷贝项目代码(先排除 api/webui,用下面的前端产物覆盖)
COPY . .
# 拷贝前端构建产物(覆盖 api/webui/)
COPY --from=frontend /build/api/webui ./api/webui

# 数据/登录态/日志目录(运行时挂载 volume)
RUN mkdir -p /app/data /app/browser_data /app/logs

COPY docker/supervisord.conf /etc/supervisor/conf.d/mediacrawler.conf

EXPOSE 8765 8080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
