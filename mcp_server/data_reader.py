# -*- coding: utf-8 -*-
"""读取 MediaCrawler 爬取产生的数据文件。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# MediaCrawler 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据存储根目录
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# MCP 使用短平台代号，部分文件存储实现使用完整英文目录名。
PLATFORM_DATA_DIRS = {
    "dy": "douyin",
    "ks": "kuaishou",
    "wb": "weibo",
}


def _get_date_str() -> str:
    """获取当前日期字符串 (YYYY-MM-DD)"""
    return datetime.now().strftime("%Y-%m-%d")


def find_data_files(
    platform: str,
    crawler_type: str,
    file_type: str = "jsonl",
    date_str: Optional[str] = None,
) -> Dict[str, str]:
    """查找爬取产生的数据文件。

    Args:
        platform: 平台代号 (xhs/dy/ks/bili/wb/tieba/zhihu)
        crawler_type: 爬取类型 (search/detail/creator)
        file_type: 文件类型 (jsonl/json/csv)
        date_str: 日期字符串，默认今天

    Returns:
        dict: {item_type: file_path}，item_type 为 contents/comments/creators
    """
    if date_str is None:
        date_str = _get_date_str()

    platform_dir = PLATFORM_DATA_DIRS.get(platform, platform)
    base_path = os.path.join(DATA_DIR, platform_dir, file_type)
    files: Dict[str, str] = {}

    if not os.path.exists(base_path):
        return files

    # MediaCrawler 文件名格式: {crawler_type}_{item_type}_{date}.{file_type}
    for item_type in ("contents", "comments", "creators"):
        prefix = f"{crawler_type}_{item_type}_{date_str}"
        for fname in os.listdir(base_path):
            if fname.startswith(prefix) and fname.endswith(f".{file_type}"):
                files[item_type] = os.path.join(base_path, fname)
                break

    return files


def read_data_file(file_path: str, max_items: int = 100) -> Dict[str, Any]:
    """读取单个数据文件。

    Args:
        file_path: 数据文件路径
        max_items: 最多返回的条目数

    Returns:
        dict: {count: 总数, items: 数据列表}
    """
    if not os.path.exists(file_path):
        return {"count": 0, "items": []}

    ext = os.path.splitext(file_path)[1].lower()
    items: List[Any] = []

    try:
        if ext == ".jsonl":
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        items.append(json.loads(line))
        elif ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]
        elif ext == ".csv":
            import csv
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                items = list(reader)
        else:
            return {"count": 0, "items": [], "error": f"不支持的文件类型: {ext}"}
    except Exception as e:
        return {"count": 0, "items": [], "error": f"读取失败: {e}"}

    total = len(items)
    return {
        "count": total,
        "items": items[:max_items],
    }


def get_data_summary(
    platform: str,
    crawler_type: str,
    file_type: str = "jsonl",
) -> Dict[str, Any]:
    """获取爬取数据的摘要信息（文件路径 + 条目数 + 前3条预览）。

    Args:
        platform: 平台代号
        crawler_type: 爬取类型
        file_type: 文件类型

    Returns:
        dict: 包含文件路径、条目数、预览数据
    """
    files = find_data_files(platform, crawler_type, file_type)
    result: Dict[str, Any] = {"platform": platform, "crawler_type": crawler_type, "files": {}}

    for item_type, fpath in files.items():
        data = read_data_file(fpath, max_items=3)
        result["files"][item_type] = {
            "file_path": os.path.relpath(fpath, PROJECT_ROOT),
            "count": data["count"],
            "preview": data["items"],
        }

    return result


def get_full_data(
    platform: str,
    crawler_type: str,
    file_type: str = "jsonl",
    max_items: int = 200,
) -> Dict[str, Any]:
    """获取爬取的完整数据。

    Args:
        platform: 平台代号
        crawler_type: 爬取类型
        file_type: 文件类型
        max_items: 每个文件最多返回的条目数

    Returns:
        dict: 包含文件路径和完整数据
    """
    files = find_data_files(platform, crawler_type, file_type)
    result: Dict[str, Any] = {"platform": platform, "crawler_type": crawler_type, "files": {}}

    for item_type, fpath in files.items():
        data = read_data_file(fpath, max_items=max_items)
        result["files"][item_type] = {
            "file_path": os.path.relpath(fpath, PROJECT_ROOT),
            "count": data["count"],
            "items": data["items"],
        }

    return result
