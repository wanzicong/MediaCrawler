# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests\test_cmd_arg_media.py
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
    monkeypatch.setattr(config, "WHISPER_BACKEND", "api")
    monkeypatch.setattr(config, "WHISPER_MODEL", "small")
    monkeypatch.setattr(config, "WHISPER_LANGUAGE", "auto")

    args = await parse_cmd(
        [
            "--download_media",
            "false",
            "--transcribe_media",
            "true",
            "--whisper_backend",
            "local",
            "--whisper_model",
            "tiny",
            "--whisper_language",
            "zh",
        ]
    )

    assert args.download_media is True
    assert args.transcribe_media is True
    assert args.whisper_backend == "local"
    assert config.DOWNLOAD_MEDIA is True
    assert config.WHISPER_BACKEND == "local"
    assert config.WHISPER_MODEL == "tiny"
    assert config.WHISPER_LANGUAGE == "zh"


@pytest.mark.asyncio
async def test_transcription_backend_defaults_to_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "WHISPER_BACKEND", "api")

    args = await parse_cmd([])

    assert args.whisper_backend == "api"
    assert config.WHISPER_BACKEND == "api"
