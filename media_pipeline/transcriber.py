# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_pipeline\transcriber.py
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

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import aiofiles
import httpx

import config

from .models import MediaAsset, TranscriptResult, TranscriptSegment, TranscriptionJob
from .repository import MediaRepository

logger = logging.getLogger("MediaCrawler")


@dataclass(frozen=True)
class WhisperOptions:
    model: str = "small"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = "auto"
    vad_filter: bool = True
    word_timestamps: bool = False
    backend: str = field(default_factory=lambda: config.WHISPER_BACKEND)
    api_base_url: str = field(default_factory=lambda: config.WHISPER_API_BASE_URL)
    api_key: str = field(
        default_factory=lambda: config.WHISPER_API_KEY,
        repr=False,
        compare=False,
    )
    api_model: str = field(default_factory=lambda: config.WHISPER_API_MODEL)
    api_model_version: str = field(
        default_factory=lambda: config.WHISPER_API_MODEL_VERSION
    )
    api_deployment_fingerprint: str = field(
        default_factory=lambda: config.WHISPER_API_DEPLOYMENT_FINGERPRINT
    )
    api_timeout: float = field(default_factory=lambda: config.WHISPER_API_TIMEOUT)
    api_fallback_to_local: bool = field(
        default_factory=lambda: config.WHISPER_API_FALLBACK_TO_LOCAL
    )
    api_trust_env: bool = field(default_factory=lambda: config.WHISPER_API_TRUST_ENV)

    @classmethod
    def from_config(cls) -> "WhisperOptions":
        return cls(
            model=config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            language=config.WHISPER_LANGUAGE,
            vad_filter=config.WHISPER_VAD_FILTER,
            word_timestamps=config.WHISPER_WORD_TIMESTAMPS,
            backend=config.WHISPER_BACKEND,
            api_base_url=config.WHISPER_API_BASE_URL,
            api_key=config.WHISPER_API_KEY,
            api_model=config.WHISPER_API_MODEL,
            api_model_version=config.WHISPER_API_MODEL_VERSION,
            api_deployment_fingerprint=config.WHISPER_API_DEPLOYMENT_FINGERPRINT,
            api_timeout=config.WHISPER_API_TIMEOUT,
            api_fallback_to_local=config.WHISPER_API_FALLBACK_TO_LOCAL,
            api_trust_env=config.WHISPER_API_TRUST_ENV,
        )

    def normalized_backend(self) -> str:
        backend = self.backend.strip().lower()
        if backend not in {"api", "local"}:
            raise ValueError(
                f"不支持的转写后端: {self.backend!r}，可选值为 api 或 local"
            )
        return backend

    def stable_hash(self) -> str:
        backend = self.normalized_backend()
        values: dict[str, Any] = {
            "backend": backend,
            "language": self.language,
            "word_timestamps": self.word_timestamps,
        }
        local_values = {
            "model": self.model,
            "device": self.device,
            "compute_type": self.compute_type,
            "vad_filter": self.vad_filter,
        }
        if backend == "local":
            values.update(local_values)
        else:
            values.update(
                {
                    "api_base_url": self.api_base_url.strip().rstrip("/"),
                    "api_model": self.api_model,
                    "api_model_version": self.api_model_version,
                    "api_deployment_fingerprint": self.api_deployment_fingerprint,
                    "api_fallback_to_local": self.api_fallback_to_local,
                }
            )
            if self.api_fallback_to_local:
                values["local_fallback"] = local_values
        payload = json.dumps(values, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def legacy_local_hash(self) -> str:
        """Hash used before backend selection was introduced."""
        values = {
            "model": self.model,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "vad_filter": self.vad_filter,
            "word_timestamps": self.word_timestamps,
        }
        payload = json.dumps(values, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FasterWhisperEngine:
    _models: dict[tuple[str, str, str, str], Any] = {}
    _model_lock = threading.Lock()

    @staticmethod
    def _resolve_runtime(options: WhisperOptions) -> tuple[str, str]:
        device = options.device
        if device == "auto":
            try:
                import ctranslate2

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        compute_type = options.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        return device, compute_type

    def _get_model(self, options: WhisperOptions):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "未安装 faster-whisper，请先执行 `uv sync` 安装项目依赖"
            ) from exc

        device, compute_type = self._resolve_runtime(options)
        model_dir = getattr(config, "WHISPER_MODEL_DIR", "")
        key = (options.model, device, compute_type, model_dir)
        with self._model_lock:
            if key not in self._models:
                self._models[key] = WhisperModel(
                    options.model,
                    device=device,
                    compute_type=compute_type,
                    download_root=model_dir or None,
                )
            return self._models[key]

    def transcribe(self, file_path: str, options: WhisperOptions) -> TranscriptResult:
        model = self._get_model(options)
        language = None if options.language in ("", "auto") else options.language
        segments_iter, info = model.transcribe(
            file_path,
            language=language,
            beam_size=5,
            vad_filter=options.vad_filter,
            word_timestamps=options.word_timestamps,
        )
        segments: list[TranscriptSegment] = []
        texts: list[str] = []
        for segment in segments_iter:
            words = []
            for word in segment.words or []:
                words.append(
                    {
                        "start": word.start,
                        "end": word.end,
                        "word": word.word,
                        "probability": word.probability,
                    }
                )
            text = segment.text.strip()
            if text:
                texts.append(text)
            segments.append(
                TranscriptSegment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=text,
                    avg_logprob=getattr(segment, "avg_logprob", None),
                    no_speech_prob=getattr(segment, "no_speech_prob", None),
                    words=words,
                )
            )
        return TranscriptResult(
            language=getattr(info, "language", language or ""),
            language_probability=float(getattr(info, "language_probability", 0.0)),
            duration_seconds=float(getattr(info, "duration", 0.0)),
            full_text="\n".join(texts),
            segments=segments,
            backend="local",
            resolved_model=options.model,
        )


class WhisperApiError(RuntimeError):
    """Raised when the OpenAI-compatible transcription API cannot be used."""


class WhisperApiEngine:
    def __init__(
        self,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ):
        self.client_factory = client_factory

    @staticmethod
    def _transcriptions_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise WhisperApiError("未配置 WHISPER_API_BASE_URL")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise WhisperApiError(
                "WHISPER_API_BASE_URL 必须是有效的 http 或 https 地址"
            )
        if parsed.username or parsed.password:
            raise WhisperApiError("WHISPER_API_BASE_URL 不能包含用户名或密码")
        if parsed.query or parsed.fragment:
            raise WhisperApiError("WHISPER_API_BASE_URL 不能包含查询参数或片段")
        hostname = parsed.hostname.rstrip(".").lower()
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = hostname == "localhost"
        if parsed.scheme == "http" and not is_loopback:
            raise WhisperApiError(
                "非本机 WHISPER_API_BASE_URL 必须使用 https，避免泄露音视频和 API Key"
            )
        if normalized.endswith("/v1"):
            return f"{normalized}/audio/transcriptions"
        return f"{normalized}/v1/audio/transcriptions"

    @staticmethod
    def _float_value(
        value: Any,
        *,
        field_name: str,
        minimum: float | None = None,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise WhisperApiError(f"转写 API 返回的 {field_name} 不是有效数字") from exc
        if not math.isfinite(number):
            raise WhisperApiError(f"转写 API 返回的 {field_name} 不是有限数字")
        if minimum is not None and number < minimum:
            raise WhisperApiError(f"转写 API 返回的 {field_name} 不能小于 {minimum}")
        return number

    @classmethod
    def _parse_result(cls, payload: Any) -> TranscriptResult:
        if not isinstance(payload, dict):
            raise WhisperApiError("转写 API 返回的 JSON 不是对象")
        required_fields = {"language", "duration", "text"}
        missing_fields = sorted(required_fields.difference(payload))
        if missing_fields:
            raise WhisperApiError(f"转写 API 响应缺少字段: {', '.join(missing_fields)}")
        if not isinstance(payload.get("language"), str):
            raise WhisperApiError("转写 API 返回的 language 不是字符串")
        if not isinstance(payload.get("text"), str):
            raise WhisperApiError("转写 API 返回的 text 不是字符串")

        raw_segments = payload.get("segments", [])
        if raw_segments is None:
            raw_segments = []
        if not isinstance(raw_segments, list):
            raise WhisperApiError("转写 API 返回的 segments 格式无效")

        segments: list[TranscriptSegment] = []
        previous_start = 0.0
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                raise WhisperApiError("转写 API 返回的 segment 不是对象")
            if not isinstance(raw_segment.get("text"), str):
                raise WhisperApiError("转写 API 返回的 segment.text 不是字符串")
            start = cls._float_value(
                raw_segment.get("start"),
                field_name="segment.start",
                minimum=0.0,
            )
            end = cls._float_value(
                raw_segment.get("end"),
                field_name="segment.end",
                minimum=0.0,
            )
            if end < start:
                raise WhisperApiError("转写 API 返回的 segment.end 小于 start")
            if segments and start < previous_start:
                raise WhisperApiError("转写 API 返回的 segments 未按时间排序")
            previous_start = start
            segments.append(
                TranscriptSegment(
                    start=start,
                    end=end,
                    text=str(raw_segment.get("text") or "").strip(),
                    avg_logprob=(
                        cls._float_value(
                            raw_segment.get("avg_logprob"),
                            field_name="segment.avg_logprob",
                        )
                        if raw_segment.get("avg_logprob") is not None
                        else None
                    ),
                    no_speech_prob=(
                        cls._float_value(
                            raw_segment.get("no_speech_prob"),
                            field_name="segment.no_speech_prob",
                        )
                        if raw_segment.get("no_speech_prob") is not None
                        else None
                    ),
                )
            )

        raw_words = payload.get("words", [])
        if raw_words is None:
            raw_words = []
        if not isinstance(raw_words, list):
            raise WhisperApiError("转写 API 返回的 words 格式无效")
        parsed_words: list[dict[str, Any]] = []
        for raw_word in raw_words:
            if not isinstance(raw_word, dict):
                raise WhisperApiError("转写 API 返回的 word 不是对象")
            if not isinstance(raw_word.get("word"), str):
                raise WhisperApiError("转写 API 返回的 word.word 不是字符串")
            word_start = cls._float_value(
                raw_word.get("start"),
                field_name="word.start",
                minimum=0.0,
            )
            word_end = cls._float_value(
                raw_word.get("end"),
                field_name="word.end",
                minimum=0.0,
            )
            if word_end < word_start:
                raise WhisperApiError("转写 API 返回的 word.end 小于 start")
            word: dict[str, Any] = {
                "start": word_start,
                "end": word_end,
                "word": raw_word["word"],
            }
            if raw_word.get("probability") is not None:
                word["probability"] = cls._float_value(
                    raw_word.get("probability"),
                    field_name="word.probability",
                )
            parsed_words.append(word)

        duration = cls._float_value(
            payload.get("duration"),
            field_name="duration",
            minimum=0.0,
        )
        if segments and duration + 0.05 < max(segment.end for segment in segments):
            raise WhisperApiError("转写 API 返回的 duration 小于分段结束时间")
        response_text = str(payload.get("text") or "").strip()
        segment_texts = [segment.text for segment in segments if segment.text]
        full_text = "\n".join(segment_texts) if segment_texts else response_text

        if not segments and (response_text or parsed_words):
            segments.append(
                TranscriptSegment(
                    start=0.0,
                    end=duration,
                    text=response_text,
                )
            )

        if segments:
            segment_index = 0
            for word in parsed_words:
                word_start = float(word["start"])
                word_end = float(word["end"])
                midpoint = (word_start + word_end) / 2
                while (
                    segment_index < len(segments) - 1
                    and midpoint > segments[segment_index].end
                ):
                    segment_index += 1
                segment = segments[segment_index]
                if segment.start <= midpoint <= segment.end:
                    segment.words.append(word)

        language_probability = 0.0
        if payload.get("language_probability") is not None:
            language_probability = cls._float_value(
                payload.get("language_probability"),
                field_name="language_probability",
            )

        return TranscriptResult(
            language=str(payload.get("language") or ""),
            language_probability=language_probability,
            duration_seconds=duration,
            full_text=full_text,
            segments=segments,
            backend="api",
        )

    def transcribe(self, file_path: str, options: WhisperOptions) -> TranscriptResult:
        media_path = Path(file_path)
        if not media_path.is_file():
            raise WhisperApiError(f"待转写文件不存在: {media_path}")

        timestamp_granularities = ["segment"]
        data: dict[str, Any] = {
            "model": options.api_model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": timestamp_granularities,
        }
        if options.language not in ("", "auto"):
            data["language"] = options.language
        if options.word_timestamps:
            timestamp_granularities.append("word")

        headers = {}
        if options.api_key:
            headers["Authorization"] = f"Bearer {options.api_key}"

        endpoint = self._transcriptions_url(options.api_base_url)
        try:
            with media_path.open("rb") as media_file:
                files = {
                    "file": (
                        media_path.name,
                        media_file,
                        "application/octet-stream",
                    )
                }
                timeout = httpx.Timeout(
                    connect=min(options.api_timeout, 5.0),
                    read=options.api_timeout,
                    write=min(options.api_timeout, 300.0),
                    pool=5.0,
                )
                with self.client_factory(
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=options.api_trust_env,
                ) as client:
                    response = client.post(
                        endpoint,
                        data=data,
                        files=files,
                        headers=headers,
                    )
        except (OSError, httpx.HTTPError) as exc:
            raise WhisperApiError(
                f"无法调用转写 API {endpoint}: {type(exc).__name__}: {exc}"
            ) from exc

        if response.status_code >= 300:
            detail = response.text.strip().replace("\r", " ").replace("\n", " ")
            if len(detail) > 500:
                detail = f"{detail[:500]}..."
            raise WhisperApiError(
                f"转写 API 返回 HTTP {response.status_code}: {detail or '无错误详情'}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WhisperApiError("转写 API 未返回有效 JSON") from exc
        result = self._parse_result(payload)
        result.resolved_model = options.api_model_version or options.api_model
        return result


class HybridWhisperEngine:
    """Use the configured API first and optionally fall back to local Whisper."""

    def __init__(
        self,
        api_engine_factory: Callable[[], WhisperApiEngine] = WhisperApiEngine,
        local_engine_factory: Callable[[], FasterWhisperEngine] = FasterWhisperEngine,
    ):
        self.api_engine_factory = api_engine_factory
        self.local_engine_factory = local_engine_factory

    def transcribe(self, file_path: str, options: WhisperOptions) -> TranscriptResult:
        if options.normalized_backend() == "local":
            return self.local_engine_factory().transcribe(file_path, options)

        try:
            return self.api_engine_factory().transcribe(file_path, options)
        except WhisperApiError as exc:
            if not options.api_fallback_to_local:
                raise
            reason = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "[Transcription] API 转写失败，自动回退本地模型: %s",
                reason,
            )
            try:
                result = self.local_engine_factory().transcribe(file_path, options)
            except Exception as local_exc:
                raise RuntimeError(
                    "API 与本地转写均失败；"
                    f"API: {reason}；"
                    f"本地: {type(local_exc).__name__}: {local_exc}"
                ) from local_exc
            result.backend = "local"
            result.resolved_model = result.resolved_model or options.model
            result.fallback_reason = reason
            return result


def _subtitle_timestamp(seconds: float, *, vtt: bool = False) -> str:
    milliseconds = max(int(round(seconds * 1000)), 0)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


class TranscriptionManager:
    def __init__(
        self,
        repository: MediaRepository,
        engine_factory: Callable[[], Any] = HybridWhisperEngine,
    ):
        self.repository = repository
        self.engine_factory = engine_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._api_semaphore = asyncio.Semaphore(config.WHISPER_API_CONCURRENCY)
        self._enqueue_lock = asyncio.Lock()

    @staticmethod
    def _options_hash_for_asset(
        asset: MediaAsset,
        options: WhisperOptions,
    ) -> str:
        options_hash = options.stable_hash()
        asset_sha256 = (asset.sha256 or "").strip().lower()
        if not asset_sha256:
            return options_hash
        payload = json.dumps(
            {
                "cache_version": 2,
                "asset_sha256": asset_sha256,
                "options_hash": options_hash,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def enqueue_asset(
        self,
        asset: MediaAsset,
        options: WhisperOptions | None = None,
        *,
        wait: bool = False,
    ) -> TranscriptionJob:
        options = options or WhisperOptions.from_config()
        if asset.status != "downloaded":
            raise ValueError(f"媒体尚未下载完成: asset_id={asset.id}")
        if not asset.has_audio:
            raise ValueError(f"媒体不包含音频流: asset_id={asset.id}")

        async with self._enqueue_lock:
            requested_backend = options.normalized_backend()
            asset_sha256 = (asset.sha256 or "").strip()
            if requested_backend == "local" and not asset_sha256:
                legacy_job = await self.repository.find_completed_job(
                    asset.id,
                    options.legacy_local_hash(),
                )
                if legacy_job is not None:
                    return legacy_job

            options_hash = self._options_hash_for_asset(asset, options)
            active_job = await self.repository.find_active_job(
                asset.id,
                options_hash,
            )
            task = None
            if active_job is not None:
                active_task = self._tasks.get(active_job.job_id)
                if active_task is not None and not active_task.done():
                    job = active_job
                    task = active_task

            if task is None:
                if requested_backend == "api":
                    resolved_device, resolved_compute = "api", "remote"
                    requested_model = options.api_model_version or options.api_model
                else:
                    resolved_device, resolved_compute = (
                        FasterWhisperEngine._resolve_runtime(options)
                    )
                    requested_model = options.model
                job = await self.repository.create_job(
                    asset_id=asset.id,
                    model=requested_model,
                    device=resolved_device,
                    compute_type=resolved_compute,
                    language=options.language,
                    options_hash=options_hash,
                    requested_backend=requested_backend,
                )
                if job.status == "completed":
                    return job
                task = asyncio.create_task(
                    self._run_job(job.job_id, asset, options),
                    name=job.job_id,
                )
                self._tasks[job.job_id] = task
        if wait:
            await asyncio.shield(task)
        refreshed = await self.repository.get_job(job.job_id)
        if refreshed is None:
            raise RuntimeError(f"转写任务丢失: {job.job_id}")
        return refreshed

    async def _run_job(
        self,
        job_id: str,
        asset: MediaAsset,
        options: WhisperOptions,
    ) -> None:
        try:

            async def run_transcription() -> TranscriptResult:
                await self.repository.update_job(
                    job_id,
                    status="running",
                    started_at=int(time.time()),
                    error_message="",
                )
                engine = self.engine_factory()
                return await asyncio.to_thread(
                    engine.transcribe,
                    asset.local_path,
                    options,
                )

            if options.normalized_backend() == "api":
                async with self._api_semaphore:
                    result = await run_transcription()
            else:
                result = await run_transcription()
            paths = await self._write_outputs(job_id, asset, result, options)
            actual_backend = result.backend or options.normalized_backend()
            resolved_model = result.resolved_model or (
                options.api_model if actual_backend == "api" else options.model
            )
            await self.repository.update_job(
                job_id,
                status="completed",
                actual_backend=actual_backend,
                resolved_model=resolved_model,
                fallback_reason=result.fallback_reason,
                full_text=result.full_text,
                segments_json=json.dumps(
                    [segment.to_dict() for segment in result.segments],
                    ensure_ascii=False,
                ),
                transcript_path=str(paths["json"].resolve()),
                subtitle_path=str(paths["srt"].resolve()),
                finished_at=int(time.time()),
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                self.repository.update_job(
                    job_id,
                    status="failed",
                    error_message="CancelledError: 转写任务已取消",
                    finished_at=int(time.time()),
                )
            )
            raise
        except Exception as exc:
            await self.repository.update_job(
                job_id,
                status="failed",
                error_message=f"{type(exc).__name__}: {exc}",
                finished_at=int(time.time()),
            )
        finally:
            self._tasks.pop(job_id, None)

    @staticmethod
    async def _write_outputs(
        job_id: str,
        asset: MediaAsset,
        result: TranscriptResult,
        options: WhisperOptions,
    ) -> dict[str, Path]:
        asset_dir = Path(asset.local_path).parent
        if Path(job_id).name != job_id:
            raise ValueError(f"非法转写任务 ID: {job_id!r}")
        output_dir = asset_dir / "transcripts" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "txt": output_dir / "transcript.txt",
            "json": output_dir / "transcript.json",
            "srt": output_dir / "transcript.srt",
            "vtt": output_dir / "transcript.vtt",
        }
        payload = {
            "job_id": job_id,
            "platform": asset.platform,
            "content_id": asset.content_id,
            "asset_id": asset.id,
            "model": result.resolved_model or options.model,
            "local_fallback_model": options.model,
            "requested_backend": options.normalized_backend(),
            "api_model": options.api_model,
            "api_model_version": options.api_model_version,
            "api_deployment_fingerprint": options.api_deployment_fingerprint,
            **result.to_dict(),
        }
        srt_blocks = []
        vtt_blocks = ["WEBVTT\n"]
        for index, segment in enumerate(result.segments, start=1):
            start_srt = _subtitle_timestamp(segment.start)
            end_srt = _subtitle_timestamp(segment.end)
            start_vtt = _subtitle_timestamp(segment.start, vtt=True)
            end_vtt = _subtitle_timestamp(segment.end, vtt=True)
            srt_blocks.append(f"{index}\n{start_srt} --> {end_srt}\n{segment.text}\n")
            vtt_blocks.append(f"{index}\n{start_vtt} --> {end_vtt}\n{segment.text}\n")

        contents = {
            "txt": result.full_text,
            "json": json.dumps(payload, ensure_ascii=False, indent=2),
            "srt": "\n".join(srt_blocks),
            "vtt": "\n".join(vtt_blocks),
        }
        for output_format, content in contents.items():
            await TranscriptionManager._atomic_write_text(
                paths[output_format],
                content,
            )
        return paths

    @staticmethod
    async def _atomic_write_text(path: Path, content: str) -> None:
        temporary_path = path.with_name(f".{path.name}.tmp")
        try:
            async with aiofiles.open(
                temporary_path,
                "w",
                encoding="utf-8",
            ) as file:
                await file.write(content)
                await file.flush()
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
