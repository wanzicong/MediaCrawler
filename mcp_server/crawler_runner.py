# -*- coding: utf-8 -*-
"""通过 subprocess 调用 MediaCrawler 的 main.py，封装为异步接口。

抗卡死策略（任一缺失都会让 MCP 工具"假死"）：
  1. 用 threading + 同步 subprocess.Popen + 同步 read，完全绕开 asyncio 子进程流读取。
     这是因为 MCP server 跑在 Claude Code 的 stdio 上下文里，asyncio 默认
     ProactorEventLoop 上 read 子进程 stream 偶发"长时间不前进"现象（实测复现），
     会让 watchdog 误判为卡死。
  2. 心跳线程：每 HEARTBEAT_INTERVAL 秒通过 loop.call_soon_threadsafe 推进时间戳。
  3. 软超时：连续 PROGRESS_INTERVAL 秒心跳未推进 → kill。
  4. 硬超时兜底：到 timeout 秒强制 kill。
  5. PYTHONUNBUFFERED=1 + python -u 关闭 Python 输出缓冲。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

# MediaCrawler 项目根目录（mcp_server 的上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 默认硬超时 180 秒（3 分钟）。
DEFAULT_TIMEOUT = 180

# 软超时阈值：连续 180 秒心跳未推进 → 视为卡死，立即 kill。
PROGRESS_INTERVAL = 180
HEARTBEAT_INTERVAL = 30

# 单流最多保留的字节数。MediaCrawler 一跑能写 400+ KB 日志，
# 全带回给 MCP 调用方会让 JSON 响应膨胀到反序列化慢/失败。
MAX_BUFFER_BYTES = 256 * 1024
KEEP_TAIL_BYTES = 64 * 1024


@dataclass
class CrawlResult:
    """爬取结果"""

    returncode: int
    stdout: str
    stderr: str
    success: bool

    def summary(self) -> str:
        status = "成功" if self.success else f"失败(退出码 {self.returncode})"
        tail = "\n".join(self.stdout.strip().splitlines()[-20:]) if self.stdout else ""
        return f"[爬取{status}]\n{tail}"


async def run_crawler(
    platform: str,
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
    media_run_id: str = "",
    whisper_model: str = "small",
    whisper_device: str = "auto",
    whisper_compute_type: str = "auto",
    whisper_language: str = "auto",
    whisper_word_timestamps: bool = False,
    save_data_option: str = "jsonl",
    timeout: int = DEFAULT_TIMEOUT,
    on_log: Optional[Callable[[str], None]] = None,
) -> CrawlResult:
    """异步调用 MediaCrawler main.py 执行爬取，全程有 watchdog 防卡死。

    Args:
        platform: 平台代号 (xhs/dy/ks/bili/wb/tieba/zhihu)
        crawler_type: 爬取类型 (search/detail/creator)
        keywords: 搜索关键词（search 模式必填）
        specified_id: 内容ID/URL列表（detail 模式必填）
        creator_id: 创作者ID/URL列表（creator 模式必填）
        login_type: 登录方式 (qrcode/phone/cookie)
        cookies: Cookie 字符串
        get_comment: 是否抓取一级评论
        get_sub_comment: 是否抓取二级评论
        max_notes_count: 最大爬取数量
        headless: 是否无头模式，默认 False（使用有头浏览器）
        download_media: 是否下载图片和视频资源
        transcribe_media: 是否在爬虫进程内同步转写视频
        media_run_id: 媒体任务关联 ID
        save_data_option: 数据保存格式 (jsonl/json/csv/sqlite/db)
        timeout: 硬超时秒数
        on_log: 实时日志行回调（可选）
    """
    cmd = [
        sys.executable, "-u", "main.py",
        "--platform", platform,
        "--lt", login_type,
        "--type", crawler_type,
        "--headless", "true" if headless else "false",
        "--save_data_option", save_data_option,
        "--crawler_max_notes_count", str(max_notes_count),
        "--get_comment", "true" if get_comment else "false",
        "--get_sub_comment", "true" if get_sub_comment else "false",
        "--download_media", "true" if download_media or transcribe_media else "false",
        "--transcribe_media", "true" if transcribe_media else "false",
        "--whisper_model", whisper_model,
        "--whisper_device", whisper_device,
        "--whisper_compute_type", whisper_compute_type,
        "--whisper_language", whisper_language,
        "--whisper_word_timestamps", "true" if whisper_word_timestamps else "false",
    ]
    if media_run_id:
        cmd.extend(["--media_run_id", media_run_id])
    if keywords:
        cmd.extend(["--keywords", keywords])
    if specified_id:
        cmd.extend(["--specified_id", specified_id])
    if creator_id:
        cmd.extend(["--creator_id", creator_id])
    if cookies:
        cmd.extend(["--cookies", cookies])

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    # 创建子进程前 + 启动时间记录
    loop = asyncio.get_event_loop()

    def _blocking_run() -> CrawlResult:
        """在 ThreadPoolExecutor 里跑：进程启动 + 流读取 + watchdog 都在这里。

        这样 MCP server 主事件循环只 await 一个 future，**绝不会被同步 IO 阻塞**。
        watchdog 也在这里用纯 time.sleep() 不依赖事件循环。
        """
        state = {"last_activity": time.time()}

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )
        except Exception as e:
            return CrawlResult(
                returncode=-1,
                stdout="",
                stderr=f"启动爬虫失败: {e}",
                success=False,
            )

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        stdout_bytes = {"n": 0}
        stderr_bytes = {"n": 0}

        def _append_capped(sink: list[str], new_text: str, byte_counter: dict) -> None:
            sink.append(new_text)
            byte_counter["n"] += len(new_text.encode("utf-8", errors="replace"))
            if byte_counter["n"] > MAX_BUFFER_BYTES:
                joined = "".join(sink)
                sink.clear()
                sink.append(
                    f"\n... [已截断，前面 {byte_counter['n'] - KEEP_TAIL_BYTES} 字节被丢弃] ...\n"
                )
                sink.append(joined[-KEEP_TAIL_BYTES:])

        def _bump():
            # 纯共享 dict 写，没有线程安全问题（CPython dict 字节码原子）
            state["last_activity"] = time.time()

        def _read_thread(stream, sink: list[str], byte_counter: dict) -> None:
            """线程里同步读子进程 stream。Windows 上同步 read 比 asyncio Proactor 稳定。"""
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        return
                    text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
                    _append_capped(sink, text, byte_counter)
                    _bump()
                    if on_log and text:
                        try:
                            on_log(text.rstrip("\n"))
                        except Exception:
                            pass
            except Exception as e:
                try:
                    stderr_chunks.append(
                        f"\n[read thread] 异常: {type(e).__name__}: {e}\n"
                    )
                except Exception:
                    pass

        t_out = threading.Thread(
            target=_read_thread, args=(proc.stdout, stdout_chunks, stdout_bytes), daemon=True
        )
        t_err = threading.Thread(
            target=_read_thread, args=(proc.stderr, stderr_chunks, stderr_bytes), daemon=True
        )
        t_out.start()
        t_err.start()

        def _heartbeat_thread():
            while True:
                time.sleep(HEARTBEAT_INTERVAL)
                if proc.poll() is not None:
                    _bump()
                    return
                _bump()

        t_hb = threading.Thread(target=_heartbeat_thread, daemon=True)
        t_hb.start()

        # watchdog 主循环：纯阻塞 sleep + 检查 state。完全在 worker 线程内，
        # 不消耗 MCP server 的事件循环时间。
        start = time.time()
        while True:
            time.sleep(2)
            if proc.poll() is not None:
                break
            idle = time.time() - state["last_activity"]
            if idle > PROGRESS_INTERVAL:
                stderr_chunks.append(
                    f"\n[watchdog] {int(idle)}s 无活动，视为卡死并 kill "
                    f"(pid={proc.pid})\n"
                )
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                break
            if time.time() - start > timeout:
                stderr_chunks.append(
                    f"\n[watchdog] 硬超时 {timeout}s 到达，强制 kill (pid={proc.pid})\n"
                )
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                break

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        t_out.join(timeout=3)
        t_err.join(timeout=3)
        t_hb.join(timeout=1)

        returncode = proc.returncode if proc.returncode is not None else -1
        return CrawlResult(
            returncode=returncode,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            success=returncode == 0,
        )

    # 全部 IO 在 default ThreadPoolExecutor 里跑，事件循环只 await 一个 future。
    # 这从根本上避免 ProactorEventLoop "read 不前进" 的玄学。
    return await loop.run_in_executor(None, _blocking_run)
