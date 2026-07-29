# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/douyin/_store_impl.py
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


# -*- coding: utf-8 -*-
# @Author  : persist1@126.com
# @Time    : 2025/9/5 19:34
# @Desc    : Douyin storage implementation class
import asyncio
from typing import Dict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.models import DouyinAweme, DouyinAwemeComment, DouyinUserAction
from tools import utils
from tools.async_file_writer import AsyncFileWriter
from var import crawler_type_var
from database.mongodb_store_base import MongoDBStoreBase


class DouyinCsvStoreImplement(AbstractStore):
    def __init__(self):
        self.file_writer = AsyncFileWriter(
            crawler_type=crawler_type_var.get(),
            platform="douyin"
        )

    async def store_content(self, content_item: Dict):
        """
        Douyin content CSV storage implementation
        Args:
            content_item: note item dict

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=content_item,
            item_type="contents"
        )

    async def store_comment(self, comment_item: Dict):
        """
        Douyin comment CSV storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=comment_item,
            item_type="comments"
        )

    async def store_creator(self, creator: Dict):
        """
        Douyin creator CSV storage implementation
        Args:
            creator: creator item dict

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=creator,
            item_type="creators"
        )


    async def store_user_action(self, action_item: Dict):
        await self.file_writer.write_to_csv(
            item=action_item,
            item_type="user_actions",
        )


class DouyinDbStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        """
        Douyin content DB storage implementation
        Args:
            content_item: content item dict
        """
        aweme_id = content_item.get("aweme_id")
        if not aweme_id:
            raise ValueError("Douyin content requires a non-empty aweme_id")
        async with get_session() as session:
            result = await session.execute(select(DouyinAweme).where(DouyinAweme.aweme_id == aweme_id))
            aweme_detail = result.scalar_one_or_none()

            if not aweme_detail:
                content_item["add_ts"] = utils.get_current_timestamp()
                new_content = DouyinAweme(**content_item)
                session.add(new_content)
            else:
                for key, value in content_item.items():
                    setattr(aweme_detail, key, value)
            await session.commit()

    async def store_comment(self, comment_item: Dict):
        """
        Douyin comment DB storage implementation
        Args:
            comment_item: comment item dict
        """
        comment_id = comment_item.get("comment_id")
        async with get_session() as session:
            result = await session.execute(select(DouyinAwemeComment).where(DouyinAwemeComment.comment_id == comment_id))
            comment_detail = result.scalar_one_or_none()

            if not comment_detail:
                comment_item["add_ts"] = utils.get_current_timestamp()
                new_comment = DouyinAwemeComment(**comment_item)
                session.add(new_comment)
            else:
                for key, value in comment_item.items():
                    setattr(comment_detail, key, value)
            await session.commit()

    async def store_creator(self, creator: Dict):
        # 教学版：创作者个人资料不再落库
        pass


    async def store_user_action(self, action_item: Dict):
        account_hash = action_item.get("account_hash")
        aweme_id = action_item.get("aweme_id")
        action_type = action_item.get("action_type")
        async with get_session() as session:
            result = await session.execute(
                select(DouyinUserAction).where(
                    DouyinUserAction.account_hash == account_hash,
                    DouyinUserAction.aweme_id == aweme_id,
                    DouyinUserAction.action_type == action_type,
                )
            )
            user_action = result.scalar_one_or_none()
            if user_action is None:
                session.add(DouyinUserAction(**action_item))
                try:
                    await session.flush()
                except IntegrityError:
                    # Another worker may have inserted the same relation after
                    # our select. Retry as an update under the unique key.
                    await session.rollback()
                    result = await session.execute(
                        select(DouyinUserAction).where(
                            DouyinUserAction.account_hash == account_hash,
                            DouyinUserAction.aweme_id == aweme_id,
                            DouyinUserAction.action_type == action_type,
                        )
                    )
                    user_action = result.scalar_one_or_none()
                    if user_action is None:
                        raise
                    user_action.observed_ts = action_item["observed_ts"]
            else:
                user_action.observed_ts = action_item["observed_ts"]
            await session.commit()


class DouyinJsonStoreImplement(AbstractStore):
    def __init__(self):
        self.file_writer = AsyncFileWriter(
            crawler_type=crawler_type_var.get(),
            platform="douyin"
        )

    async def store_content(self, content_item: Dict):
        """
        content JSON storage implementation
        Args:
            content_item:

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=content_item,
            item_type="contents"
        )

    async def store_comment(self, comment_item: Dict):
        """
        comment JSON storage implementation
        Args:
            comment_item:

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=comment_item,
            item_type="comments"
        )

    async def store_creator(self, creator: Dict):
        """
        creator JSON storage implementation
        Args:
            creator:

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=creator,
            item_type="creators"
        )



    async def store_user_action(self, action_item: Dict):
        await self.file_writer.write_single_item_to_json(
            item=action_item,
            item_type="user_actions",
        )


class DouyinJsonlStoreImplement(AbstractStore):
    def __init__(self):
        self.file_writer = AsyncFileWriter(
            crawler_type=crawler_type_var.get(),
            platform="douyin"
        )

    async def store_content(self, content_item: Dict):
        await self.file_writer.write_to_jsonl(
            item=content_item,
            item_type="contents"
        )

    async def store_comment(self, comment_item: Dict):
        await self.file_writer.write_to_jsonl(
            item=comment_item,
            item_type="comments"
        )

    async def store_creator(self, creator: Dict):
        await self.file_writer.write_to_jsonl(
            item=creator,
            item_type="creators"
        )


    async def store_user_action(self, action_item: Dict):
        await self.file_writer.write_to_jsonl(
            item=action_item,
            item_type="user_actions",
        )


class DouyinSqliteStoreImplement(DouyinDbStoreImplement):
    pass


class DouyinMongoStoreImplement(AbstractStore):
    """Douyin MongoDB storage implementation"""

    _user_actions_index_ready = False
    _user_actions_index_lock = asyncio.Lock()

    def __init__(self):
        self.mongo_store = MongoDBStoreBase(collection_prefix="douyin")

    async def store_content(self, content_item: Dict):
        """
        Store video content to MongoDB
        Args:
            content_item: Video content data
        """
        aweme_id = content_item.get("aweme_id")
        if not aweme_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="contents",
            query={"aweme_id": aweme_id},
            data=content_item
        )
        utils.logger.info(f"[DouyinMongoStoreImplement.store_content] Saved aweme {aweme_id} to MongoDB")

    async def store_comment(self, comment_item: Dict):
        """
        Store comment to MongoDB
        Args:
            comment_item: Comment data
        """
        comment_id = comment_item.get("comment_id")
        if not comment_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="comments",
            query={"comment_id": comment_id},
            data=comment_item
        )
        utils.logger.info(f"[DouyinMongoStoreImplement.store_comment] Saved comment {comment_id} to MongoDB")

    async def store_creator(self, creator_item: Dict):
        # 教学版：创作者个人资料不再落库
        pass


    async def store_user_action(self, action_item: Dict):
        account_hash = action_item.get("account_hash")
        aweme_id = action_item.get("aweme_id")
        action_type = action_item.get("action_type")
        if not account_hash or not aweme_id or not action_type:
            return

        collection = await self.mongo_store.get_collection("user_actions")
        store_class = type(self)
        if not store_class._user_actions_index_ready:
            async with store_class._user_actions_index_lock:
                if not store_class._user_actions_index_ready:
                    await collection.create_index(
                        [
                            ("account_hash", 1),
                            ("aweme_id", 1),
                            ("action_type", 1),
                        ],
                        unique=True,
                        name="uq_douyin_user_action",
                    )
                    store_class._user_actions_index_ready = True

        query = {
            "account_hash": account_hash,
            "aweme_id": aweme_id,
            "action_type": action_type,
        }
        await collection.update_one(
            query,
            {
                "$set": {"observed_ts": action_item["observed_ts"]},
                "$setOnInsert": query,
            },
            upsert=True,
        )
        utils.logger.info(
            "[DouyinMongoStoreImplement.store_user_action] "
            f"Saved {action_type}/{aweme_id} to MongoDB"
        )


class DouyinExcelStoreImplement:
    """Douyin Excel storage implementation - Global singleton"""

    def __new__(cls, *args, **kwargs):
        from store.excel_store_base import ExcelStoreBase
        return ExcelStoreBase.get_instance(
            platform="douyin",
            crawler_type=crawler_type_var.get()
        )
