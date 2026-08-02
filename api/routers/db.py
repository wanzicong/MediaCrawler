# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/routers/db.py
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
数据库查询 API 路由
Database Query API Routes
提供 RESTful API 用于查询 MySQL 数据库中的爬虫数据
"""

import math
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import JSONResponse, StreamingResponse
import csv
import io
import json
from datetime import datetime

from ..schemas.db import (
    PlatformEnum,
    PaginatedResponse,
    ApiResponse,
    GlobalStats,
    PlatformInfo,
    ContentListRequest,
    ContentDetailRequest,
    CommentListRequest,
    CreatorListRequest,
    SearchRequest,
    ExportRequest,
    SearchResult,
    SortOrderEnum,
)
from ..services.db_service import db_query_service, PLATFORM_CONTENT_MODELS
from tools.utils import logger

router = APIRouter(prefix="/db", tags=["database"])

# 响应类型别名
ContentResponse = dict
CommentResponse = dict
CreatorResponse = dict


# ============ 平台和统计端点 ============

@router.get("/platforms", response_model=ApiResponse)
async def get_platforms():
    """
    [DbApi.get_platforms] 获取所有平台列表及记录统计
    GET /api/db/platforms
    """
    logger.info("[DbApi.get_platforms] 接收到请求")

    try:
        platforms = await db_query_service.get_platform_list()

        logger.info(f"[DbApi.get_platforms] 返回 {len(platforms)} 个平台")
        return ApiResponse(
            success=True,
            message="平台列表获取成功",
            data={"platforms": platforms}
        )

    except Exception as e:
        logger.error(f"[DbApi.get_platforms] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取平台列表失败: {str(e)}")


@router.get("/stats", response_model=ApiResponse)
async def get_global_stats():
    """
    [DbApi.get_global_stats] 获取全局数据统计
    GET /api/db/stats
    """
    logger.info("[DbApi.get_global_stats] 接收到请求")

    try:
        stats = await db_query_service.get_global_stats()

        logger.info(
            f"[DbApi.get_global_stats] 统计完成: "
            f"内容={stats.get('total_content')}, "
            f"评论={stats.get('total_comments')}, "
            f"创作者={stats.get('total_creators')}"
        )

        return ApiResponse(
            success=True,
            message="统计数据获取成功",
            data=stats
        )

    except Exception as e:
        logger.error(f"[DbApi.get_global_stats] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}")


# ============ 内容端点 ============

@router.get("/{platform}/content", response_model=ApiResponse)
async def get_content_list(
    platform: PlatformEnum = Path(..., description="平台名称"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(default=None, description="搜索关键词"),
    start_time: Optional[int] = Query(default=None, description="开始时间戳"),
    end_time: Optional[int] = Query(default=None, description="结束时间戳"),
    sort_by: str = Query(default="create_time", regex="^(create_time|liked_count|comment_count)$", description="排序字段"),
    sort_order: str = Query(default="desc", regex="^(asc|desc)$", description="排序方向"),
):
    """
    [DbApi.get_content_list] 获取平台内容列表
    GET /api/db/{platform}/content
    """
    logger.info(
        f"[DbApi.get_content_list] 接收到请求: platform={platform.value}, page={page}, "
        f"page_size={page_size}, keyword={keyword}, sort_by={sort_by}, sort_order={sort_order}"
    )

    try:
        items, total = await db_query_service.get_content_list(
            platform=platform.value,
            page=page,
            page_size=page_size,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        logger.info(
            f"[DbApi.get_content_list] 查询完成: platform={platform.value}, "
            f"total={total}, page={page}, 返回={len(items)} 条"
        )

        return ApiResponse(
            success=True,
            message="内容列表获取成功",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    except ValueError as e:
        logger.warning(f"[DbApi.get_content_list] 参数验证错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DbApi.get_content_list] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取内容列表失败: {str(e)}")


@router.get("/{platform}/content/{content_id}", response_model=ApiResponse)
async def get_content_detail(
    platform: PlatformEnum = Path(..., description="平台名称"),
    content_id: str = Path(..., description="内容ID"),
):
    """
    [DbApi.get_content_detail] 获取内容详情
    GET /api/db/{platform}/content/{content_id}
    """
    logger.info(
        f"[DbApi.get_content_detail] 接收到请求: platform={platform.value}, content_id={content_id}"
    )

    try:
        content = await db_query_service.get_content_detail(
            platform=platform.value,
            content_id=content_id,
        )

        if content is None:
            logger.warning(
                f"[DbApi.get_content_detail] 内容未找到: platform={platform.value}, content_id={content_id}"
            )
            raise HTTPException(status_code=404, detail="内容未找到")

        logger.info(
            f"[DbApi.get_content_detail] 返回内容详情: platform={platform.value}, content_id={content_id}"
        )

        return ApiResponse(
            success=True,
            message="内容详情获取成功",
            data=content
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DbApi.get_content_detail] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取内容详情失败: {str(e)}")


@router.get("/{platform}/content/{content_id}/comments", response_model=ApiResponse)
async def get_content_comments(
    platform: PlatformEnum = Path(..., description="平台名称"),
    content_id: str = Path(..., description="内容ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(default=None, description="评论内容关键词"),
):
    """
    [DbApi.get_content_comments] 获取指定内容的评论列表
    GET /api/db/{platform}/content/{content_id}/comments
    """
    logger.info(
        f"[DbApi.get_content_comments] 接收到请求: platform={platform.value}, "
        f"content_id={content_id}, page={page}, page_size={page_size}"
    )

    try:
        items, total = await db_query_service.get_content_comments(
            platform=platform.value,
            content_id=content_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        logger.info(
            f"[DbApi.get_content_comments] 查询完成: platform={platform.value}, "
            f"content_id={content_id}, total={total}, 返回={len(items)} 条"
        )

        return ApiResponse(
            success=True,
            message="评论列表获取成功",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    except ValueError as e:
        logger.warning(f"[DbApi.get_content_comments] 参数验证错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DbApi.get_content_comments] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取评论列表失败: {str(e)}")


# ============ 创作者端点 ============

@router.get("/{platform}/creators", response_model=ApiResponse)
async def get_creator_list(
    platform: PlatformEnum = Path(..., description="平台名称"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(default=None, description="搜索关键词"),
    sort_by: str = Query(default="fans", regex="^(fans|follows|interaction)$", description="排序字段"),
    sort_order: str = Query(default="desc", regex="^(asc|desc)$", description="排序方向"),
):
    """
    [DbApi.get_creator_list] 获取平台创作者列表
    GET /api/db/{platform}/creators
    """
    logger.info(
        f"[DbApi.get_creator_list] 接收到请求: platform={platform.value}, page={page}, "
        f"page_size={page_size}, keyword={keyword}, sort_by={sort_by}"
    )

    try:
        items, total = await db_query_service.get_creator_list(
            platform=platform.value,
            page=page,
            page_size=page_size,
            keyword=keyword,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        logger.info(
            f"[DbApi.get_creator_list] 查询完成: platform={platform.value}, "
            f"total={total}, page={page}, 返回={len(items)} 条"
        )

        return ApiResponse(
            success=True,
            message="创作者列表获取成功",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    except ValueError as e:
        logger.warning(f"[DbApi.get_creator_list] 参数验证错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DbApi.get_creator_list] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取创作者列表失败: {str(e)}")


@router.get("/{platform}/creators/{creator_id}", response_model=ApiResponse)
async def get_creator_detail(
    platform: PlatformEnum = Path(..., description="平台名称"),
    creator_id: str = Path(..., description="创作者ID"),
):
    """
    [DbApi.get_creator_detail] 获取创作者详情
    GET /api/db/{platform}/creators/{creator_id}
    """
    logger.info(
        f"[DbApi.get_creator_detail] 接收到请求: platform={platform.value}, creator_id={creator_id}"
    )

    try:
        creator = await db_query_service.get_creator_detail(
            platform=platform.value,
            creator_id=creator_id,
        )

        if creator is None:
            logger.warning(
                f"[DbApi.get_creator_detail] 创作者未找到: platform={platform.value}, creator_id={creator_id}"
            )
            raise HTTPException(status_code=404, detail="创作者未找到")

        logger.info(
            f"[DbApi.get_creator_detail] 返回创作者详情: platform={platform.value}, creator_id={creator_id}"
        )

        return ApiResponse(
            success=True,
            message="创作者详情获取成功",
            data=creator
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DbApi.get_creator_detail] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取创作者详情失败: {str(e)}")


@router.get("/{platform}/creators/{creator_id}/content", response_model=ApiResponse)
async def get_creator_content(
    platform: PlatformEnum = Path(..., description="平台名称"),
    creator_id: str = Path(..., description="创作者ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
):
    """
    [DbApi.get_creator_content] 获取创作者的内容列表
    GET /api/db/{platform}/creators/{creator_id}/content
    """
    logger.info(
        f"[DbApi.get_creator_content] 接收到请求: platform={platform.value}, "
        f"creator_id={creator_id}, page={page}, page_size={page_size}"
    )

    try:
        items, total = await db_query_service.get_creator_content(
            platform=platform.value,
            creator_id=creator_id,
            page=page,
            page_size=page_size,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        logger.info(
            f"[DbApi.get_creator_content] 查询完成: platform={platform.value}, "
            f"creator_id={creator_id}, total={total}, 返回={len(items)} 条"
        )

        return ApiResponse(
            success=True,
            message="创作者内容列表获取成功",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    except ValueError as e:
        logger.warning(f"[DbApi.get_creator_content] 参数验证错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DbApi.get_creator_content] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取创作者内容列表失败: {str(e)}")


# ============ 评论端点 ============

@router.get("/{platform}/comments", response_model=ApiResponse)
async def get_comment_list(
    platform: PlatformEnum = Path(..., description="平台名称"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(default=None, description="评论内容关键词"),
    start_time: Optional[int] = Query(default=None, description="开始时间戳"),
    end_time: Optional[int] = Query(default=None, description="结束时间戳"),
):
    """
    [DbApi.get_comment_list] 获取平台评论列表
    GET /api/db/{platform}/comments
    """
    logger.info(
        f"[DbApi.get_comment_list] 接收到请求: platform={platform.value}, page={page}, "
        f"page_size={page_size}, keyword={keyword}"
    )

    try:
        items, total = await db_query_service.get_comment_list(
            platform=platform.value,
            page=page,
            page_size=page_size,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        logger.info(
            f"[DbApi.get_comment_list] 查询完成: platform={platform.value}, "
            f"total={total}, page={page}, 返回={len(items)} 条"
        )

        return ApiResponse(
            success=True,
            message="评论列表获取成功",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    except ValueError as e:
        logger.warning(f"[DbApi.get_comment_list] 参数验证错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DbApi.get_comment_list] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取评论列表失败: {str(e)}")


# ============ 搜索端点 ============

@router.get("/search", response_model=ApiResponse)
async def cross_platform_search(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    platforms: Optional[str] = Query(default=None, description="逗号分隔的平台列表"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    start_time: Optional[int] = Query(default=None, description="开始时间戳"),
    end_time: Optional[int] = Query(default=None, description="结束时间戳"),
):
    """
    [DbApi.cross_platform_search] 跨平台全局搜索
    GET /api/db/search
    """
    logger.info(
        f"[DbApi.cross_platform_search] 接收到请求: keyword={keyword}, platforms={platforms}, "
        f"page={page}, page_size={page_size}"
    )

    try:
        # 解析平台列表
        platform_list = []
        if platforms:
            platform_list = [p.strip() for p in platforms.split(",")]

        items, total = await db_query_service.cross_platform_search(
            keyword=keyword,
            platforms=platform_list,
            page=page,
            page_size=page_size,
            start_time=start_time,
            end_time=end_time,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        logger.info(
            f"[DbApi.cross_platform_search] 搜索完成: keyword={keyword}, "
            f"total={total}, page={page}, 返回={len(items)} 条"
        )

        return ApiResponse(
            success=True,
            message="搜索完成",
            data={
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    except Exception as e:
        logger.error(f"[DbApi.cross_platform_search] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


# ============ 导出端点 ============

@router.post("/export")
async def export_data(request: ExportRequest):
    """
    [DbApi.export_data] 导出数据
    POST /api/db/export
    """
    logger.info(
        f"[DbApi.export_data] 接收到请求: platform={request.platform}, "
        f"content_type={request.content_type}, format={request.format}, max_records={request.max_records}"
    )

    try:
        data, format_used = await db_query_service.export_data(
            platform=request.platform.value if request.platform else None,
            content_type=request.content_type,
            format=request.format,
            keyword=request.keyword,
            start_time=request.start_time,
            end_time=request.end_time,
            max_records=request.max_records,
        )

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        platform_str = request.platform.value if request.platform else "all"
        filename = f"{platform_str}_{request.content_type}_{timestamp}"

        logger.info(
            f"[DbApi.export_data] 导出完成: 共 {len(data)} 条记录, 格式={format_used}, 文件名={filename}"
        )

        if format_used == "csv":
            # 返回 CSV 文件
            output = io.StringIO()
            if data:
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)

            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}.csv"
                }
            )

        elif format_used == "excel":
            # Excel 格式返回 JSON 说明（实际生成需要 openpyxl）
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Excel 导出准备完成",
                    "data": data,
                    "total": len(data),
                    "note": "大数据量建议使用 CSV 格式导出"
                }
            )

        else:
            # 默认返回 JSON
            return JSONResponse(
                content={
                    "success": True,
                    "message": "数据导出成功",
                    "data": data,
                    "total": len(data),
                }
            )

    except Exception as e:
        logger.error(f"[DbApi.export_data] 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")
