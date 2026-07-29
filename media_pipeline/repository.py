# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_pipeline\repository.py
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

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

import config

from .models import MediaAsset, TranscriptionJob


class MediaRepository:
    """Durable SQLite registry for media assets and transcription jobs."""

    def __init__(self, db_path: str | Path | None = None):
        media_root = Path(config.MEDIA_OUTPUT_DIR)
        self.db_path = Path(db_path) if db_path else media_root / "media_pipeline.db"
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS media_assets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        content_id TEXT NOT NULL,
                        media_type TEXT NOT NULL DEFAULT 'video',
                        source_url TEXT NOT NULL DEFAULT '',
                        local_path TEXT NOT NULL DEFAULT '',
                        mime_type TEXT NOT NULL DEFAULT '',
                        file_size INTEGER NOT NULL DEFAULT 0,
                        sha256 TEXT NOT NULL DEFAULT '',
                        duration_ms INTEGER NOT NULL DEFAULT 0,
                        has_audio INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'discovered',
                        error_message TEXT NOT NULL DEFAULT '',
                        run_id TEXT NOT NULL DEFAULT '',
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        UNIQUE(platform, content_id, media_type)
                    );

                    CREATE INDEX IF NOT EXISTS idx_media_assets_run_id
                    ON media_assets(run_id);

                    CREATE TABLE IF NOT EXISTS transcription_jobs (
                        job_id TEXT PRIMARY KEY,
                        asset_id INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        model TEXT NOT NULL,
                        device TEXT NOT NULL,
                        compute_type TEXT NOT NULL,
                        language TEXT NOT NULL DEFAULT 'auto',
                        options_hash TEXT NOT NULL,
                        requested_backend TEXT NOT NULL DEFAULT 'local',
                        actual_backend TEXT NOT NULL DEFAULT '',
                        resolved_model TEXT NOT NULL DEFAULT '',
                        fallback_reason TEXT NOT NULL DEFAULT '',
                        full_text TEXT NOT NULL DEFAULT '',
                        segments_json TEXT NOT NULL DEFAULT '[]',
                        transcript_path TEXT NOT NULL DEFAULT '',
                        subtitle_path TEXT NOT NULL DEFAULT '',
                        error_message TEXT NOT NULL DEFAULT '',
                        created_at INTEGER NOT NULL,
                        started_at INTEGER NOT NULL DEFAULT 0,
                        finished_at INTEGER NOT NULL DEFAULT 0,
                        FOREIGN KEY(asset_id) REFERENCES media_assets(id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_transcription_jobs_asset
                    ON transcription_jobs(asset_id, created_at DESC);
                    """
                )
                # Different crawler/MCP processes can initialize the same legacy
                # database at the same time.  Serialize the schema inspection and
                # ALTER statements so every waiter re-reads the columns after the
                # process holding the write transaction commits.
                await db.execute("BEGIN IMMEDIATE")
                cursor = await db.execute("PRAGMA table_info(transcription_jobs)")
                columns = {row[1] for row in await cursor.fetchall()}
                migrations = {
                    "requested_backend": (
                        "ALTER TABLE transcription_jobs ADD COLUMN "
                        "requested_backend TEXT NOT NULL DEFAULT 'local'"
                    ),
                    "actual_backend": (
                        "ALTER TABLE transcription_jobs ADD COLUMN "
                        "actual_backend TEXT NOT NULL DEFAULT ''"
                    ),
                    "resolved_model": (
                        "ALTER TABLE transcription_jobs ADD COLUMN "
                        "resolved_model TEXT NOT NULL DEFAULT ''"
                    ),
                    "fallback_reason": (
                        "ALTER TABLE transcription_jobs ADD COLUMN "
                        "fallback_reason TEXT NOT NULL DEFAULT ''"
                    ),
                }
                for column, statement in migrations.items():
                    if column not in columns:
                        await db.execute(statement)
                await db.execute(
                    """
                    UPDATE transcription_jobs
                    SET requested_backend = 'local',
                        actual_backend = 'local',
                        resolved_model = model
                    WHERE status = 'completed' AND actual_backend = ''
                    """
                )
                await db.commit()
            self._initialized = True

    @staticmethod
    def _asset_from_row(row: aiosqlite.Row) -> MediaAsset:
        return MediaAsset(
            id=row["id"],
            platform=row["platform"],
            content_id=row["content_id"],
            media_type=row["media_type"],
            source_url=row["source_url"],
            local_path=row["local_path"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            sha256=row["sha256"],
            duration_ms=row["duration_ms"],
            has_audio=bool(row["has_audio"]),
            status=row["status"],
            error_message=row["error_message"],
            run_id=row["run_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _job_from_row(row: aiosqlite.Row) -> TranscriptionJob:
        return TranscriptionJob(
            job_id=row["job_id"],
            asset_id=row["asset_id"],
            status=row["status"],
            model=row["model"],
            device=row["device"],
            compute_type=row["compute_type"],
            language=row["language"],
            options_hash=row["options_hash"],
            requested_backend=row["requested_backend"],
            actual_backend=row["actual_backend"],
            resolved_model=row["resolved_model"],
            fallback_reason=row["fallback_reason"],
            full_text=row["full_text"],
            segments_json=row["segments_json"],
            transcript_path=row["transcript_path"],
            subtitle_path=row["subtitle_path"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    async def upsert_asset(
        self,
        *,
        platform: str,
        content_id: str,
        media_type: str = "video",
        source_url: str = "",
        local_path: str = "",
        mime_type: str = "",
        file_size: int = 0,
        sha256: str = "",
        duration_ms: int = 0,
        has_audio: bool = False,
        status: str = "discovered",
        error_message: str = "",
        run_id: str = "",
    ) -> MediaAsset:
        await self.initialize()
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO media_assets (
                    platform, content_id, media_type, source_url, local_path,
                    mime_type, file_size, sha256, duration_ms, has_audio,
                    status, error_message, run_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, content_id, media_type) DO UPDATE SET
                    source_url=excluded.source_url,
                    local_path=excluded.local_path,
                    mime_type=excluded.mime_type,
                    file_size=excluded.file_size,
                    sha256=excluded.sha256,
                    duration_ms=excluded.duration_ms,
                    has_audio=excluded.has_audio,
                    status=excluded.status,
                    error_message=excluded.error_message,
                    run_id=excluded.run_id,
                    updated_at=excluded.updated_at
                """,
                (
                    platform,
                    content_id,
                    media_type,
                    source_url,
                    local_path,
                    mime_type,
                    file_size,
                    sha256,
                    duration_ms,
                    int(has_audio),
                    status,
                    error_message,
                    run_id,
                    now,
                    now,
                ),
            )
            await db.commit()
            cursor = await db.execute(
                """
                SELECT * FROM media_assets
                WHERE platform = ? AND content_id = ? AND media_type = ?
                """,
                (platform, content_id, media_type),
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to persist media asset")
        return self._asset_from_row(row)

    async def get_asset(
        self,
        *,
        asset_id: int | None = None,
        platform: str = "",
        content_id: str = "",
        media_type: str = "video",
    ) -> MediaAsset | None:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if asset_id is not None:
                cursor = await db.execute(
                    "SELECT * FROM media_assets WHERE id = ?",
                    (asset_id,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM media_assets
                    WHERE platform = ? AND content_id = ? AND media_type = ?
                    """,
                    (platform, content_id, media_type),
                )
            row = await cursor.fetchone()
        return self._asset_from_row(row) if row else None

    async def list_assets(
        self,
        *,
        platform: str = "",
        content_id: str = "",
        run_id: str = "",
        status: str = "",
        limit: int = 100,
    ) -> list[MediaAsset]:
        await self.initialize()
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("platform", platform),
            ("content_id", content_id),
            ("run_id", run_id),
            ("status", status),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = min(max(int(limit), 1), 500)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM media_assets {where} ORDER BY updated_at DESC LIMIT ?",
                (*params, safe_limit),
            )
            rows = await cursor.fetchall()
        return [self._asset_from_row(row) for row in rows]

    async def create_job(
        self,
        *,
        asset_id: int,
        model: str,
        device: str,
        compute_type: str,
        language: str,
        options_hash: str,
        requested_backend: str,
    ) -> TranscriptionJob:
        await self.initialize()
        existing = await self.find_completed_job(asset_id, options_hash)
        if existing:
            return existing
        job_id = f"transcribe_{uuid.uuid4().hex}"
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO transcription_jobs (
                    job_id, asset_id, status, model, device, compute_type,
                    language, options_hash, requested_backend, created_at
                ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    asset_id,
                    model,
                    device,
                    compute_type,
                    language,
                    options_hash,
                    requested_backend,
                    now,
                ),
            )
            await db.commit()
        job = await self.get_job(job_id)
        if job is None:
            raise RuntimeError("Failed to create transcription job")
        return job

    async def find_completed_job(
        self,
        asset_id: int,
        options_hash: str,
    ) -> TranscriptionJob | None:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM transcription_jobs
                WHERE asset_id = ? AND options_hash = ? AND status = 'completed'
                  AND NOT (
                    requested_backend = 'api' AND actual_backend = 'local'
                  )
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (asset_id, options_hash),
            )
            row = await cursor.fetchone()
        return self._job_from_row(row) if row else None

    async def get_job(self, job_id: str) -> TranscriptionJob | None:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM transcription_jobs WHERE job_id = ?",
                (job_id,),
            )
            row = await cursor.fetchone()
        return self._job_from_row(row) if row else None

    async def find_active_job(
        self,
        asset_id: int,
        options_hash: str,
    ) -> TranscriptionJob | None:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM transcription_jobs
                WHERE asset_id = ? AND options_hash = ?
                  AND status IN ('pending', 'running')
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (asset_id, options_hash),
            )
            row = await cursor.fetchone()
        return self._job_from_row(row) if row else None

    async def get_latest_job_for_asset(self, asset_id: int) -> TranscriptionJob | None:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM transcription_jobs
                WHERE asset_id = ?
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (asset_id,),
            )
            row = await cursor.fetchone()
        return self._job_from_row(row) if row else None

    async def update_job(self, job_id: str, **fields: Any) -> TranscriptionJob:
        await self.initialize()
        allowed = {
            "status",
            "full_text",
            "segments_json",
            "transcript_path",
            "subtitle_path",
            "actual_backend",
            "resolved_model",
            "fallback_reason",
            "error_message",
            "started_at",
            "finished_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            job = await self.get_job(job_id)
            if job is None:
                raise KeyError(job_id)
            return job
        assignments = ", ".join(f"{key} = ?" for key in updates)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE transcription_jobs SET {assignments} WHERE job_id = ?",
                (*updates.values(), job_id),
            )
            await db.commit()
        job = await self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job
