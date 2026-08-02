# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/douyin/core.py
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

import asyncio
import os
import random
from asyncio import Task
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

import config
from base.base_crawler import AbstractCrawler
from media_pipeline import (
    MediaDownloader,
    get_media_repository,
    get_transcription_manager,
)
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import douyin as douyin_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from var import crawler_type_var, source_keyword_var

from .client import DouYinClient
from .exception import DataFetchError
from .field import PublishTimeType
from .help import parse_video_info_from_url, parse_creator_info_from_url
from .login import DouYinLogin


class DouYinCrawler(AbstractCrawler):
    context_page: Page
    dy_client: DouYinClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self) -> None:
        self.index_url = "https://www.douyin.com"
        self.cookie_urls = [
            "https://douyin.com",
            self.index_url,
            "https://creator.douyin.com",
            "https://douhot.douyin.com",
            "https://live.douyin.com",
        ]
        self.cdp_manager = None
        self.ip_proxy_pool = None  # Proxy IP pool for automatic proxy refresh

    async def start(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # Select startup mode based on configuration
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[DouYinCrawler] 使用CDP模式启动浏览器")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    None,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[DouYinCrawler] 使用标准模式启动浏览器")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    playwright_proxy_format,
                    user_agent=None,
                    headless=config.HEADLESS,
                )
                # stealth.min.js is a js script to prevent the website from detecting the crawler.
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            try:
                await self.context_page.goto(self.index_url)
            except PlaywrightTimeoutError:
                # 抖音首页资源多，30s 内等不到 load 事件属常见网络抖动；
                # 页面 DOM 通常已就绪，登录检测与二维码弹窗不受影响，继续执行。
                utils.logger.warning(
                    "[DouYinCrawler] index page load timeout, continue with partially loaded page"
                )

            self.dy_client = await self.create_douyin_client(httpx_proxy_format)
            explicit_cookie_login = (
                config.LOGIN_TYPE == "cookie"
                and bool(str(config.COOKIES or "").strip())
            )
            if (
                explicit_cookie_login
                or not await self.dy_client.pong(
                    browser_context=self.browser_context,
                    require_self_profile=config.CRAWLER_TYPE
                    in {"liked", "collected"},
                )
            ):
                login_obj = DouYinLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # you phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await self.dy_client.update_cookies(
                    browser_context=self.browser_context,
                    urls=self.cookie_urls,
                )
            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_awemes()
            elif config.CRAWLER_TYPE == "creator":
                # Get the information and comments of the specified creator
                await self.get_creators_and_videos()
            elif config.CRAWLER_TYPE == "liked":
                await self.get_self_liked_awemes()
            elif config.CRAWLER_TYPE == "collected":
                await self.get_self_collected_awemes()

            utils.logger.info("[DouYinCrawler.start] Douyin Crawler finished ...")

    async def search(self) -> None:
        utils.logger.info("[DouYinCrawler.search] Begin search douyin keywords")
        dy_limit_count = 10  # douyin limit page fixed value
        target_count = max(1, config.CRAWLER_MAX_NOTES_COUNT)
        start_page = config.START_PAGE  # start page number
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[DouYinCrawler.search] Current keyword: {keyword}")
            aweme_list: List[str] = []
            page = 0
            dy_search_id = ""
            while len(aweme_list) < target_count:
                if page < start_page:
                    utils.logger.info(f"[DouYinCrawler.search] Skip {page}")
                    page += 1
                    continue
                try:
                    utils.logger.info(f"[DouYinCrawler.search] search douyin keyword: {keyword}, page: {page}")
                    posts_res = await self.dy_client.search_info_by_keyword(
                        keyword=keyword,
                        offset=page * dy_limit_count - dy_limit_count,
                        publish_time=PublishTimeType(config.PUBLISH_TIME_TYPE),
                        search_id=dy_search_id,
                    )
                    if posts_res.get("data") is None or posts_res.get("data") == []:
                        utils.logger.info(f"[DouYinCrawler.search] search douyin keyword: {keyword}, page: {page} is empty,{posts_res.get('data')}`")
                        break
                except DataFetchError:
                    utils.logger.error(f"[DouYinCrawler.search] search douyin keyword: {keyword} failed")
                    break

                page += 1
                if "data" not in posts_res:
                    utils.logger.error(f"[DouYinCrawler.search] search douyin keyword: {keyword} failed，账号也许被风控了。")
                    break
                dy_search_id = posts_res.get("extra", {}).get("logid", "")
                page_aweme_list = []
                for post_item in posts_res.get("data"):
                    if len(aweme_list) >= target_count:
                        break
                    try:
                        aweme_info: Dict = (post_item.get("aweme_info") or post_item.get("aweme_mix_info", {}).get("mix_items")[0])
                    except TypeError:
                        continue
                    aweme_list.append(aweme_info.get("aweme_id", ""))
                    page_aweme_list.append(aweme_info.get("aweme_id", ""))
                    await douyin_store.update_douyin_aweme(aweme_item=aweme_info)
                    await self.get_aweme_media(aweme_item=aweme_info)
                
                # Batch get note comments for the current page
                await self.batch_get_note_comments(page_aweme_list)

                # Sleep after each page navigation
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[DouYinCrawler.search] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after page {page-1}")
            utils.logger.info(f"[DouYinCrawler.search] keyword:{keyword}, aweme_list:{aweme_list}")

    async def get_self_liked_awemes(self) -> None:
        """Crawl awemes liked by the current authenticated account."""
        await self._crawl_self_aweme_feed("liked")

    async def get_self_collected_awemes(self) -> None:
        """Crawl awemes collected by the current authenticated account."""
        await self._crawl_self_aweme_feed("collected")

    @staticmethod
    def _extract_self_user_ids(payload: Dict) -> Tuple[str, str]:
        """Return uid and sec_uid without persisting either value."""
        data = payload.get("data")
        candidates = [
            payload.get("user"),
            payload.get("user_info"),
            data.get("user") if isinstance(data, dict) else None,
            data.get("user_info") if isinstance(data, dict) else None,
            data,
            payload,
        ]
        user_id = ""
        sec_user_id = ""
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            user_id = user_id or str(candidate.get("uid") or "")
            sec_user_id = sec_user_id or str(
                candidate.get("sec_uid")
                or candidate.get("sec_user_id")
                or ""
            )
            if user_id and sec_user_id:
                break
        return user_id, sec_user_id

    @classmethod
    def _stable_self_account_key(cls, payload: Dict) -> str:
        """Build one stable, namespaced identity from Douyin's sec_uid."""
        _, sec_user_id = cls._extract_self_user_ids(payload)
        if not sec_user_id:
            return ""
        return f"dy:sec_uid:{sec_user_id}"

    @staticmethod
    def _is_business_success(payload: Dict) -> bool:
        if "status_code" not in payload:
            return False
        status_code = payload.get("status_code")
        return status_code in (0, "0")

    async def _crawl_self_aweme_feed(self, feed_type: str) -> None:
        """Crawl and persist a paginated liked or collected feed."""
        if feed_type not in {"liked", "collected"}:
            raise ValueError(f"Unsupported Douyin self feed type: {feed_type}")

        source_keyword_var.set(feed_type)
        target_count = int(config.CRAWLER_MAX_NOTES_COUNT)
        if target_count < 1:
            raise DataFetchError(
                f"Douyin {feed_type} target count must be at least 1"
            )

        try:
            profile_res = await self.dy_client.get_self_profile()
        except Exception as exc:
            raise DataFetchError(
                f"Unable to verify the current Douyin login for {feed_type}: "
                f"{type(exc).__name__}"
            ) from exc

        if (
            not isinstance(profile_res, dict)
            or not profile_res
            or not self._is_business_success(profile_res)
        ):
            status_code = (
                profile_res.get("status_code")
                if isinstance(profile_res, dict)
                else "invalid_response"
            )
            raise DataFetchError(
                f"Douyin self-profile request failed for {feed_type}, "
                f"status_code:{status_code}"
            )

        account_id = self._stable_self_account_key(profile_res)
        if not account_id:
            raise DataFetchError(
                "Douyin self-profile response does not contain a stable sec_uid"
            )
        _, sec_user_id = self._extract_self_user_ids(profile_res)

        cursor: Any = 0
        total_count = 0
        page = 1
        seen_aweme_ids = set()

        while total_count < target_count:
            page_size = min(20, target_count - total_count)
            try:
                if feed_type == "liked":
                    feed_res = await self.dy_client.get_self_liked_awemes(
                        sec_user_id=sec_user_id,
                        max_cursor=cursor,
                        count=page_size,
                    )
                else:
                    feed_res = await self.dy_client.get_self_collected_awemes(
                        cursor=cursor,
                        count=page_size,
                    )
            except Exception as exc:
                raise DataFetchError(
                    f"Unable to fetch Douyin {feed_type} page {page}: "
                    f"{type(exc).__name__}"
                ) from exc

            if not isinstance(feed_res, dict) or not self._is_business_success(feed_res):
                status_code = (
                    feed_res.get("status_code")
                    if isinstance(feed_res, dict)
                    else "invalid_response"
                )
                raise DataFetchError(
                    f"Douyin {feed_type} page {page} failed, "
                    f"status_code:{status_code}"
                )

            aweme_list = feed_res.get("aweme_list")
            if not isinstance(aweme_list, list):
                raise DataFetchError(
                    f"Douyin {feed_type} page {page} response does not "
                    "contain a valid aweme_list"
                )

            raw_has_more = feed_res.get("has_more")
            if raw_has_more in (True, 1, "1"):
                has_more = True
            elif raw_has_more in (False, 0, "0"):
                has_more = False
            else:
                raise DataFetchError(
                    f"Douyin {feed_type} page {page} response contains "
                    f"an invalid has_more value"
                )

            if not aweme_list:
                if has_more:
                    raise DataFetchError(
                        f"Douyin {feed_type} page {page} is empty while "
                        "has_more is true"
                    )
                utils.logger.info(
                    f"[DouYinCrawler._crawl_self_aweme_feed] "
                    f"{feed_type} page {page} is empty"
                )
                break

            page_aweme_ids: List[str] = []
            try:
                for aweme_item in aweme_list:
                    if total_count >= target_count:
                        break
                    if not isinstance(aweme_item, dict):
                        continue
                    aweme_id = str(aweme_item.get("aweme_id") or "")
                    if not aweme_id or aweme_id in seen_aweme_ids:
                        continue

                    seen_aweme_ids.add(aweme_id)
                    await douyin_store.update_douyin_aweme(aweme_item=aweme_item)
                    await douyin_store.update_douyin_user_action(
                        account_id=account_id,
                        aweme_id=aweme_id,
                        action_type=feed_type,
                    )
                    await self.get_aweme_media(aweme_item=aweme_item)
                    page_aweme_ids.append(aweme_id)
                    total_count += 1

                if page_aweme_ids:
                    await self.batch_get_note_comments(page_aweme_ids)
            except Exception as exc:
                raise DataFetchError(
                    f"Unable to process Douyin {feed_type} page {page}: "
                    f"{type(exc).__name__}"
                ) from exc

            utils.logger.info(
                f"[DouYinCrawler._crawl_self_aweme_feed] "
                f"processed {feed_type} page {page}, "
                f"page_count:{len(page_aweme_ids)}, total_count:{total_count}"
            )
            if not page_aweme_ids:
                raise DataFetchError(
                    f"Douyin {feed_type} page {page} contained no valid aweme ids"
                )
            if total_count >= target_count:
                break

            if not has_more:
                break

            next_cursor = (
                feed_res.get("max_cursor")
                if feed_type == "liked"
                else feed_res.get("cursor")
            )
            if next_cursor is None or str(next_cursor) == str(cursor):
                raise DataFetchError(
                    f"Douyin {feed_type} cursor did not advance on page {page}"
                )

            cursor = next_cursor
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
            page += 1

    async def get_specified_awemes(self):
        """Get the information and comments of the specified post from URLs or IDs"""
        utils.logger.info("[DouYinCrawler.get_specified_awemes] Parsing video URLs...")
        aweme_id_list = []
        for video_url in config.DY_SPECIFIED_ID_LIST:
            try:
                video_info = parse_video_info_from_url(video_url)

                # Handling short links
                if video_info.url_type == "short":
                    utils.logger.info(f"[DouYinCrawler.get_specified_awemes] Resolving short link: {video_url}")
                    resolved_url = await self.dy_client.resolve_short_url(video_url)
                    if resolved_url:
                        # Extract video ID from parsed URL
                        video_info = parse_video_info_from_url(resolved_url)
                        utils.logger.info(f"[DouYinCrawler.get_specified_awemes] Short link resolved to aweme ID: {video_info.aweme_id}")
                    else:
                        utils.logger.error(f"[DouYinCrawler.get_specified_awemes] Failed to resolve short link: {video_url}")
                        continue

                aweme_id_list.append(video_info.aweme_id)
                utils.logger.info(f"[DouYinCrawler.get_specified_awemes] Parsed aweme ID: {video_info.aweme_id} from {video_url}")
            except ValueError as e:
                utils.logger.error(f"[DouYinCrawler.get_specified_awemes] Failed to parse video URL: {e}")
                continue

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [self.get_aweme_detail(aweme_id=aweme_id, semaphore=semaphore) for aweme_id in aweme_id_list]
        aweme_details = await asyncio.gather(*task_list)
        for aweme_detail in aweme_details:
            if aweme_detail is not None:
                await douyin_store.update_douyin_aweme(aweme_item=aweme_detail)
                await self.get_aweme_media(aweme_item=aweme_detail)
        await self.batch_get_note_comments(aweme_id_list)

    async def get_aweme_detail(self, aweme_id: str, semaphore: asyncio.Semaphore) -> Any:
        """Get note detail"""
        async with semaphore:
            try:
                result = await self.dy_client.get_video_by_id(aweme_id)
                # Sleep after fetching aweme detail
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[DouYinCrawler.get_aweme_detail] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching aweme {aweme_id}")
                return result
            except DataFetchError as ex:
                utils.logger.error(f"[DouYinCrawler.get_aweme_detail] Get aweme detail error: {ex}")
                return None
            except KeyError as ex:
                utils.logger.error(f"[DouYinCrawler.get_aweme_detail] have not fund note detail aweme_id:{aweme_id}, err: {ex}")
                return None

    async def batch_get_note_comments(self, aweme_list: List[str]) -> None:
        """
        Batch get note comments
        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info("[DouYinCrawler.batch_get_note_comments] Crawling comment mode is not enabled")
            return

        task_list: List[Task] = []
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        for aweme_id in aweme_list:
            task = asyncio.create_task(self.get_comments(aweme_id, semaphore), name=aweme_id)
            task_list.append(task)
        if len(task_list) > 0:
            await asyncio.wait(task_list)

    async def get_comments(self, aweme_id: str, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            try:
                # Pass the list of keywords to the get_aweme_all_comments method
                # Use fixed crawling interval
                crawl_interval = config.CRAWLER_MAX_SLEEP_SEC
                await self.dy_client.get_aweme_all_comments(
                    aweme_id=aweme_id,
                    crawl_interval=crawl_interval,
                    is_fetch_sub_comments=config.ENABLE_GET_SUB_COMMENTS,
                    callback=douyin_store.batch_update_dy_aweme_comments,
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
                # Sleep after fetching comments
                await asyncio.sleep(crawl_interval)
                utils.logger.info(f"[DouYinCrawler.get_comments] Sleeping for {crawl_interval} seconds after fetching comments for aweme {aweme_id}")
                utils.logger.info(f"[DouYinCrawler.get_comments] aweme_id: {aweme_id} comments have all been obtained and filtered ...")
            except DataFetchError as e:
                utils.logger.error(f"[DouYinCrawler.get_comments] aweme_id: {aweme_id} get comments failed, error: {e}")

    async def get_creators_and_videos(self) -> None:
        """
        Get the information and videos of the specified creator from URLs or IDs
        """
        utils.logger.info("[DouYinCrawler.get_creators_and_videos] Begin get douyin creators")
        utils.logger.info("[DouYinCrawler.get_creators_and_videos] Parsing creator URLs...")

        for creator_url in config.DY_CREATOR_ID_LIST:
            try:
                creator_info_parsed = parse_creator_info_from_url(creator_url)
                user_id = creator_info_parsed.sec_user_id
                utils.logger.info(f"[DouYinCrawler.get_creators_and_videos] Parsed sec_user_id: {user_id} from {creator_url}")
            except ValueError as e:
                utils.logger.error(f"[DouYinCrawler.get_creators_and_videos] Failed to parse creator URL: {e}")
                continue

            creator_info: Dict = await self.dy_client.get_user_info(user_id)
            if creator_info:
                await douyin_store.save_creator(user_id, creator=creator_info)

            # Get all video information of the creator
            all_video_list = await self.dy_client.get_all_user_aweme_posts(sec_user_id=user_id, callback=self.fetch_creator_video_detail)

            video_ids = [video_item.get("aweme_id") for video_item in all_video_list]
            await self.batch_get_note_comments(video_ids)

    async def fetch_creator_video_detail(self, video_list: List[Dict]):
        """
        Concurrently obtain the specified post list and save the data
        """
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [self.get_aweme_detail(post_item.get("aweme_id"), semaphore) for post_item in video_list]

        note_details = await asyncio.gather(*task_list)
        for aweme_item in note_details:
            if aweme_item is not None:
                await douyin_store.update_douyin_aweme(aweme_item=aweme_item)
                await self.get_aweme_media(aweme_item=aweme_item)

    async def create_douyin_client(self, httpx_proxy: Optional[str]) -> DouYinClient:
        """Create douyin client"""
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            self.browser_context,
            urls=self.cookie_urls,
        )  # type: ignore
        douyin_client = DouYinClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": await self.context_page.evaluate("() => navigator.userAgent"),
                "Cookie": cookie_str,
                "Host": "www.douyin.com",
                "Origin": "https://www.douyin.com/",
                "Referer": "https://www.douyin.com/",
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,  # Pass proxy pool for automatic refresh
        )
        return douyin_client

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                user_agent=user_agent,
            )  # type: ignore
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=user_agent)
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        使用CDP模式启动浏览器
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # Add anti-detection script
            await self.cdp_manager.add_stealth_script()

            # Show browser information
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[DouYinCrawler] CDP浏览器信息: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(f"[DouYinCrawler] CDP模式启动失败，回退到标准模式: {e}")
            # Fall back to standard mode
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def close(self) -> None:
        """Close browser context"""
        # If you use CDP mode, special processing is required
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[DouYinCrawler.close] Browser context closed ...")

    async def get_aweme_media(self, aweme_item: Dict):
        """
        获取抖音媒体，自动判断媒体类型是短视频还是帖子图片并下载

        Args:
            aweme_item (Dict): 抖音作品详情
        """
        if not config.is_media_download_enabled():
            utils.logger.info("[DouYinCrawler.get_aweme_media] Crawling image mode is not enabled")
            return
        # List of note urls. If it is a short video type, an empty list will be returned.
        note_download_url: List[str] = douyin_store._extract_note_image_list(aweme_item)
        # TODO: Douyin does not adopt the audio and video separation strategy, so the audio can be separated from the original video and will not be extracted for the time being.
        if note_download_url:
            await self.get_aweme_images(aweme_item)
        else:
            await self.get_aweme_video(aweme_item)

    async def get_aweme_images(self, aweme_item: Dict):
        """
        get aweme images. please use get_aweme_media

        Args:
            aweme_item (Dict): 抖音作品详情
        """
        if not config.is_media_download_enabled():
            return
        aweme_id = aweme_item.get("aweme_id")
        # List of note urls. If it is a short video type, an empty list will be returned.
        note_download_url: List[str] = douyin_store._extract_note_image_list(aweme_item)

        if not note_download_url:
            return
        picNum = 0
        for url in note_download_url:
            if not url:
                continue
            content = await self.dy_client.get_aweme_media(url)
            await asyncio.sleep(random.random())
            if content is None:
                continue
            extension_file_name = f"{picNum:>03d}.jpeg"
            picNum += 1
            await douyin_store.update_dy_aweme_image(aweme_id, content, extension_file_name)

    async def get_aweme_video(self, aweme_item: Dict):
        """
        get aweme videos. please use get_aweme_media

        Args:
            aweme_item (Dict): 抖音作品详情
        """
        if not config.is_media_download_enabled():
            return
        aweme_id = aweme_item.get("aweme_id")

        # The video URL will always exist, but when it is a short video type, the file is actually an audio file.
        video_download_url: str = douyin_store._extract_video_download_url(aweme_item)

        if not video_download_url:
            return
        repository = get_media_repository()
        downloader = MediaDownloader(repository)
        request_headers = {
            key: value
            for key, value in self.dy_client.headers.items()
            if key.lower() in {"user-agent", "referer", "cookie"}
        }
        try:
            result = await downloader.download(
                platform="dy",
                content_id=str(aweme_id),
                source_url=video_download_url,
                headers=request_headers,
                proxy=self.dy_client.proxy,
                run_id=config.MEDIA_RUN_ID,
            )
            utils.logger.info(
                f"[DouYinCrawler.get_aweme_video] video saved to {result.local_path}"
            )
            if config.TRANSCRIBE_MEDIA and result.has_audio:
                asset = await repository.get_asset(asset_id=result.asset_id)
                if asset:
                    job = await get_transcription_manager().enqueue_asset(
                        asset,
                        wait=True,
                    )
                    utils.logger.info(
                        f"[DouYinCrawler.get_aweme_video] transcription {job.status}: {job.job_id}"
                    )
        except Exception as exc:
            utils.logger.error(
                f"[DouYinCrawler.get_aweme_video] download/transcription failed: {exc}"
            )
        await asyncio.sleep(random.random())
