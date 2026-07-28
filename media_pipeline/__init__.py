"""Media download and speech-to-text pipeline."""

from .downloader import DownloadResult, MediaDownloader, register_local_media
from .repository import MediaRepository
from .transcriber import TranscriptionManager, WhisperOptions

_repository: MediaRepository | None = None
_transcription_manager: TranscriptionManager | None = None


def get_media_repository() -> MediaRepository:
    global _repository
    if _repository is None:
        _repository = MediaRepository()
    return _repository


def get_transcription_manager() -> TranscriptionManager:
    global _transcription_manager
    if _transcription_manager is None:
        _transcription_manager = TranscriptionManager(get_media_repository())
    return _transcription_manager


__all__ = [
    "DownloadResult",
    "MediaDownloader",
    "MediaRepository",
    "TranscriptionManager",
    "WhisperOptions",
    "get_media_repository",
    "get_transcription_manager",
    "register_local_media",
]
