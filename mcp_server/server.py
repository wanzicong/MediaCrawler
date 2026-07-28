# -*- coding: utf-8 -*-
"""MediaCrawler MCP Server 入口。

将 MediaCrawler 的 7 大平台爬虫能力封装为 MCP 工具，
支持 search / detail / creator 三种爬取模式。
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

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
from .data_reader import get_data_summary, get_full_data
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
    get_comment: bool = True,
    get_sub_comment: bool = False,
    max_notes_count: int = 15,
    headless: bool = False,
    download_media: bool = False,
    transcribe_media: bool = False,
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
    if crawler_type not in ("search", "detail", "creator"):
        return json.dumps({"success": False, "error": "crawler_type 必须为 search/detail/creator"}, ensure_ascii=False)

    if crawler_type == "search" and not keywords:
        return json.dumps({"success": False, "error": "search 模式必须提供 keywords"}, ensure_ascii=False)
    if crawler_type == "detail" and not specified_id:
        return json.dumps({"success": False, "error": "detail 模式必须提供 specified_id"}, ensure_ascii=False)
    if crawler_type == "creator" and not creator_id:
        return json.dumps({"success": False, "error": "creator 模式必须提供 creator_id"}, ensure_ascii=False)

    media_run_id = f"media_{uuid.uuid4().hex}" if download_media or transcribe_media else ""

    # MCP 中只同步等待下载。转写由 MCP 后台任务执行，避免长视频阻塞工具调用。
    result = await run_crawler(
        platform=platform,
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
        download_media=download_media or transcribe_media,
        transcribe_media=False,
        media_run_id=media_run_id,
        save_data_option=save_data_option,
        timeout=900 if download_media or transcribe_media else 180,
    )

    response: Dict[str, Any] = {
        "platform": platform,
        "platform_name": cn_name,
        "crawler_type": crawler_type,
        "success": result.success,
        "returncode": result.returncode,
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
            response["error"] = f"--- stderr tail ---\n{stderr_tail}\n--- stdout tail ---\n{stdout_tail}"
        else:
            response["error"] = stderr_tail or stdout_tail or result.summary()
        # 常见错误提示
        if "登录" in (stderr_tail + stdout_tail) or "login" in (stderr_tail + stdout_tail).lower():
            response["hint"] = (
                f"可能需要先登录{cn_name}。请在 MediaCrawler 目录下手动执行: "
                f"uv run main.py --platform {platform} --lt qrcode --type search --keywords test "
                f"--headless false 完成扫码登录，登录态会保存到 browser_data/ 目录"
            )
        return json.dumps(response, ensure_ascii=False, indent=2)

    # 爬取成功，读取数据
    if return_data:
        data = get_full_data(platform, crawler_type, file_type=save_data_option)
        response["data"] = data
    else:
        summary = get_data_summary(platform, crawler_type, file_type=save_data_option)
        response["data_summary"] = summary

    if media_run_id:
        repository = get_media_repository()
        assets = await repository.list_assets(run_id=media_run_id, limit=500)
        response["media_run_id"] = media_run_id
        response["media_assets"] = [asset.to_dict() for asset in assets]
        if transcribe_media:
            manager = get_transcription_manager()
            options = WhisperOptions(
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
        get_comment: bool = True,
        get_sub_comment: bool = False,
        max_notes_count: int = 15,
        headless: bool = False,
        download_media: bool = False,
        transcribe_media: bool = False,
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
    crawl_tool.__doc__ = (
        f"爬取【{cn_name}】({platform}) 的内容数据。\n\n"
        f"三种爬取模式 (crawler_type):\n"
        f"  - search: 关键词搜索 (需提供 keywords)\n"
        f"  - detail: 指定内容详情 (需提供 specified_id，逗号分隔的ID或URL)\n"
        f"  - creator: 创作者主页 (需提供 creator_id，逗号分隔的ID或URL)\n\n"
        f"参数:\n"
        f"  crawler_type: 爬取模式 search|detail|creator (必填)\n"
        f"  keywords: 搜索关键词，多个用逗号分隔 (search 模式必填)\n"
        f"  specified_id: 内容ID/URL列表 (detail 模式必填)\n"
        f"  creator_id: 创作者ID/URL列表 (creator 模式必填)\n"
        f"  login_type: 登录方式 qrcode|phone|cookie (默认 qrcode)\n"
        f"  cookies: Cookie字符串 (cookie登录时使用)\n"
        f"  get_comment: 是否抓取评论 (默认 True)\n"
        f"  get_sub_comment: 是否抓取二级评论 (默认 False)\n"
        f"  max_notes_count: 最大爬取数量 (默认 15)\n"
        f"  headless: 是否无头模式 (默认 False，使用有头浏览器)\n"
        f"  download_media: 是否下载图片/视频 (默认 False)\n"
        f"  transcribe_media: 是否异步转写视频内容，开启后自动下载视频 (默认 False)\n"
        f"  transcription_model: faster-whisper 模型 (默认 small)\n"
        f"  transcription_device: auto|cpu|cuda (默认 auto)\n"
        f"  transcription_compute_type: auto|int8|float16|int8_float16 (默认 auto)\n"
        f"  transcription_language: 语言代码或 auto (默认 auto)\n"
        f"  word_timestamps: 是否生成词级时间戳 (默认 False)\n"
        f"  save_data_option: 保存格式 jsonl|json|csv|sqlite (默认 jsonl)\n"
        f"  return_data: 是否返回完整数据 (默认 False，只返回摘要和文件路径)\n\n"
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

    返回各平台代号、中文名，以及统一的爬取模式说明。
    """
    info = {
        "platforms": [{"code": k, "name": v} for k, v in PLATFORMS.items()],
        "crawler_types": {
            "search": "关键词搜索 - 通过关键词搜索平台内容",
            "detail": "指定内容详情 - 通过内容ID/URL获取指定帖子/视频详情",
            "creator": "创作者主页 - 通过创作者ID/URL获取其作品列表",
        },
        "login_types": {
            "qrcode": "二维码登录（默认）",
            "phone": "手机号登录",
            "cookie": "Cookie登录",
        },
        "save_formats": ["jsonl", "json", "csv", "sqlite", "db", "excel"],
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
    platform: str,
    crawler_type: str,
    file_type: str = "jsonl",
    max_items: int = 200,
) -> str:
    """读取之前爬取产生的数据文件。

    用于在爬取完成后（return_data=False 时）按需读取完整数据。

    Args:
        platform: 平台代号 (xhs/dy/ks/bili/wb/tieba/zhihu)
        crawler_type: 爬取类型 (search/detail/creator)
        file_type: 文件类型 (默认 jsonl)
        max_items: 每个文件最多返回的条目数 (默认 200)
    """
    if platform not in PLATFORMS:
        return json.dumps(
            {"success": False, "error": f"不支持的平台: {platform}，支持: {list(PLATFORMS.keys())}"},
            ensure_ascii=False,
        )

    data = get_full_data(platform, crawler_type, file_type=file_type, max_items=max_items)
    if not data["files"]:
        return json.dumps(
            {
                "success": False,
                "hint": f"未找到 {platform}/{crawler_type} 的 {file_type} 数据文件。"
                f"请先执行 crawl_{platform} 工具进行爬取。",
            },
            ensure_ascii=False,
            indent=2,
        )

    return json.dumps({"success": True, **data}, ensure_ascii=False, indent=2)


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
        {"success": True, "count": len(assets), "assets": [asset.to_dict() for asset in assets]},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def transcribe_downloaded_media(
    platform: str,
    content_id: str,
    model: str = "small",
    device: str = "auto",
    compute_type: str = "auto",
    language: str = "auto",
    word_timestamps: bool = False,
    wait: bool = False,
) -> str:
    """为已下载的视频创建 faster-whisper 转写任务。默认异步返回任务 ID。"""
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
) -> str:
    """读取视频转写结果，格式支持 json、text、srt、vtt。"""
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
    job = await repository.get_latest_job_for_asset(asset.id)
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
        transcript_dir = Path(job.transcript_path).parent
        subtitle_path = transcript_dir / f"transcript.{output_format}"
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
