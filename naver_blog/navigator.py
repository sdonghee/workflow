"""
naver_blog/navigator.py
------------------------------------------------------------------
글쓰기 페이지 URL 이동 + SmartEditor DOM 로드 대기.
입력/발행 로직 없음.

공개 API:
  go_to_write_page(page, blog_id)  -> bool
  wait_for_editor(page)            -> bool
------------------------------------------------------------------
"""
import logging

log = logging.getLogger(__name__)

_WRITE_URL = "https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"

_EDITOR_SELECTORS = [
    ".se-title-text",
    ".se-placeholder",
    '[class*="se-document"]',
]


async def go_to_write_page(page, blog_id: str) -> bool:
    """
    글쓰기 URL로 이동. 로그인 페이지로 리다이렉트되면 False.

    Returns:
        True  -- 글쓰기 페이지 도달
        False -- 로그인 페이지 리다이렉트 또는 timeout
    """
    url = _WRITE_URL.format(blog_id=blog_id)
    log.info(f"[navigator] 글쓰기 페이지 이동: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(8000)   # SmartEditor React 초기화 대기
    except Exception as e:
        log.error(f"[navigator] goto 실패: {e}")
        return False

    if "nidlogin" in page.url or "login" in page.url.lower():
        log.error(f"[navigator] 로그인 페이지 리다이렉트: {page.url}")
        return False

    log.info(f"[navigator] 글쓰기 페이지 도달: {page.url[:80]}")
    return True


async def wait_for_editor(page) -> bool:
    """
    SmartEditor 핵심 DOM 요소가 attached 상태가 될 때까지 대기.
    최대 10초 × 3개 selector 순차 시도.

    Returns:
        True  -- 에디터 로드 확인
        False -- 모든 selector 시간 초과
    """
    for sel in _EDITOR_SELECTORS:
        try:
            await page.locator(sel).first.wait_for(state="attached", timeout=10000)
            log.info(f"[navigator] SmartEditor 로드 확인 ({sel})")
            await page.wait_for_timeout(1000)   # React hydration 여유
            return True
        except Exception:
            continue

    # DOM 직접 확인 (fallback)
    found = await page.evaluate("""
        () => !!(
            document.querySelector('.se-title-text') ||
            document.querySelector('.se-placeholder') ||
            document.querySelector('[class*="se-document"]')
        )
    """)
    if found:
        log.info("[navigator] SmartEditor 로드 확인 (JS fallback)")
        return True

    log.error("[navigator] SmartEditor 로드 실패 -- 모든 selector 미매칭")
    return False
