import pytest

import config
from cmd_arg.arg import parse_cmd


@pytest.mark.asyncio
async def test_download_media_cli_updates_canonical_and_legacy_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "DOWNLOAD_MEDIA", False)
    monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", False)
    monkeypatch.setattr(config, "TRANSCRIBE_MEDIA", False)
    monkeypatch.setattr(config, "MEDIA_RUN_ID", "")

    args = await parse_cmd(
        [
            "--download_media",
            "true",
            "--media_run_id",
            "cli-run",
        ]
    )

    assert args.download_media is True
    assert args.transcribe_media is False
    assert config.DOWNLOAD_MEDIA is True
    assert config.ENABLE_GET_MEIDAS is True
    assert config.is_media_download_enabled() is True
    assert config.MEDIA_RUN_ID == "cli-run"


@pytest.mark.asyncio
async def test_transcription_implicitly_enables_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "DOWNLOAD_MEDIA", False)
    monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", False)
    monkeypatch.setattr(config, "TRANSCRIBE_MEDIA", False)
    monkeypatch.setattr(config, "WHISPER_MODEL", "small")
    monkeypatch.setattr(config, "WHISPER_LANGUAGE", "auto")

    args = await parse_cmd(
        [
            "--download_media",
            "false",
            "--transcribe_media",
            "true",
            "--whisper_model",
            "tiny",
            "--whisper_language",
            "zh",
        ]
    )

    assert args.download_media is True
    assert args.transcribe_media is True
    assert config.DOWNLOAD_MEDIA is True
    assert config.WHISPER_MODEL == "tiny"
    assert config.WHISPER_LANGUAGE == "zh"
