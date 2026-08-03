---
name: find-creator-id
description: 当用户要用 creator 模式爬取抖音/快手/B站/小红书/微博/贴吧/知乎主播作品，但只知道昵称/抖音号/视频链接而没有 creator_id（如抖音 sec_uid）时使用。解决搜索结果只返回匿名化 creator_hash、无法直接当 creator_id 用的问题。
---

# 主播 creator_id 查找技能

调用 `crawl_*` 的 `creator` 模式时必须传 `creator_id`（抖音是 `sec_uid`,B站是 `mid`)。**搜索结果里返回的 `creator_hash` 是匿名化 hash,不是 `sec_uid`,直接当 `creator_id` 传会爬到错的人。**

## 各平台 creator_id 形式

| 平台 | 字段 | 形式 | 主页 URL 示例 |
| --- | --- | --- | --- |
| 抖音 dy | `sec_uid` | `MS4wLjABAAAA...` 长字符串 | `https://www.douyin.com/user/MS4wLjABAAAA...` |
| B站 bili | `mid` | 纯数字 UID | `https://space.bilibili.com/<mid>` |
| 小红书 xhs | `user_id` | 24 位 hex | `https://www.xiaohongshu.com/user/profile/<user_id>` |
| 快手 ks | `user_id` | 数字或字母 | `https://www.kuaishou.com/profile/<user_id>` |
| 微博 wb | `uid` | 数字 | `https://weibo.com/u/<uid>` |
| 贴吧 tieba | `user_name` | 用户名 | `https://tieba.baidu.com/home/main?un=<user_name>` |
| 知乎 zhihu | `url_token` | 英文 ID | `https://www.zhihu.com/people/<url_token>` |

**通用规则**:`creator_id` 一定藏在主播的**主页 URL** 里。搜索结果只给 `creator_hash`(脱敏)。

## 三种获取方式

### 方式 1：用户提供主页 URL（最稳）

直接问用户："请把主播主页链接发我"。从 URL 里用正则提取：

```python
import re
# 抖音
m = re.search(r"douyin\.com/user/([A-Za-z0-9_\-]+)", url)
sec_uid = m.group(1) if m else None
# B站
m = re.search(r"space\.bilibili\.com/(\d+)", url)
mid = m.group(1) if m else None
```

### 方式 2：按昵称搜索（需登录态）

适用：只有昵称（如"程序员鱼皮")，没有 URL。

**思路**：复用 `browser_data/<platform>_user_data_dir` 登录态，用 Playwright 打开搜索页，从结果卡片的 `<a href="/user/<id>">` 提取。**不要走"用户"搜索 Tab**（要登录且 DOM 复杂）,**走"视频/综合"Tab**（不需要登录），从视频卡片里的作者链接抓。

参考脚本骨架（以抖音为例）:

```python
# -*- coding: utf-8 -*-
import asyncio, json, re, sys, io
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
USER_DATA = Path("browser_data/dy_user_data_dir")
KEYWORD = "程序员鱼皮"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA), headless=False,
            viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        # 注意:用综合搜索,不是 /search/<kw>?type=user
        await page.goto(f"https://www.douyin.com/search/{KEYWORD}",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
        links = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="/user/"]'))
                .map(a => ({href: a.href, text: (a.textContent||'').trim().slice(0,80)}))""")
        seen, out = set(), []
        for it in links:
            m = re.search(r"/user/([A-Za-z0-9_\-]+)", it["href"] or "")
            if m and m.group(1) not in ("self", "") and m.group(1) not in seen:
                seen.add(m.group(1))
                out.append({"sec_uid": m.group(1), "text": it["text"]})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        await ctx.close()

asyncio.run(main())
```

**关键点**:
- 用 `launch_persistent_context` + `browser_data/dy_user_data_dir` 复用登录态，否则会弹扫码
- 终端编码 `gbk` 会炸，用 `sys.stdout = io.TextIOWrapper(...)` 强制 UTF-8
- 抓到 0 条说明被风控或没登录，先手动跑一次 `uv run main.py --platform dy --lt qrcode --type search --keywords test --headless false` 扫码

### 方式 3：按视频链接反查

适用：用户给了主播某条作品的链接（`douyin.com/video/<aweme_id>` 或短链 `v.douyin.com/xxx`)。

**思路**:
1. 短链先用 `curl -IL` 或 Playwright 跳转拿到完整 URL
2. 用 `crawl_dy detail` 模式爬这条视频，`creator_hash` 字段会返回（但还是匿名 hash)
3. 浏览器打开这条视频页，从作者昵称链接的 `href` 提取 `sec_uid`（同方式 2 的 DOM 抓取）

```python
# 视频页里作者链接选择器
await page.goto(f"https://www.douyin.com/video/{aweme_id}")
await page.wait_for_timeout(4000)
links = await page.evaluate(
    """() => Array.from(document.querySelectorAll('a[href*="/user/"]'))
        .map(a => a.href)""")
# 取第一个匹配 /user/<sec_uid> 的
```

## 验证 creator_id 正确性

拿到候选 `creator_id` 后**必须**先小批量验证，再全量爬：

```
crawl_dy(crawler_type="creator", creator_id="<候选>", max_notes_count=3,
         download_media=false, transcribe_media=false, return_data=true)
```

看返回 `preview` 里的 `nickname` 字段：是不是目标主播。**我之前没做这步直接传 `creator_hash` 爬到错的人，浪费了整轮任务。**

确认无误后再上 `max_notes_count=1000` 全量爬。

## 常见坑

| 坑 | 现象 | 解法 |
| --- | --- | --- |
| 把 `creator_hash` 当 `sec_uid` | creator 模式爬到错的人 | creator_hash 是脱敏的，必须用方式 1/2/3 拿真 sec_uid |
| 抓 `/search/<kw>?type=user` 返回 0 条 | 用户搜索 Tab 要登录且 DOM 懒加载 | 改用综合搜索（默认 Tab)，从视频卡片抓作者链接 |
| Playwright 弹扫码登录 | 没用 `browser_data` 持久化目录 | `launch_persistent_context(user_data_dir=...)` |
| 控制台输出中文乱码 | Windows GBK | `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")` |
| 拿到 sec_uid 直接全量爬 | 万一 ID 错了，浪费几小时 | 先 `max_notes_count=3` 验证 nickname |

## 给其他平台用

**B站** 最简单：搜索接口直接返回 `mid`，或者 `space.bilibili.com/<mid>` 数字一眼能看。不需要这个技能。

**小红书 / 快手 / 微博 / 知乎**：思路一样，只是 URL 路径不同（参考上面"各平台 creator_id 形式"表），把方式 2 脚本里的 `/user/` 改成对应路径即可。
