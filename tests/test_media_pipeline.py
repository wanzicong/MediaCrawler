# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests\test_media_pipeline.py
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

import json
from pathlib import Path

import httpx
import pytest

from media_pipeline.downloader import MediaDownloader
from media_pipeline.models import TranscriptResult, TranscriptSegment
from media_pipeline.probe import MediaProbeResult
from media_pipeline.repository import MediaRepository
from media_pipeline.transcriber import TranscriptionManager, WhisperOptions


def _client_factory(handler):
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        kwargs.pop("proxy", None)
        return httpx.AsyncClient(transport=transport, **kwargs)

    return factory


async def _audio_probe(_path: str | Path) -> MediaProbeResult:
    return MediaProbeResult(
        duration_ms=1_250,
        has_audio=True,
        has_video=True,
        format_name="mov,mp4",
    )


@pytest.mark.asyncio
async def test_streaming_download_registers_media_asset(tmp_path: Path) -> None:
    payload = b"fake-mp4-content"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://example.test/video.mp4"
        return httpx.Response(
            200,
            headers={
                "content-type": "video/mp4",
                "content-length": str(len(payload)),
            },
            content=payload,
        )

    repository = MediaRepository(tmp_path / "registry.db")
    downloader = MediaDownloader(
        repository,
        output_dir=tmp_path / "media",
        retries=1,
        client_factory=_client_factory(handler),
        probe_func=_audio_probe,
    )

    result = await downloader.download(
        platform="dy",
        content_id="734567890",
        source_url="https://example.test/video.mp4",
        run_id="run-1",
    )

    media_path = Path(result.local_path)
    assert media_path.read_bytes() == payload
    assert not media_path.with_suffix(".mp4.part").exists()
    assert result.duration_ms == 1_250
    assert result.has_audio is True

    stored = await repository.get_asset(asset_id=result.asset_id)
    assert stored is not None
    assert stored.status == "downloaded"
    assert stored.run_id == "run-1"
    assert stored.file_size == len(payload)
    assert len(stored.sha256) == 64


@pytest.mark.asyncio
async def test_download_rejects_oversized_response_and_cleans_partial_file(
    tmp_path: Path,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "video/mp4",
                "content-length": str(2 * 1024 * 1024),
            },
            content=b"",
        )

    repository = MediaRepository(tmp_path / "registry.db")
    downloader = MediaDownloader(
        repository,
        output_dir=tmp_path / "media",
        max_size_mb=1,
        retries=1,
        client_factory=_client_factory(handler),
        probe_func=_audio_probe,
    )

    with pytest.raises(RuntimeError, match="媒体文件超过"):
        await downloader.download(
            platform="dy",
            content_id="too-large",
            source_url="https://example.test/large.mp4",
        )

    stored = await repository.get_asset(platform="dy", content_id="too-large")
    assert stored is not None
    assert stored.status == "failed"
    assert "超过" in stored.error_message
    assert not (tmp_path / "media" / "dy" / "too-large" / "source.mp4.part").exists()


class _FakeWhisperEngine:
    def transcribe(
        self,
        file_path: str,
        options: WhisperOptions,
    ) -> TranscriptResult:
        assert Path(file_path).is_file()
        assert options.model == "tiny"
        return TranscriptResult(
            language="zh",
            language_probability=0.99,
            duration_seconds=2.5,
            full_text="第一句\n第二句",
            segments=[
                TranscriptSegment(start=0.0, end=1.2, text="第一句"),
                TranscriptSegment(start=1.2, end=2.5, text="第二句"),
            ],
        )


@pytest.mark.asyncio
async def test_transcription_job_persists_text_json_and_subtitles(
    tmp_path: Path,
) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "media" / "dy" / "video-1" / "source.mp4"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"local media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="video-1",
        local_path=str(media_file),
        mime_type="video/mp4",
        file_size=media_file.stat().st_size,
        has_audio=True,
        status="downloaded",
    )
    manager = TranscriptionManager(
        repository,
        engine_factory=_FakeWhisperEngine,
    )
    options = WhisperOptions(model="tiny", device="cpu", compute_type="int8")

    job = await manager.enqueue_asset(asset, options, wait=True)

    assert job.status == "completed"
    assert job.full_text == "第一句\n第二句"
    assert json.loads(job.segments_json)[1]["text"] == "第二句"
    output_dir = Path(job.transcript_path).parent
    assert output_dir == media_file.parent / "transcripts" / job.job_id
    assert (output_dir / "transcript.txt").read_text(encoding="utf-8") == job.full_text
    assert '"language": "zh"' in (output_dir / "transcript.json").read_text(
        encoding="utf-8"
    )
    assert "00:00:00,000 --> 00:00:01,200" in (output_dir / "transcript.srt").read_text(
        encoding="utf-8"
    )
    assert (
        (output_dir / "transcript.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    )

    duplicate = await manager.enqueue_asset(asset, options, wait=False)
    assert duplicate.job_id == job.job_id
    assert duplicate.status == "completed"


@pytest.mark.asyncio
async def test_transcription_rejects_video_without_audio(tmp_path: Path) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="silent-video",
        local_path=str(tmp_path / "silent.mp4"),
        status="downloaded",
        has_audio=False,
    )
    manager = TranscriptionManager(repository, engine_factory=_FakeWhisperEngine)

    with pytest.raises(ValueError, match="不包含音频流"):
        await manager.enqueue_asset(asset, WhisperOptions(model="tiny"))
