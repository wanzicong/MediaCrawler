# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests\test_mcp_server_defaults.py
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

from mcp_server import crawler_runner, server
from mcp_server.crawler_runner import CrawlResult, run_crawler


def test_mcp_tool_defaults_to_headed_browser() -> None:
    crawl_xhs = server._make_crawl_tool("xhs", "小红书")

    assert inspect.signature(crawl_xhs).parameters["headless"].default is False
    assert inspect.signature(run_crawler).parameters["headless"].default is False


@pytest.mark.asyncio
async def test_do_crawl_passes_headed_default_to_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_crawler(**kwargs: object) -> CrawlResult:
        captured.update(kwargs)
        return CrawlResult(returncode=0, stdout="", stderr="", success=True)

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
    monkeypatch.setattr(server, "MCP_RUNS_DIR", tmp_path / "mcp_runs")
    monkeypatch.setattr(
        server,
        "get_data_summary",
        lambda *_args, **_kwargs: {"files": {}},
    )

    response = json.loads(
        await server._do_crawl(
            platform="xhs",
            cn_name="小红书",
            crawler_type="search",
            keywords="测试",
        )
    )

    assert response["success"] is True
    assert captured["headless"] is False


@pytest.mark.asyncio
async def test_runner_builds_headed_command_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class EmptyStream:
        @staticmethod
        def read(_size: int) -> bytes:
            return b""

    class FinishedProcess:
        pid = 1234
        returncode = 0
        stdout = EmptyStream()
        stderr = EmptyStream()

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    def fake_popen(command: list[str], **kwargs: object) -> FinishedProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FinishedProcess()

    monkeypatch.setattr(crawler_runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="xhs",
        crawler_type="search",
        keywords="测试",
    )

    command = captured["command"]
    assert isinstance(command, list)
    headless_index = command.index("--headless")
    assert command[headless_index + 1] == "false"
    popen_kwargs = captured["kwargs"]
    assert isinstance(popen_kwargs, dict)
    if crawler_runner.os.name == "nt":
        assert (
            popen_kwargs["creationflags"]
            & crawler_runner.subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        assert popen_kwargs["start_new_session"] is True
    assert result.success is True


@pytest.mark.skipif(
    crawler_runner.os.name != "nt",
    reason="Windows process-tree termination uses taskkill",
)
def test_force_kill_process_tree_uses_taskkill_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class RunningProcess:
        pid = 4321
        kill_called = False

        @staticmethod
        def poll():
            return None

        def kill(self) -> None:
            self.kill_called = True

    class Completed:
        returncode = 0

    def fake_run(command: list[str], **kwargs: object) -> Completed:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    process = RunningProcess()
    monkeypatch.setattr(crawler_runner.subprocess, "run", fake_run)

    crawler_runner._force_kill_process_tree(process)

    assert captured["command"] == [
        "taskkill",
        "/PID",
        "4321",
        "/T",
        "/F",
    ]
    assert process.kill_called is False


@pytest.mark.skipif(
    crawler_runner.os.name != "nt",
    reason="Windows taskkill fallback",
)
def test_force_kill_process_tree_falls_back_when_taskkill_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RunningProcess:
        pid = 4321
        kill_called = False

        @staticmethod
        def poll():
            return None

        def kill(self) -> None:
            self.kill_called = True

    def failed_run(*_args, **_kwargs):
        raise OSError("taskkill unavailable")

    process = RunningProcess()
    monkeypatch.setattr(crawler_runner.subprocess, "run", failed_run)

    crawler_runner._force_kill_process_tree(process)

    assert process.kill_called is True


@pytest.mark.skipif(
    crawler_runner.os.name == "nt",
    reason="POSIX process-tree termination uses killpg",
)
def test_force_kill_process_tree_uses_killpg_on_posix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class RunningProcess:
        pid = 4321
        kill_called = False

        @staticmethod
        def poll():
            return None

        def kill(self) -> None:
            self.kill_called = True

    process = RunningProcess()
    monkeypatch.setattr(crawler_runner.os, "getpgid", lambda _pid: 9876)

    def fake_killpg(process_group_id: int, sig: int) -> None:
        captured["process_group_id"] = process_group_id
        captured["signal"] = sig

    monkeypatch.setattr(crawler_runner.os, "killpg", fake_killpg)

    crawler_runner._force_kill_process_tree(process)

    assert captured["process_group_id"] == 9876
    assert captured["signal"] == crawler_runner.signal.SIGKILL
    assert process.kill_called is False


@pytest.mark.asyncio
async def test_runner_passes_media_and_whisper_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class EmptyStream:
        @staticmethod
        def read(_size: int) -> bytes:
            return b""

    class FinishedProcess:
        pid = 1234
        returncode = 0
        stdout = EmptyStream()
        stderr = EmptyStream()

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    def fake_popen(command: list[str], **_kwargs: object) -> FinishedProcess:
        captured["command"] = command
        return FinishedProcess()

    monkeypatch.setattr(crawler_runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="dy",
        crawler_type="detail",
        specified_id="123",
        download_media=True,
        transcribe_media=True,
        media_run_id="run-123",
        whisper_backend="local",
        whisper_model="tiny",
        whisper_language="zh",
        whisper_word_timestamps=True,
    )

    command = captured["command"]
    assert isinstance(command, list)

    def value_of(option: str) -> str:
        return command[command.index(option) + 1]

    assert value_of("--download_media") == "true"
    assert value_of("--transcribe_media") == "true"
    assert value_of("--whisper_backend") == "local"
    assert value_of("--media_run_id") == "run-123"
    assert value_of("--whisper_model") == "tiny"
    assert value_of("--whisper_language") == "zh"
    assert value_of("--whisper_word_timestamps") == "true"
    assert result.success is True
