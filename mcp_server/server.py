# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/mcp_server\server.py
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

"""MediaCrawler MCP Server 入口。

将 MediaCrawler 的 7 大平台爬虫能力封装为 MCP 工具。
抖音额外支持读取当前登录账号的点赞与收藏作品。
"""

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from media_pipeline import (
    WhisperOptions,
    get_media_repository,
    get_transcription_manager,
)

from .crawler_runner import run_crawler
from .data_reader import (
    READABLE_FILE_TYPES,
    get_data_summary,
    get_full_data,
)
from .runtime import parse_server_config

mcp = FastMCP("MediaCrawler")

# 支持的平台: 代号 -> 中文名
PLATFORMS: Dict[str, str] = {
    "xhs": "小红书",
    "dy": "抖音",
    "ks": "快手",
    "bili": "B站",
    "wb": "微博",
    "tieba": "贴吧",
    "zhihu": "知乎",
}

COMMON_CRAWLER_TYPES = ("search", "detail", "creator")
DOUYIN_PERSONAL_CRAWLER_TYPES = ("liked", "collected")
SUPPORTED_SAVE_FORMATS = (
    "jsonl",
    "json",
    "csv",
    "excel",
    "sqlite",
    "db",
    "mongodb",
    "postgres",
)
MCP_RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "mcp_runs"
_CRAWL_RUN_ID_PATTERN = re.compile(r"^crawl_[0-9a-f]{32}$")
MAX_READ_ITEMS = 1000
MAX_CRAWL_NOTES_COUNT = 1000


def _supported_crawler_types(platform: str) -> tuple[str, ...]:
    """返回指定平台可用的爬取模式。"""
    if platform == "dy":
        return COMMON_CRAWLER_TYPES + DOUYIN_PERSONAL_CRAWLER_TYPES
    return COMMON_CRAWLER_TYPES


def _collect_data_read_errors(data: Dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for details in data.get("files", {}).values():
        errors.extend(str(error) for error in details.get("errors", []))
    return errors


def _write_run_manifest(
    run_root: Path,
    *,
    crawl_run_id: str,
    platform: str,
    crawler_type: str,
    save_data_option: str,
    status: str,
    returncode: Optional[int] = None,
) -> None:
    """Write a privacy-safe manifest for one isolated MCP crawl."""
    manifest: Dict[str, Any] = {
        "version": 1,
        "crawl_run_id": crawl_run_id,
        "platform": platform,
        "crawler_type": crawler_type,
        "save_data_option": save_data_option,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if returncode is not None:
        manifest["returncode"] = returncode
    (run_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_run_manifest(crawl_run_id: str) -> tuple[Path, Dict[str, Any]]:
    if not _CRAWL_RUN_ID_PATTERN.fullmatch(crawl_run_id):
        raise ValueError("crawl_run_id 格式无效")
    run_root = (MCP_RUNS_DIR / crawl_run_id).resolve()
    runs_root = MCP_RUNS_DIR.resolve()
    if run_root.parent != runs_root:
        raise ValueError("crawl_run_id 路径无效")
    manifest_path = run_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("未找到该 crawl_run_id 的运行清单")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("crawl_run_id") != crawl_run_id
    ):
        raise ValueError("运行清单无效")
    return run_root, manifest


def _display_run_path(run_root: Path) -> str:
    project_root = Path(__file__).resolve().parent.parent
    try:
        return str(run_root.resolve().relative_to(project_root))
    except ValueError:
        return str(run_root.resolve())


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    """用于网络 MCP 服务的轻量健康检查。"""
    return JSONResponse(
        {
            "status": "ok",
            "service": "MediaCrawler MCP",
            "transport": "streamable-http",
        }
    )


async def _do_crawl(
    platform: str,
    cn_name: str,
    crawler_type: str,
    keywords: str = "",
    specified_id: str = "",
    creator_id: str = "",
    login_type: str = "qrcode",
    cookies: str = "",
    get_comment: Optional[bool] = None,
    get_sub_comment: bool = False,
    max_notes_count: int = 15,
    headless: bool = False,
    download_media: bool = False,
    transcribe_media: bool = False,
    transcription_backend: str = "api",
    transcription_model: str = "small",
    transcription_device: str = "auto",
    transcription_compute_type: str = "auto",
    transcription_language: str = "auto",
    word_timestamps: bool = False,
    save_data_option: str = "jsonl",
    return_data: bool = False,
) -> str:
    """统一的爬取执行逻辑，供各平台工具调用。"""
    # 参数校验
    if platform not in PLATFORMS:
        return json.dumps(
            {"success": False, "error": f"不支持的平台: {platform}"},
            ensure_ascii=False,
        )

    supported_types = _supported_crawler_types(platform)
    if crawler_type not in supported_types:
        supported_text = "/".join(supported_types)
        return json.dumps(
            {
                "success": False,
                "error": (f"{platform} 平台的 crawler_type 必须为 {supported_text}"),
            },
            ensure_ascii=False,
        )

    if crawler_type == "search" and not keywords:
        return json.dumps(
            {"success": False, "error": "search 模式必须提供 keywords"},
            ensure_ascii=False,
        )
    if crawler_type == "detail" and not specified_id:
        return json.dumps(
            {"success": False, "error": "detail 模式必须提供 specified_id"},
            ensure_ascii=False,
        )
    if crawler_type == "creator" and not creator_id:
        return json.dumps(
            {"success": False, "error": "creator 模式必须提供 creator_id"},
            ensure_ascii=False,
        )
    if login_type not in {"qrcode", "phone", "cookie"}:
        return json.dumps(
            {
                "success": False,
                "error": "login_type 必须为 qrcode/phone/cookie",
            },
            ensure_ascii=False,
        )
    if max_notes_count < 1:
        return json.dumps(
            {"success": False, "error": "max_notes_count 必须至少为 1"},
            ensure_ascii=False,
        )
    if max_notes_count > MAX_CRAWL_NOTES_COUNT:
        return json.dumps(
            {
                "success": False,
                "error_code": "MAX_NOTES_EXCEEDED",
                "error": (
                    "MCP 单次 max_notes_count 不能超过 "
                    f"{MAX_CRAWL_NOTES_COUNT}"
                ),
                "max_notes_count_limit": MAX_CRAWL_NOTES_COUNT,
            },
            ensure_ascii=False,
        )
    if save_data_option not in SUPPORTED_SAVE_FORMATS:
        return json.dumps(
            {
                "success": False,
                "error": (
                    f"不支持的 save_data_option: {save_data_option}，支持: "
                    f"{'/'.join(SUPPORTED_SAVE_FORMATS)}"
                ),
            },
            ensure_ascii=False,
        )
    if return_data and save_data_option not in READABLE_FILE_TYPES:
        return json.dumps(
            {
                "success": False,
                "error_code": "RETURN_DATA_UNSUPPORTED",
                "error": (
                    f"{save_data_option} 是共享数据库存储，无法可靠区分本次"
                    "运行写入的记录；请将 return_data 设为 false，或改用"
                    " jsonl/json/csv/excel"
                ),
                "return_data_supported_formats": sorted(READABLE_FILE_TYPES),
            },
            ensure_ascii=False,
        )

    crawl_run_id = f"crawl_{uuid.uuid4().hex}"
    run_root = MCP_RUNS_DIR / crawl_run_id
    run_root.mkdir(parents=True, exist_ok=False)
    _write_run_manifest(
        run_root,
        crawl_run_id=crawl_run_id,
        platform=platform,
        crawler_type=crawler_type,
        save_data_option=save_data_option,
        status="running",
    )

    media_run_id = (
        f"media_{uuid.uuid4().hex}" if download_media or transcribe_media else ""
    )
    personal_mode = crawler_type in DOUYIN_PERSONAL_CRAWLER_TYPES
    effective_get_comment = (
        not personal_mode if get_comment is None else get_comment
    )
    effective_get_sub_comment = get_sub_comment and effective_get_comment
    cookies = cookies.strip()
    effective_login_type = "cookie" if cookies else login_type
    # 硬超时传 0：关闭总时长上限，慢爬虫可跑任意久（不被误杀）。
    # 防"假死"由 crawler_runner 内部的软/空闲看门狗负责（进程完全无输出才 kill）。
    crawl_timeout = 0

    # MCP 中只同步等待下载。转写由 MCP 后台任务执行，避免长视频阻塞工具调用。
    try:
        result = await run_crawler(
            platform=platform,
            crawler_type=crawler_type,
            keywords=keywords,
            specified_id=specified_id,
            creator_id=creator_id,
            login_type=effective_login_type,
            cookies=cookies,
            get_comment=effective_get_comment,
            get_sub_comment=effective_get_sub_comment,
            max_notes_count=max_notes_count,
            headless=headless,
            download_media=download_media or transcribe_media,
            transcribe_media=False,
            whisper_backend=transcription_backend,
            media_run_id=media_run_id,
            save_data_option=save_data_option,
            save_data_path=str(run_root.resolve()),
            timeout=crawl_timeout,
        )
    except Exception as exc:
        _write_run_manifest(
            run_root,
            crawl_run_id=crawl_run_id,
            platform=platform,
            crawler_type=crawler_type,
            save_data_option=save_data_option,
            status="failed",
            returncode=-1,
        )
        return json.dumps(
            {
                "platform": platform,
                "platform_name": cn_name,
                "crawler_type": crawler_type,
                "crawl_run_id": crawl_run_id,
                "success": False,
                "returncode": -1,
                "error": f"启动爬取失败: {type(exc).__name__}",
            },
            ensure_ascii=False,
            indent=2,
        )

    _write_run_manifest(
        run_root,
        crawl_run_id=crawl_run_id,
        platform=platform,
        crawler_type=crawler_type,
        save_data_option=save_data_option,
        status="completed" if result.success else "failed",
        returncode=result.returncode,
    )

    response: Dict[str, Any] = {
        "platform": platform,
        "platform_name": cn_name,
        "crawler_type": crawler_type,
        "crawl_run_id": crawl_run_id,
        "success": result.success,
        "returncode": result.returncode,
        "storage": {
            "backend": save_data_option,
            "scope": (
                "isolated_run"
                if save_data_option in READABLE_FILE_TYPES
                else "shared_database"
            ),
            "run_path": _display_run_path(run_root),
        },
    }

    if not result.success:
        # 爬取失败，返回错误信息。错误信息可能在 stderr 也可能在 stdout，
        # 两侧都取尾部，让调用方看到真正的失败原因（比如 watchdog 超时）。
        def _tail(text: str, n: int = 30) -> str:
            if not text:
                return ""
            lines = [ln for ln in text.splitlines() if ln.strip()]
            return "\n".join(lines[-n:])

        stderr_tail = _tail(result.stderr)
        stdout_tail = _tail(result.stdout)
        # watchdog 标记优先露出
        if "[watchdog]" in stderr_tail or "[runner]" in stderr_tail:
            response["error"] = stderr_tail
        elif stderr_tail and stdout_tail:
            response["error"] = (
                f"--- stderr tail ---\n{stderr_tail}\n--- stdout tail ---\n{stdout_tail}"
            )
        else:
            response["error"] = stderr_tail or stdout_tail or result.summary()
        # 常见错误提示
        if (
            "登录" in (stderr_tail + stdout_tail)
            or "login" in (stderr_tail + stdout_tail).lower()
        ):
            response["hint"] = (
                f"可能需要先登录{cn_name}。请在 MediaCrawler 目录下手动执行: "
                f"uv run main.py --platform {platform} --lt qrcode --type search --keywords test "
                f"--headless false 完成扫码登录，登录态会保存到 browser_data/ 目录"
            )
        return json.dumps(response, ensure_ascii=False, indent=2)

    # 爬取成功，读取数据
    if save_data_option not in READABLE_FILE_TYPES:
        response["data_summary"] = {
            "files": {},
            "total_count": None,
            "note": (
                f"{save_data_option} 数据已写入共享数据库；为避免把历史记录"
                "误当成本次结果，MCP 不执行文件回读。"
            ),
        }
    elif return_data:
        response["data"] = get_full_data(
            platform,
            crawler_type,
            file_type=save_data_option,
            data_root=str(run_root),
        )
    else:
        response["data_summary"] = get_data_summary(
            platform,
            crawler_type,
            file_type=save_data_option,
            data_root=str(run_root),
        )

    if save_data_option in READABLE_FILE_TYPES:
        readback = response.get("data", response.get("data_summary", {}))
        read_errors = _collect_data_read_errors(readback)
        if read_errors:
            response["success"] = False
            response["partial"] = bool(readback.get("total_count", 0))
            response["error_code"] = "DATA_READ_ERROR"
            response["error"] = (
                "爬取进程已完成，但产物回读发现损坏或不支持的数据"
            )
            response["read_errors"] = read_errors[:20]

    if media_run_id:
        repository = get_media_repository()
        assets = await repository.list_assets(run_id=media_run_id, limit=500)
        response["media_run_id"] = media_run_id
        response["media_assets"] = [asset.to_dict() for asset in assets]
        if transcribe_media:
            manager = get_transcription_manager()
            options = WhisperOptions(
                backend=transcription_backend,
                model=transcription_model,
                device=transcription_device,
                compute_type=transcription_compute_type,
                language=transcription_language,
                word_timestamps=word_timestamps,
            )
            jobs = []
            for asset in assets:
                if asset.status != "downloaded" or not asset.has_audio:
                    continue
                try:
                    job = await manager.enqueue_asset(asset, options, wait=False)
                    jobs.append(job.to_dict())
                except Exception as exc:
                    jobs.append(
                        {
                            "asset_id": asset.id,
                            "status": "failed_to_schedule",
                            "error_message": str(exc),
                        }
                    )
            response["transcription_jobs"] = jobs

    # 附带 stdout + stderr 尾部日志（取更有内容的那一侧）
    def _tail(text: str, n: int = 10) -> str:
        if not text:
            return ""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines[-n:])

    stdout_tail = _tail(result.stdout)
    stderr_tail = _tail(result.stderr)
    response["log_tail"] = stdout_tail or stderr_tail
    response["stderr_tail"] = stderr_tail if stdout_tail else ""

    return json.dumps(response, ensure_ascii=False, indent=2)


def _make_crawl_tool(platform: str, cn_name: str):
    """为指定平台动态创建一个 MCP 爬取工具函数。"""

    async def crawl_tool(
        crawler_type: str,
        keywords: str = "",
        specified_id: str = "",
        creator_id: str = "",
        login_type: str = "qrcode",
        cookies: str = "",
        get_comment: Optional[bool] = None,
        get_sub_comment: bool = False,
        max_notes_count: int = 15,
        headless: bool = False,
        download_media: bool = False,
        transcribe_media: bool = False,
        transcription_backend: str = "api",
        transcription_model: str = "small",
        transcription_device: str = "auto",
        transcription_compute_type: str = "auto",
        transcription_language: str = "auto",
        word_timestamps: bool = False,
        save_data_option: str = "jsonl",
        return_data: bool = False,
    ) -> str:
        """爬取工具（由 _make_crawl_tool 动态生成，docstring 在注册时覆盖）。"""
        return await _do_crawl(
            platform=platform,
            cn_name=cn_name,
            crawler_type=crawler_type,
            keywords=keywords,
            specified_id=specified_id,
            creator_id=creator_id,
            login_type=login_type,
            cookies=cookies,
            get_comment=get_comment,
            get_sub_comment=get_sub_comment,
            max_notes_count=max_notes_count,
            headless=headless,
            download_media=download_media,
            transcribe_media=transcribe_media,
            transcription_backend=transcription_backend,
            transcription_model=transcription_model,
            transcription_device=transcription_device,
            transcription_compute_type=transcription_compute_type,
            transcription_language=transcription_language,
            word_timestamps=word_timestamps,
            save_data_option=save_data_option,
            return_data=return_data,
        )

    # 设置函数名和文档，FastMCP 依赖这些生成工具描述
    crawl_tool.__name__ = f"crawl_{platform}"
    supported_types = _supported_crawler_types(platform)
    mode_lines = [
        "  - search: 关键词搜索 (需提供 keywords)",
        "  - detail: 指定内容详情 (需提供 specified_id，逗号分隔的ID或URL)",
        "  - creator: 创作者主页 (需提供 creator_id，逗号分隔的ID或URL)",
    ]
    if platform == "dy":
        mode_lines.extend(
            [
                "  - liked: 当前登录抖音账号点赞的作品 (无需内容筛选参数)",
                "  - collected: 当前登录抖音账号收藏的作品 (无需内容筛选参数)",
            ]
        )
    modes_doc = "\n".join(mode_lines)
    supported_text = "|".join(supported_types)
    comment_default_doc = (
        "普通模式默认 True，个人模式默认 False"
        if platform == "dy"
        else "默认 True"
    )
    crawl_tool.__doc__ = (
        f"爬取【{cn_name}】({platform}) 的内容数据。\n\n"
        f"可用爬取模式 (crawler_type):\n{modes_doc}\n\n"
        f"参数:\n"
        f"  crawler_type: 爬取模式 {supported_text} (必填)\n"
        f"  keywords: 搜索关键词，多个用逗号分隔 (search 模式必填)\n"
        f"  specified_id: 内容ID/URL列表 (detail 模式必填)\n"
        f"  creator_id: 创作者ID/URL列表 (creator 模式必填)\n"
        f"  login_type: 登录方式 qrcode|phone|cookie (默认 qrcode)\n"
        f"  cookies: Cookie字符串 (可选；优先复用 browser_data 登录态，"
        f"避免敏感参数进入 MCP 客户端/模型日志)\n"
        f"  get_comment: 是否抓取评论 ({comment_default_doc})\n"
        f"  get_sub_comment: 是否抓取二级评论 (默认 False)\n"
        f"  max_notes_count: 最大爬取数量 (默认 15，MCP 单次上限 1000)\n"
        f"  headless: 是否无头模式 (默认 False，使用有头浏览器)\n"
        f"  download_media: 是否下载图片/视频 (默认 False)\n"
        f"  transcribe_media: 是否异步转写视频内容，开启后自动下载视频 (默认 False)\n"
        f"  transcription_backend: api|local (默认 api，API 失败自动回退本地)\n"
        f"  transcription_model: faster-whisper 模型 (默认 small)\n"
        f"  transcription_device: auto|cpu|cuda (默认 auto)\n"
        f"  transcription_compute_type: auto|int8|float16|int8_float16 (默认 auto)\n"
        f"  transcription_language: 语言代码或 auto (默认 auto)\n"
        f"  word_timestamps: 是否生成词级时间戳 (默认 False)\n"
        f"  save_data_option: 保存格式 "
        f"{'|'.join(SUPPORTED_SAVE_FORMATS)} (默认 jsonl)\n"
        f"  return_data: 是否返回本次运行数据；"
        f"jsonl/json/csv/excel 支持 (默认 False，只返回摘要和文件路径)\n\n"
        f"注意: 首次使用需先登录。若返回登录失败提示，请手动执行 "
        f"'uv run main.py --platform {platform} --lt qrcode --type search --keywords test --headless false' "
        f"扫码登录，登录态会自动保存。"
    )
    return crawl_tool


# 动态注册 7 个平台的爬取工具
for _platform, _cn_name in PLATFORMS.items():
    mcp.tool()(_make_crawl_tool(_platform, _cn_name))


@mcp.tool()
def list_platforms() -> str:
    """列出 MediaCrawler 支持的所有平台和爬取模式。

    返回各平台代号、中文名、各平台可用模式及模式说明。
    """
    info = {
        "platforms": [
            {
                "code": code,
                "name": name,
                "crawler_types": list(_supported_crawler_types(code)),
            }
            for code, name in PLATFORMS.items()
        ],
        "crawler_types": {
            "search": "关键词搜索 - 通过关键词搜索平台内容",
            "detail": "指定内容详情 - 通过内容ID/URL获取指定帖子/视频详情",
            "creator": "创作者主页 - 通过创作者ID/URL获取其作品列表",
            "liked": "抖音个人点赞 - 获取当前登录抖音账号点赞的作品",
            "collected": "抖音个人收藏 - 获取当前登录抖音账号收藏的作品",
        },
        "crawler_types_by_platform": {
            code: list(_supported_crawler_types(code)) for code in PLATFORMS
        },
        "login_types": {
            "qrcode": "二维码登录（默认）",
            "phone": "手机号登录",
            "cookie": "Cookie登录",
        },
        "save_formats": list(SUPPORTED_SAVE_FORMATS),
        "return_data_supported_formats": sorted(READABLE_FILE_TYPES),
        "run_isolation": (
            "每次 MCP 爬取使用独立运行目录，并返回 crawl_run_id；"
            "空结果不会回读以前任务的数据。"
        ),
        "tool_naming": "每个平台对应一个工具: crawl_{平台代号}，如 crawl_xhs / crawl_dy / crawl_bili",
        "usage_hint": (
            "首次使用前需先登录对应平台。"
            "登录方法: 在 MediaCrawler 目录执行 "
            "'uv run main.py --platform {平台} --lt qrcode --type search --keywords test --headless false'，"
            "扫码登录后登录态会保存到 browser_data/ 目录，后续 MCP 调用可复用。"
        ),
    }
    return json.dumps(info, ensure_ascii=False, indent=2)


@mcp.tool()
def read_crawl_data(
    platform: str = "",
    crawler_type: str = "",
    file_type: str = "",
    max_items: int = 200,
    crawl_run_id: str = "",
) -> str:
    """读取之前爬取产生的数据文件。

    用于在爬取完成后（return_data=False 时）按需读取完整数据。

    Args:
        platform: 平台代号；提供 crawl_run_id 时可省略
        crawler_type: 爬取类型；提供 crawl_run_id 时可省略
        file_type: jsonl/json/csv/excel；提供 crawl_run_id 时可省略
        max_items: 每类最多返回的条目数 (默认 200，最大 1000)
        crawl_run_id: crawl_* 工具返回的本次运行 ID（点赞/收藏必填）
    """
    if max_items < 1:
        return json.dumps(
            {
                "success": False,
                "error": "max_items 必须至少为 1",
            },
            ensure_ascii=False,
        )
    if max_items > MAX_READ_ITEMS:
        return json.dumps(
            {
                "success": False,
                "error_code": "MAX_ITEMS_EXCEEDED",
                "error": f"max_items 不能超过 {MAX_READ_ITEMS}",
                "max_items_limit": MAX_READ_ITEMS,
            },
            ensure_ascii=False,
        )

    data_root: Optional[str] = None
    if crawl_run_id:
        try:
            run_root, manifest = _load_run_manifest(crawl_run_id)
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            return json.dumps(
                {"success": False, "error": str(exc)},
                ensure_ascii=False,
            )

        manifest_platform = str(manifest.get("platform") or "")
        manifest_crawler_type = str(manifest.get("crawler_type") or "")
        manifest_file_type = str(manifest.get("save_data_option") or "")
        for supplied, recorded, field_name in (
            (platform, manifest_platform, "platform"),
            (crawler_type, manifest_crawler_type, "crawler_type"),
            (file_type, manifest_file_type, "file_type"),
        ):
            if supplied and supplied != recorded:
                return json.dumps(
                    {
                        "success": False,
                        "error": (
                            f"{field_name} 与 crawl_run_id 运行清单不一致"
                        ),
                    },
                    ensure_ascii=False,
                )
        if manifest.get("status") != "completed":
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        f"该运行状态为 {manifest.get('status', 'unknown')}，"
                        "只有 completed 运行可以读取"
                    ),
                },
                ensure_ascii=False,
            )
        platform = manifest_platform
        crawler_type = manifest_crawler_type
        file_type = manifest_file_type
        data_root = str(run_root)
    else:
        file_type = file_type or "jsonl"

    if (
        not crawl_run_id
        and platform == "dy"
        and crawler_type in DOUYIN_PERSONAL_CRAWLER_TYPES
    ):
        return json.dumps(
            {
                "success": False,
                "error": (
                    "读取抖音点赞/收藏数据必须提供 crawl_dy 返回的 "
                    "crawl_run_id，避免混合不同账号或历史任务。"
                ),
            },
            ensure_ascii=False,
        )

    if platform not in PLATFORMS:
        return json.dumps(
            {
                "success": False,
                "error": f"不支持的平台: {platform}，支持: {list(PLATFORMS.keys())}",
            },
            ensure_ascii=False,
        )
    supported_types = _supported_crawler_types(platform)
    if crawler_type not in supported_types:
        return json.dumps(
            {
                "success": False,
                "error": (
                    f"{platform} 平台的 crawler_type 必须为 "
                    f"{'/'.join(supported_types)}"
                ),
            },
            ensure_ascii=False,
        )
    if file_type not in READABLE_FILE_TYPES:
        return json.dumps(
            {
                "success": False,
                "error": (
                    f"{file_type or '空'} 不支持文件回读；支持: "
                    f"{'/'.join(sorted(READABLE_FILE_TYPES))}"
                ),
            },
            ensure_ascii=False,
        )

    data = get_full_data(
        platform,
        crawler_type,
        file_type=file_type,
        max_items=max_items,
        data_root=data_root,
    )
    read_errors = _collect_data_read_errors(data)
    if read_errors:
        return json.dumps(
            {
                "success": False,
                "partial": bool(data.get("total_count", 0)),
                "error_code": "DATA_READ_ERROR",
                "error": "数据产物包含损坏或不支持的记录",
                "read_errors": read_errors[:20],
                **({"crawl_run_id": crawl_run_id} if crawl_run_id else {}),
                **data,
            },
            ensure_ascii=False,
            indent=2,
        )
    if not data["files"]:
        if crawl_run_id:
            return json.dumps(
                {
                    "success": True,
                    "crawl_run_id": crawl_run_id,
                    **data,
                    "empty": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(
            {
                "success": False,
                "hint": f"未找到 {platform}/{crawler_type} 的 {file_type} 数据文件。"
                f"请先执行 crawl_{platform} 工具进行爬取。",
            },
            ensure_ascii=False,
            indent=2,
        )

    return json.dumps(
        {
            "success": True,
            **({"crawl_run_id": crawl_run_id} if crawl_run_id else {}),
            **data,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def list_media_assets(
    platform: str = "",
    content_id: str = "",
    media_run_id: str = "",
    status: str = "",
    limit: int = 100,
) -> str:
    """查询已经发现或下载的媒体资产，只返回元数据和本地路径。"""
    if platform and platform not in PLATFORMS:
        return json.dumps(
            {"success": False, "error": f"不支持的平台: {platform}"},
            ensure_ascii=False,
        )
    assets = await get_media_repository().list_assets(
        platform=platform,
        content_id=content_id,
        run_id=media_run_id,
        status=status,
        limit=limit,
    )
    return json.dumps(
        {
            "success": True,
            "count": len(assets),
            "assets": [asset.to_dict() for asset in assets],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def transcribe_downloaded_media(
    platform: str,
    content_id: str,
    backend: str = "api",
    model: str = "small",
    device: str = "auto",
    compute_type: str = "auto",
    language: str = "auto",
    word_timestamps: bool = False,
    wait: bool = False,
) -> str:
    """为已下载的视频创建转写任务，默认 API 优先且失败回退本地。"""
    if platform not in PLATFORMS:
        return json.dumps(
            {"success": False, "error": f"不支持的平台: {platform}"},
            ensure_ascii=False,
        )
    repository = get_media_repository()
    asset = await repository.get_asset(platform=platform, content_id=content_id)
    if asset is None:
        return json.dumps(
            {"success": False, "error": "未找到已下载的媒体资产"},
            ensure_ascii=False,
        )
    try:
        job = await get_transcription_manager().enqueue_asset(
            asset,
            WhisperOptions(
                backend=backend,
                model=model,
                device=device,
                compute_type=compute_type,
                language=language,
                word_timestamps=word_timestamps,
            ),
            wait=wait,
        )
    except Exception as exc:
        return json.dumps(
            {"success": False, "error": str(exc), "asset": asset.to_dict()},
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(
        {"success": True, "asset": asset.to_dict(), "job": job.to_dict()},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def get_media_task_status(task_id: str) -> str:
    """查询视频转写任务状态。"""
    job = await get_media_repository().get_job(task_id)
    if job is None:
        return json.dumps(
            {"success": False, "error": f"未找到任务: {task_id}"},
            ensure_ascii=False,
        )
    return json.dumps(
        {"success": True, "job": job.to_dict()},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def read_media_transcript(
    platform: str,
    content_id: str,
    output_format: str = "json",
    task_id: str = "",
) -> str:
    """读取视频转写结果，可按 task_id 读取指定版本。"""
    if output_format not in {"json", "text", "srt", "vtt"}:
        return json.dumps(
            {"success": False, "error": "output_format 必须为 json/text/srt/vtt"},
            ensure_ascii=False,
        )
    repository = get_media_repository()
    asset = await repository.get_asset(platform=platform, content_id=content_id)
    if asset is None:
        return json.dumps(
            {"success": False, "error": "未找到媒体资产"},
            ensure_ascii=False,
        )
    job = (
        await repository.get_job(task_id)
        if task_id
        else await repository.get_latest_job_for_asset(asset.id)
    )
    if job is not None and job.asset_id != asset.id:
        return json.dumps(
            {"success": False, "error": "指定任务不属于该媒体资产"},
            ensure_ascii=False,
        )
    if job is None or job.status != "completed":
        return json.dumps(
            {
                "success": False,
                "error": "转写尚未完成",
                "job": job.to_dict() if job else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    if output_format == "text":
        content: Any = job.full_text
    elif output_format == "json":
        content = {
            "full_text": job.full_text,
            "segments": json.loads(job.segments_json or "[]"),
        }
    else:
        if output_format == "srt" and job.subtitle_path:
            subtitle_path = Path(job.subtitle_path)
        elif job.transcript_path:
            subtitle_path = Path(job.transcript_path).with_name(
                f"transcript.{output_format}"
            )
        else:
            subtitle_path = (
                Path(asset.local_path).parent / f"transcript.{output_format}"
            )
        if not subtitle_path.is_file():
            return json.dumps(
                {"success": False, "error": f"字幕文件不存在: {subtitle_path}"},
                ensure_ascii=False,
            )
        content = subtitle_path.read_text(encoding="utf-8")
    return json.dumps(
        {
            "success": True,
            "platform": platform,
            "content_id": content_id,
            "format": output_format,
            "content": content,
        },
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> None:
    """MCP Server 入口，支持 stdio 与 Streamable HTTP。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        server_config = parse_server_config(argv)
    except ValueError as exc:
        raise SystemExit(f"MCP 配置错误: {exc}") from exc
    if server_config.transport == "stdio":
        mcp.run(transport="stdio")
        return

    mcp.settings.host = server_config.host
    mcp.settings.port = server_config.port
    mcp.settings.streamable_http_path = server_config.path
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=server_config.effective_allowed_hosts(),
        allowed_origins=list(server_config.allowed_origins),
    )
    app = mcp.streamable_http_app()
    uvicorn.run(
        app,
        host=server_config.host,
        port=server_config.port,
        log_level=mcp.settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
