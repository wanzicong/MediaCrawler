# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# 本文件为 MediaCrawler 教学版的一部分。
# 出于教学与防骚扰定位，爬取结果中不保留任何可定位到真人的用户个人信息
# （用户 ID、IP 归属地、头像、主页链接、签名、性别等一律不采集；
# 昵称保留但做中间脱敏）。本模块提供匿名化与脱敏工具。
import hashlib
import hmac
import os
import secrets
from functools import lru_cache
from pathlib import Path


def anonymize_user_id(user_id) -> str:
    """把原始用户 ID 转成匿名哈希，用于内容/评论记录的创作者分组，
    不暴露真实身份。返回 sha256 截断 16 位的十六进制串。"""
    if user_id is None:
        return ""
    s = str(user_id).strip()
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=1)
def _get_account_hash_key() -> bytes:
    """Load a stable local key used only for authenticated account actions."""
    env_key = os.getenv("MEDIACRAWLER_ACCOUNT_HASH_KEY", "").strip()
    if env_key:
        return env_key.encode("utf-8")

    configured_path = os.getenv("MEDIACRAWLER_ACCOUNT_HASH_KEY_FILE", "").strip()
    key_path = (
        Path(configured_path)
        if configured_path
        else Path(__file__).resolve().parent.parent
        / "browser_data"
        / ".account_hash_key"
    )
    key_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        stored_key = key_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        stored_key = secrets.token_hex(32)
        try:
            with key_path.open("x", encoding="ascii") as key_file:
                key_file.write(stored_key)
            try:
                key_path.chmod(0o600)
            except OSError:
                pass
        except FileExistsError:
            stored_key = key_path.read_text(encoding="ascii").strip()

    if not stored_key:
        raise RuntimeError(f"Account hash key file is empty: {key_path}")
    return stored_key.encode("ascii")


def anonymize_account_id(account_id) -> str:
    """Create a non-enumerable, stable HMAC for the signed-in account id."""
    if account_id is None:
        return ""
    normalized_id = str(account_id).strip()
    if not normalized_id:
        return ""
    return hmac.new(
        _get_account_hash_key(),
        normalized_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def mask_nickname(name) -> str:
    """昵称中间脱敏：首尾各保留 1 字，中间替换为星号。
    - 长度 <= 1：返回 "*"
    - 长度 == 2：首字 + "*"
    - 长度 >= 3：首字 + "***" + 尾字
    这样既保留教学分析所需的内容归属语义，又无法据昵称定位到真人。
    """
    if name is None:
        return ""
    s = str(name)
    if len(s) <= 1:
        return "*"
    if len(s) == 2:
        return s[0] + "*"
    return s[0] + "***" + s[-1]
