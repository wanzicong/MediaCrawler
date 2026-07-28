from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MediaProbeResult:
    duration_ms: int = 0
    has_video: bool = False
    has_audio: bool = False
    format_name: str = ""


class MediaValidationError(RuntimeError):
    pass


async def probe_media(file_path: str | Path) -> MediaProbeResult:
    """Validate a downloaded media file using ffprobe when available."""
    path = Path(file_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise MediaValidationError(f"媒体文件不存在或为空: {path}")

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return MediaProbeResult()

    process = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise MediaValidationError(message or "ffprobe 无法解析媒体文件")

    payload = json.loads(stdout.decode("utf-8"))
    streams = payload.get("streams", [])
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    if not has_video and not has_audio:
        raise MediaValidationError("媒体文件不包含音频或视频流")

    duration_raw = payload.get("format", {}).get("duration", 0)
    try:
        duration_ms = max(int(float(duration_raw) * 1000), 0)
    except (TypeError, ValueError):
        duration_ms = 0
    return MediaProbeResult(
        duration_ms=duration_ms,
        has_video=has_video,
        has_audio=has_audio,
        format_name=payload.get("format", {}).get("format_name", ""),
    )
