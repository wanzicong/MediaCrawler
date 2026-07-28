import inspect
import json

import pytest

from mcp_server import crawler_runner, server
from mcp_server.crawler_runner import CrawlResult, run_crawler


def test_mcp_tool_defaults_to_headed_browser() -> None:
    crawl_xhs = server._make_crawl_tool("xhs", "小红书")

    assert inspect.signature(crawl_xhs).parameters["headless"].default is False
    assert inspect.signature(run_crawler).parameters["headless"].default is False


@pytest.mark.asyncio
async def test_do_crawl_passes_headed_default_to_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_crawler(**kwargs: object) -> CrawlResult:
        captured.update(kwargs)
        return CrawlResult(returncode=0, stdout="", stderr="", success=True)

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
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
async def test_runner_builds_headed_command_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
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
        platform="xhs",
        crawler_type="search",
        keywords="测试",
    )

    command = captured["command"]
    assert isinstance(command, list)
    headless_index = command.index("--headless")
    assert command[headless_index + 1] == "false"
    assert result.success is True


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
    assert value_of("--media_run_id") == "run-123"
    assert value_of("--whisper_model") == "tiny"
    assert value_of("--whisper_language") == "zh"
    assert value_of("--whisper_word_timestamps") == "true"
    assert result.success is True
