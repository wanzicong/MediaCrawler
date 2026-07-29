# -*- coding: utf-8 -*-
"""Cross-process lock protecting persistent browser profiles."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import BinaryIO, Optional


class CrawlerProcessLock:
    """A small cross-platform advisory lock with an explicit timeout."""

    def __init__(self, lock_path: Optional[Path] = None) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.lock_path = lock_path or (
            project_root / "browser_data" / ".crawler_process.lock"
        )
        self._handle: Optional[BinaryIO] = None

    def acquire(self, timeout: float = 3.0) -> None:
        if self._handle is not None:
            return

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)
        handle = self.lock_path.open("r+b")
        if self.lock_path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()

        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(
                        handle.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                self._handle = handle
                return
            except OSError as exc:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise TimeoutError(
                        "another MediaCrawler process is using browser_data"
                    ) from exc
                time.sleep(0.1)

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> "CrawlerProcessLock":
        self.acquire()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.release()
