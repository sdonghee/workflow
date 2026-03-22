"""
네이버 블로그 자동 포스팅 모듈
Playwright를 사용하여 네이버 블로그에 자동으로 글을 게시합니다.
"""
import asyncio
import logging
import time
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from config import NAVER_ID, NAVER_PW, NAVER_BLOG_ID, HEADLESS

logger = logging.getLogger(__name__)

# 네이버 블로그 카테고리 이름 (블로그 설정에 맞게 수정 필요)
NAVER_CATEGORY_MAP = {
    "여행_항공_호텔": "여행/항공/호텔",
    "정부혜택": "정부혜택",
    "건강": "건강",
}


async def naver_login(page):
    """네이버 로그인"""
    try:
        await page.goto("https://nid.naver.com/nidlogin.login", wait_until="networkidle")
        await page.wait_for_timeout(1000)

        # ID 입력
        await page.click("#id")
        await page.type("#id", NAVER_ID, delay=50)
        await page.wait_for_timeout(500)

        # 비밀번호 입력
        await page.click("#pw")
        await page.type("#pw", NAVER_PW, delay=50)
        await page.wait_for_timeout(500)

        # 로그인 버튼 클릭
        await page.click(".btn_login")
        await page.wait_for_timeout(3000)

        # 로그인 성공 확인
        current_url = page.url
        if "naver.com" in current_url and "nidlogin" not in current_url:
            logger.info("네이버 로그인 성공")
            return True
        else:
            logger.error(f"로그인 실패. 현재 URL: {current_url}")
            return False
    except Exception as e:
        logger.error(f"로그인 중 오류: {e}")
        return False


async def post_to_naver_blog(title, content_html, tags, category=""):
    """
    네이버 블로그에 글 포스팅

    Args:
        title: 글 제목
        content_html: HTML 형식의 본문
        tags: 태그 문자열 (쉼표 구분)
        category: 블로그 카테고리 이름

    Returns:
        bool: 성공 여부
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # 로그인
            logged_in = await naver_login(page)
            if not logged_in:
                return False

            # 블로그 글쓰기 페이지 이동
            await page.goto(f"https://blog.naver.com/{NAVER_BLOG_ID}", wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # 글쓰기 버튼 클릭
            write_btn_selectors = [
                ".btn_write",
                "a[href*='PostWriteForm']",
                ".blog_btn.btn_write",
                "button:has-text('글쓰기')",
                "a:has-text('글쓰기')",
            ]

            write_clicked = False
            for selector in write_btn_selectors:
                try:
                    await page.click(selector, timeout=3000)
                    write_clicked = True
                    break
                except Exception:
                    continue

            if not write_clicked:
                # 직접 URL로 이동
                await page.goto(f"https://blog.naver.com/PostWriteForm.naver?blogId={NAVER_BLOG_ID}", wait_until="networkidle")

            await page.wait_for_timeout(3000)

            # 새 탭이 열린 경우 처리
            pages = context.pages
            if len(pages) > 1:
                page = pages[-1]
                await page.wait_for_load_state("networkidle")

            logger.info(f"글쓰기 페이지: {page.url}")

            # SmartEditor 로드 대기
            await page.wait_for_timeout(3000)

            # 제목 입력
            title_selectors = [
                "#post-title .input_text",
                ".se-title-input",
                "#post-title input",
                "input[placeholder*='제목']",
                ".pcol2 #post-title",
            ]

            title_entered = False
            for selector in title_selectors:
                try:
                    await page.click(selector, timeout=3000)
                    await page.fill(selector, title)
                    title_entered = True
                    logger.info(f"제목 입력 완료: {title}")
                    break
                except Exception:
                    continue

            if not title_entered:
                # iframe 내부 시도
                frames = page.frames
                for frame in frames:
                    try:
                        await frame.click("input[placeholder*='제목']", timeout=2000)
                        await frame.fill("input[placeholder*='제목']", title)
                        title_entered = True
                        break
                    except Exception:
                        continue

            await page.wait_for_timeout(1000)

            # 본문 입력 (SmartEditor)
            content_entered = False
            editor_selectors = [
                ".se-content",
                "#smarteditor",
                ".se2_inputarea",
                "[contenteditable='true']",
            ]

            for selector in editor_selectors:
                try:
                    editor = await page.query_selector(selector)
                    if editor:
                        await editor.click()
                        # HTML 삽입
                        safe_html = content_html.replace("`", "'")
                        js_code = f"""
                            var editor = document.querySelector('{selector}');
                            if (editor) {{
                                editor.innerHTML = `{safe_html}`;
                            }}
                        """
                        await page.evaluate(js_code)
                        content_entered = True
                        logger.info("본문 입력 완료")
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(1000)

            # 태그 입력
            tag_selectors = [
                "#post-tag input",
                ".tag_input",
                "input[placeholder*='태그']",
            ]

            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            for selector in tag_selectors:
                try:
                    for tag in tag_list[:10]:
                        await page.click(selector, timeout=2000)
                        await page.type(selector, tag, delay=30)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(300)
                    logger.info(f"태그 입력 완료: {', '.join(tag_list[:10])}")
                    break
                except Exception:
                    continue

            await page.wait_for_timeout(1000)

            # 발행 버튼 클릭
            publish_selectors = [
                ".btn_publish",
                "button:has-text('발행')",
                "button:has-text('공개발행')",
                "#publish-btn",
            ]

            published = False
            for selector in publish_selectors:
                try:
                    await page.click(selector, timeout=3000)
                    published = True
                    break
                except Exception:
                    continue

            if published:
                await page.wait_for_timeout(3000)

                # 발행 확인 팝업 처리
                confirm_selectors = [
                    "button:has-text('확인')",
                    ".btn_confirm",
                    ".btn_ok",
                ]
                for selector in confirm_selectors:
                    try:
                        await page.click(selector, timeout=2000)
                        break
                    except Exception:
                        continue

                await page.wait_for_timeout(2000)
                logger.info(f"포스팅 완료: {title}")
                return True
            else:
                logger.error("발행 버튼을 찾을 수 없음")
                return False

        except PlaywrightTimeout as e:
            logger.error(f"타임아웃 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"포스팅 중 오류: {e}")
            return False
        finally:
            await page.wait_for_timeout(1000)
            await browser.close()


def post_blog(title, content_html, tags, category=""):
    """동기 함수 래퍼"""
    return asyncio.run(post_to_naver_blog(title, content_html, tags, category))


def save_post_locally(title, content_html, tags, category, filename=None):
    """
    포스팅 실패 시 로컬에 저장 (나중에 재시도)
    """
    os.makedirs("drafts", exist_ok=True)
    if not filename:
        safe_title = "".join(c for c in title[:30] if c.isalnum() or c in " _-")
        filename = f"drafts/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_title}.json"

    draft = {
        "title": title,
        "content_html": content_html,
        "tags": tags,
        "category": category,
        "created_at": datetime.now().isoformat(),
        "posted": False,
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    logger.info(f"임시 저장: {filename}")
    return filename
