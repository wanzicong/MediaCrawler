from __future__ import annotations

import asyncio
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import aiofiles
import httpx

import config
from tools.httpx_util import make_async_client

from .probe import MediaProbeResult, probe_media
from .repository import MediaRepository


@dataclass
class DownloadResult:
    asset_id: int
    local_path: str
    file_size: int
    sha256: str
    duration_ms: int
    has_audio: bool
    reused: bool = False


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned[:180] or hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


async def _sha256_file(path: Path) -> str:
    def calculate() -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    return await asyncio.to_thread(calculate)


async def register_local_media(
    repository: MediaRepository,
    *,
    platform: str,
    content_id: str,
    local_path: str | Path,
    source_url: str = "",
    run_id: str = "",
) -> DownloadResult:
    """Register a media file written by a legacy platform downloader."""
    path = Path(local_path).resolve()
    probe = await probe_media(path)
    digest = await _sha256_file(path)
    asset = await repository.upsert_asset(
        platform=platform,
        content_id=str(content_id),
        source_url=source_url,
        local_path=str(path),
        mime_type="video/mp4",
        file_size=path.stat().st_size,
        sha256=digest,
        duration_ms=probe.duration_ms,
        has_audio=probe.has_audio,
        status="downloaded",
        run_id=run_id,
    )
    return DownloadResult(
        asset_id=asset.id,
        local_path=asset.local_path,
        file_size=asset.file_size,
        sha256=asset.sha256,
        duration_ms=asset.duration_ms,
        has_audio=asset.has_audio,
    )


class MediaDownloader:
    """Streaming, size-limited and atomically committed media downloader."""

    def __init__(
        self,
        repository: MediaRepository,
        *,
        output_dir: str | Path | None = None,
        max_size_mb: int | None = None,
        timeout_seconds: int | None = None,
        retries: int | None = None,
        client_factory: Callable[..., httpx.AsyncClient] = make_async_client,
        probe_func: Callable[[str | Path], Any] = probe_media,
    ):
        self.repository = repository
        self.output_dir = Path(output_dir or config.MEDIA_OUTPUT_DIR)
        self.max_bytes = int(max_size_mb or config.MEDIA_MAX_SIZE_MB) * 1024 * 1024
        self.timeout_seconds = int(timeout_seconds or config.MEDIA_DOWNLOAD_TIMEOUT)
        self.retries = max(int(retries if retries is not None else config.MEDIA_DOWNLOAD_RETRIES), 1)
        self.client_factory = client_factory
        self.probe_func = probe_func

    async def download(
        self,
        *,
        platform: str,
        content_id: str,
        source_url: str,
        headers: dict[str, str] | None = None,
        proxy: str | None = None,
        run_id: str = "",
        overwrite: bool = False,
        extension: str = ".mp4",
    ) -> DownloadResult:
        safe_platform = _safe_component(platform)
        safe_content_id = _safe_component(content_id)
        suffix = extension if extension.startswith(".") else f".{extension}"
        asset_dir = self.output_dir / safe_platform / safe_content_id
        final_path = asset_dir / f"source{suffix}"
        partial_path = asset_dir / f"source{suffix}.part"
        asset_dir.mkdir(parents=True, exist_ok=True)

        if final_path.exists() and final_path.stat().st_size > 0 and not overwrite:
            probe = await self.probe_func(final_path)
            digest = await _sha256_file(final_path)
            asset = await self.repository.upsert_asset(
                platform=platform,
                content_id=content_id,
                source_url=source_url,
                local_path=str(final_path.resolve()),
                mime_type="video/mp4",
                file_size=final_path.stat().st_size,
                sha256=digest,
                duration_ms=probe.duration_ms,
                has_audio=probe.has_audio,
                status="downloaded",
                run_id=run_id,
            )
            return DownloadResult(
                asset_id=asset.id,
                local_path=asset.local_path,
                file_size=asset.file_size,
                sha256=asset.sha256,
                duration_ms=asset.duration_ms,
                has_audio=asset.has_audio,
                reused=True,
            )

        await self.repository.upsert_asset(
            platform=platform,
            content_id=content_id,
            source_url=source_url,
            local_path=str(final_path.resolve()),
            status="downloading",
            run_id=run_id,
        )

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                result = await self._download_once(
                    source_url=source_url,
                    partial_path=partial_path,
                    final_path=final_path,
                    headers=headers,
                    proxy=proxy,
                )
                asset = await self.repository.upsert_asset(
                    platform=platform,
                    content_id=content_id,
                    source_url=source_url,
                    local_path=str(final_path.resolve()),
                    mime_type=result["mime_type"],
                    file_size=result["file_size"],
                    sha256=result["sha256"],
                    duration_ms=result["probe"].duration_ms,
                    has_audio=result["probe"].has_audio,
                    status="downloaded",
                    run_id=run_id,
                )
                return DownloadResult(
                    asset_id=asset.id,
                    local_path=asset.local_path,
                    file_size=asset.file_size,
                    sha256=asset.sha256,
                    duration_ms=asset.duration_ms,
                    has_audio=asset.has_audio,
                )
            except Exception as exc:
                last_error = exc
                partial_path.unlink(missing_ok=True)
                if attempt < self.retries:
                    await asyncio.sleep(min(2**attempt, 5))

        message = str(last_error or "unknown download error")
        await self.repository.upsert_asset(
            platform=platform,
            content_id=content_id,
            source_url=source_url,
            local_path=str(final_path.resolve()),
            status="failed",
            error_message=message,
            run_id=run_id,
        )
        raise RuntimeError(f"媒体下载失败: {message}") from last_error

    async def _download_once(
        self,
        *,
        source_url: str,
        partial_path: Path,
        final_path: Path,
        headers: dict[str, str] | None,
        proxy: str | None,
    ) -> dict[str, Any]:
        digest = hashlib.sha256()
        total = 0
        timeout = httpx.Timeout(self.timeout_seconds)
        client_kwargs: dict[str, Any] = {
            "headers": headers,
            "follow_redirects": True,
            "timeout": timeout,
        }
        if proxy:
            client_kwargs["proxy"] = proxy

        async with self.client_factory(**client_kwargs) as client:
            async with client.stream("GET", source_url) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.max_bytes:
                    raise ValueError(f"媒体文件超过 {self.max_bytes} 字节限制")
                mime_type = response.headers.get("content-type", "").split(";", 1)[0]
                if mime_type and not (
                    mime_type.startswith("video/")
                    or mime_type.startswith("audio/")
                    or mime_type == "application/octet-stream"
                ):
                    raise ValueError(f"响应不是媒体内容: {mime_type}")

                async with aiofiles.open(partial_path, "wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise ValueError(f"媒体文件超过 {self.max_bytes} 字节限制")
                        digest.update(chunk)
                        await output.write(chunk)

        if total <= 0:
            raise ValueError("下载结果为空")
        probe: MediaProbeResult = await self.probe_func(partial_path)
        os.replace(partial_path, final_path)
        return {
            "file_size": total,
            "sha256": digest.hexdigest(),
            "mime_type": mime_type or "application/octet-stream",
            "probe": probe,
        }
