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

# 基础配置
PLATFORM = "xhs"  # 平台，支持: xhs | dy | ks | bili | wb | tieba | zhihu
KEYWORDS = ""  # 关键词搜索配置，英文逗号分隔
LOGIN_TYPE = "qrcode"  # 登录方式: qrcode(二维码) or phone(手机号) or cookie
COOKIES = ""
CRAWLER_TYPE = (
    "search"  # 爬取类型，search(关键词搜索) | detail(帖子详情) | creator(创作者主页数据)
)
# 是否启用IP代理
ENABLE_IP_PROXY = False

# 代理IP池数量
IP_PROXY_POOL_COUNT = 2

# 代理IP服务商名称
IP_PROXY_PROVIDER_NAME = "kuaidaili"  # kuaidaili | wandouhttp

# 设置为True将不会打开浏览器（无头浏览器）
# 设置False将打开浏览器
# 如果小红书一直扫码登录失败，打开浏览器手动通过滑动验证
# 如果抖音一直提示失败，打开浏览器查看扫码后是否出现手机号验证，如果出现手动通过后重试
HEADLESS = False

# 是否保存登录状态
SAVE_LOGIN_STATE = True

# ==================== CDP (Chrome DevTools Protocol) 配置 ====================
# 是否启用CDP模式 - 使用用户现有的Chrome/Edge浏览器进行爬取，提供更好的反检测能力
# 启用后，系统会自动检测并启动用户的Chrome/Edge浏览器，通过CDP协议进行控制
# 此方式使用真实浏览器环境，包括用户的扩展程序、cookie和设置，大大降低被检测的风险
ENABLE_CDP_MODE = True

# CDP调试端口，用于与浏览器通信
# 如果端口被占用，系统会自动尝试下一个可用端口
CDP_DEBUG_PORT = 9222

# 自定义浏览器路径（可选）
# 如果为空，系统将自动检测Chrome/Edge的安装路径
# Windows示例: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# macOS示例: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CUSTOM_BROWSER_PATH = ""

# CDP模式下是否启用无头模式
# 注意：即使设置为True，某些反检测功能在无头模式下可能效果不佳
CDP_HEADLESS = False

# 浏览器启动超时时间（秒）
BROWSER_LAUNCH_TIMEOUT = 60

# 程序结束时是否自动关闭浏览器
# 设置为False保持浏览器运行，方便调试
AUTO_CLOSE_BROWSER = True

# 数据保存类型配置，支持: csv, db, json, jsonl, sqlite, excel, postgres。最好保存到DB，具有去重功能
SAVE_DATA_OPTION = "jsonl"  # csv or db or json or jsonl or sqlite or excel or postgres

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

# 是否启用爬取媒体模式（包括图片或视频资源），默认不启用媒体爬取
ENABLE_GET_MEIDAS = False

# 是否启用评论爬取模式，默认启用评论爬取
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
