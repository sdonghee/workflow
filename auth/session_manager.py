"""
auth/session_manager.py
------------------------------------------------------------------
Playwright 브라우저 context/page 생성 + 쿠키 주입 + 로그인 확인.
발행 로직 없음.

공개 API:
  build_context(p, headless)
      -> (browser, context, page)
  verify_login(page, naver_id)
      -> bool
  login_with_cookies(context, page, cookie_path, naver_id)
      -> bool
------------------------------------------------------------------
"""
import logging

from auth import cookie_store

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def build_context(p, headless: bool = True):
    """
    Chromium 브라우저 + context + page 생성.

    Returns:
        (browser, context, page)
    """
    browser = await p.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=_UA,
        locale="ko-KR",
        permissions=["clipboard-read", "clipboard-write"],
    )
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    page = await context.new_page()
    log.debug("[session_manager] 브라우저/컨텍스트/페이지 생성 완료")
    return browser, context, page


async def verify_login(page, naver_id: str) -> bool:
    """
    naver.com에 접속해 로그인 상태 확인.
    naver_id가 소스에 있거나 로그아웃 링크가 있으면 True.
    """
    try:
        await page.goto(
            "https://www.naver.com", wait_until="domcontentloaded", timeout=15000
        )
        await page.wait_for_timeout(1500)
        content = await page.content()
        result = naver_id.lower() in content.lower() or "logout" in content.lower()
        log.info(f"[session_manager] 로그인 확인: {result} ({naver_id})")
        return result
    except Exception as e:
        log.error(f"[session_manager] verify_login 예외: {e}")
        return False


async def login_with_cookies(
    context, page, cookie_path: str, naver_id: str
) -> bool:
    """
    쿠키 파일을 주입하고 로그인 상태를 확인.

    Returns:
        True  -- 쿠키 유효, 로그인 확인됨
        False -- 쿠키 없거나 만료
    """
    cookies = cookie_store.load(cookie_path)
    if not cookies:
        log.info(f"[session_manager] 쿠키 없음: {cookie_path}")
        return False

    try:
        await context.add_cookies(cookies)
        ok = await verify_login(page, naver_id)
        if ok:
            log.info(f"[session_manager] 쿠키 로그인 성공 ({naver_id})")
        else:
            log.warning("[session_manager] 쿠키 만료 -- 재로그인 필요")
        return ok
    except Exception as e:
        log.error(f"[session_manager] login_with_cookies 예외: {e}")
        return False
