from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import aiofiles

import config

from .models import MediaAsset, TranscriptResult, TranscriptSegment, TranscriptionJob
from .repository import MediaRepository


@dataclass(frozen=True)
class WhisperOptions:
    model: str = "small"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = "auto"
    vad_filter: bool = True
    word_timestamps: bool = False

    @classmethod
    def from_config(cls) -> "WhisperOptions":
        return cls(
            model=config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            language=config.WHISPER_LANGUAGE,
            vad_filter=config.WHISPER_VAD_FILTER,
            word_timestamps=config.WHISPER_WORD_TIMESTAMPS,
        )

    def stable_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=True)
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
        )


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
        engine_factory: Callable[[], FasterWhisperEngine] = FasterWhisperEngine,
    ):
        self.repository = repository
        self.engine_factory = engine_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}

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

        resolved_device, resolved_compute = FasterWhisperEngine._resolve_runtime(options)
        job = await self.repository.create_job(
            asset_id=asset.id,
            model=options.model,
            device=resolved_device,
            compute_type=resolved_compute,
            language=options.language,
            options_hash=options.stable_hash(),
        )
        if job.status == "completed":
            return job

        task = self._tasks.get(job.job_id)
        if task is None or task.done():
            task = asyncio.create_task(
                self._run_job(job.job_id, asset, options),
                name=job.job_id,
            )
            self._tasks[job.job_id] = task
        if wait:
            await task
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
        await self.repository.update_job(
            job_id,
            status="running",
            started_at=int(time.time()),
            error_message="",
        )
        try:
            engine = self.engine_factory()
            result = await asyncio.to_thread(
                engine.transcribe,
                asset.local_path,
                options,
            )
            paths = await self._write_outputs(asset, result, options)
            await self.repository.update_job(
                job_id,
                status="completed",
                full_text=result.full_text,
                segments_json=json.dumps(
                    [segment.to_dict() for segment in result.segments],
                    ensure_ascii=False,
                ),
                transcript_path=str(paths["json"].resolve()),
                subtitle_path=str(paths["srt"].resolve()),
                finished_at=int(time.time()),
            )
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
        asset: MediaAsset,
        result: TranscriptResult,
        options: WhisperOptions,
    ) -> dict[str, Path]:
        asset_dir = Path(asset.local_path).parent
        asset_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "txt": asset_dir / "transcript.txt",
            "json": asset_dir / "transcript.json",
            "srt": asset_dir / "transcript.srt",
            "vtt": asset_dir / "transcript.vtt",
        }
        payload = {
            "platform": asset.platform,
            "content_id": asset.content_id,
            "asset_id": asset.id,
            "model": options.model,
            **result.to_dict(),
        }
        srt_blocks = []
        vtt_blocks = ["WEBVTT\n"]
        for index, segment in enumerate(result.segments, start=1):
            start_srt = _subtitle_timestamp(segment.start)
            end_srt = _subtitle_timestamp(segment.end)
            start_vtt = _subtitle_timestamp(segment.start, vtt=True)
            end_vtt = _subtitle_timestamp(segment.end, vtt=True)
            srt_blocks.append(
                f"{index}\n{start_srt} --> {end_srt}\n{segment.text}\n"
            )
            vtt_blocks.append(
                f"{index}\n{start_vtt} --> {end_vtt}\n{segment.text}\n"
            )

        async with aiofiles.open(paths["txt"], "w", encoding="utf-8") as file:
            await file.write(result.full_text)
        async with aiofiles.open(paths["json"], "w", encoding="utf-8") as file:
            await file.write(json.dumps(payload, ensure_ascii=False, indent=2))
        async with aiofiles.open(paths["srt"], "w", encoding="utf-8") as file:
            await file.write("\n".join(srt_blocks))
        async with aiofiles.open(paths["vtt"], "w", encoding="utf-8") as file:
            await file.write("\n".join(vtt_blocks))
        return paths
