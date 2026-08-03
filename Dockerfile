# MediaCrawler 一体化镜像:爬虫 + MCP 服务 + API/WebUI + Xvfb 有头 Chrome
# 构建:docker build -t mediacrawler .
# 运行:见 docker-compose.yml 或 docs/Docker化部署设计方案.md

# ---------- 阶段 1:构建 WebUI 前端 ----------
FROM node:20-alpine AS frontend
# npm 走 npmmirror 国内镜像,无需代理
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
WORKDIR /build/webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci
COPY webui/ ./
# 产物输出到 api/webui/(由 vite 配置决定),供 FastAPI 托管
RUN npm run build

# ---------- 阶段 2:运行时 ----------
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

# 构建期代理(可选;默认空,通过 --build-arg 注入;不配也能用国内源跑通)
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY="localhost,127.0.0.1"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    DISPLAY=:99 \
    MEDIACRAWLER_DOCKER=true

# apt 换阿里云镜像(jammy 是 22.04 LTS);uv/pip 换阿里云 PyPI;Chrome 从 npmmirror 下载(替代 dl.google.com)
RUN sed -i 's@archive.ubuntu.com@mirrors.aliyun.com@g; s@security.ubuntu.com@mirrors.aliyun.com@g' /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        supervisor \
        wget \
        gnupg \
        ca-certificates \
        fonts-noto-cjk \
        curl \
        x11vnc \
        novnc \
        websockify \
    && wget -q -O /tmp/chrome-linux64.zip https://registry.npmmirror.com/-/binary/chrome-for-testing/141.0.7390.65/linux64/chrome-linux64.zip \
    && apt-get install -y --no-install-recommends unzip \
    && unzip -q /tmp/chrome-linux64.zip -d /opt/ \
    && mv /opt/chrome-linux64 /opt/chrome \
    && ln -sf /opt/chrome/chrome /usr/local/bin/google-chrome \
    # playwright channel="chrome" 固定从 /opt/google/chrome/chrome 查找,建符号链接兼容
    && mkdir -p /opt/google/chrome \
    && ln -sf /opt/chrome/chrome /opt/google/chrome/chrome \
    && rm -f /tmp/chrome-linux64.zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20(抖音/快手等平台的 execjs JS 签名运行时需要)。
# NodeSource 官方源在国外,改用 npmmirror 的 Node.js 二进制镜像直接解压(tar.gz 兼容性更好,无需 xz)
RUN wget -q -O /tmp/node.tar.gz https://registry.npmmirror.com/-/binary/node/v20.18.1/node-v20.18.1-linux-x64.tar.gz \
    && tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 \
    && rm -f /tmp/node.tar.gz \
    && node -v && npm -v

# 安装 uv(用 pip 从阿里云 PyPI 装,替代 ghcr.io/astral-sh/uv 二进制)
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv \
    && uv --version

WORKDIR /app

# 先拷贝依赖声明,利用构建缓存;uv 走阿里云 PyPI 镜像
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/
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

EXPOSE 8765 8080 6080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
