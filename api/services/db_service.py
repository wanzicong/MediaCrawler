# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/services/db_service.py
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

"""
数据库查询服务层
Database Query Service Layer
提供统一的数据库数据访问接口
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_session import get_session
from database import models as db_models
from tools.utils import logger

# 平台内容模型映射
PLATFORM_CONTENT_MODELS = {
    "bilibili": db_models.BilibiliVideo,
    "douyin": db_models.DouyinAweme,
    "kuaishou": db_models.KuaishouVideo,
    "weibo": db_models.WeiboNote,
    "tieba": db_models.TiebaNote,
    "zhihu": db_models.ZhihuContent,
    "xhs": db_models.XhsNote,
}

# 平台评论模型映射
PLATFORM_COMMENT_MODELS = {
    "bilibili": db_models.BilibiliVideoComment,
    "douyin": db_models.DouyinAwemeComment,
    "kuaishou": db_models.KuaishouVideoComment,
    "weibo": db_models.WeiboNoteComment,
    "tieba": db_models.TiebaComment,
    "zhihu": db_models.ZhihuComment,
    "xhs": db_models.XhsNoteComment,
}

# 平台创作者模型映射
PLATFORM_CREATOR_MODELS = {
    "bilibili": db_models.BilibiliUpInfo,
    "douyin": db_models.DyCreator,
    "weibo": db_models.WeiboCreator,
    "tieba": db_models.TiebaCreator,
    "zhihu": db_models.ZhihuCreator,
    "xhs": db_models.XhsCreator,
}

# 平台内容ID字段映射
CONTENT_ID_FIELDS = {
    "bilibili": "video_id",
    "douyin": "aweme_id",
    "kuaishou": "video_id",
    "weibo": "note_id",
    "tieba": "note_id",
    "zhihu": "content_id",
    "xhs": "note_id",
}


class DatabaseQueryService:
    """统一数据库查询服务"""

    def __init__(self):
        self.logger = logger
        self._check_db_config()

    def _check_db_config(self):
        """检查数据库配置是否正确"""
        import config
        if config.SAVE_DATA_OPTION in ["json", "jsonl", "csv"]:
            self.logger.warning(
                f"[DbQueryService] 当前数据存储配置为 '{config.SAVE_DATA_OPTION}'，"
                f"不支持数据库查询 API。请将 SAVE_DATA_OPTION 设置为 'db' 以启用 MySQL 数据库存储。"
            )

    async def get_platform_list(self) -> List[Dict[str, Any]]:
        """
        [DbQueryService.get_platform_list] 获取所有平台列表及统计信息
        """
        self.logger.info("[DbQueryService.get_platform_list] 开始获取平台列表")

        platform_stats = []
        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_platform_list] 无法获取数据库会话")
                return []

            try:
                for platform in PLATFORM_CONTENT_MODELS.keys():
                    content_model = PLATFORM_CONTENT_MODELS[platform]
                    comment_model = PLATFORM_COMMENT_MODELS.get(platform)
                    creator_model = PLATFORM_CREATOR_MODELS.get(platform)

                    # 获取各表数量
                    content_count = await self._count_table(session, content_model)
                    comment_count = await self._count_table(session, comment_model) if comment_model else 0
                    creator_count = await self._count_table(session, creator_model) if creator_model else 0

                    platform_stats.append({
                        "platform": platform,
                        "label": self._get_platform_label(platform),
                        "icon": self._get_platform_icon(platform),
                        "content_count": content_count,
                        "comment_count": comment_count,
                        "creator_count": creator_count,
                    })

                    self.logger.info(
                        f"[DbQueryService.get_platform_list] 平台 {platform} 统计: "
                        f"内容={content_count}, 评论={comment_count}, 创作者={creator_count}"
                    )

                self.logger.info(f"[DbQueryService.get_platform_list] 获取到 {len(platform_stats)} 个平台")
                return platform_stats

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_platform_list] 错误: {str(e)}")
                raise

    async def get_global_stats(self) -> Dict[str, Any]:
        """
        [DbQueryService.get_global_stats] 获取全局统计数据
        """
        self.logger.info("[DbQueryService.get_global_stats] 开始计算全局统计")

        total_content = 0
        total_comments = 0
        total_creators = 0
        platforms = []

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_global_stats] 无法获取数据库会话")
                return {
                    "total_content": 0,
                    "total_comments": 0,
                    "total_creators": 0,
                    "platforms": []
                }

            try:
                for platform in PLATFORM_CONTENT_MODELS.keys():
                    content_model = PLATFORM_CONTENT_MODELS[platform]
                    comment_model = PLATFORM_COMMENT_MODELS.get(platform)
                    creator_model = PLATFORM_CREATOR_MODELS.get(platform)

                    content_count = await self._count_table(session, content_model)
                    comment_count = await self._count_table(session, comment_model) if comment_model else 0
                    creator_count = await self._count_table(session, creator_model) if creator_model else 0

                    total_content += content_count
                    total_comments += comment_count
                    total_creators += creator_count

                    platforms.append({
                        "platform": platform,
                        "label": self._get_platform_label(platform),
                        "icon": self._get_platform_icon(platform),
                        "content_count": content_count,
                        "comment_count": comment_count,
                        "creator_count": creator_count,
                    })

                self.logger.info(
                    f"[DbQueryService.get_global_stats] 统计完成: "
                    f"内容={total_content}, 评论={total_comments}, 创作者={total_creators}"
                )

                return {
                    "total_content": total_content,
                    "total_comments": total_comments,
                    "total_creators": total_creators,
                    "platforms": platforms,
                }

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_global_stats] 错误: {str(e)}")
                raise

    async def get_content_list(
        self,
        platform: str,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        sort_by: str = "create_time",
        sort_order: str = "desc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        [DbQueryService.get_content_list] 获取平台内容列表
        """
        self.logger.info(
            f"[DbQueryService.get_content_list] 开始查询: platform={platform}, page={page}, "
            f"page_size={page_size}, keyword={keyword}, start_time={start_time}, end_time={end_time}"
        )

        model = PLATFORM_CONTENT_MODELS.get(platform)
        if not model:
            self.logger.error(f"[DbQueryService.get_content_list] 不支持的平台: {platform}")
            raise ValueError(f"不支持的平台: {platform}")

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_content_list] 无法获取数据库会话")
                return [], 0

            try:
                # 构建基础查询
                query = select(model)
                count_query = select(func.count()).select_from(model)

                # 关键词过滤
                if keyword:
                    search_pattern = f"%{keyword}%"
                    title_col = getattr(model, "title", None)
                    desc_col = getattr(model, "desc", None)

                    keyword_conditions = []
                    if title_col is not None:
                        keyword_conditions.append(title_col.ilike(search_pattern))
                    if desc_col is not None:
                        keyword_conditions.append(desc_col.ilike(search_pattern))

                    if keyword_conditions:
                        query = query.where(or_(*keyword_conditions))
                        count_query = count_query.where(or_(*keyword_conditions))

                # 时间范围过滤
                if start_time or end_time:
                    time_conditions = []
                    time_col = getattr(model, "create_time", None)
                    if time_col is not None:
                        if start_time:
                            time_conditions.append(time_col >= start_time)
                        if end_time:
                            time_col_end = getattr(model, "create_time", None)
                            if time_col_end is not None:
                                time_conditions.append(time_col_end <= end_time)

                    if time_conditions:
                        query = query.where(and_(*time_conditions))
                        count_query = count_query.where(and_(*time_conditions))

                # 排序
                sort_column = getattr(model, sort_by, None)
                if sort_column is not None:
                    if sort_order == "desc":
                        query = query.order_by(sort_column.desc())
                    else:
                        query = query.order_by(sort_column.asc())
                else:
                    default_sort = getattr(model, "create_time", None)
                    if default_sort is not None:
                        query = query.order_by(default_sort.desc())

                # 分页
                offset = (page - 1) * page_size
                query = query.offset(offset).limit(page_size)

                # 执行查询
                result = await session.execute(query)
                items = result.scalars().all()

                count_result = await session.execute(count_query)
                total = count_result.scalar() or 0

                # 转换为字典
                items_data = [self._model_to_dict(item) for item in items]

                self.logger.info(
                    f"[DbQueryService.get_content_list] 查询完成: platform={platform}, "
                    f"total={total}, 返回={len(items_data)}"
                )

                return items_data, total

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_content_list] 错误: {str(e)}")
                raise

    async def get_content_detail(
        self,
        platform: str,
        content_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        [DbQueryService.get_content_detail] 获取内容详情
        """
        self.logger.info(
            f"[DbQueryService.get_content_detail] 开始查询: platform={platform}, content_id={content_id}"
        )

        model = PLATFORM_CONTENT_MODELS.get(platform)
        if not model:
            self.logger.error(f"[DbQueryService.get_content_detail] 不支持的平台: {platform}")
            raise ValueError(f"不支持的平台: {platform}")

        id_field = CONTENT_ID_FIELDS.get(platform, "id")

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_content_detail] 无法获取数据库会话")
                return None

            try:
                # 根据平台处理ID类型
                id_value = content_id
                if id_field == "video_id" and platform == "bilibili":
                    try:
                        id_value = int(content_id)
                    except ValueError:
                        pass

                # 构建查询
                query = select(model).where(text(f"{id_field} = :id_value")).params(id_value=id_value)
                result = await session.execute(query)
                item = result.scalar_one_or_none()

                if item:
                    item_dict = self._model_to_dict(item)
                    self.logger.info(
                        f"[DbQueryService.get_content_detail] 找到内容: platform={platform}, content_id={content_id}"
                    )
                    return item_dict
                else:
                    self.logger.warning(
                        f"[DbQueryService.get_content_detail] 未找到内容: platform={platform}, content_id={content_id}"
                    )
                    return None

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_content_detail] 错误: {str(e)}")
                raise

    async def get_content_comments(
        self,
        platform: str,
        content_id: str,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        [DbQueryService.get_content_comments] 获取指定内容的评论列表
        """
        self.logger.info(
            f"[DbQueryService.get_content_comments] 开始查询: platform={platform}, "
            f"content_id={content_id}, page={page}, page_size={page_size}"
        )

        model = PLATFORM_COMMENT_MODELS.get(platform)
        if not model:
            self.logger.error(f"[DbQueryService.get_content_comments] 不支持的平台: {platform}")
            raise ValueError(f"不支持的平台: {platform}")

        # 内容ID字段映射
        content_id_field_map = {
            "bilibili": "video_id",
            "douyin": "aweme_id",
            "kuaishou": "video_id",
            "weibo": "note_id",
            "tieba": "note_id",
            "zhihu": "content_id",
            "xhs": "note_id",
        }

        content_id_field = content_id_field_map.get(platform, "note_id")

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_content_comments] 无法获取数据库会话")
                return [], 0

            try:
                # 处理ID类型
                content_id_value = content_id
                if content_id_field == "video_id" and platform == "bilibili":
                    try:
                        content_id_value = int(content_id)
                    except ValueError:
                        pass

                # 构建查询
                query = select(model)
                count_query = select(func.count()).select_from(model)

                # 按内容ID过滤
                query = query.where(text(f"{content_id_field} = :content_id")).params(content_id=content_id_value)
                count_query = count_query.where(text(f"{content_id_field} = :content_id")).params(content_id=content_id_value)

                # 关键词过滤
                if keyword:
                    search_pattern = f"%{keyword}%"
                    content_col = getattr(model, "content", None)
                    if content_col is not None:
                        query = query.where(content_col.ilike(search_pattern))
                        count_query = count_query.where(content_col.ilike(search_pattern))

                # 按创建时间排序
                sort_col = getattr(model, "create_time", None)
                if sort_col is not None:
                    query = query.order_by(sort_col.desc())

                # 分页
                offset = (page - 1) * page_size
                query = query.offset(offset).limit(page_size)

                # 执行
                result = await session.execute(query)
                items = result.scalars().all()

                count_result = await session.execute(count_query)
                total = count_result.scalar() or 0

                items_data = [self._model_to_dict(item) for item in items]

                self.logger.info(
                    f"[DbQueryService.get_content_comments] 查询完成: platform={platform}, "
                    f"content_id={content_id}, total={total}, 返回={len(items_data)}"
                )

                return items_data, total

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_content_comments] 错误: {str(e)}")
                raise

    async def get_creator_list(
        self,
        platform: str,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        sort_by: str = "fans",
        sort_order: str = "desc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        [DbQueryService.get_creator_list] 获取创作者列表
        """
        self.logger.info(
            f"[DbQueryService.get_creator_list] 开始查询: platform={platform}, page={page}, "
            f"page_size={page_size}, keyword={keyword}, sort_by={sort_by}"
        )

        model = PLATFORM_CREATOR_MODELS.get(platform)
        if not model:
            self.logger.error(f"[DbQueryService.get_creator_list] 不支持的平台: {platform}")
            raise ValueError(f"不支持的平台: {platform}")

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_creator_list] 无法获取数据库会话")
                return [], 0

            try:
                query = select(model)
                count_query = select(func.count()).select_from(model)

                # 关键词过滤
                if keyword:
                    search_pattern = f"%{keyword}%"
                    nickname_col = getattr(model, "nickname", None)
                    desc_col = getattr(model, "desc", None)

                    keyword_conditions = []
                    if nickname_col is not None:
                        keyword_conditions.append(nickname_col.ilike(search_pattern))
                    if desc_col is not None:
                        keyword_conditions.append(desc_col.ilike(search_pattern))

                    if keyword_conditions:
                        query = query.where(or_(*keyword_conditions))
                        count_query = count_query.where(or_(*keyword_conditions))

                # 排序
                sort_column = getattr(model, sort_by, None)
                if sort_column is not None:
                    if sort_order == "desc":
                        query = query.order_by(sort_column.desc())
                    else:
                        query = query.order_by(sort_column.asc())

                # 分页
                offset = (page - 1) * page_size
                query = query.offset(offset).limit(page_size)

                # 执行
                result = await session.execute(query)
                items = result.scalars().all()

                count_result = await session.execute(count_query)
                total = count_result.scalar() or 0

                items_data = [self._model_to_dict(item) for item in items]

                self.logger.info(
                    f"[DbQueryService.get_creator_list] 查询完成: platform={platform}, "
                    f"total={total}, 返回={len(items_data)}"
                )

                return items_data, total

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_creator_list] 错误: {str(e)}")
                raise

    async def get_creator_detail(
        self,
        platform: str,
        creator_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        [DbQueryService.get_creator_detail] 获取创作者详情
        """
        self.logger.info(
            f"[DbQueryService.get_creator_detail] 开始查询: platform={platform}, creator_id={creator_id}"
        )

        model = PLATFORM_CREATOR_MODELS.get(platform)
        if not model:
            self.logger.error(f"[DbQueryService.get_creator_detail] 不支持的平台: {platform}")
            raise ValueError(f"不支持的平台: {platform}")

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_creator_detail] 无法获取数据库会话")
                return None

            try:
                # 处理user_id类型
                user_id_value = creator_id
                if platform == "bilibili":
                    try:
                        user_id_value = int(creator_id)
                    except ValueError:
                        pass

                query = select(model).where(text("user_id = :user_id")).params(user_id=user_id_value)
                result = await session.execute(query)
                item = result.scalar_one_or_none()

                if item:
                    item_dict = self._model_to_dict(item)
                    self.logger.info(
                        f"[DbQueryService.get_creator_detail] 找到创作者: platform={platform}, creator_id={creator_id}"
                    )
                    return item_dict
                else:
                    self.logger.warning(
                        f"[DbQueryService.get_creator_detail] 未找到创作者: platform={platform}, creator_id={creator_id}"
                    )
                    return None

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_creator_detail] 错误: {str(e)}")
                raise

    async def get_creator_content(
        self,
        platform: str,
        creator_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        [DbQueryService.get_creator_content] 获取创作者的内容列表
        """
        self.logger.info(
            f"[DbQueryService.get_creator_content] 开始查询: platform={platform}, "
            f"creator_id={creator_id}, page={page}, page_size={page_size}"
        )

        content_model = PLATFORM_CONTENT_MODELS.get(platform)
        if not content_model:
            self.logger.error(f"[DbQueryService.get_creator_content] 不支持的平台: {platform}")
            raise ValueError(f"不支持的平台: {platform}")

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_creator_content] 无法获取数据库会话")
                return [], 0

            try:
                # 处理user_id类型
                user_id_value = creator_id
                if platform == "bilibili":
                    try:
                        user_id_value = int(creator_id)
                    except ValueError:
                        pass

                # 构建查询
                query = select(content_model).where(text("user_id = :user_id")).params(user_id=user_id_value)
                count_query = select(func.count()).select_from(content_model).where(
                    text("user_id = :user_id")
                ).params(user_id=user_id_value)

                # 按创建时间排序
                sort_col = getattr(content_model, "create_time", None)
                if sort_col is not None:
                    query = query.order_by(sort_col.desc())

                # 分页
                offset = (page - 1) * page_size
                query = query.offset(offset).limit(page_size)

                # 执行
                result = await session.execute(query)
                items = result.scalars().all()

                count_result = await session.execute(count_query)
                total = count_result.scalar() or 0

                items_data = [self._model_to_dict(item) for item in items]

                self.logger.info(
                    f"[DbQueryService.get_creator_content] 查询完成: platform={platform}, "
                    f"creator_id={creator_id}, total={total}, 返回={len(items_data)}"
                )

                return items_data, total

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_creator_content] 错误: {str(e)}")
                raise

    async def get_comment_list(
        self,
        platform: str,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        [DbQueryService.get_comment_list] 获取评论列表
        """
        self.logger.info(
            f"[DbQueryService.get_comment_list] 开始查询: platform={platform}, page={page}, "
            f"page_size={page_size}, keyword={keyword}"
        )

        model = PLATFORM_COMMENT_MODELS.get(platform)
        if not model:
            self.logger.error(f"[DbQueryService.get_comment_list] 不支持的平台: {platform}")
            raise ValueError(f"不支持的平台: {platform}")

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.get_comment_list] 无法获取数据库会话")
                return [], 0

            try:
                query = select(model)
                count_query = select(func.count()).select_from(model)

                # 关键词过滤
                if keyword:
                    search_pattern = f"%{keyword}%"
                    content_col = getattr(model, "content", None)
                    if content_col is not None:
                        query = query.where(content_col.ilike(search_pattern))
                        count_query = count_query.where(content_col.ilike(search_pattern))

                # 时间范围过滤
                if start_time or end_time:
                    time_conditions = []
                    time_col = getattr(model, "create_time", None)
                    if time_col is not None:
                        if start_time:
                            time_conditions.append(time_col >= start_time)
                        if end_time:
                            time_conditions.append(time_col <= end_time)

                    if time_conditions:
                        query = query.where(and_(*time_conditions))
                        count_query = count_query.where(and_(*time_conditions))

                # 按创建时间排序
                sort_col = getattr(model, "create_time", None)
                if sort_col is not None:
                    query = query.order_by(sort_col.desc())

                # 分页
                offset = (page - 1) * page_size
                query = query.offset(offset).limit(page_size)

                # 执行
                result = await session.execute(query)
                items = result.scalars().all()

                count_result = await session.execute(count_query)
                total = count_result.scalar() or 0

                items_data = [self._model_to_dict(item) for item in items]

                self.logger.info(
                    f"[DbQueryService.get_comment_list] 查询完成: platform={platform}, "
                    f"total={total}, 返回={len(items_data)}"
                )

                return items_data, total

            except Exception as e:
                self.logger.error(f"[DbQueryService.get_comment_list] 错误: {str(e)}")
                raise

    async def cross_platform_search(
        self,
        keyword: str,
        platforms: List[str],
        page: int = 1,
        page_size: int = 20,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        [DbQueryService.cross_platform_search] 跨平台全局搜索
        """
        self.logger.info(
            f"[DbQueryService.cross_platform_search] 开始搜索: keyword={keyword}, "
            f"platforms={platforms}, page={page}, page_size={page_size}"
        )

        if not platforms:
            platforms = list(PLATFORM_CONTENT_MODELS.keys())

        all_results = []
        total = 0
        search_pattern = f"%{keyword}%"

        async with get_session() as session:
            if session is None:
                self.logger.warning("[DbQueryService.cross_platform_search] 无法获取数据库会话")
                return [], 0

            try:
                for platform in platforms:
                    if platform not in PLATFORM_CONTENT_MODELS:
                        self.logger.warning(f"[DbQueryService.cross_platform_search] 跳过不支持的平台: {platform}")
                        continue

                    model = PLATFORM_CONTENT_MODELS[platform]

                    # 构建查询
                    query = select(model)
                    count_query = select(func.count()).select_from(model)

                    # 关键词搜索条件
                    title_col = getattr(model, "title", None)
                    desc_col = getattr(model, "desc", None)
                    content_col = getattr(model, "content", None)

                    search_conditions = []
                    if title_col is not None:
                        search_conditions.append(title_col.ilike(search_pattern))
                    if desc_col is not None:
                        search_conditions.append(desc_col.ilike(search_pattern))
                    if content_col is not None:
                        search_conditions.append(content_col.ilike(search_pattern))

                    if not search_conditions:
                        continue

                    query = query.where(or_(*search_conditions))
                    count_query = count_query.where(or_(*search_conditions))

                    # 时间过滤
                    if start_time or end_time:
                        time_col = getattr(model, "create_time", None)
                        if time_col is not None:
                            time_conditions = []
                            if start_time:
                                time_conditions.append(time_col >= start_time)
                            if end_time:
                                time_conditions.append(time_col <= end_time)

                            if time_conditions:
                                query = query.where(and_(*time_conditions))
                                count_query = count_query.where(and_(*time_conditions))

                    # 排序和限制
                    sort_col = getattr(model, "create_time", None)
                    if sort_col is not None:
                        query = query.order_by(sort_col.desc())
                    query = query.limit(100)  # 每个平台最多100条

                    # 执行
                    result = await session.execute(query)
                    items = result.scalars().all()

                    count_result = await session.execute(count_query)
                    platform_total = count_result.scalar() or 0
                    total += platform_total

                    # 转换为搜索结果格式
                    for item in items:
                        item_dict = self._model_to_dict(item)
                        all_results.append({
                            "platform": platform,
                            "content_type": "content",
                            "content_id": (
                                item_dict.get("note_id") or
                                item_dict.get("video_id") or
                                item_dict.get("aweme_id") or
                                item_dict.get("content_id")
                            ),
                            "title": item_dict.get("title"),
                            "content": item_dict.get("desc") or item_dict.get("content"),
                            "nickname": item_dict.get("nickname"),
                            "liked_count": item_dict.get("liked_count"),
                            "comment_count": item_dict.get("comment_count"),
                            "create_time": item_dict.get("create_time"),
                        })

                # 按创建时间排序并分页
                all_results.sort(key=lambda x: x.get("create_time") or 0, reverse=True)

                offset = (page - 1) * page_size
                paginated_results = all_results[offset:offset + page_size]

                self.logger.info(
                    f"[DbQueryService.cross_platform_search] 搜索完成: keyword={keyword}, "
                    f"total={total}, 返回={len(paginated_results)}"
                )

                return paginated_results, total

            except Exception as e:
                self.logger.error(f"[DbQueryService.cross_platform_search] 错误: {str(e)}")
                raise

    async def export_data(
        self,
        platform: Optional[str],
        content_type: str,
        format: str,
        keyword: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        max_records: int = 10000,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        [DbQueryService.export_data] 导出数据
        """
        self.logger.info(
            f"[DbQueryService.export_data] 开始导出: platform={platform}, content_type={content_type}, "
            f"format={format}, max_records={max_records}"
        )

        if platform:
            platforms = [platform]
        else:
            platforms = list(PLATFORM_CONTENT_MODELS.keys())

        all_data = []

        try:
            for p in platforms:
                if content_type == "content":
                    data, _ = await self.get_content_list(
                        p, page=1, page_size=max_records,
                        keyword=keyword, start_time=start_time, end_time=end_time
                    )
                elif content_type == "comments":
                    data, _ = await self.get_comment_list(
                        p, page=1, page_size=max_records,
                        keyword=keyword, start_time=start_time, end_time=end_time
                    )
                elif content_type == "creators":
                    data, _ = await self.get_creator_list(
                        p, page=1, page_size=max_records, keyword=keyword
                    )
                else:
                    continue

                # 为每条记录添加平台字段
                for item in data:
                    item["platform"] = p
                all_data.extend(data)

                if len(all_data) >= max_records:
                    break

            self.logger.info(
                f"[DbQueryService.export_data] 导出完成: 共 {len(all_data)} 条记录, 格式={format}"
            )

            return all_data[:max_records], format

        except Exception as e:
            self.logger.error(f"[DbQueryService.export_data] 错误: {str(e)}")
            raise

    # ============ 辅助方法 ============

    async def _count_table(self, session: AsyncSession, model) -> int:
        """
        [DbQueryService._count_table] 统计表记录数
        """
        try:
            if model is None:
                return 0
            result = await session.execute(select(func.count()).select_from(model))
            return result.scalar() or 0
        except Exception as e:
            self.logger.warning(f"[DbQueryService._count_table] 统计表记录数错误: {str(e)}")
            return 0

    def _model_to_dict(self, model) -> Dict[str, Any]:
        """
        [DbQueryService._model_to_dict] 将 SQLAlchemy 模型转换为字典
        """
        result = {}
        for column in model.__table__.columns:
            value = getattr(model, column.name, None)
            result[column.name] = value
        return result

    def _get_platform_label(self, platform: str) -> str:
        """
        [DbQueryService._get_platform_label] 获取平台显示名称
        """
        labels = {
            "bilibili": "B站",
            "douyin": "抖音",
            "kuaishou": "快手",
            "weibo": "微博",
            "tieba": "贴吧",
            "zhihu": "知乎",
            "xhs": "小红书",
        }
        return labels.get(platform, platform)

    def _get_platform_icon(self, platform: str) -> str:
        """
        [DbQueryService._get_platform_icon] 获取平台图标名称
        """
        icons = {
            "bilibili": "tv",
            "douyin": "music",
            "kuaishou": "video",
            "weibo": "message-circle",
            "tieba": "messages-square",
            "zhihu": "help-circle",
            "xhs": "book-open",
        }
        return icons.get(platform, "globe")


# 全局单例
db_query_service = DatabaseQueryService()
