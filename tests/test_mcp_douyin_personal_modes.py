# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from mcp_server import crawler_runner, data_reader, server
from mcp_server.crawler_runner import CrawlResult, run_crawler


@pytest.fixture(autouse=True)
def isolate_mcp_run_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server, "MCP_RUNS_DIR", tmp_path / "mcp_runs")


@pytest.mark.asyncio
@pytest.mark.parametrize("crawler_type", ["liked", "collected"])
async def test_douyin_personal_modes_need_no_selector(
    crawler_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_crawler(**kwargs: object) -> CrawlResult:
        captured.update(kwargs)
        return CrawlResult(returncode=0, stdout="done", stderr="", success=True)

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
    monkeypatch.setattr(
        server,
        "get_data_summary",
        lambda *_args, **_kwargs: {"files": {}},
    )

    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type=crawler_type,
        )
    )

    assert response["success"] is True
    assert captured["crawler_type"] == crawler_type
    assert captured["keywords"] == ""
    assert captured["specified_id"] == ""
    assert captured["creator_id"] == ""
    assert captured["get_comment"] is False
    assert captured["get_sub_comment"] is False
    save_data_path = Path(str(captured["save_data_path"]))
    assert save_data_path.parent == server.MCP_RUNS_DIR
    manifest = json.loads(
        (save_data_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "completed"
    assert manifest["crawler_type"] == crawler_type


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["xhs", "ks", "bili", "wb", "tieba", "zhihu"])
async def test_personal_modes_are_rejected_for_non_douyin_platforms(
    platform: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_runner(**_kwargs: object) -> CrawlResult:
        raise AssertionError("不应启动爬虫子进程")

    monkeypatch.setattr(server, "run_crawler", unexpected_runner)

    response = json.loads(
        await server._do_crawl(
            platform=platform,
            cn_name=server.PLATFORMS[platform],
            crawler_type="liked",
        )
    )

    assert response["success"] is False
    assert "search/detail/creator" in response["error"]
    assert "liked" not in response["error"]


@pytest.mark.asyncio
async def test_mcp_nonempty_cookie_selects_cookie_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    async def fake_run_crawler(**kwargs: object) -> CrawlResult:
        captured.update(kwargs)
        return CrawlResult(
            returncode=0,
            stdout="done",
            stderr="",
            success=True,
        )

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
    await server._do_crawl(
        platform="dy",
        cn_name="抖音",
        crawler_type="liked",
        cookies="sessionid=explicit",
    )

    assert captured["login_type"] == "cookie"


def test_list_platforms_exposes_platform_specific_modes() -> None:
    response = json.loads(server.list_platforms())

    by_platform = response["crawler_types_by_platform"]
    assert by_platform["dy"] == [
        "search",
        "detail",
        "creator",
        "liked",
        "collected",
    ]
    assert by_platform["xhs"] == ["search", "detail", "creator"]
    assert response["crawler_types"]["liked"].startswith("抖音个人点赞")
    assert response["crawler_types"]["collected"].startswith("抖音个人收藏")

    platforms = {item["code"]: item for item in response["platforms"]}
    assert platforms["dy"]["crawler_types"] == by_platform["dy"]
    assert platforms["xhs"]["crawler_types"] == by_platform["xhs"]


def test_generated_tool_docs_only_advertise_supported_personal_modes() -> None:
    douyin_doc = server._make_crawl_tool("dy", "抖音").__doc__ or ""
    xhs_doc = server._make_crawl_tool("xhs", "小红书").__doc__ or ""

    assert "search|detail|creator|liked|collected" in douyin_doc
    assert "liked: 当前登录抖音账号点赞的作品" in douyin_doc
    assert "collected: 当前登录抖音账号收藏的作品" in douyin_doc
    assert "liked" not in xhs_doc
    assert "collected" not in xhs_doc


def test_read_data_rejects_personal_mode_for_non_douyin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_reader(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("不应读取不受支持模式的数据")

    monkeypatch.setattr(server, "get_full_data", unexpected_reader)

    response = json.loads(
        server.read_crawl_data(platform="xhs", crawler_type="collected")
    )

    assert response["success"] is False
    assert "search/detail/creator" in response["error"]


def test_read_personal_data_requires_crawl_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_reader(*_args, **_kwargs):
        raise AssertionError("不应读取跨任务的个人数据")

    monkeypatch.setattr(server, "get_full_data", unexpected_reader)
    response = json.loads(
        server.read_crawl_data(
            platform="dy",
            crawler_type="liked",
            file_type="jsonl",
        )
    )
    assert response["success"] is False
    assert "crawl_run_id" in response["error"]


def test_data_reader_returns_personal_user_actions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "douyin" / "jsonl"
    output_dir.mkdir(parents=True)
    action_file = output_dir / "liked_user_actions_2026-07-28.jsonl"
    action_file.write_text(
        '{"account_hash":"hash","aweme_id":"1",'
        '"action_type":"liked","observed_ts":1}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(data_reader, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data_reader, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(data_reader, "_get_date_str", lambda: "2026-07-28")

    result = data_reader.get_full_data("dy", "liked", max_items=10)

    assert result["files"]["user_actions"]["count"] == 1
    assert result["files"]["user_actions"]["items"][0]["action_type"] == "liked"


@pytest.mark.asyncio
async def test_mcp_run_id_reads_only_the_current_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_crawler(**kwargs: object) -> CrawlResult:
        output_dir = (
            Path(str(kwargs["save_data_path"]))
            / "douyin"
            / "jsonl"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "liked_user_actions_2026-07-28.jsonl").write_text(
            '{"account_hash":"current","aweme_id":"1",'
            '"action_type":"liked","observed_ts":1}\n',
            encoding="utf-8",
        )
        return CrawlResult(
            returncode=0,
            stdout="done",
            stderr="",
            success=True,
        )

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="liked",
        )
    )

    data = json.loads(
        server.read_crawl_data(crawl_run_id=response["crawl_run_id"])
    )
    assert data["success"] is True
    assert data["files"]["user_actions"]["count"] == 1
    assert (
        data["files"]["user_actions"]["items"][0]["account_hash"]
        == "current"
    )


@pytest.mark.asyncio
async def test_do_crawl_marks_corrupt_jsonl_as_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_crawler(**kwargs: object) -> CrawlResult:
        output_dir = (
            Path(str(kwargs["save_data_path"]))
            / "douyin"
            / "jsonl"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "liked_user_actions_run.jsonl").write_text(
            '{"account_hash":"hash","aweme_id":"1",'
            '"action_type":"liked","observed_ts":1}\n'
            "not-json\n",
            encoding="utf-8",
        )
        return CrawlResult(
            returncode=0,
            stdout="done",
            stderr="",
            success=True,
        )

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)

    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="liked",
            return_data=True,
        )
    )

    assert response["success"] is False
    assert response["partial"] is True
    assert response["error_code"] == "DATA_READ_ERROR"
    assert response["data"]["files"]["user_actions"]["count"] == 1


@pytest.mark.asyncio
async def test_empty_mcp_run_does_not_fall_back_to_historical_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_crawler(**_kwargs: object) -> CrawlResult:
        return CrawlResult(
            returncode=0,
            stdout="empty",
            stderr="",
            success=True,
        )

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="collected",
        )
    )
    assert response["data_summary"]["files"] == {}
    assert response["data_summary"]["total_count"] == 0

    data = json.loads(
        server.read_crawl_data(crawl_run_id=response["crawl_run_id"])
    )
    assert data["success"] is True
    assert data["empty"] is True
    assert data["files"] == {}


@pytest.mark.asyncio
async def test_database_return_data_is_rejected_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_runner(**_kwargs: object) -> CrawlResult:
        raise AssertionError("不应启动爬虫子进程")

    monkeypatch.setattr(server, "run_crawler", unexpected_runner)
    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="liked",
            save_data_option="sqlite",
            return_data=True,
        )
    )

    assert response["success"] is False
    assert response["error_code"] == "RETURN_DATA_UNSUPPORTED"
    assert not server.MCP_RUNS_DIR.exists()


@pytest.mark.asyncio
async def test_mcp_rejects_zero_max_notes_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_runner(**_kwargs: object) -> CrawlResult:
        raise AssertionError("不应启动爬虫子进程")

    monkeypatch.setattr(server, "run_crawler", unexpected_runner)
    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="liked",
            max_notes_count=0,
        )
    )
    assert response["success"] is False
    assert "至少为 1" in response["error"]


@pytest.mark.asyncio
async def test_mcp_rejects_excessive_max_notes_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_runner(**_kwargs: object) -> CrawlResult:
        raise AssertionError("不应启动爬虫子进程")

    monkeypatch.setattr(server, "run_crawler", unexpected_runner)
    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="liked",
            max_notes_count=server.MAX_CRAWL_NOTES_COUNT + 1,
        )
    )

    assert response["success"] is False
    assert response["error_code"] == "MAX_NOTES_EXCEEDED"
    assert (
        response["max_notes_count_limit"]
        == server.MAX_CRAWL_NOTES_COUNT
    )


@pytest.mark.asyncio
async def test_mcp_disables_timeout_for_large_accepted_crawl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_crawler(**kwargs: object) -> CrawlResult:
        captured.update(kwargs)
        return CrawlResult(
            returncode=0,
            stdout="done",
            stderr="",
            success=True,
        )

    monkeypatch.setattr(server, "run_crawler", fake_run_crawler)
    response = json.loads(
        await server._do_crawl(
            platform="dy",
            cn_name="抖音",
            crawler_type="liked",
            max_notes_count=server.MAX_CRAWL_NOTES_COUNT,
        )
    )

    assert response["success"] is True
    # 硬超时已关闭（server.py 传 0）,慢爬虫可跑任意久,防假死由空闲看门狗负责
    assert captured["timeout"] == 0


def test_data_reader_supports_excel_workbook_sheets(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "douyin"
    output_dir.mkdir(parents=True)
    workbook_path = output_dir / "douyin_liked_run.xlsx"
    workbook = Workbook()
    contents = workbook.active
    contents.title = "Contents"
    contents.append(["aweme_id", "title"])
    contents.append(["1", "content"])
    contents.append(["2", "content-2"])
    actions = workbook.create_sheet("UserActions")
    actions.append(["account_hash", "aweme_id", "action_type"])
    actions.append(["hash", "1", "liked"])
    actions.append(["hash", "2", "liked"])
    workbook.save(workbook_path)

    result = data_reader.get_full_data(
        "dy",
        "liked",
        file_type="excel",
        max_items=1,
        data_root=str(tmp_path),
    )

    workbook_data = result["files"]["workbook"]
    assert workbook_data["count"] == 4
    assert workbook_data["returned_count"] == 1
    assert workbook_data["truncated"] is True
    assert workbook_data["sheets"]["Contents"]["count"] == 2
    assert workbook_data["sheets"]["Contents"]["returned_count"] == 1
    assert workbook_data["sheets"]["Contents"]["truncated"] is True
    assert workbook_data["sheets"]["UserActions"]["count"] == 2
    assert workbook_data["sheets"]["UserActions"]["items"][0][
        "action_type"
    ] == "liked"


def test_read_run_id_rejects_path_traversal() -> None:
    response = json.loads(
        server.read_crawl_data(crawl_run_id="../manifest")
    )
    assert response["success"] is False
    assert "格式无效" in response["error"]


def test_read_crawl_data_rejects_excessive_max_items() -> None:
    response = json.loads(
        server.read_crawl_data(max_items=server.MAX_READ_ITEMS + 1)
    )

    assert response["success"] is False
    assert response["error_code"] == "MAX_ITEMS_EXCEEDED"
    assert response["max_items_limit"] == server.MAX_READ_ITEMS


def test_read_crawl_data_marks_corrupt_jsonl_as_partial_failure() -> None:
    crawl_run_id = "crawl_" + ("a" * 32)
    run_root = server.MCP_RUNS_DIR / crawl_run_id
    output_dir = run_root / "douyin" / "jsonl"
    output_dir.mkdir(parents=True)
    (output_dir / "liked_user_actions_run.jsonl").write_text(
        '{"account_hash":"hash","aweme_id":"1",'
        '"action_type":"liked","observed_ts":1}\n'
        "not-json\n",
        encoding="utf-8",
    )
    server._write_run_manifest(
        run_root,
        crawl_run_id=crawl_run_id,
        platform="dy",
        crawler_type="liked",
        save_data_option="jsonl",
        status="completed",
        returncode=0,
    )

    response = json.loads(
        server.read_crawl_data(crawl_run_id=crawl_run_id)
    )

    assert response["success"] is False
    assert response["partial"] is True
    assert response["error_code"] == "DATA_READ_ERROR"
    assert response["files"]["user_actions"]["count"] == 1
    assert response["files"]["user_actions"]["items"][0][
        "action_type"
    ] == "liked"


@pytest.mark.asyncio
async def test_runner_passes_cookie_only_via_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    secret = "sessionid=never-put-this-in-argv"

    class EmptyStream:
        @staticmethod
        def read(_size: int) -> bytes:
            return b""

    class SecretStream:
        def __init__(self):
            self.sent = False

        def read(self, _size: int) -> bytes:
            if self.sent:
                return b""
            self.sent = True
            return f"Cookie: {secret}\n".encode()

    class FinishedProcess:
        pid = 1234
        returncode = 0
        stdout = SecretStream()
        stderr = EmptyStream()

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    def fake_popen(command: list[str], **kwargs: object) -> FinishedProcess:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return FinishedProcess()

    monkeypatch.setattr(crawler_runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="dy",
        crawler_type="liked",
        login_type="cookie",
        cookies=secret,
        save_data_path="D:/isolated/mcp-run",
    )

    command = captured["command"]
    env = captured["env"]
    assert isinstance(command, list)
    assert isinstance(env, dict)
    assert "--cookies" not in command
    assert secret not in " ".join(command)
    assert env["MEDIACRAWLER_COOKIES"] == secret
    assert command[command.index("--type") + 1] == "liked"
    assert "--keywords" not in command
    assert "--specified_id" not in command
    assert "--creator_id" not in command
    assert command[command.index("--save_data_path") + 1] == (
        "D:/isolated/mcp-run"
    )
    assert result.success is True
    assert secret not in result.stdout
    assert "[REDACTED]" in result.stdout


@pytest.mark.asyncio
async def test_runner_does_not_inherit_parent_cookie_when_argument_is_empty(
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
        captured["env"] = kwargs["env"]
        return FinishedProcess()

    monkeypatch.setenv("MEDIACRAWLER_COOKIES", "parent-secret")
    monkeypatch.setattr(crawler_runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="dy",
        crawler_type="liked",
        cookies="",
    )

    assert "MEDIACRAWLER_COOKIES" not in captured["env"]
    assert result.success is True


@pytest.mark.asyncio
async def test_runner_redacts_cookie_split_across_output_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "custom_cookie_name=" + ("S" * 5000)
    callback_output = []

    class ChunkedStream:
        def __init__(self, chunks):
            self.chunks = list(chunks)

        def read(self, _size: int) -> bytes:
            return self.chunks.pop(0) if self.chunks else b""

    class EmptyStream:
        @staticmethod
        def read(_size: int) -> bytes:
            return b""

    class FinishedProcess:
        pid = 1234
        returncode = 0
        stdout = ChunkedStream(
            [
                f"prefix {secret[:3000]}".encode(),
                f"{secret[3000:]} suffix".encode(),
            ]
        )
        stderr = EmptyStream()

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    monkeypatch.setattr(
        crawler_runner.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FinishedProcess(),
    )
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="dy",
        crawler_type="liked",
        login_type="cookie",
        cookies=secret,
        on_log=callback_output.append,
    )

    assert secret not in result.stdout
    assert secret not in "".join(callback_output)
    assert "[REDACTED]" in result.stdout


@pytest.mark.asyncio
async def test_runner_preserves_utf8_split_across_output_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "prefix 中文日志 suffix"
    encoded = message.encode("utf-8")
    split_at = encoded.index("中".encode("utf-8")) + 1

    class ChunkedStream:
        def __init__(self, chunks):
            self.chunks = list(chunks)

        def read(self, _size: int) -> bytes:
            return self.chunks.pop(0) if self.chunks else b""

    class EmptyStream:
        @staticmethod
        def read(_size: int) -> bytes:
            return b""

    class FinishedProcess:
        pid = 1234
        returncode = 0
        stdout = ChunkedStream([encoded[:split_at], encoded[split_at:]])
        stderr = EmptyStream()

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    monkeypatch.setattr(
        crawler_runner.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FinishedProcess(),
    )
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="dy",
        crawler_type="liked",
    )

    assert result.stdout == message
    assert "\ufffd" not in result.stdout


@pytest.mark.asyncio
async def test_runner_redacts_non_ascii_cookie_split_inside_utf8_character(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "custom_name=" + ("密" * 20)
    encoded = f"prefix {secret} suffix".encode("utf-8")
    split_at = encoded.index("密".encode("utf-8")) + 1
    callback_output = []

    class ChunkedStream:
        def __init__(self, chunks):
            self.chunks = list(chunks)

        def read(self, _size: int) -> bytes:
            return self.chunks.pop(0) if self.chunks else b""

    class EmptyStream:
        @staticmethod
        def read(_size: int) -> bytes:
            return b""

    class FinishedProcess:
        pid = 1234
        returncode = 0
        stdout = ChunkedStream([encoded[:split_at], encoded[split_at:]])
        stderr = EmptyStream()

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    monkeypatch.setattr(
        crawler_runner.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FinishedProcess(),
    )
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="dy",
        crawler_type="liked",
        login_type="cookie",
        cookies=secret,
        on_log=callback_output.append,
    )

    combined_output = result.stdout + "".join(callback_output)
    assert secret not in combined_output
    assert "custom_name=" not in combined_output
    assert "密" not in combined_output
    assert "\ufffd" not in combined_output
    assert "[REDACTED]" in result.stdout


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("credential", "secret_fragments"),
    [
        ("sessionid=" + ("Q" * 100), ("Q" * 20,)),
        (
            "Cookie: foo="
            + ("Q" * 100)
            + "; bar="
            + ("Z" * 100),
            ("Q" * 20, "Z" * 20),
        ),
    ],
)
async def test_runner_redacts_credentials_crossing_live_callback_window(
    credential: str,
    secret_fragments: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = ("x" * 480) + f" {credential} " + ("y" * 500)
    callback_output = []

    class SingleChunkStream:
        def __init__(self, payload: bytes):
            self.payload = payload

        def read(self, _size: int) -> bytes:
            payload, self.payload = self.payload, b""
            return payload

    class EmptyStream:
        @staticmethod
        def read(_size: int) -> bytes:
            return b""

    class FinishedProcess:
        pid = 1234
        returncode = 0
        stdout = SingleChunkStream(message.encode("utf-8"))
        stderr = EmptyStream()

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    monkeypatch.setattr(
        crawler_runner.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FinishedProcess(),
    )
    monkeypatch.setattr(crawler_runner.time, "sleep", lambda _seconds: None)

    result = await run_crawler(
        platform="dy",
        crawler_type="liked",
        on_log=callback_output.append,
    )

    combined_callback = "".join(callback_output)
    for secret_fragment in secret_fragments:
        assert secret_fragment not in combined_callback
        assert secret_fragment not in result.stdout
    assert "[REDACTED]" in combined_callback
    assert "[REDACTED]" in result.stdout
