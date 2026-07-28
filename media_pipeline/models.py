from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MediaAsset:
    id: int
    platform: str
    content_id: str
    media_type: str
    source_url: str
    local_path: str
    mime_type: str
    file_size: int
    sha256: str
    duration_ms: int
    has_audio: bool
    status: str
    error_message: str
    run_id: str
    created_at: int
    updated_at: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    words: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptResult:
    language: str
    language_probability: float
    duration_seconds: float
    full_text: str
    segments: list[TranscriptSegment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "language_probability": self.language_probability,
            "duration_seconds": self.duration_seconds,
            "full_text": self.full_text,
            "segments": [segment.to_dict() for segment in self.segments],
        }


@dataclass
class TranscriptionJob:
    job_id: str
    asset_id: int
    status: str
    model: str
    device: str
    compute_type: str
    language: str
    options_hash: str
    full_text: str
    segments_json: str
    transcript_path: str
    subtitle_path: str
    error_message: str
    created_at: int
    started_at: int
    finished_at: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
