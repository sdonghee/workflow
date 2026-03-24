"""
네이버 블로그 자동 포스팅 모듈
- 쿠키 저장 방식으로 캡차 없이 안정적으로 로그인
- 처음 한 번만 수동 로그인 → 이후 자동으로 쿠키 사용
- 멀티 블로그 지원: blog_config 딕셔너리로 계정 전달
"""
import asyncio
import logging
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from config import HEADLESS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 쿠키 저장 / 불러오기
# ─────────────────────────────────────────

def save_cookies(cookies, cookie_file):
    with open(cookie_file, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    logger.info(f"쿠키 저장 완료: {cookie_file}")


def load_cookies(cookie_file):
    if not os.path.exists(cookie_file):
        return None
    with open(cookie_file, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────
# 로그인 상태 확인
# ─────────────────────────────────────────

async def is_logged_in(page, naver_id):
    """현재 네이버에 로그인되어 있는지 확인"""
    try:
        await page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        content = await page.content()
        return naver_id.lower() in content.lower() or "로그아웃" in content
    except Exception:
        return False


# ─────────────────────────────────────────
# 쿠키로 로그인 시도
# ─────────────────────────────────────────

async def login_with_cookies(context, page, blog_config):
    """저장된 쿠키로 로그인 시도"""
    cookies = load_cookies(blog_config["cookie_file"])
    if not cookies:
        logger.info(f"[{blog_config['name']}] 저장된 쿠키 없음")
        return False

    try:
        await context.add_cookies(cookies)
        logged_in = await is_logged_in(page, blog_config["naver_id"])
        if logged_in:
            logger.info(f"[{blog_config['name']}] ✅ 쿠키 로그인 성공")
            return True
        else:
            logger.info(f"[{blog_config['name']}] 쿠키가 만료되었습니다. 재로그인 필요")
            return False
    except Exception as e:
        logger.error(f"[{blog_config['name']}] 쿠키 로그인 실패: {e}")
        return False


# ─────────────────────────────────────────
# 자동 로그인 (ID/PW)
# ─────────────────────────────────────────

async def login_with_password(page, blog_config):
    """ID/PW로 로그인 (쿠키 없을 때 또는 만료 시)"""
    naver_id = blog_config["naver_id"]
    naver_pw = blog_config["naver_pw"]
    try:
        await page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        await page.click("#id")
        await page.wait_for_timeout(500)
        for char in naver_id:
            await page.type("#id", char, delay=80)
        await page.wait_for_timeout(700)

        await page.click("#pw")
        await page.wait_for_timeout(500)
        for char in naver_pw:
            await page.type("#pw", char, delay=80)
        await page.wait_for_timeout(700)

        await page.click(".btn_login")
        await page.wait_for_timeout(4000)

        current_url = page.url
        if "nidlogin" in current_url:
            logger.error(f"[{blog_config['name']}] ❌ 로그인 실패 - 캡차 또는 계정 오류. first_login.py 를 실행하세요")
            return False

        logger.info(f"[{blog_config['name']}] ✅ ID/PW 로그인 성공")
        return True

    except Exception as e:
        logger.error(f"[{blog_config['name']}] 로그인 오류: {e}")
        return False


# ─────────────────────────────────────────
# 메인 포스팅 함수
# ─────────────────────────────────────────

async def post_to_naver_blog(title, content_html, tags, category, blog_config):
    """
    네이버 블로그에 글 포스팅
    blog_config: BLOGS dict의 개별 블로그 설정
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            # 1. 쿠키로 로그인 시도
            logged_in = await login_with_cookies(context, page, blog_config)

            # 2. 쿠키 만료 시 ID/PW 로그인
            if not logged_in:
                logged_in = await login_with_password(page, blog_config)
                if not logged_in:
                    return False
                cookies = await context.cookies()
                save_cookies(cookies, blog_config["cookie_file"])

            # 3. 글쓰기 페이지 이동
            blog_id = blog_config["blog_id"]
            write_url = f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"
            await page.goto(write_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            if len(context.pages) > 1:
                page = context.pages[-1]
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)

            logger.info(f"[{blog_config['name']}] 글쓰기 페이지: {page.url}")

            # 4. 제목 입력
            await _enter_title(page, title)
            await page.wait_for_timeout(1500)

            # 5. 본문 입력
            await _enter_content(page, content_html)
            await page.wait_for_timeout(1500)

            # 6. 태그 입력
            await _enter_tags(page, tags)
            await page.wait_for_timeout(1500)

            # 7. 발행
            success = await _publish(page)

            if success:
                cookies = await context.cookies()
                save_cookies(cookies, blog_config["cookie_file"])
                logger.info(f"[{blog_config['name']}] ✅ 포스팅 완료: {title}")

            return success

        except PlaywrightTimeout as e:
            logger.error(f"[{blog_config['name']}] 타임아웃 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"[{blog_config['name']}] 포스팅 오류: {e}", exc_info=True)
            return False
        finally:
            await page.wait_for_timeout(1000)
            await browser.close()


# ─────────────────────────────────────────
# 세부 동작 함수들
# ─────────────────────────────────────────

async def _enter_title(page, title):
    """제목 입력"""
    selectors = [
        ".se-title-input",
        "#post-title .input_text",
        "#post-title input",
        "input[placeholder*='제목']",
    ]
    for selector in selectors:
        try:
            await page.click(selector, timeout=4000)
            await page.fill(selector, title)
            logger.info(f"제목 입력: {title[:30]}")
            return
        except Exception:
            continue

    for frame in page.frames:
        try:
            await frame.click("input[placeholder*='제목']", timeout=2000)
            await frame.fill("input[placeholder*='제목']", title)
            logger.info(f"제목 입력(iframe): {title[:30]}")
            return
        except Exception:
            continue

    logger.warning("제목 입력 실패")


async def _enter_content(page, content_html):
    """본문 입력 - SmartEditor"""
    selectors = [
        ".se-content",
        ".se2_inputarea",
        "[contenteditable='true']",
        "#smarteditor",
    ]
    safe_html = content_html.replace("`", "'").replace("\n", "")

    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                await el.click()
                await page.wait_for_timeout(500)
                js = f"""
                    (function() {{
                        var el = document.querySelector('{selector}');
                        if (el) {{ el.innerHTML = `{safe_html}`; return true; }}
                        return false;
                    }})()
                """
                result = await page.evaluate(js)
                if result:
                    logger.info("본문 입력 완료")
                    return
        except Exception:
            continue

    for frame in page.frames:
        try:
            el = await frame.query_selector("[contenteditable='true']")
            if el:
                await el.click()
                await frame.evaluate(f"document.querySelector('[contenteditable]').innerHTML = `{safe_html}`")
                logger.info("본문 입력 완료(iframe)")
                return
        except Exception:
            continue

    logger.warning("본문 입력 실패")


async def _enter_tags(page, tags):
    """태그 입력"""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()][:10]
    selectors = [
        "#post-tag input",
        ".tag_input",
        "input[placeholder*='태그']",
    ]
    for selector in selectors:
        try:
            for tag in tag_list:
                await page.click(selector, timeout=3000)
                await page.type(selector, tag, delay=40)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(400)
            logger.info(f"태그 입력: {', '.join(tag_list)}")
            return
        except Exception:
            continue

    logger.warning("태그 입력 실패 (계속 진행)")


async def _publish(page):
    """발행 버튼 클릭"""
    selectors = [
        ".btn_publish",
        "button:has-text('발행')",
        "button:has-text('공개발행')",
        "#publish-btn",
    ]
    for selector in selectors:
        try:
            await page.click(selector, timeout=4000)
            await page.wait_for_timeout(3000)

            for confirm in ["button:has-text('확인')", ".btn_confirm", ".btn_ok"]:
                try:
                    await page.click(confirm, timeout=2000)
                    break
                except Exception:
                    continue

            await page.wait_for_timeout(2000)
            return True
        except Exception:
            continue

    logger.error("발행 버튼 없음")
    return False


# ─────────────────────────────────────────
# 동기 래퍼 & 로컬 저장
# ─────────────────────────────────────────

def post_blog(title, content_html, tags, category, blog_config):
    """동기 함수 래퍼"""
    return asyncio.run(post_to_naver_blog(title, content_html, tags, category, blog_config))


def save_post_locally(title, content_html, tags, category, blog_config, filename=None):
    """포스팅 실패 시 로컬 임시 저장"""
    blog_key = blog_config.get("blog_id", "unknown")
    drafts_dir = f"drafts/{blog_key}"
    os.makedirs(drafts_dir, exist_ok=True)

    if not filename:
        safe_title = "".join(c for c in title[:30] if c.isalnum() or c in " _-")
        filename = f"{drafts_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_title}.json"

    draft = {
        "title": title,
        "content_html": content_html,
        "tags": tags,
        "category": category,
        "blog": blog_config.get("name", ""),
        "created_at": datetime.now().isoformat(),
        "posted": False,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    logger.info(f"임시 저장: {filename}")
    return filename
