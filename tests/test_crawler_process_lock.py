from pathlib import Path

import pytest

from tools.crawler_process_lock import CrawlerProcessLock


def test_crawler_process_lock_prevents_concurrent_profile_use(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "crawler.lock"
    first = CrawlerProcessLock(lock_path)
    second = CrawlerProcessLock(lock_path)

    first.acquire(timeout=0)
    try:
        with pytest.raises(TimeoutError, match="another MediaCrawler"):
            second.acquire(timeout=0)
    finally:
        first.release()

    second.acquire(timeout=0)
    second.release()
