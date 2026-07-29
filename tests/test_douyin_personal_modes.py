import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import config
from database.models import DouyinAweme, DouyinUserAction
from media_platform.douyin import client as douyin_client_module
from media_platform.douyin.client import DouYinClient
from media_platform.douyin.core import DouYinCrawler
from media_platform.douyin.exception import DataFetchError
from media_platform.douyin.login import DouYinLogin
from store import douyin as douyin_store
from store.douyin import _store_impl
from tools import user_hash


class FakePage:
    async def evaluate(self, _script: str):
        return {}


def make_client() -> DouYinClient:
    return DouYinClient(
        headers={"User-Agent": "test-agent", "Cookie": ""},
        playwright_page=FakePage(),
        cookie_dict={},
    )


def test_cookie_parser_preserves_equals_inside_values() -> None:
    parsed = douyin_store.utils.convert_str_cookie_to_dict(
        "sessionid=abc==; ttwid=device=value"
    )
    assert parsed == {
        "sessionid": "abc==",
        "ttwid": "device=value",
    }


@pytest.mark.asyncio
async def test_client_decode_error_does_not_expose_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_body = "<html>private-account-content-密</html>"

    class FakeResponse:
        text = secret_body
        status_code = 502
        headers = {"content-type": "text/html; charset=utf-8"}

        @staticmethod
        def json():
            raise ValueError(secret_body)

    class FakeHttpClient:
        @staticmethod
        async def request(*_args, **_kwargs):
            return FakeResponse()

    @asynccontextmanager
    async def fake_make_async_client(**_kwargs):
        yield FakeHttpClient()

    client = make_client()
    client._refresh_proxy_if_expired = AsyncMock()
    monkeypatch.setattr(
        douyin_client_module,
        "make_async_client",
        fake_make_async_client,
    )

    with pytest.raises(DataFetchError) as exc_info:
        await client.request("GET", "https://www.douyin.com/private")

    error_message = str(exc_info.value)
    assert secret_body not in error_message
    assert "private-account-content" not in error_message
    assert "status=502" in error_message
    assert "content_type=text/html" in error_message
    assert "body_length=" in error_message


@pytest.mark.asyncio
async def test_collected_post_keeps_query_and_form_body_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    client.request = AsyncMock(return_value={"status_code": 0})
    sign_calls = []

    async def fake_get_a_bogus(
        uri,
        query_string,
        post_data,
        user_agent,
        page,
    ):
        sign_calls.append(
            {
                "uri": uri,
                "query_string": query_string,
                "post_data": dict(post_data),
                "user_agent": user_agent,
                "page": page,
            }
        )
        return "signed-post"

    monkeypatch.setattr(
        douyin_client_module,
        "get_a_bogus",
        fake_get_a_bogus,
    )

    await client.get_self_collected_awemes(cursor=7, count=11)

    request_call = client.request.await_args
    assert request_call.kwargs["params"]["aid"] == "6383"
    assert request_call.kwargs["params"]["device_platform"] == "webapp"
    assert request_call.kwargs["params"]["a_bogus"] == "signed-post"
    assert request_call.kwargs["data"] == {"count": 11, "cursor": 7}
    assert request_call.kwargs["headers"]["Content-Type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert len(sign_calls) == 1
    sign_call = sign_calls[0]
    assert sign_call["uri"] == "/aweme/v1/web/aweme/listcollection/"
    assert "aid=6383" in sign_call["query_string"]
    assert "device_platform=webapp" in sign_call["query_string"]
    assert "count=11" not in sign_call["query_string"]
    assert sign_call["post_data"] == {"count": 11, "cursor": 7}
    assert sign_call["user_agent"] == "test-agent"
    assert sign_call["page"] is client.playwright_page


@pytest.mark.asyncio
async def test_personal_gets_use_common_parameter_and_signature_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    client.request = AsyncMock(return_value={"status_code": 0})
    sign_calls = []

    async def fake_get_a_bogus(
        uri,
        query_string,
        post_data,
        user_agent,
        page,
    ):
        sign_calls.append(
            {
                "uri": uri,
                "query_string": query_string,
                "post_data": post_data,
                "user_agent": user_agent,
                "page": page,
            }
        )
        return f"signed-{len(sign_calls)}"

    monkeypatch.setattr(
        douyin_client_module,
        "get_a_bogus",
        fake_get_a_bogus,
    )

    await client.get_self_profile()
    await client.get_self_liked_awemes(
        sec_user_id="sec-user-id",
        max_cursor=7,
        count=11,
    )

    profile_request, liked_request = client.request.await_args_list
    profile_params = profile_request.kwargs["params"]
    liked_params = liked_request.kwargs["params"]
    assert profile_request.kwargs["method"] == "GET"
    assert profile_params["aid"] == "6383"
    assert profile_params["device_platform"] == "webapp"
    assert profile_params["a_bogus"] == "signed-1"
    assert liked_request.kwargs["method"] == "GET"
    assert liked_params["sec_user_id"] == "sec-user-id"
    assert liked_params["max_cursor"] == 7
    assert liked_params["count"] == 11
    assert liked_params["device_platform"] == "webapp"
    assert liked_params["a_bogus"] == "signed-2"
    assert [item["uri"] for item in sign_calls] == [
        "/aweme/v1/web/user/profile/self/",
        "/aweme/v1/web/aweme/favorite/",
    ]
    assert all(item["post_data"] == {} for item in sign_calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile_response",
    [
        {
            "status_code": 0,
            "user": {"uid": "raw-account-id", "sec_uid": "sec-user-id"},
        },
        {
            "status_code": 0,
            "data": {
                "user_info": {
                    "uid": "raw-account-id",
                    "sec_uid": "sec-user-id",
                }
            },
        },
    ],
)
async def test_pong_falls_back_to_authenticated_self_profile(
    profile_response: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()

    async def no_login_markers(*_args, **_kwargs):
        return "", {}

    monkeypatch.setattr(
        "media_platform.douyin.client.utils.convert_browser_context_cookies",
        no_login_markers,
    )
    client.get_self_profile = AsyncMock(return_value=profile_response)

    assert await client.pong(browser_context=object()) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile_response",
    [
        {"status_code": 8},
        {
            "status_code": None,
            "user": {"uid": "stale-account", "sec_uid": "stale-sec"},
        },
    ],
)
async def test_personal_pong_rejects_stale_legacy_login_markers(
    profile_response: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MarkerPage:
        async def evaluate(self, _script: str):
            return {"HasUserLogin": "1"}

    client = DouYinClient(
        headers={"User-Agent": "test-agent", "Cookie": ""},
        playwright_page=MarkerPage(),
        cookie_dict={},
    )

    async def stale_cookies(*_args, **_kwargs):
        return "", {"LOGIN_STATUS": "1"}

    monkeypatch.setattr(
        "media_platform.douyin.client.utils.convert_browser_context_cookies",
        stale_cookies,
    )
    client.get_self_profile = AsyncMock(return_value=profile_response)

    assert (
        await client.pong(
            browser_context=object(),
            require_self_profile=True,
        )
        is False
    )


@pytest.mark.asyncio
async def test_cookie_login_replaces_saved_session_and_uses_self_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeContext:
        def __init__(self):
            self.cleared = False
            self.clear_filter = None
            self.added = []
            self.pages = []

        async def clear_cookies(self, **kwargs):
            self.cleared = True
            self.clear_filter = kwargs.get("domain")

        async def add_cookies(self, cookies):
            self.added.extend(cookies)

        async def cookies(self):
            return []

    class CookiePage:
        def __init__(self):
            self.reloaded = False

        async def reload(self, **_kwargs):
            self.reloaded = True

        async def evaluate(self, script: str):
            assert "profile/self" in script
            assert "user_info" in script
            return {"status_code": 0, "account_id": "new-account"}

    context = FakeContext()
    page = CookiePage()
    context.pages = [page]
    login = DouYinLogin(
        login_type="cookie",
        browser_context=context,
        context_page=page,
        cookie_str="sessionid=new-session; ttwid=new-device",
    )
    monkeypatch.setattr(config, "LOGIN_TYPE", "cookie")

    await login.login_by_cookies()

    assert context.cleared is True
    assert context.clear_filter.search(".douyin.com")
    assert context.clear_filter.search("www.douyin.com")
    assert context.clear_filter.search("example.com") is None
    assert page.reloaded is True
    assert {item["name"] for item in context.added} == {
        "sessionid",
        "ttwid",
    }
    assert await login._check_login_state_once() is True


@pytest.mark.asyncio
async def test_cookie_self_profile_overrides_stale_legacy_login_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StalePage:
        async def evaluate(self, script: str):
            if "profile/self" in script:
                return {"status_code": 8, "account_id": ""}
            return {"HasUserLogin": "1"}

    class StaleContext:
        pages = [StalePage()]

        async def cookies(self):
            return [{"name": "LOGIN_STATUS", "value": "1"}]

    monkeypatch.setattr(config, "LOGIN_TYPE", "cookie")
    login = DouYinLogin(
        login_type="cookie",
        browser_context=StaleContext(),
        context_page=StalePage(),
        cookie_str="sessionid=expired",
    )

    assert await login._check_login_state_once() is False


@pytest.mark.asyncio
async def test_interactive_login_marker_requires_self_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StalePage:
        async def evaluate(self, script: str):
            if "profile/self" in script:
                return {"status_code": 8, "account_id": ""}
            return {"HasUserLogin": "1"}

    class StaleContext:
        pages = [StalePage()]

        async def cookies(self):
            return [{"name": "LOGIN_STATUS", "value": "1"}]

    monkeypatch.setattr(config, "LOGIN_TYPE", "qrcode")
    login = DouYinLogin(
        login_type="qrcode",
        browser_context=StaleContext(),
        context_page=StalePage(),
    )

    assert await login._check_login_state_once() is False


@pytest.mark.asyncio
async def test_self_profile_requires_explicit_success_status() -> None:
    class MissingStatusPage:
        @staticmethod
        async def evaluate(_script: str):
            return {"account_id": "account"}

    login = DouYinLogin(
        login_type="cookie",
        browser_context=object(),
        context_page=MissingStatusPage(),
        cookie_str="sessionid=value",
    )

    assert await login._check_authenticated_self_profile() is False


@pytest.mark.asyncio
async def test_stale_interactive_marker_does_not_bypass_profile_throttle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StalePage:
        profile_checks = 0

        async def evaluate(self, script: str):
            if "profile/self" in script:
                self.profile_checks += 1
                return {"status_code": 8, "account_id": ""}
            return {"HasUserLogin": "1"}

    class StaleContext:
        pages = []

        @staticmethod
        async def cookies():
            return [{"name": "LOGIN_STATUS", "value": "1"}]

    page = StalePage()
    StaleContext.pages = [page]
    monkeypatch.setattr(config, "LOGIN_TYPE", "qrcode")
    login = DouYinLogin(
        login_type="qrcode",
        browser_context=StaleContext(),
        context_page=page,
    )

    assert await login._check_login_state_once() is False
    assert await login._check_login_state_once() is False
    assert page.profile_checks == 1


@pytest.mark.asyncio
async def test_interactive_login_accepts_self_profile_without_legacy_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProfilePage:
        async def evaluate(self, script: str):
            if "profile/self" in script:
                return {"status_code": 0, "account_id": "account"}
            return {}

    class ProfileContext:
        pages = [ProfilePage()]

        async def cookies(self):
            return []

    monkeypatch.setattr(config, "LOGIN_TYPE", "qrcode")
    login = DouYinLogin(
        login_type="qrcode",
        browser_context=ProfileContext(),
        context_page=ProfilePage(),
    )

    assert await login._check_login_state_once() is True


@pytest.mark.asyncio
async def test_liked_feed_paginates_deduplicates_and_honors_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self):
            self.calls = []

        async def get_self_profile(self):
            return {
                "status_code": 0,
                "user": {"uid": "account-123", "sec_uid": "sec-123"},
            }

        async def get_self_liked_awemes(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["max_cursor"] == 0:
                return {
                    "status_code": 0,
                    "aweme_list": [
                        {"aweme_id": "a1"},
                        {"aweme_id": "a2"},
                    ],
                    "has_more": 1,
                    "max_cursor": 10,
                }
            return {
                "status_code": 0,
                "aweme_list": [
                    {"aweme_id": "a2"},
                    {"aweme_id": "a3"},
                ],
                "has_more": 0,
                "max_cursor": 20,
            }

    crawler = object.__new__(DouYinCrawler)
    crawler.dy_client = FakeClient()
    stored_awemes = []
    stored_actions = []
    media_ids = []
    comment_pages = []

    async def store_aweme(aweme_item):
        stored_awemes.append(aweme_item["aweme_id"])

    async def store_action(**kwargs):
        stored_actions.append(kwargs)

    async def store_media(aweme_item):
        media_ids.append(aweme_item["aweme_id"])

    async def store_comments(aweme_ids):
        comment_pages.append(aweme_ids)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 3)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0)
    monkeypatch.setattr(douyin_store, "update_douyin_aweme", store_aweme)
    monkeypatch.setattr(
        douyin_store,
        "update_douyin_user_action",
        store_action,
    )
    monkeypatch.setattr(crawler, "get_aweme_media", store_media)
    monkeypatch.setattr(crawler, "batch_get_note_comments", store_comments)
    monkeypatch.setattr("media_platform.douyin.core.asyncio.sleep", no_sleep)

    await crawler.get_self_liked_awemes()

    assert stored_awemes == ["a1", "a2", "a3"]
    assert media_ids == stored_awemes
    assert [item["aweme_id"] for item in stored_actions] == stored_awemes
    assert {item["action_type"] for item in stored_actions} == {"liked"}
    assert {item["account_id"] for item in stored_actions} == {
        "dy:sec_uid:sec-123"
    }
    assert comment_pages == [["a1", "a2"], ["a3"]]
    assert crawler.dy_client.calls == [
        {"sec_user_id": "sec-123", "max_cursor": 0, "count": 3},
        {"sec_user_id": "sec-123", "max_cursor": 10, "count": 1},
    ]


def test_stable_account_key_prefers_sec_uid_across_profile_shapes() -> None:
    full_profile = {
        "status_code": 0,
        "user": {"uid": "uid-1", "sec_uid": "sec-1"},
    }
    sec_only_profile = {
        "status_code": 0,
        "data": {"user_info": {"sec_uid": "sec-1"}},
    }

    assert DouYinCrawler._stable_self_account_key(full_profile) == (
        "dy:sec_uid:sec-1"
    )
    assert DouYinCrawler._stable_self_account_key(sec_only_profile) == (
        "dy:sec_uid:sec-1"
    )


@pytest.mark.asyncio
async def test_personal_feed_auth_failure_is_not_reported_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExpiredClient:
        async def get_self_profile(self):
            return {"status_code": 8}

    crawler = object.__new__(DouYinCrawler)
    crawler.dy_client = ExpiredClient()
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 1)

    with pytest.raises(DataFetchError, match="self-profile"):
        await crawler.get_self_collected_awemes()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "feed_response",
    [
        {"status_code": 0},
        {"status_code": 0, "aweme_list": {"unexpected": "shape"}},
        {"aweme_list": []},
        {"status_code": 0, "aweme_list": [], "has_more": 1},
        {"status_code": 0, "aweme_list": [{"aweme_id": "1"}]},
    ],
)
async def test_malformed_personal_feed_is_not_reported_as_empty_success(
    feed_response: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MalformedClient:
        async def get_self_profile(self):
            return {
                "status_code": 0,
                "user": {"uid": "account-123"},
            }

        async def get_self_liked_awemes(self, **_kwargs):
            return feed_response

    crawler = object.__new__(DouYinCrawler)
    crawler.dy_client = MalformedClient()
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 1)

    with pytest.raises(DataFetchError):
        await crawler.get_self_liked_awemes()


@pytest.mark.asyncio
async def test_account_action_is_keyed_hmac_and_never_stores_raw_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CaptureStore:
        def __init__(self):
            self.item = None

        async def store_user_action(self, action_item):
            self.item = action_item

    capture_store = CaptureStore()
    monkeypatch.setenv("MEDIACRAWLER_ACCOUNT_HASH_KEY", "unit-test-key")
    user_hash._get_account_hash_key.cache_clear()
    monkeypatch.setattr(
        douyin_store.DouyinStoreFactory,
        "create_store",
        staticmethod(lambda: capture_store),
    )
    monkeypatch.setattr(
        douyin_store.utils,
        "get_current_timestamp",
        lambda: 123456,
    )

    await douyin_store.update_douyin_user_action(
        account_id="raw-account-id",
        aweme_id="aweme-1",
        action_type="collected",
    )

    assert capture_store.item == {
        "account_hash": user_hash.anonymize_account_id("raw-account-id"),
        "aweme_id": "aweme-1",
        "action_type": "collected",
        "observed_ts": 123456,
    }
    assert "raw-account-id" not in repr(capture_store.item)
    assert len(capture_store.item["account_hash"]) == 32
    user_hash._get_account_hash_key.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("store_class", "writer_method"),
    [
        (_store_impl.DouyinCsvStoreImplement, "write_to_csv"),
        (
            _store_impl.DouyinJsonStoreImplement,
            "write_single_item_to_json",
        ),
        (_store_impl.DouyinJsonlStoreImplement, "write_to_jsonl"),
    ],
)
async def test_file_stores_write_dedicated_user_action_output(
    store_class,
    writer_method: str,
) -> None:
    store = object.__new__(store_class)
    store.file_writer = AsyncMock()
    action = {
        "account_hash": "hash",
        "aweme_id": "aweme-1",
        "action_type": "liked",
        "observed_ts": 1,
    }

    await store.store_user_action(action)

    writer = getattr(store.file_writer, writer_method)
    writer.assert_awaited_once_with(item=action, item_type="user_actions")


@pytest.mark.asyncio
async def test_mongo_store_uses_unique_index_and_atomic_upsert() -> None:
    collection = AsyncMock()
    store_class = _store_impl.DouyinMongoStoreImplement
    store_class._user_actions_index_ready = False
    store_class._user_actions_index_lock = asyncio.Lock()
    store = object.__new__(_store_impl.DouyinMongoStoreImplement)
    store.mongo_store = AsyncMock()
    store.mongo_store.get_collection.return_value = collection
    action = {
        "account_hash": "hash",
        "aweme_id": "aweme-1",
        "action_type": "collected",
        "observed_ts": 10,
    }

    await store.store_user_action(action)
    await store.store_user_action({**action, "observed_ts": 20})

    collection.create_index.assert_awaited_once()
    first_update = collection.update_one.await_args_list[0]
    assert first_update.kwargs["upsert"] is True
    assert first_update.args[1]["$set"] == {"observed_ts": 10}
    assert first_update.args[1]["$setOnInsert"] == {
        "account_hash": "hash",
        "aweme_id": "aweme-1",
        "action_type": "collected",
    }
    store_class._user_actions_index_ready = False


@pytest.mark.asyncio
async def test_mongo_index_is_reused_across_factory_store_instances() -> None:
    collection = AsyncMock()
    store_class = _store_impl.DouyinMongoStoreImplement
    store_class._user_actions_index_ready = False
    store_class._user_actions_index_lock = asyncio.Lock()
    stores = []
    for _ in range(2):
        store = object.__new__(store_class)
        store.mongo_store = AsyncMock()
        store.mongo_store.get_collection.return_value = collection
        stores.append(store)

    action = {
        "account_hash": "hash",
        "aweme_id": "aweme-1",
        "action_type": "liked",
        "observed_ts": 10,
    }
    await stores[0].store_user_action(action)
    await stores[1].store_user_action(action)

    collection.create_index.assert_awaited_once()
    store_class._user_actions_index_ready = False


@pytest.mark.asyncio
async def test_sql_store_upserts_observation_and_keeps_action_types_separate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'actions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(DouyinAweme.__table__.create)
        await connection.run_sync(DouyinUserAction.__table__.create)

    session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    @asynccontextmanager
    async def local_session():
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()

    monkeypatch.setattr(_store_impl, "get_session", local_session)
    store = _store_impl.DouyinDbStoreImplement()
    base_item = {
        "account_hash": "hash-a",
        "aweme_id": "aweme-1",
        "action_type": "liked",
        "observed_ts": 100,
    }

    await store.store_content(
        {
            "aweme_id": "aweme-1",
            "title": "",
            "desc": "",
            "last_modify_ts": 100,
        }
    )
    await store.store_user_action(dict(base_item))
    await store.store_user_action({**base_item, "observed_ts": 200})
    await store.store_user_action(
        {**base_item, "action_type": "collected", "observed_ts": 300}
    )

    async with session_factory() as session:
        count = await session.scalar(select(func.count(DouyinUserAction.id)))
        content = await session.scalar(
            select(DouyinAweme).where(
                DouyinAweme.aweme_id == "aweme-1"
            )
        )
        liked = await session.scalar(
            select(DouyinUserAction).where(
                DouyinUserAction.action_type == "liked"
            )
        )
    await engine.dispose()

    assert count == 2
    assert content is not None
    assert content.title == ""
    assert liked.observed_ts == 200
    assert "observed_ts" in DouyinUserAction.__table__.columns
    assert "active" not in DouyinUserAction.__table__.columns
