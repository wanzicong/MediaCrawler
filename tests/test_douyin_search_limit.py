import pytest

import config
from media_platform.douyin import core


@pytest.mark.asyncio
async def test_search_respects_max_notes_count(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def search_info_by_keyword(self, **_kwargs):
            return {
                "data": [
                    {"aweme_info": {"aweme_id": str(index)}}
                    for index in range(13)
                ],
                "extra": {"logid": "next-page"},
            }

    crawler = object.__new__(core.DouYinCrawler)
    crawler.dy_client = FakeClient()
    stored_ids: list[str] = []

    async def store_aweme(aweme_item):
        stored_ids.append(aweme_item["aweme_id"])

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 5)
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "KEYWORDS", "人工智能")
    monkeypatch.setattr(core.douyin_store, "update_douyin_aweme", store_aweme)
    monkeypatch.setattr(crawler, "get_aweme_media", noop)
    monkeypatch.setattr(crawler, "batch_get_note_comments", noop)
    monkeypatch.setattr(core.asyncio, "sleep", noop)

    await crawler.search()

    assert stored_ids == ["0", "1", "2", "3", "4"]
