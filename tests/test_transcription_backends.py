# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

import asyncio
import json
import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

import config
from media_pipeline.models import MediaAsset, TranscriptResult, TranscriptSegment
from media_pipeline.repository import MediaRepository
from media_pipeline.transcriber import (
    HybridWhisperEngine,
    TranscriptionManager,
    WhisperApiEngine,
    WhisperApiError,
    WhisperOptions,
)


def _client_factory(handler):
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        return httpx.Client(transport=transport, **kwargs)

    return factory


def _api_payload() -> dict:
    return {
        "language": "zh",
        "language_probability": 0.98,
        "duration": 2.5,
        "text": "第一句 第二句",
        "segments": [
            {
                "start": 0.0,
                "end": 1.2,
                "text": "第一句",
                "avg_logprob": -0.1,
                "no_speech_prob": 0.01,
            },
            {
                "start": 1.2,
                "end": 2.5,
                "text": "第二句",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.02,
            },
        ],
        "words": [
            {"word": "第一句", "start": 0.1, "end": 1.0, "probability": 0.95},
            {"word": "第二句", "start": 1.3, "end": 2.4},
        ],
    }


def _local_result(text: str = "本地回退成功") -> TranscriptResult:
    return TranscriptResult(
        language="zh",
        language_probability=1.0,
        duration_seconds=1.0,
        full_text=text,
        segments=[TranscriptSegment(start=0.0, end=1.0, text=text)],
        backend="local",
        resolved_model="small",
    )


def test_api_engine_sends_openai_multipart_and_parses_verbose_json(
    tmp_path: Path,
) -> None:
    media_file = tmp_path / "中文 视频.mp4"
    media_file.write_bytes(b"fake-media")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ("http://127.0.0.1:9000/v1/audio/transcriptions")
        assert request.headers["Authorization"] == "Bearer secret"
        body = request.read()
        assert b'name="file"; filename="' in body
        assert b'name="model"' in body and b"whisper-1" in body
        assert b'name="language"' in body and b"zh" in body
        assert b'name="response_format"' in body and b"verbose_json" in body
        assert body.count(b'name="timestamp_granularities[]"') == 2
        assert b"\r\n\r\nsegment\r\n" in body
        assert b"\r\n\r\nword\r\n" in body
        assert b"fake-media" in body
        return httpx.Response(200, json=_api_payload())

    engine = WhisperApiEngine(_client_factory(handler))
    result = engine.transcribe(
        str(media_file),
        WhisperOptions(
            backend="api",
            api_base_url="http://127.0.0.1:9000",
            api_key="secret",
            api_model="whisper-1",
            api_model_version="base",
            language="zh",
            word_timestamps=True,
        ),
    )

    assert result.backend == "api"
    assert result.resolved_model == "base"
    assert result.full_text == "第一句\n第二句"
    assert result.duration_seconds == 2.5
    assert result.segments[0].words[0]["word"] == "第一句"
    assert result.segments[1].words[0]["word"] == "第二句"


def test_api_engine_accepts_word_only_verbose_json(tmp_path: Path) -> None:
    media_file = tmp_path / "word-only.wav"
    media_file.write_bytes(b"audio")
    payload = {
        "language": "zh",
        "duration": 1.5,
        "text": "标准响应",
        "words": [
            {"word": "标准", "start": 0.0, "end": 0.7},
            {"word": "响应", "start": 0.8, "end": 1.5},
        ],
    }
    engine = WhisperApiEngine(
        _client_factory(lambda _request: httpx.Response(200, json=payload))
    )

    result = engine.transcribe(
        str(media_file),
        WhisperOptions(
            backend="api",
            api_base_url="http://127.0.0.1:9000",
            word_timestamps=True,
        ),
    )

    assert result.full_text == "标准响应"
    assert len(result.segments) == 1
    assert [word["word"] for word in result.segments[0].words] == [
        "标准",
        "响应",
    ]


def test_api_engine_omits_auto_language_and_accepts_silence(
    tmp_path: Path,
) -> None:
    media_file = tmp_path / "silence.wav"
    media_file.write_bytes(b"silence")

    def handler(request: httpx.Request) -> httpx.Response:
        assert b'name="language"' not in request.read()
        return httpx.Response(
            200,
            json={
                "language": "zh",
                "duration": 1.0,
                "text": "",
                "segments": [],
            },
        )

    result = WhisperApiEngine(_client_factory(handler)).transcribe(
        str(media_file),
        WhisperOptions(
            backend="api",
            api_base_url="http://127.0.0.1:9000/v1",
            language="auto",
        ),
    )

    assert result.backend == "api"
    assert result.language_probability == 0.0
    assert result.full_text == ""
    assert result.segments == []


def test_api_url_requires_https_outside_loopback() -> None:
    assert (
        WhisperApiEngine._transcriptions_url("https://whisper.example/v1")
        == "https://whisper.example/v1/audio/transcriptions"
    )
    assert (
        WhisperApiEngine._transcriptions_url("http://localhost:9000")
        == "http://localhost:9000/v1/audio/transcriptions"
    )
    with pytest.raises(WhisperApiError, match="必须使用 https"):
        WhisperApiEngine._transcriptions_url("http://192.0.2.10:9000")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"detail": "server error"}),
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={}),
        httpx.Response(
            200,
            json={
                "language": "zh",
                "duration": 1.0,
                "text": "",
                "words": {},
            },
        ),
    ],
)
def test_api_engine_rejects_http_and_contract_errors(
    tmp_path: Path,
    response: httpx.Response,
) -> None:
    media_file = tmp_path / "audio.wav"
    media_file.write_bytes(b"audio")
    engine = WhisperApiEngine(_client_factory(lambda _request: response))

    with pytest.raises(WhisperApiError):
        engine.transcribe(
            str(media_file),
            WhisperOptions(
                backend="api",
                api_base_url="http://127.0.0.1:9000",
            ),
        )


class _StaticEngine:
    def __init__(
        self,
        *,
        result: TranscriptResult | None = None,
        error: Exception | None = None,
    ):
        self.result = result
        self.error = error
        self.calls = 0

    def transcribe(self, _file_path: str, _options: WhisperOptions):
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class _CountingLocalEngine:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(
        self,
        _file_path: str,
        _options: WhisperOptions,
    ) -> TranscriptResult:
        self.calls += 1
        return _local_result(f"本地转写第 {self.calls} 次")


def test_hybrid_api_success_never_initializes_local() -> None:
    api = _StaticEngine(result=replace(_local_result("API 成功"), backend="api"))
    local = _StaticEngine(error=AssertionError("不应调用本地引擎"))
    engine = HybridWhisperEngine(lambda: api, lambda: local)

    result = engine.transcribe(
        "unused.mp4",
        WhisperOptions(backend="api", api_fallback_to_local=True),
    )

    assert result.full_text == "API 成功"
    assert api.calls == 1
    assert local.calls == 0


def test_hybrid_api_failure_falls_back_and_records_reason() -> None:
    api = _StaticEngine(error=WhisperApiError("connection refused"))
    local = _StaticEngine(result=_local_result())
    engine = HybridWhisperEngine(lambda: api, lambda: local)

    result = engine.transcribe(
        "unused.mp4",
        WhisperOptions(backend="api", api_fallback_to_local=True),
    )

    assert result.backend == "local"
    assert result.full_text == "本地回退成功"
    assert "connection refused" in result.fallback_reason
    assert api.calls == 1
    assert local.calls == 1


def test_hybrid_local_backend_skips_api() -> None:
    api = _StaticEngine(error=AssertionError("不应调用 API"))
    local = _StaticEngine(result=_local_result("仅本地"))
    engine = HybridWhisperEngine(lambda: api, lambda: local)

    result = engine.transcribe("unused.mp4", WhisperOptions(backend="local"))

    assert result.full_text == "仅本地"
    assert api.calls == 0
    assert local.calls == 1


def test_hybrid_can_disable_fallback() -> None:
    api = _StaticEngine(error=WhisperApiError("API failed"))
    local = _StaticEngine(error=AssertionError("不应调用本地引擎"))
    engine = HybridWhisperEngine(lambda: api, lambda: local)

    with pytest.raises(WhisperApiError, match="API failed"):
        engine.transcribe(
            "unused.mp4",
            WhisperOptions(backend="api", api_fallback_to_local=False),
        )
    assert local.calls == 0


def test_hybrid_does_not_hide_unexpected_programming_errors() -> None:
    api = _StaticEngine(error=AssertionError("adapter bug"))
    local = _StaticEngine(error=AssertionError("不应调用本地引擎"))
    engine = HybridWhisperEngine(lambda: api, lambda: local)

    with pytest.raises(AssertionError, match="adapter bug"):
        engine.transcribe(
            "unused.mp4",
            WhisperOptions(backend="api", api_fallback_to_local=True),
        )
    assert local.calls == 0


def test_hybrid_reports_both_api_and_local_errors() -> None:
    api = _StaticEngine(error=WhisperApiError("API failed"))
    local = _StaticEngine(error=RuntimeError("local failed"))
    engine = HybridWhisperEngine(lambda: api, lambda: local)

    with pytest.raises(RuntimeError, match="API 与本地转写均失败") as exc_info:
        engine.transcribe(
            "unused.mp4",
            WhisperOptions(backend="api", api_fallback_to_local=True),
        )

    assert "API failed" in str(exc_info.value)
    assert "local failed" in str(exc_info.value)


def test_options_hash_uses_semantic_backend_fields_but_not_secrets() -> None:
    local = WhisperOptions(
        backend="local",
        model="small",
        api_base_url="http://one.test",
        api_key="first-secret",
    )
    assert (
        local.stable_hash()
        == replace(
            local,
            api_base_url="http://two.test",
            api_key="second-secret",
            api_timeout=1,
        ).stable_hash()
    )

    api = replace(
        local,
        backend="api",
        api_base_url="http://one.test",
        api_model_version="base",
    )
    assert (
        api.stable_hash()
        == replace(
            api,
            api_key="another-secret",
            api_timeout=2,
        ).stable_hash()
    )
    assert (
        api.stable_hash()
        != replace(
            api,
            api_model_version="small",
        ).stable_hash()
    )
    assert api.stable_hash() != local.stable_hash()


@pytest.mark.asyncio
async def test_manager_persists_requested_and_fallback_backend(
    tmp_path: Path,
) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "media" / "source.mp4"
    media_file.parent.mkdir()
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="fallback",
        local_path=str(media_file),
        has_audio=True,
        status="downloaded",
    )
    api = _StaticEngine(error=WhisperApiError("API unavailable"))
    local = _StaticEngine(result=_local_result())
    manager = TranscriptionManager(
        repository,
        engine_factory=lambda: HybridWhisperEngine(
            lambda: api,
            lambda: local,
        ),
    )

    job = await manager.enqueue_asset(
        asset,
        WhisperOptions(
            backend="api",
            model="small",
            api_model_version="base",
            api_fallback_to_local=True,
        ),
        wait=True,
    )

    assert job.status == "completed"
    assert job.requested_backend == "api"
    assert job.actual_backend == "local"
    assert job.resolved_model == "small"
    assert "API unavailable" in job.fallback_reason
    payload = json.loads(Path(job.transcript_path).read_text(encoding="utf-8"))
    assert payload["job_id"] == job.job_id
    assert payload["requested_backend"] == "api"
    assert payload["backend"] == "local"
    assert "API unavailable" in payload["fallback_reason"]


@pytest.mark.asyncio
async def test_manager_persists_successful_api_backend(tmp_path: Path) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "media" / "source.mp4"
    media_file.parent.mkdir()
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="api-success",
        local_path=str(media_file),
        has_audio=True,
        status="downloaded",
    )
    api_result = replace(
        _local_result("API 成功"),
        backend="api",
        resolved_model="base",
    )
    manager = TranscriptionManager(
        repository,
        engine_factory=lambda: _StaticEngine(result=api_result),
    )

    job = await manager.enqueue_asset(
        asset,
        WhisperOptions(
            backend="api",
            api_model_version="base",
            api_fallback_to_local=True,
        ),
        wait=True,
    )

    assert job.status == "completed"
    assert job.requested_backend == "api"
    assert job.actual_backend == "api"
    assert job.resolved_model == "base"
    assert job.fallback_reason == ""
    payload = json.loads(Path(job.transcript_path).read_text(encoding="utf-8"))
    assert payload["job_id"] == job.job_id
    assert payload["backend"] == "api"
    assert payload["model"] == "base"
    assert payload["local_fallback_model"] == "small"


@pytest.mark.asyncio
async def test_manager_records_both_failures(tmp_path: Path) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "source.mp4"
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="both-fail",
        local_path=str(media_file),
        has_audio=True,
        status="downloaded",
    )
    api = _StaticEngine(error=WhisperApiError("API failed"))
    local = _StaticEngine(error=RuntimeError("local failed"))
    manager = TranscriptionManager(
        repository,
        engine_factory=lambda: HybridWhisperEngine(
            lambda: api,
            lambda: local,
        ),
    )

    job = await manager.enqueue_asset(
        asset,
        WhisperOptions(backend="api", api_fallback_to_local=True),
        wait=True,
    )

    assert job.status == "failed"
    assert "API failed" in job.error_message
    assert "local failed" in job.error_message


@pytest.mark.asyncio
async def test_manager_retries_api_after_completed_local_fallback(
    tmp_path: Path,
) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "source.mp4"
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="retry-api",
        local_path=str(media_file),
        has_audio=True,
        status="downloaded",
    )
    api = _StaticEngine(error=WhisperApiError("API unavailable"))
    local = _StaticEngine(result=_local_result())
    manager = TranscriptionManager(
        repository,
        engine_factory=lambda: HybridWhisperEngine(
            lambda: api,
            lambda: local,
        ),
    )
    options = WhisperOptions(backend="api", api_fallback_to_local=True)

    first = await manager.enqueue_asset(asset, options, wait=True)
    second = await manager.enqueue_asset(asset, options, wait=True)

    assert first.job_id != second.job_id
    assert first.actual_backend == second.actual_backend == "local"
    assert first.transcript_path != second.transcript_path
    assert Path(first.transcript_path).is_file()
    assert Path(second.transcript_path).is_file()
    assert Path(first.transcript_path).parent.name == first.job_id
    assert Path(second.transcript_path).parent.name == second.job_id
    assert not list(media_file.parent.rglob("*.tmp"))
    assert api.calls == 2
    assert local.calls == 2


@pytest.mark.asyncio
async def test_manager_reuses_legacy_local_cache(tmp_path: Path) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "source.mp4"
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="legacy-local",
        local_path=str(media_file),
        has_audio=True,
        status="downloaded",
    )
    options = WhisperOptions(
        backend="local",
        model="small",
        device="cpu",
        compute_type="int8",
    )
    legacy = await repository.create_job(
        asset_id=asset.id,
        model="small",
        device="cpu",
        compute_type="int8",
        language=options.language,
        options_hash=options.legacy_local_hash(),
        requested_backend="local",
    )
    legacy = await repository.update_job(
        legacy.job_id,
        status="completed",
        actual_backend="local",
        resolved_model="small",
        full_text="旧缓存",
    )
    manager = TranscriptionManager(
        repository,
        engine_factory=lambda: _StaticEngine(error=AssertionError("不应重新转写")),
    )

    reused = await manager.enqueue_asset(asset, options, wait=True)

    assert reused.job_id == legacy.job_id
    assert reused.full_text == "旧缓存"


@pytest.mark.asyncio
async def test_manager_cache_is_bound_to_asset_sha256(tmp_path: Path) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "source.mp4"
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="asset-fingerprint",
        local_path=str(media_file),
        file_size=media_file.stat().st_size,
        sha256="a" * 64,
        has_audio=True,
        status="downloaded",
    )
    engine = _CountingLocalEngine()
    manager = TranscriptionManager(repository, engine_factory=lambda: engine)
    options = WhisperOptions(
        backend="local",
        model="small",
        device="cpu",
        compute_type="int8",
    )

    first = await manager.enqueue_asset(asset, options, wait=True)
    same_content = await manager.enqueue_asset(asset, options, wait=True)

    changed_asset = await repository.upsert_asset(
        platform="dy",
        content_id="asset-fingerprint",
        local_path=str(media_file),
        file_size=media_file.stat().st_size,
        sha256="b" * 64,
        has_audio=True,
        status="downloaded",
    )
    changed_content = await manager.enqueue_asset(changed_asset, options, wait=True)

    assert same_content.job_id == first.job_id
    assert changed_content.job_id != first.job_id
    assert first.full_text == same_content.full_text == "本地转写第 1 次"
    assert changed_content.full_text == "本地转写第 2 次"
    assert engine.calls == 2


@pytest.mark.asyncio
async def test_manager_does_not_reuse_unfingerprinted_legacy_cache_for_hashed_asset(
    tmp_path: Path,
) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    media_file = tmp_path / "source.mp4"
    media_file.write_bytes(b"media")
    asset = await repository.upsert_asset(
        platform="dy",
        content_id="hashed-legacy-local",
        local_path=str(media_file),
        file_size=media_file.stat().st_size,
        sha256="a" * 64,
        has_audio=True,
        status="downloaded",
    )
    options = WhisperOptions(
        backend="local",
        model="small",
        device="cpu",
        compute_type="int8",
    )
    legacy = await repository.create_job(
        asset_id=asset.id,
        model="small",
        device="cpu",
        compute_type="int8",
        language=options.language,
        options_hash=options.legacy_local_hash(),
        requested_backend="local",
    )
    legacy = await repository.update_job(
        legacy.job_id,
        status="completed",
        actual_backend="local",
        resolved_model="small",
        full_text="无资产指纹的旧缓存",
    )
    engine = _CountingLocalEngine()
    manager = TranscriptionManager(repository, engine_factory=lambda: engine)

    fresh = await manager.enqueue_asset(asset, options, wait=True)

    assert fresh.job_id != legacy.job_id
    assert fresh.full_text == "本地转写第 1 次"
    assert engine.calls == 1


class _ConcurrencyEngine:
    def __init__(self):
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def transcribe(self, _file_path: str, _options: WhisperOptions):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.05)
        with self.lock:
            self.active -= 1
        return replace(
            _local_result("API 队列"),
            backend="api",
            resolved_model="base",
        )


@pytest.mark.asyncio
async def test_manager_limits_api_concurrency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "WHISPER_API_CONCURRENCY", 1)
    repository = MediaRepository(tmp_path / "registry.db")
    engine = _ConcurrencyEngine()
    manager = TranscriptionManager(repository, engine_factory=lambda: engine)
    assets = []
    for index in range(2):
        media_file = tmp_path / str(index) / "source.mp4"
        media_file.parent.mkdir()
        media_file.write_bytes(b"media")
        assets.append(
            await repository.upsert_asset(
                platform="dy",
                content_id=str(index),
                local_path=str(media_file),
                has_audio=True,
                status="downloaded",
            )
        )

    jobs = await asyncio.gather(
        *[
            manager.enqueue_asset(
                asset,
                WhisperOptions(backend="api", api_model_version="base"),
                wait=True,
            )
            for asset in assets
        ]
    )

    assert all(job.status == "completed" for job in jobs)
    assert engine.peak == 1


class _BlockingApiEngine:
    def __init__(self):
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, _file_path: str, _options: WhisperOptions):
        self.calls += 1
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("测试引擎等待释放超时")
        return replace(
            _local_result("API 阻塞任务"),
            backend="api",
            resolved_model="base",
        )


async def _create_downloaded_asset(
    repository: MediaRepository,
    tmp_path: Path,
    content_id: str,
) -> MediaAsset:
    media_file = tmp_path / content_id / "source.mp4"
    media_file.parent.mkdir()
    media_file.write_bytes(b"media")
    return await repository.upsert_asset(
        platform="dy",
        content_id=content_id,
        local_path=str(media_file),
        has_audio=True,
        status="downloaded",
    )


@pytest.mark.asyncio
async def test_manager_deduplicates_same_active_job(tmp_path: Path) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    asset = await _create_downloaded_asset(repository, tmp_path, "same-job")
    engine = _BlockingApiEngine()
    manager = TranscriptionManager(repository, engine_factory=lambda: engine)
    options = WhisperOptions(
        backend="api",
        api_model_version="base",
        api_fallback_to_local=True,
    )

    first, second = await asyncio.gather(
        manager.enqueue_asset(asset, options, wait=False),
        manager.enqueue_asset(asset, options, wait=False),
    )
    assert await asyncio.to_thread(engine.started.wait, 2)

    assert second.job_id == first.job_id
    assert engine.calls == 1
    with sqlite3.connect(repository.db_path) as db:
        job_count = db.execute(
            "SELECT COUNT(*) FROM transcription_jobs WHERE asset_id = ?",
            (asset.id,),
        ).fetchone()[0]
    assert job_count == 1

    task = manager._tasks[first.job_id]
    engine.release.set()
    await task
    stored = await repository.get_job(first.job_id)
    assert stored is not None
    assert stored.status == "completed"
    assert first.job_id not in manager._tasks


@pytest.mark.asyncio
async def test_manager_keeps_queued_job_pending_and_records_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "WHISPER_API_CONCURRENCY", 1)
    repository = MediaRepository(tmp_path / "registry.db")
    first_asset = await _create_downloaded_asset(repository, tmp_path, "running")
    queued_asset = await _create_downloaded_asset(repository, tmp_path, "queued")
    engine = _BlockingApiEngine()
    manager = TranscriptionManager(repository, engine_factory=lambda: engine)
    options = WhisperOptions(
        backend="api",
        api_model_version="base",
        api_fallback_to_local=True,
    )

    first = await manager.enqueue_asset(first_asset, options, wait=False)
    assert await asyncio.to_thread(engine.started.wait, 2)
    queued = await manager.enqueue_asset(queued_asset, options, wait=False)
    await asyncio.sleep(0.05)

    running_job = await repository.get_job(first.job_id)
    queued_job = await repository.get_job(queued.job_id)
    assert running_job is not None
    assert queued_job is not None
    assert running_job.status == "running"
    assert running_job.started_at > 0
    assert queued_job.status == "pending"
    assert queued_job.started_at == 0
    assert engine.calls == 1

    queued_task = manager._tasks[queued.job_id]
    queued_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued_task

    cancelled_job = await repository.get_job(queued.job_id)
    assert cancelled_job is not None
    assert cancelled_job.status == "failed"
    assert cancelled_job.started_at == 0
    assert cancelled_job.finished_at > 0
    assert "CancelledError" in cancelled_job.error_message
    assert queued.job_id not in manager._tasks
    assert engine.calls == 1

    first_task = manager._tasks[first.job_id]
    engine.release.set()
    await first_task
    completed_job = await repository.get_job(first.job_id)
    assert completed_job is not None
    assert completed_job.status == "completed"


@pytest.mark.asyncio
async def test_manager_records_running_task_cancellation(tmp_path: Path) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    asset = await _create_downloaded_asset(repository, tmp_path, "cancel-running")
    engine = _BlockingApiEngine()
    manager = TranscriptionManager(repository, engine_factory=lambda: engine)
    options = WhisperOptions(
        backend="api",
        api_model_version="base",
        api_fallback_to_local=True,
    )

    job = await manager.enqueue_asset(asset, options, wait=False)
    assert await asyncio.to_thread(engine.started.wait, 2)
    task = manager._tasks[job.job_id]
    try:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        stored = await repository.get_job(job.job_id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.started_at > 0
        assert stored.finished_at > 0
        assert "CancelledError" in stored.error_message
        assert job.job_id not in manager._tasks
    finally:
        engine.release.set()


@pytest.mark.asyncio
async def test_caller_cancellation_does_not_cancel_shared_job(
    tmp_path: Path,
) -> None:
    repository = MediaRepository(tmp_path / "registry.db")
    asset = await _create_downloaded_asset(repository, tmp_path, "cancel-waiter")
    engine = _BlockingApiEngine()
    manager = TranscriptionManager(repository, engine_factory=lambda: engine)
    options = WhisperOptions(
        backend="api",
        api_model_version="base",
        api_fallback_to_local=True,
    )

    waiter = asyncio.create_task(
        manager.enqueue_asset(asset, options, wait=True),
    )
    assert await asyncio.to_thread(engine.started.wait, 2)
    job_id = next(iter(manager._tasks))
    shared_task = manager._tasks[job_id]

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not shared_task.cancelled()
    assert not shared_task.done()

    engine.release.set()
    await shared_task
    stored = await repository.get_job(job_id)
    assert stored is not None
    assert stored.status == "completed"


def _create_legacy_transcription_jobs_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE transcription_jobs (
                job_id TEXT PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                model TEXT NOT NULL,
                device TEXT NOT NULL,
                compute_type TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'auto',
                options_hash TEXT NOT NULL,
                full_text TEXT NOT NULL DEFAULT '',
                segments_json TEXT NOT NULL DEFAULT '[]',
                transcript_path TEXT NOT NULL DEFAULT '',
                subtitle_path TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                started_at INTEGER NOT NULL DEFAULT 0,
                finished_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        db.execute(
            """
            INSERT INTO transcription_jobs (
                job_id, asset_id, status, model, device, compute_type,
                language, options_hash, created_at
            ) VALUES (
                'legacy-job', 1, 'completed', 'small', 'cpu', 'int8',
                'zh', 'legacy-hash', 1
            )
            """
        )


@pytest.mark.asyncio
async def test_repository_migrates_existing_transcription_jobs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"
    _create_legacy_transcription_jobs_db(db_path)

    repository = MediaRepository(db_path)
    await repository.initialize()
    job = await repository.get_job("legacy-job")

    assert job is not None
    assert job.requested_backend == "local"
    assert job.actual_backend == "local"
    assert job.resolved_model == "small"
    assert job.fallback_reason == ""


@pytest.mark.asyncio
async def test_repository_serializes_concurrent_legacy_migrations(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "concurrent-legacy.db"
    _create_legacy_transcription_jobs_db(db_path)
    repositories = [MediaRepository(db_path) for _ in range(20)]

    await asyncio.gather(*(repository.initialize() for repository in repositories))
    jobs = await asyncio.gather(
        *(repository.get_job("legacy-job") for repository in repositories)
    )

    assert all(job is not None for job in jobs)
    assert all(job.requested_backend == "local" for job in jobs if job is not None)
    assert all(job.actual_backend == "local" for job in jobs if job is not None)
    assert all(job.resolved_model == "small" for job in jobs if job is not None)
