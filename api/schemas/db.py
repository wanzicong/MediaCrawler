# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/schemas/db.py
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
数据库查询 API 的 Pydantic 模型定义
Database Query API Pydantic Models
"""

from enum import Enum
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class PlatformEnum(str, Enum):
    """支持的媒体平台枚举"""
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"
    WEIBO = "weibo"
    TIEBA = "tieba"
    ZHIHU = "zhihu"
    XHS = "xhs"


class ContentTypeEnum(str, Enum):
    """内容类型枚举"""
    VIDEO = "video"
    NOTE = "note"
    ARTICLE = "article"
    COMMENT = "comment"


class SortOrderEnum(str, Enum):
    """排序方向枚举"""
    ASC = "asc"
    DESC = "desc"


# ============ 通用响应模型 ============

class PaginatedResponse(BaseModel):
    """分页响应包装"""
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class ApiResponse(BaseModel):
    """统一 API 响应格式"""
    success: bool = True
    message: str = "OK"
    data: Optional[Any] = None


class PlatformInfo(BaseModel):
    """平台信息"""
    platform: str
    label: str
    icon: str
    content_count: int = 0
    comment_count: int = 0
    creator_count: int = 0


class GlobalStats(BaseModel):
    """全局统计数据"""
    total_content: int = 0
    total_comments: int = 0
    total_creators: int = 0
    platforms: List[PlatformInfo] = Field(default_factory=list)


# ============ 内容查询模型 ============

class ContentListRequest(BaseModel):
    """内容列表查询参数"""
    platform: PlatformEnum
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    keyword: Optional[str] = Field(default=None, description="搜索关键词")
    start_time: Optional[int] = Field(default=None, description="开始时间戳")
    end_time: Optional[int] = Field(default=None, description="结束时间戳")
    sort_by: str = Field(default="create_time", description="排序字段")
    sort_order: SortOrderEnum = Field(default=SortOrderEnum.DESC, description="排序方向")


class ContentDetailRequest(BaseModel):
    """内容详情查询参数"""
    platform: PlatformEnum
    content_id: str


class ContentItem(BaseModel):
    """内容项"""
    id: Optional[int] = None
    note_id: Optional[str] = None
    video_id: Optional[str] = None
    aweme_id: Optional[str] = None
    content_id: Optional[str] = None
    user_id: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    ip_location: Optional[str] = None
    title: Optional[str] = None
    desc: Optional[str] = None
    content: Optional[str] = None
    liked_count: Optional[str] = None
    collected_count: Optional[str] = None
    comment_count: Optional[str] = None
    share_count: Optional[str] = None
    create_time: Optional[int] = None
    add_ts: Optional[int] = None
    last_modify_ts: Optional[int] = None
    source_keyword: Optional[str] = None

    class Config:
        populate_by_name = True


# ============ 评论查询模型 ============

class CommentListRequest(BaseModel):
    """评论列表查询参数"""
    platform: PlatformEnum
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    content_id: Optional[str] = Field(default=None, description="内容ID")
    keyword: Optional[str] = Field(default=None, description="评论内容关键词")
    start_time: Optional[int] = Field(default=None, description="开始时间戳")
    end_time: Optional[int] = Field(default=None, description="结束时间戳")


class CommentItem(BaseModel):
    """评论项"""
    id: Optional[int] = None
    comment_id: Optional[str] = None
    user_id: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    ip_location: Optional[str] = None
    content: Optional[str] = None
    like_count: Optional[str] = None
    sub_comment_count: Optional[int] = 0
    create_time: Optional[int] = None
    parent_comment_id: Optional[str] = None
    add_ts: Optional[int] = None

    class Config:
        populate_by_name = True


# ============ 创作者查询模型 ============

class CreatorListRequest(BaseModel):
    """创作者列表查询参数"""
    platform: PlatformEnum
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    keyword: Optional[str] = Field(default=None, description="搜索关键词")
    sort_by: str = Field(default="fans", description="排序字段")
    sort_order: SortOrderEnum = Field(default=SortOrderEnum.DESC, description="排序方向")


class CreatorItem(BaseModel):
    """创作者项"""
    id: Optional[int] = None
    user_id: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    ip_location: Optional[str] = None
    gender: Optional[str] = None
    follows: Optional[str] = None
    fans: Optional[str] = None
    desc: Optional[str] = None
    add_ts: Optional[int] = None
    last_modify_ts: Optional[int] = None

    class Config:
        populate_by_name = True


# ============ 搜索模型 ============

class SearchRequest(BaseModel):
    """跨平台搜索参数"""
    keyword: str = Field(min_length=1, max_length=200, description="搜索关键词")
    platforms: List[PlatformEnum] = Field(default_factory=list, description="平台列表")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    start_time: Optional[int] = Field(default=None, description="开始时间戳")
    end_time: Optional[int] = Field(default=None, description="结束时间戳")


class SearchResult(BaseModel):
    """搜索结果项"""
    platform: str
    content_type: str
    content_id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    nickname: Optional[str] = None
    liked_count: Optional[str] = None
    comment_count: Optional[str] = None
    create_time: Optional[int] = None


# ============ 导出模型 ============

class ExportRequest(BaseModel):
    """数据导出请求"""
    platform: Optional[PlatformEnum] = Field(default=None, description="平台")
    content_type: str = Field(default="content", description="内容类型: content/comments/creators")
    format: str = Field(default="json", description="导出格式: json/csv/excel")
    keyword: Optional[str] = Field(default=None, description="搜索关键词")
    start_time: Optional[int] = Field(default=None, description="开始时间戳")
    end_time: Optional[int] = Field(default=None, description="结束时间戳")
    max_records: int = Field(default=10000, ge=1, le=100000, description="最大导出记录数")


class ExportResponse(BaseModel):
    """导出响应"""
    success: bool = True
    message: str = "OK"
    data: Optional[List[Dict[str, Any]]] = None
    total: Optional[int] = None
    filename: Optional[str] = None
