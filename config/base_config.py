# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import math
import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 必须是 true/false、1/0、yes/no 或 on/off")


def _env_positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} 必须是大于 0 的有限数字")
    return value


def _env_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0")
    return value


# Basic configuration
PLATFORM = "xhs"  # Platform, xhs | dy | ks | bili | wb | tieba | zhihu

# 是否使用海外版小红书 (rednote.com)
# 开启后 API 走 webapi.rednote.com，cookie 域使用 .rednote.com
XHS_INTERNATIONAL = False

KEYWORDS = (
    "编程副业,编程兼职"  # Keyword search configuration, separated by English commas
)
LOGIN_TYPE = "qrcode"  # qrcode or phone or cookie
COOKIES = ""
CRAWLER_TYPE = "search"  # search | detail | creator | liked (Douyin) | collected (Douyin)
# Whether to enable IP proxy
ENABLE_IP_PROXY = False

# 代理IP池数量
IP_PROXY_POOL_COUNT = 2

# Proxy IP provider name
IP_PROXY_PROVIDER_NAME = "kuaidaili"  # kuaidaili | wandouhttp | static

# Static proxy configuration (used when IP_PROXY_PROVIDER_NAME is set to "static")
# Format: "http://your_home_domain:port" or "http://user:password@your_home_domain:port"
STATIC_PROXY_URL = ""

# 设置为True将不会打开浏览器（无头浏览器）
# 设置False将打开浏览器
# 如果小红书一直扫码登录失败，打开浏览器手动通过滑动验证
# 如果抖音一直提示失败，打开浏览器查看扫码后是否出现手机号验证，如果出现手动通过后重试
HEADLESS = False

# 是否保存登录状态
SAVE_LOGIN_STATE = True

# ==================== CDP (Chrome DevTools Protocol) 配置 ====================
# 是否启用 CDP 模式 - 使用用户本地的 Chrome/Edge 浏览器进行爬取，具有更好的反检测能力
# 开启后，会自动检测并启动用户的 Chrome/Edge 浏览器，通过 CDP 协议进行控制
# 该方式使用真实浏览器环境，包括用户的扩展、Cookie 和设置，大幅降低被风控检测的风险
ENABLE_CDP_MODE = True

# CDP 调试端口，用于与浏览器通信
# 如果端口被占用，系统会自动尝试下一个可用端口
CDP_DEBUG_PORT = 9222

# 自定义浏览器路径（可选）
# 如果为空，系统会自动检测 Chrome/Edge 的安装路径
# Windows 示例: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# macOS 示例: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CUSTOM_BROWSER_PATH = ""

# 是否在 CDP 模式下启用无头模式
# 注意：即使设置为 True，某些反检测功能在无头模式下可能无法正常工作
CDP_HEADLESS = False

# 浏览器启动超时时间（秒）
BROWSER_LAUNCH_TIMEOUT = 60

# 是否连接用户已打开的浏览器，而不是启动新的浏览器
# 开启后，程序会连接一个已经启用了远程调试的浏览器
# 用户需要在 Chrome 中开启远程调试：chrome://inspect/#remote-debugging
# 或者使用命令行参数启动 Chrome：--remote-debugging-port=9222
# 这种方式反检测效果最好，因为直接使用用户真实浏览器的所有 Cookie、扩展和浏览历史
CDP_CONNECT_EXISTING = False

# 程序结束时是否自动关闭浏览器
# 设置为False保持浏览器运行，方便调试
AUTO_CLOSE_BROWSER = True

# 数据保存类型配置，支持: csv, db, json, jsonl, sqlite, excel, postgres。最好保存到DB，具有去重功能
# 默认 sqlite：MediaCrawler SQLAlchemy ORM 支持零依赖落盘到 database/sqlite_tables.db。
SAVE_DATA_OPTION = "sqlite"  # csv or db or json or jsonl or sqlite or excel or postgres

# 数据保存路径，如果不指定默认为data文件夹
SAVE_DATA_PATH = ""

# 用户浏览器缓存的浏览器文件配置
USER_DATA_DIR = "%s_user_data_dir"  # %s将被替换为平台名称

# 开始爬取的页数，默认为第一页
START_PAGE = 1

# 控制爬取的视频/笔记数量
CRAWLER_MAX_NOTES_COUNT = 10

# 控制并发爬虫数量
MAX_CONCURRENCY_NUM = 1

# Whether to download media resources (images/videos). Disabled by default.
DOWNLOAD_MEDIA = False

# Backward-compatible alias for the historical misspelled setting.
# Use is_media_download_enabled() in new code so either setting remains effective.
ENABLE_GET_MEIDAS = False


def is_media_download_enabled() -> bool:
    return bool(DOWNLOAD_MEDIA or ENABLE_GET_MEIDAS)


# Media pipeline
MEDIA_RUN_ID = ""
MEDIA_OUTPUT_DIR = "data/media"
MEDIA_DOWNLOAD_TIMEOUT = 180
MEDIA_DOWNLOAD_RETRIES = 3
MEDIA_DOWNLOAD_CONCURRENCY = 2
MEDIA_MAX_SIZE_MB = 500

# Speech-to-text. Transcription implies media download.
TRANSCRIBE_MEDIA = False
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "api").strip().lower()
if WHISPER_BACKEND not in {"api", "local"}:
    raise ValueError("WHISPER_BACKEND 必须是 api 或 local")
WHISPER_MODEL = "small"
WHISPER_DEVICE = "auto"  # auto | cpu | cuda
WHISPER_COMPUTE_TYPE = "auto"  # auto | int8 | float16 | int8_float16
WHISPER_LANGUAGE = "auto"
WHISPER_VAD_FILTER = True
WHISPER_WORD_TIMESTAMPS = False
WHISPER_MODEL_DIR = ""
WHISPER_API_BASE_URL = os.getenv(
    "WHISPER_API_BASE_URL",
    "http://127.0.0.1:9000",
).strip()
WHISPER_API_KEY = os.getenv("WHISPER_API_KEY", "")
WHISPER_API_MODEL = os.getenv("WHISPER_API_MODEL", "whisper-1").strip()
if not WHISPER_API_MODEL:
    raise ValueError("WHISPER_API_MODEL 不能为空")
WHISPER_API_TIMEOUT = _env_positive_float("WHISPER_API_TIMEOUT", 1800)
WHISPER_API_FALLBACK_TO_LOCAL = _env_bool(
    "WHISPER_API_FALLBACK_TO_LOCAL",
    True,
)
WHISPER_API_TRUST_ENV = _env_bool("WHISPER_API_TRUST_ENV", False)
WHISPER_API_MODEL_VERSION = os.getenv("WHISPER_API_MODEL_VERSION", "").strip()
WHISPER_API_DEPLOYMENT_FINGERPRINT = os.getenv(
    "WHISPER_API_DEPLOYMENT_FINGERPRINT",
    "",
).strip()
WHISPER_API_CONCURRENCY = _env_positive_int("WHISPER_API_CONCURRENCY", 1)

# Whether to enable comment crawling mode. Comment crawling is enabled by default.
ENABLE_GET_COMMENTS = True

# 控制爬取的一级评论数量（单个视频/笔记）
CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 10

# 是否启用爬取二级评论模式，默认不启用二级评论爬取
# 如果旧版本项目使用db，需要参考schema/tables.sql第287行添加表字段
ENABLE_GET_SUB_COMMENTS = False

# 词云相关
# 是否启用生成评论词云
ENABLE_GET_WORDCLOUD = False
# 自定义词语及其分组
# 添加规则: xx:yy，其中xx是自定义添加的词语，yy是该词语所属的分组名称
CUSTOM_WORDS = {
    "零几": "年份",  # 将"零几"作为一个整体识别
    "高频词": "专业术语",  # 示例自定义词语
}

# 停用词文件路径
STOP_WORDS_FILE = "./docs/hit_stopwords.txt"

# 中文字体文件路径
FONT_PATH = "./docs/STZHONGS.TTF"

# 爬取间隔
CRAWLER_MAX_SLEEP_SEC = 3

# 是否禁用 SSL 证书验证。仅在使用企业代理、Burp Suite、mitmproxy 等会注入自签名证书的中间人代理时设为 True。
# 警告：禁用 SSL 验证将使所有流量暴露于中间人攻击风险，请勿在生产环境中开启。
DISABLE_SSL_VERIFY = False

from .bilibili_config import *
from .xhs_config import *
from .dy_config import *
from .ks_config import *
from .weibo_config import *
from .tieba_config import *
from .zhihu_config import *
