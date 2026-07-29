# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests\test_mcp_media.py
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

import inspect
import json
from pathlib import Path

import pytest

from mcp_server import server
from mcp_server.crawler_runner import CrawlResult
from media_pipeline.models import TranscriptResult, TranscriptSegment
from media_pipeline.repository import MediaRepository
from media_pipeline.transcriber import TranscriptionManager


class _FakeWhisperEngine:
    def transcribe(self, _file_path, _options):
        return TranscriptResult(
            language="zh",
            language_probability=1.0,
            duration_seconds=1.0,
            full_text="MCP 转写成功",
            segments=[TranscriptSegment(start=0.0, end=1.0, text="MCP 转写成功")],
        )


def test_generated_crawl_tool_exposes_media_options() -> None:
    signature = inspect.signature(server._make_crawl_tool("dy", "抖音"))
    assert signature.parameters["download_media"].default is False
    assert signature.parameters["transcribe_media"].default is False
    assert signature.parameters["transcription_backend"].default == "api"
    assert signature.parameters["transcription_model"].default == "small"
    assert signature.parameters["transcription_language"].default == "auto"


@pytest.mark.asyncio
async def test_crawl_downloads_then_schedules_background_transcription(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "dy" / "123" / "source.mp4"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"media")
    manager = TranscriptionManager(repository, engine_factory=_FakeWhisperEngine)
    captured: dict[str, object] = {}

    async def fake_run_crawler(**kwargs):
        captured.update(kwargs)
        await repository.upsert_asset(
            platform="dy",
            content_id="123",
            source_url="https://example.test/video.mp4",
            local_path=str(media_file),
            mime_type="video/mp4",
            file_size=media_file.stat().st_size,
            duration_ms=1_000,
            has_audio=True,
            status="downloaded",
            run_id=str(kwargs["media_run_id"]),
        )
        return CrawlResult(returncode=0, stdout="done", stderr="", success=True)

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
    monkeypatch.setattr(server, "MCP_RUNS_DIR", tmp_path / "mcp_runs")
    monkeypatch.setattr(server, "get_media_repository", lambda: repository)
    monkeypatch.setattr(server, "get_transcription_manager", lambda: manager)
    monkeypatch.setattr(
        server,
        "get_data_summary",
        lambda *_args, **_kwargs: {"files": {}},
    )

    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="detail",
            specified_id="123",
            transcribe_media=True,
            transcription_backend="local",
            transcription_model="tiny",
            transcription_language="zh",
        )
    )

    assert response["success"] is True
    assert len(response["media_assets"]) == 1
    assert len(response["transcription_jobs"]) == 1
    assert captured["download_media"] is True
    assert captured["transcribe_media"] is False
    assert captured["whisper_backend"] == "local"
    assert captured["timeout"] == 900
    assert str(captured["media_run_id"]).startswith("media_")

    task_id = response["transcription_jobs"][0]["job_id"]
    task = manager._tasks.get(task_id)
    if task:
        await task
    stored_job = await repository.get_job(task_id)
    assert stored_job is not None
    assert stored_job.status == "completed"


@pytest.mark.asyncio
async def test_mcp_media_tools_list_status_and_read_transcript(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "dy" / "456" / "source.mp4"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="456",
        local_path=str(media_file),
        mime_type="video/mp4",
        file_size=media_file.stat().st_size,
        has_audio=True,
        status="downloaded",
        run_id="run-456",
    )
    manager = TranscriptionManager(repository, engine_factory=_FakeWhisperEngine)
    monkeypatch.setattr(server, "get_media_repository", lambda: repository)
    monkeypatch.setattr(server, "get_transcription_manager", lambda: manager)

    listed = json.loads(await server.list_media_assets(platform="dy"))
    assert listed["success"] is True
    assert listed["assets"][0]["content_id"] == "456"

    scheduled = json.loads(
        await server.transcribe_downloaded_media(
            platform="dy",
            content_id="456",
            backend="local",
            model="tiny",
            wait=True,
        )
    )
    task_id = scheduled["job"]["job_id"]

    status = json.loads(await server.get_media_task_status(task_id))
    assert status["job"]["status"] == "completed"

    transcript = json.loads(
        await server.read_media_transcript(
            platform="dy",
            content_id="456",
            output_format="json",
            task_id=task_id,
        )
    )
    assert transcript["success"] is True
    assert transcript["content"]["full_text"] == "MCP 转写成功"
    assert transcript["content"]["segments"][0]["text"] == "MCP 转写成功"
    assert scheduled["asset"]["id"] == asset.id

    subtitle = json.loads(
        await server.read_media_transcript(
            platform="dy",
            content_id="456",
            output_format="srt",
            task_id=task_id,
        )
    )
    assert subtitle["success"] is True
    assert "MCP 转写成功" in subtitle["content"]
    assert "-->" in subtitle["content"]
