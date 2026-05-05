"""B站视频发布 — Playwright 浏览器自动化（绕过 API 风控 + 投稿入口升级）

B站已禁用所有个人账号的 API 直接发布接口（/x/vu/web/add 返回 21150），
同时服务器 IP 发起的请求触发 geetest 验证码（412）。
此模块使用 Playwright 浏览器自动化完整模拟用户投稿流程，已验证可行。
"""
import os
import json
import time
import logging
import asyncio
from typing import Optional

logger = logging.getLogger("bilibili_browser_publisher")

BILIBILI_CREDENTIAL_PATH = os.environ.get(
    "BILIBILI_CREDENTIAL_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "bilibili_credential.json",
    ),
)


class BilibiliBrowserError(Exception):
    pass


async def _set_quill_content(page, text: str):
    """设置 Quill.js 编辑器的内容（B站简介使用 Quill 富文本编辑器）。"""
    await page.evaluate(f"""
    () => {{
        const el = document.querySelector('.ql-editor');
        if (!el) return;
        el.innerHTML = '<p>' + {json.dumps(text)}.replace(/\\n/g, '</p><p>') + '</p>';
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
    }}
    """)


async def publish_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: Optional[list] = None,
    tid: int = 174,
    copyright: int = 2,
    headless: bool = True,
) -> dict:
    """使用 Playwright 浏览器自动化上传并发布视频到 B站。

    流程：导航→上传→填表→发布。完全模拟真人操作，绕过 API 限制。

    Args:
        file_path: 视频文件路径
        title: 视频标题
        description: 视频简介
        tags: 标签列表
        tid: 分区 ID (默认 174=生活-日常)
        copyright: 1=自制 2=转载
        headless: 是否无头模式

    Returns:
        {"bvid": str, "url": str} 或 {"bvid": "", "url": str, "draft": True, ...}
    """
    from playwright.async_api import async_playwright

    if not os.path.exists(BILIBILI_CREDENTIAL_PATH):
        raise BilibiliBrowserError("B站未登录，请先扫码登录")

    with open(BILIBILI_CREDENTIAL_PATH) as f:
        creds = json.load(f)

    # 构建 cookies
    cookies = [{"name": k, "value": str(v), "domain": ".bilibili.com", "path": "/"}
               for k, v in creds.items() if v]

    # 确保 buvid cookies 存在（B站反爬需要）
    if "buvid3" not in creds or not creds.get("buvid3"):
        import uuid
        cookies.append({"name": "buvid3", "value": str(uuid.uuid4()) + "infoc", "domain": ".bilibili.com", "path": "/"})
    if "buvid4" not in creds or not creds.get("buvid4"):
        cookies.append({"name": "buvid4", "value": str(uuid.uuid4()), "domain": ".bilibili.com", "path": "/"})

    tags_str = ",".join(tags) if isinstance(tags, list) else (tags or "漫剧,AI视频")

    if not os.path.exists(file_path):
        raise BilibiliBrowserError(f"视频文件不存在: {file_path}")

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        publish_result = {"bvid": "", "url": ""}
        _all_add_responses = []  # 捕获所有相关响应用于调试

        # 注册全局 response 处理器 — 记录所有疑似发布相关的请求
        async def capture_all_vu_responses(response):
            url = response.url
            if any(kw in url for kw in ["/x/vu/web/add", "/x/vu/web", "/vu/web/add"]):
                _all_add_responses.append(url)
                try:
                    body = await response.json()
                    logger.info(f"📡 VU响应 [{response.status}]: {url.split('?')[0]} → code={body.get('code')}")
                    if body.get("code") == 0:
                        data = body.get("data")
                        if isinstance(data, dict):
                            bvid = data.get("bvid") or ""
                            if bvid:
                                publish_result["bvid"] = bvid
                                publish_result["url"] = f"https://www.bilibili.com/video/{bvid}"
                                logger.info(f"✅ 发布成功: {bvid}")
                except Exception:
                    pass

        page.on("response", capture_all_vu_responses)

        # 1) 访问 B站首页建立 session
        logger.info("访问 B站首页...")
        await page.goto("https://www.bilibili.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # 2) 导航到投稿页
        logger.info("导航到投稿页...")
        await page.goto(
            "https://member.bilibili.com/platform/upload/video",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(5)  # 等待 SPA 微应用加载
        logger.info(f"投稿页: {page.url}")

        # 3) 选择视频文件 — 自动触发上传到 CDN
        logger.info(f"选择视频: {file_name} ({file_size / 1024 / 1024:.1f}MB)")
        file_inputs = await page.query_selector_all("input[type='file']")
        video_input = None
        for fi in file_inputs:
            accept = await fi.get_attribute("accept")
            if accept and ".mp4" in accept:
                video_input = fi
                break

        if not video_input:
            await page.screenshot(path="/tmp/bili_error_no_input.png")
            raise BilibiliBrowserError("未找到视频文件输入框")

        await video_input.set_input_files(file_path)
        logger.info("文件已设置，等待表单加载...")

        # 4) 等待表单出现（标题输入框 — 选择文件后立即出现，无需等上传完成）
        try:
            await page.wait_for_selector(
                'input[placeholder="请输入稿件标题"]',
                timeout=20000,
            )
            logger.info("表单已加载")
        except Exception:
            await page.screenshot(path="/tmp/bili_error_form_timeout.png")
            raise BilibiliBrowserError("表单加载超时")

        await asyncio.sleep(2)

        # 5) 设置版权类型
        try:
            label = "自制" if copyright == 1 else "转载"
            radio = await page.query_selector(f'span:has-text("{label}")')
            if radio:
                await radio.click()
                logger.info(f"版权类型: {label}")
        except Exception as e:
            logger.warning(f"设置版权类型失败: {e}")

        # 6) 填写标题
        try:
            title_input = await page.query_selector('input[placeholder="请输入稿件标题"]')
            if title_input:
                await title_input.fill("")
                await title_input.fill(title[:80])  # B站标题限 80 字
                logger.info(f"标题: {title[:40]}...")
        except Exception as e:
            logger.warning(f"填写标题失败: {e}")

        # 7) 填写简介（Quill 富文本编辑器）
        try:
            desc_text = description or f"AI 生成的漫剧视频 - {title}"
            await _set_quill_content(page, desc_text)
            logger.info("简介已填写")
        except Exception as e:
            logger.warning(f"填写简介失败: {e}")

        # 8) 添加标签
        if tags:
            try:
                tag_input = await page.query_selector('input[placeholder="按回车键Enter创建标签"]')
                if tag_input:
                    for tag in tags_str.split(","):
                        tag = tag.strip()
                        if tag:
                            await tag_input.fill(tag)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(0.3)
                    logger.info(f"标签: {tags_str}")
            except Exception as e:
                logger.warning(f"添加标签失败: {e}")

        # 9) 等待视频处理完成（封面出现真实帧数据才表明可发布）
        upload_max_wait = max(60, min(600, int(file_size / (1024 * 1024) * 3)))
        logger.info(f"等待视频处理完成（最长 {upload_max_wait}s）...")

        try:
            await page.wait_for_selector(
                '.cover-img[style*="data:image"]',
                timeout=upload_max_wait * 1000,
            )
            logger.info("视频处理完成，封面已就绪")
        except Exception:
            logger.warning("视频处理超时，尝试继续")

        # 10) 点击「立即投稿」— SPA 会自动处理封面 + 发布
        logger.info("点击「立即投稿」发布视频...")

        # 同时使用 wait_for_response 增加捕获可靠性
        async def wait_for_add_response(timeout: int):
            try:
                resp = await page.wait_for_response(
                    lambda r: "/x/vu/web/add" in r.url,
                    timeout=timeout * 1000,
                )
                body = await resp.json()
                logger.info(f"wait_for_response 捕获: {resp.url.split('?')[0]} → code={body.get('code')}")
                if body.get("code") == 0 and body.get("data", {}).get("bvid"):
                    publish_result["bvid"] = body["data"]["bvid"]
                    publish_result["url"] = f"https://www.bilibili.com/video/{publish_result['bvid']}"
            except Exception:
                pass

        for attempt in range(3):
            # 截图当前页面状态
            await page.screenshot(path=f"/tmp/bili_before_click_{attempt}.png")

            # 检查页面上的按钮
            btn_info = await page.evaluate("""() => {
                const btn = document.querySelector('span.submit-add');
                if (btn) return {found: true, text: btn.textContent?.trim(), classes: btn.className, disabled: btn.closest('button')?.disabled || false};
                const span = document.querySelector('span:has-text("立即投稿")');
                if (span) return {found: true, text: span.textContent?.trim(), classes: span.className};
                return {found: false};
            }""")
            logger.info(f"按钮状态 (第{attempt + 1}次): {btn_info}")

            # 使用原生 .click() — dispatchEvent 在 micro-app 中无法触发 React 事件
            await page.evaluate("""() => {
                const btn = document.querySelector('span.submit-add') || document.querySelector('span:has-text("立即投稿")');
                if (btn) btn.click();
            }""")
            logger.info(f"已点击 (第{attempt + 1}次)")
            await asyncio.sleep(1)

            # 截图点击后的页面
            await page.screenshot(path=f"/tmp/bili_after_click_{attempt}.png")

            # 并发等待：wait_for_response + 轮询
            wait_time = 90 if attempt == 0 else 45
            add_task = asyncio.create_task(wait_for_add_response(wait_time))

            for _ in range(wait_time):
                if publish_result["bvid"]:
                    break
                await asyncio.sleep(1)

            # 取消 wait_for_response 任务（如果还在跑）
            add_task.cancel()
            try:
                await add_task
            except asyncio.CancelledError:
                pass

            if publish_result["bvid"]:
                logger.info(f"发布成功 (第{attempt + 1}次点击)")
                break

            # 记录当前页面 URL 和标题
            current_url = page.url
            page_title = await page.title()
            logger.info(f"当前页面: {current_url} | 标题: {page_title}")
            logger.info(f"已捕获的VU响应URL列表: {_all_add_responses}")
            logger.warning(f"发布未捕获到 add/v3 响应 (第{attempt + 1}次)")

            if attempt < 2:
                logger.info("等待后重试...")
                await asyncio.sleep(5)

        await page.screenshot(path="/tmp/bili_publish_result.png")
        logger.info(f"发布结果: bvid={publish_result['bvid'] or '无'}")
        logger.info(f"共捕获 {len(_all_add_responses)} 条VU相关响应")
        for i, url in enumerate(_all_add_responses):
            logger.info(f"  VU响应[{i}]: {url}")

        await browser.close()

        if publish_result["bvid"]:
            return publish_result

        return {
            "bvid": "",
            "url": "https://member.bilibili.com/platform/upload/video",
            "message": "视频已通过浏览器上传（可能保存为草稿），请检查 B站 创作中心",
        }


# ---- 同步包装 ----

def publish_video_sync(
    file_path: str,
    title: str,
    description: str = "",
    tags: Optional[list] = None,
    tid: int = 174,
    copyright: int = 2,
) -> dict:
    """同步版本，供非 async 上下文调用。"""
    return asyncio.run(
        publish_video(
            file_path=file_path,
            title=title,
            description=description,
            tags=tags,
            tid=tid,
            copyright=copyright,
        )
    )
