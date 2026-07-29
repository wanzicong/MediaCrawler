import os
import sys
import importlib
import io

import click
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import config
from api.main import app
from api.schemas import CrawlerStartRequest
from api.services.crawler_manager import CrawlerManager
from cmd_arg import parse_cmd


@pytest.fixture(autouse=True)
def restore_global_config():
    snapshot = {
        name: getattr(config, name)
        for name in dir(config)
        if name.isupper()
    }
    yield
    for name, value in snapshot.items():
        setattr(config, name, value)


@pytest.mark.asyncio
@pytest.mark.parametrize("crawler_type", ["liked", "collected"])
async def test_cli_accepts_douyin_personal_modes_without_selector(
    crawler_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", True)

    parsed = await parse_cmd(
        ["--platform", "dy", "--type", crawler_type]
    )

    assert parsed.platform == "dy"
    assert parsed.type == crawler_type
    assert parsed.get_comment is False
    assert parsed.get_sub_comment is False


@pytest.mark.asyncio
async def test_cli_rejects_personal_mode_for_other_platform() -> None:
    with pytest.raises(click.BadParameter, match="only supported by Douyin"):
        await parse_cmd(["--platform", "xhs", "--type", "liked"])


@pytest.mark.asyncio
async def test_cli_rejects_zero_max_notes_count() -> None:
    with pytest.raises(click.BadParameter, match="at least 1"):
        await parse_cmd(
            [
                "--platform",
                "dy",
                "--type",
                "liked",
                "--crawler_max_notes_count",
                "0",
            ]
        )


@pytest.mark.asyncio
async def test_cli_can_explicitly_enable_comments_for_personal_mode() -> None:
    parsed = await parse_cmd(
        [
            "--platform",
            "dy",
            "--type",
            "collected",
            "--get_comment",
            "true",
        ]
    )

    assert parsed.get_comment is True


@pytest.mark.asyncio
async def test_cli_reads_cookie_from_environment_then_removes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIACRAWLER_COOKIES", "sessionid=environment-secret")

    parsed = await parse_cmd(
        ["--platform", "dy", "--type", "liked", "--lt", "cookie"]
    )

    assert parsed.cookies == "sessionid=environment-secret"
    assert parsed.lt == "cookie"
    assert config.COOKIES == "sessionid=environment-secret"
    assert "MEDIACRAWLER_COOKIES" not in os.environ


@pytest.mark.asyncio
async def test_cli_help_never_displays_cookie_environment_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    secret = "sessionid=must-not-appear-in-help"
    monkeypatch.setenv("MEDIACRAWLER_COOKIES", secret)

    with pytest.raises(SystemExit):
        await parse_cmd(["--help"])

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


@pytest.mark.parametrize("crawler_type", ["liked", "collected"])
def test_api_schema_accepts_only_douyin_personal_modes(
    crawler_type: str,
) -> None:
    request = CrawlerStartRequest(
        platform="dy",
        crawler_type=crawler_type,
    )
    assert request.enable_comments is False
    assert request.enable_sub_comments is False

    with pytest.raises(ValidationError, match="only supported by Douyin"):
        CrawlerStartRequest(platform="xhs", crawler_type=crawler_type)


def test_api_manager_never_puts_cookie_in_argv_or_inherited_empty_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CrawlerManager()
    secret = "sessionid=api-secret"
    request = CrawlerStartRequest(
        platform="dy",
        crawler_type="liked",
        login_type="cookie",
        cookies=secret,
    )

    command = manager._build_command(request)
    child_env = manager._build_process_env(request)

    assert "--cookies" not in command
    assert command[:2] == [sys.executable, "-u"]
    assert secret not in " ".join(command)
    assert child_env["MEDIACRAWLER_COOKIES"] == secret

    monkeypatch.setenv("MEDIACRAWLER_COOKIES", "parent-secret")
    empty_request = CrawlerStartRequest(platform="dy", crawler_type="liked")
    assert (
        "MEDIACRAWLER_COOKIES"
        not in manager._build_process_env(empty_request)
    )


def test_api_nonempty_cookie_selects_cookie_login() -> None:
    request = CrawlerStartRequest(
        platform="dy",
        crawler_type="liked",
        cookies="sessionid=explicit",
    )
    assert request.login_type.value == "cookie"


def test_api_manager_redacts_known_and_generic_cookie_logs() -> None:
    manager = CrawlerManager()
    manager._sensitive_values.add("sessionid=exact-secret; sid_guard=other")

    exact = manager._create_log_entry(
        "failure sessionid=exact-secret; sid_guard=other"
    )
    generic = manager._create_log_entry(
        "Cookie: foo=unknown-secret; bar=second-secret"
    )

    assert "exact-secret" not in exact.message
    assert "other" not in exact.message
    assert "unknown-secret" not in generic.message
    assert "second-secret" not in generic.message
    assert "[REDACTED]" in exact.message
    assert "[REDACTED]" in generic.message


@pytest.mark.asyncio
async def test_api_reader_stays_bound_to_its_original_process() -> None:
    manager = CrawlerManager()

    class FakeProcess:
        def __init__(self, output: str, poll_results: list[int | None]):
            self.stdout = io.StringIO(output)
            self._poll_results = list(poll_results)
            self.returncode = 0

        def poll(self):
            if len(self._poll_results) > 1:
                return self._poll_results.pop(0)
            return self._poll_results[0]

    finished_process = FakeProcess("old process output\n", [0])
    current_process = FakeProcess("new process output\n", [None, 0])
    manager.process = current_process
    manager.status = "running"

    await manager._read_output(finished_process)

    messages = [entry.message for entry in manager.logs]
    assert "old process output" in messages
    assert "new process output" not in messages
    assert manager.process is current_process
    assert manager.status == "running"


@pytest.mark.asyncio
async def test_api_stop_escalates_to_process_tree_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CrawlerManager()
    calls = []

    class FakeProcess:
        pid = 1234
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self):
            return self.returncode

    process = FakeProcess()
    manager.process = process
    manager.status = "running"

    def terminate_tree(force: bool):
        calls.append(force)
        if force:
            process.returncode = -9

    async def no_sleep(_seconds: float):
        return None

    monkeypatch.setattr(manager, "_terminate_process_tree", terminate_tree)
    manager_module = importlib.import_module(
        "api.services.crawler_manager"
    )
    monkeypatch.setattr(manager_module.asyncio, "sleep", no_sleep)

    assert await manager.stop() is True
    assert calls == [False, True]
    assert manager.status == "idle"


@pytest.mark.asyncio
async def test_api_stop_failure_is_not_reported_as_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CrawlerManager()

    class FakeProcess:
        pid = 1234

        @staticmethod
        def poll():
            return None

    manager.process = FakeProcess()
    manager.status = "running"

    def fail_to_terminate(*, force: bool):
        assert force is False
        raise RuntimeError("tree still running")

    monkeypatch.setattr(manager, "_terminate_process_tree", fail_to_terminate)

    assert await manager.stop() is False
    assert manager.status == "error"
    assert manager.error_message == "tree still running"


def test_api_options_and_start_endpoint_expose_personal_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    options = client.get("/api/config/options")
    assert options.status_code == 200
    modes = {item["value"] for item in options.json()["crawler_types"]}
    assert {"liked", "collected"} <= modes

    async def fake_start(request):
        assert request.platform.value == "dy"
        assert request.crawler_type.value == "liked"
        assert request.enable_comments is False
        return True

    monkeypatch.setattr(
        "api.routers.crawler.crawler_manager.start",
        fake_start,
    )
    response = client.post(
        "/api/crawler/start",
        json={"platform": "dy", "crawler_type": "liked"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
