# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/routers/crawler.py
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

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import config
from ..schemas import CrawlerStartRequest, CrawlerStatusResponse
from ..services import crawler_manager

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.post("/start")
async def start_crawler(request: CrawlerStartRequest):
    """Start crawler task"""
    success = await crawler_manager.start(request)
    if not success:
        # Handle concurrent/duplicate requests: if process is already running, return 400 instead of 500
        if crawler_manager.process and crawler_manager.process.poll() is None:
            raise HTTPException(status_code=400, detail="Crawler is already running")
        raise HTTPException(status_code=500, detail="Failed to start crawler")

    return {"status": "ok", "message": "Crawler started successfully"}


@router.post("/stop")
async def stop_crawler():
    """Stop crawler task"""
    success = await crawler_manager.stop()
    if not success:
        # Handle concurrent/duplicate requests: if process already exited/doesn't exist, return 400 instead of 500
        if not crawler_manager.process or crawler_manager.process.poll() is not None:
            raise HTTPException(status_code=400, detail="No crawler is running")
        raise HTTPException(status_code=500, detail="Failed to stop crawler")

    return {"status": "ok", "message": "Crawler stopped successfully"}


@router.get("/status", response_model=CrawlerStatusResponse)
async def get_crawler_status():
    """Get crawler status"""
    return crawler_manager.get_status()


@router.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    logs = crawler_manager.logs[-limit:] if limit > 0 else crawler_manager.logs
    return {"logs": [log.model_dump() for log in logs]}


def _find_latest_qrcode() -> tuple[Optional[Path], float]:
    """Find the most recent login qrcode image, return (path, mtime_epoch)."""
    qr_dir = Path(crawler_manager._project_root) / config.QRCODE_OUTPUT_DIR
    if not qr_dir.is_dir():
        return None, 0.0
    candidates = sorted(
        qr_dir.glob("login_qrcode_*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None, 0.0
    latest = candidates[0]
    return latest, latest.stat().st_mtime


@router.get("/qrcode")
async def get_login_qrcode():
    """Return the latest login qrcode image for in-page display.

    The crawler subprocess writes the qrcode to QRCODE_OUTPUT_DIR when it
    needs the user to scan (Docker mode). We only serve a qrcode while a
    crawler is running and the image is fresh (<= qrcode_max_age seconds),
    so the frontend does not show a stale code after login succeeded.
    """
    import time

    path, mtime = _find_latest_qrcode()
    if path is None:
        raise HTTPException(status_code=404, detail="no qrcode available")

    # 二维码有效期短(各平台约 1-3 分钟),过期的不给前端展示
    max_age = 180
    if time.time() - mtime > max_age:
        raise HTTPException(status_code=404, detail="qrcode expired")

    return FileResponse(
        str(path),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
