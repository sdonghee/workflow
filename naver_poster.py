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

SCREENSHOT_DIR = "/app/screenshots"

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 스크린샷 저장 헬퍼
# ─────────────────────────────────────────

async def _screenshot(page, step: str, run_id: str):
    """현재 화면을 screenshots/{run_id}/{step}.png 로 저장"""
    try:
        dir_path = os.path.join(SCREENSHOT_DIR, run_id)
        os.makedirs(dir_path, exist_ok=True)
        path = os.path.join(dir_path, f"{step}.png")
        await page.screenshot(path=path, full_page=False)
        logger.info(f"[스크린샷] {path}")
    except Exception as e:
        logger.warning(f"[스크린샷 실패] {step}: {e}")


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

class BrowserUnavailableError(RuntimeError):
    """시스템 라이브러리 부족으로 브라우저를 실행할 수 없을 때"""
    pass


def _is_missing_lib_error(e: Exception) -> bool:
    msg = str(e)
    return any(k in msg for k in ("shared libraries", "exitCode=127", "libatk", "libgtk", "exitCode=255", "libmoz"))


async def _launch_browser(p):
    """Chromium → Firefox 순으로 시도, 둘 다 실패 시 BrowserUnavailableError"""
    chromium_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ]
    # 1) Chromium
    try:
        browser = await p.chromium.launch(headless=HEADLESS, args=chromium_args)
        logger.info("브라우저: Chromium")
        return browser, "chromium"
    except Exception as e:
        if not _is_missing_lib_error(e):
            raise
        logger.warning("Chromium 라이브러리 없음, Firefox 시도 중...")

    # 2) Firefox
    try:
        browser = await p.firefox.launch(
            headless=HEADLESS,
            firefox_user_prefs={
                "network.captive-portal-service.enabled": False,
                "browser.tabs.remote.autostart": False,
            },
        )
        logger.info("브라우저: Firefox")
        return browser, "firefox"
    except Exception as e:
        logger.error(f"Firefox 실행 오류 상세: {e}")
        if not _is_missing_lib_error(e):
            raise
        raise BrowserUnavailableError(
            "Chromium/Firefox 모두 실행 불가. 시스템 라이브러리 부족.\n"
            f"Firefox 오류: {e}"
        ) from e


async def post_to_naver_blog(title, content_html, tags, category, blog_config):
    """
    네이버 블로그에 글 포스팅
    blog_config: BLOGS dict의 개별 블로그 설정
    """
    # 실행마다 고유 폴더에 스크린샷 저장 (예: 20260326_153012)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{blog_config.get('blog_id','')}"

    async with async_playwright() as p:
        browser, browser_type = await _launch_browser(p)

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=ua if browser_type == "chromium" else None,
            locale="ko-KR",
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        # 브라우저 다이얼로그 처리
        # beforeunload = 발행 후 페이지 이탈 → accept()로 허용
        # 나머지(alert 등) = dismiss()로 닫기
        async def _on_dialog(dialog):
            if dialog.type == "beforeunload":
                logger.info("브라우저 다이얼로그: [beforeunload] 발행 후 이탈 허용")
                await dialog.accept()
            else:
                logger.warning(f"브라우저 다이얼로그: [{dialog.type}] {dialog.message}")
                await dialog.dismiss()
        page.on("dialog", _on_dialog)

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
            write_url = f"https://blog.naver.com/{blog_id}?Redirect=Write&categoryNo=0"
            await page.goto(write_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            if len(context.pages) > 1:
                page = context.pages[-1]
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)

            logger.info(f"[{blog_config['name']}] 글쓰기 페이지: {page.url}")

            # 쿠키 만료로 로그인 페이지로 리다이렉트된 경우 재로그인
            if "nidlogin" in page.url or ("naver.com" in page.url and "login" in page.url.lower()):
                logger.warning(f"[{blog_config['name']}] 쿠키 만료 감지 (로그인 페이지 리다이렉트) → ID/PW 재로그인")
                logged_in = await login_with_password(page, blog_config)
                if not logged_in:
                    logger.error(f"[{blog_config['name']}] ID/PW 재로그인 실패")
                    return False
                cookies = await context.cookies()
                save_cookies(cookies, blog_config["cookie_file"])
                await page.goto(write_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)
                if len(context.pages) > 1:
                    page = context.pages[-1]
                    await page.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(3000)
                logger.info(f"[{blog_config['name']}] 재로그인 후 글쓰기 페이지: {page.url}")

            # mainFrame 로드 대기
            try:
                await page.wait_for_selector(
                    "iframe[name='mainFrame'], iframe#mainFrame",
                    timeout=15000
                )
                await page.wait_for_timeout(2000)
            except Exception:
                logger.warning("mainFrame iframe DOM 미발견, 계속 진행")

            frame_info = [(f.name or "noname", f.url[:60]) for f in page.frames]
            logger.info(f"로드된 frames({len(frame_info)}개): {frame_info}")

            main_frame = page.frame(name="mainFrame")
            if main_frame:
                try:
                    await main_frame.wait_for_load_state("domcontentloaded", timeout=10000)
                    await page.wait_for_timeout(1000)
                    logger.info(f"mainFrame 로드 완료: {main_frame.url[:60]}")
                except Exception:
                    logger.warning("mainFrame 로드 대기 실패, 계속 진행")
            else:
                logger.warning("mainFrame frame 객체 없음, 계속 진행")

            # [스크린샷 1] 글쓰기 페이지 로드 직후
            await _screenshot(page, "01_write_page_loaded", run_id)

            # 3-1. "작성 중인 글이 있습니다" HTML 팝업 처리
            # (브라우저 native dialog가 아닌 HTML 모달 → page.on("dialog") 미처리)
            await _dismiss_draft_popup(page)
            await page.wait_for_timeout(800)

            # 3-2. SmartEditor ONE 본문 영역 로드 완료 대기
            # (초안 팝업 없는 계정은 대기 없이 바로 진행 → 에디터 미초기화 상태로 클릭)
            if main_frame:
                try:
                    await main_frame.wait_for_selector(
                        '.se-placeholder, .se-component.se-text',
                        timeout=8000
                    )
                    await page.wait_for_timeout(1000)
                    logger.info("SmartEditor 본문 영역 로드 완료")
                except Exception:
                    logger.warning("SmartEditor 본문 영역 로드 대기 타임아웃, 계속 진행")

            # 4. 제목 입력
            await _enter_title(page, title)
            await page.wait_for_timeout(1500)

            # [스크린샷 2] 제목 입력 후
            await _screenshot(page, "02_after_title", run_id)

            # 5. 본문 입력 (태그를 본문 끝 해시태그로 추가)
            tag_list = [t.strip() for t in tags.split(",") if t.strip()][:10]
            if tag_list:
                tag_line = " ".join(f"#{t}" for t in tag_list)
                content_with_tags = content_html + f"<p>{tag_line}</p>"
            else:
                content_with_tags = content_html
            await _enter_content(page, content_with_tags)
            await page.wait_for_timeout(1500)

            # [스크린샷 3] 본문 입력 후
            await _screenshot(page, "03_after_content", run_id)

            # 6. 발행
            success = await _publish(page, run_id)

            # [스크린샷 6] 발행 후 최종 상태
            await _screenshot(page, "06_after_publish", run_id)

            if success:
                cookies = await context.cookies()
                save_cookies(cookies, blog_config["cookie_file"])

                # 7. 실제 블로그에서 포스팅 검증
                verified = await _verify_posted(page, blog_id, title)
                if verified:
                    logger.info(f"[{blog_config['name']}] ✅ 포스팅 확인 완료: {title}")
                else:
                    logger.error(f"[{blog_config['name']}] ❌ 발행 클릭했지만 블로그에서 글을 찾을 수 없음: {title}")
                    await _screenshot(page, "07_verify_failed", run_id)
                    return False

            logger.info(f"[스크린샷 폴더] {SCREENSHOT_DIR}/{run_id}/")
            return success

        except PlaywrightTimeout as e:
            logger.error(f"[{blog_config['name']}] 타임아웃 오류: {e}")
            await _screenshot(page, "error_timeout", run_id)
            return False
        except Exception as e:
            logger.error(f"[{blog_config['name']}] 포스팅 오류: {e}", exc_info=True)
            await _screenshot(page, "error_exception", run_id)
            return False
        finally:
            await page.wait_for_timeout(1000)
            await browser.close()


# ─────────────────────────────────────────
# 세부 동작 함수들
# ─────────────────────────────────────────

async def _dismiss_draft_popup(page):
    """'작성 중인 글이 있습니다' HTML 팝업을 '취소'로 닫기 (이전 초안 버리고 새로 시작)"""
    main_frame = page.frame(name="mainFrame")
    if not main_frame:
        return
    try:
        result = await main_frame.evaluate("""
            () => {
                var btns = Array.from(document.querySelectorAll('button'));
                var cancelBtn = btns.find(b => b.textContent.trim() === '취소');
                if (cancelBtn) { cancelBtn.click(); return 'dismissed'; }
                return 'no_popup';
            }
        """)
        logger.info(f"초안 팝업 처리: {result}")
    except Exception as e:
        logger.debug(f"초안 팝업 확인 중 오류: {e}")


async def _enter_title(page, title):
    """제목 입력 - SmartEditor ONE
    핵심: Playwright의 실제 click()으로 포커스를 준 뒤 keyboard.type() 사용.
    execCommand만으로는 React 내부 상태가 갱신되지 않아 발행 시 제목이 비어버림.
    """
    main_frame = page.frame(name="mainFrame")
    if not main_frame:
        logger.warning("제목 입력 실패: mainFrame 없음")
        return

    await page.wait_for_timeout(1000)

    # 제목 영역 selector 우선순위 (SmartEditor ONE)
    selectors = [
        '.se-title-text',
        '.se-title-input',
        'div[contenteditable="true"][class*="title"]',
        'div[contenteditable="true"][aria-multiline="false"]',
        'div[contenteditable="true"][data-placeholder]',
    ]

    for sel in selectors:
        try:
            locator = main_frame.locator(sel).first
            if await locator.count() == 0:
                continue
            # Playwright 실제 클릭 → 포커스
            await locator.click()
            await page.wait_for_timeout(400)
            # 전체 선택 후 타이핑 (keyboard.type은 React 이벤트 정상 트리거)
            await page.keyboard.press("Control+a")
            await page.keyboard.type(title, delay=40)
            await page.wait_for_timeout(300)
            logger.info(f"제목 입력 완료: {title[:30]} (selector: {sel})")
            return
        except Exception as e:
            logger.debug(f"제목 selector 시도 실패 ({sel}): {e}")
            continue

    # 최후 폴백: JS로 첫 번째 contenteditable 요소를 직접 click/focus 후 keyboard.type
    try:
        result = await main_frame.evaluate("""
            () => {
                var all = Array.from(document.querySelectorAll('[contenteditable="true"]'));
                var el = all.find(function(e) { return e.tagName !== 'BODY'; });
                if (!el) {
                    var debug = Array.from(document.querySelectorAll('[contenteditable]'))
                        .map(function(e) { return e.tagName + '.' + (e.className||'').substring(0,30); }).join('|');
                    return 'not_found:' + debug;
                }
                // Frame에는 .mouse가 없으므로 JS로 직접 click/focus
                el.click();
                el.focus();
                return 'ok:' + el.className.substring(0, 40);
            }
        """)
        if result and result.startswith('ok:'):
            await page.wait_for_timeout(300)
            await page.keyboard.press("Control+a")
            await page.keyboard.type(title, delay=40)
            logger.info(f"제목 입력 완료 (JS click 폴백): {title[:30]} {result}")
        else:
            logger.warning(f"제목 입력 실패: {result}")
    except Exception as e:
        logger.warning(f"제목 입력 폴백 실패: {e}")


async def _enter_content(page, content_html):
    """본문 입력 - SmartEditor ONE

    핵심: mainFrame의 본문 영역을 Playwright click()으로 포커스한 뒤
    input_buffer에서 insertHTML. execCommand는 선택 없으면 true를 반환해도
    실제로 삽입되지 않으므로 innerHTML 길이 변화로 검증.
    """
    safe_html = content_html.replace("`", "'").replace("\\", "\\\\").replace("\n", "")

    main_frame = page.frame(name="mainFrame")
    if not main_frame:
        logger.warning("본문 입력 실패: mainFrame 없음")
        return

    # ── mainFrame 구조 진단 ─────────────────────────────────────────
    try:
        mf_debug = await main_frame.evaluate("""
            () => {
                var ces = Array.from(document.querySelectorAll('[contenteditable]'));
                var placeholders = Array.from(document.querySelectorAll('[class*="placeholder"]'));
                var components = Array.from(document.querySelectorAll('.se-component, .se-section'));
                return {
                    contentEditables: ces.map(e => e.tagName + '.' + (e.className||'').substring(0,30)).join('|'),
                    placeholders: placeholders.map(e => e.tagName + '.' + (e.className||'').substring(0,30)).join('|'),
                    components: components.slice(0,5).map(e => e.tagName + '.' + (e.className||'').substring(0,30)).join('|')
                };
            }
        """)
        logger.info(f"mainFrame 구조: CE={mf_debug['contentEditables'][:100]}")
        logger.info(f"  placeholders: {mf_debug['placeholders'][:100]}")
        logger.info(f"  components:   {mf_debug['components'][:100]}")
    except Exception as e:
        logger.debug(f"mainFrame 진단 실패: {e}")

    # ── 방법 1: mainFrame의 본문 영역 직접 Playwright click() ───────
    # SmartEditor ONE: 클릭해야 input_buffer에 커서가 본문 위치로 이동
    body_selectors = [
        'p.se-placeholder',
        '.se-placeholder',
        '.se-component-content .se-text',
        '.se-section-body .se-component .se-component-content',
        '.se-main-section',
        '.se-component:not(.se-component-title)',
    ]

    clicked_body = False
    for sel in body_selectors:
        try:
            loc = main_frame.locator(sel).first
            cnt = await loc.count()
            if cnt == 0:
                continue
            await loc.click(force=True)
            await page.wait_for_timeout(800)
            logger.info(f"본문 영역 클릭 성공: {sel} (count={cnt})")
            clicked_body = True
            break
        except Exception as e:
            logger.debug(f"본문 selector 클릭 실패 ({sel}): {e}")

    if not clicked_body:
        logger.info("본문 selector 클릭 실패 → Tab 폴백")
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(800)

    # ── input_buffer 대기 (클릭 후 SmartEditor가 준비될 때까지) ────
    input_frame = None
    for wait_i in range(12):
        input_frame = next((f for f in page.frames if f.name.startswith("input_buffer")), None)
        if input_frame:
            break
        await page.wait_for_timeout(500)
        logger.debug(f"input_buffer 대기 중... {wait_i + 1}/12")
    if not input_frame:
        logger.warning("input_buffer 프레임 없음 (6초 대기 후에도)")
        return

    logger.info(f"본문 삽입 프레임: {input_frame.name}")

    try:
        # 삽입 전 상태 진단
        diag = await input_frame.evaluate("""
            () => {
                var sel = window.getSelection();
                var selInfo = 'no_selection';
                if (sel && sel.rangeCount > 0) {
                    var range = sel.getRangeAt(0);
                    var node = range.startContainer;
                    selInfo = (node.nodeType === 3 ? 'text:' + node.textContent.substring(0,20)
                               : (node.className || node.tagName || 'unknown'))
                              + '@' + range.startOffset;
                }
                return {
                    hasFocus: document.hasFocus(),
                    bodyLen: document.body.innerHTML.length,
                    bodyPreview: document.body.innerHTML.substring(0, 120),
                    children: Array.from(document.body.children).map(
                        e => e.tagName + '.' + (e.className||'').substring(0,20)
                    ).join('|'),
                    sel: selInfo
                };
            }
        """)
        logger.info(f"input_buffer 진단: focus={diag['hasFocus']}, bodyLen={diag['bodyLen']}, sel={diag['sel']}")
        logger.info(f"  body children: {diag['children']}")
        logger.info(f"  body preview:  {diag['bodyPreview'][:80]}")

        before_len = diag['bodyLen']

        # ── 1차: 현재 커서 위치에 insertHTML ────────────────────────
        ok1 = await input_frame.evaluate(f"document.execCommand('insertHTML', false, `{safe_html}`)")
        after_len1 = await input_frame.evaluate("document.body.innerHTML.length")
        logger.info(f"1차 insertHTML: ok={ok1}, 길이 {before_len} → {after_len1}")

        if after_len1 > before_len + 50:
            logger.info("본문 입력 완료 (1차: insertHTML at cursor)")
            return

        # ── 2차: body 두 번째 자식 위치로 커서 강제 이동 후 insertHTML
        logger.warning("1차 삽입 변화 미미 → 2차: 커서 이동 후 삽입")
        result2 = await input_frame.evaluate(f"""
            (function() {{
                var body = document.body;
                var children = Array.from(body.children);
                if (children.length === 0) return 'no_children';
                // 두 번째 자식이 있으면 두 번째, 없으면 첫 번째 끝으로 커서 이동
                var targetEl = children.length > 1 ? children[1] : children[0];
                var sel = window.getSelection();
                var range = document.createRange();
                range.selectNodeContents(targetEl);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
                var ok2 = document.execCommand('insertHTML', false, `{safe_html}`);
                return 'ok=' + ok2 + ':len=' + body.innerHTML.length;
            }})()
        """)
        after_len2 = await input_frame.evaluate("document.body.innerHTML.length")
        logger.info(f"2차 삽입: {result2}, 길이 {after_len2}")

        if after_len2 > before_len + 50:
            logger.info("본문 입력 완료 (2차: cursor-moved insertHTML)")
            return

        # ── 3차: DOM 직접 삽입 (최후 수단) ─────────────────────────
        logger.warning("3차: DOM 직접 조작")
        result3 = await input_frame.evaluate(f"""
            (function() {{
                var body = document.body;
                var children = Array.from(body.children);
                var div = document.createElement('div');
                div.innerHTML = `{safe_html}`;
                // 두 번째 자식 이후에 삽입 (첫 번째는 제목)
                var refNode = children.length > 1 ? children[1] : null;
                if (refNode) {{
                    body.insertBefore(div, refNode);
                }} else {{
                    body.appendChild(div);
                }}
                body.dispatchEvent(new InputEvent('input', {{bubbles: true, inputType: 'insertText'}}));
                return 'dom:len=' + body.innerHTML.length;
            }})()
        """)
        logger.info(f"3차 DOM 삽입: {result3}")

    except Exception as e:
        logger.error(f"본문 입력 실패: {e}", exc_info=True)


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


_PUBLISH_JS = """
(function() {
    var keywords = ['발행', '게시', 'publish'];
    var cssClasses = ['publish', 'btn_publish', 'se_publish'];

    // CSS class 기반 탐색
    for (var cls of cssClasses) {
        var el = document.querySelector('button.' + cls + ', a.' + cls + ', .' + cls);
        if (el) { el.click(); return 'css:' + cls; }
    }
    // 텍스트 기반 탐색 (has-text 대신 JS로)
    var all = Array.from(document.querySelectorAll('button, a[href], input[type="button"]'));
    for (var kw of keywords) {
        var btn = all.find(function(b) {
            return b.textContent.trim() === kw ||
                   (b.value && b.value.trim() === kw);
        });
        if (btn) { btn.click(); return 'text:' + kw; }
    }
    return false;
})()
"""

_CONFIRM_JS = """
(function() {
    // 툴바(.se-toolbar) 내 버튼은 제외 — 첫 번째 '발행' 클릭 시 이미 사용된 버튼
    var toolbarEls = new Set(
        Array.from(document.querySelectorAll('.se-toolbar *, ul[class*="toolbar"] *, [class*="document-toolbar"] *'))
    );

    var all = Array.from(document.querySelectorAll('button, a[role="button"], a[class*="btn"]'));
    // 툴바 제외
    var candidates = all.filter(function(b) { return !toolbarEls.has(b); });

    // 1. '공개발행', '발행하기', '전체공개' 우선
    var keywords = ['공개발행', '발행하기', '전체공개'];
    for (var kw of keywords) {
        var btn = candidates.find(function(b) { return b.textContent.trim().includes(kw); });
        if (btn) { btn.click(); return 'kw:' + kw + ':' + btn.className.substring(0, 30); }
    }

    // 2. 툴바 외 '발행' 버튼 탐색
    // 버튼이 2개인 경우: [0]=에디터 헤더 버튼(패널 열기용, y값 작음), [1]=패널 확인 버튼(y값 큼)
    // getBoundingClientRect().y가 가장 큰 버튼 = 화면 아래쪽 = 패널 확인 버튼
    var publishBtns = candidates.filter(function(b) { return b.textContent.trim() === '발행'; });
    if (publishBtns.length > 0) {
        var btnsDebug = publishBtns.map(function(b, i) {
            var rect = b.getBoundingClientRect();
            return i + '(y=' + Math.round(rect.y) + ',cls=' + b.className.substring(0, 20) + ')';
        }).join('|');
        // y좌표가 가장 큰(화면 아래쪽) 버튼 클릭 = 패널 안의 확인 발행 버튼
        var targetBtn = publishBtns.reduce(function(max, b) {
            return b.getBoundingClientRect().y > max.getBoundingClientRect().y ? b : max;
        });
        targetBtn.click();
        return 'publish:cnt=' + publishBtns.length + ':btns=[' + btnsDebug + ']:clicked_y=' + Math.round(targetBtn.getBoundingClientRect().y);
    }

    // 3. 디버그: 후보 버튼 목록 반환
    var debugInfo = candidates.slice(0, 10).map(function(b) {
        return (b.textContent.trim() || b.className).substring(0, 20);
    }).join('|');
    return 'not_found:candidates=' + candidates.length + ':' + debugInfo;
})()
"""


async def _verify_posted(page, blog_id: str, title: str) -> bool:
    """발행 후 실제 블로그에서 글 제목 확인"""
    try:
        # 발행 후 페이지가 이미 이동했는지 먼저 확인
        await page.wait_for_timeout(2000)
        current_url = page.url
        logger.info(f"[검증] 현재 URL: {current_url[:80]}")

        # 에디터 URL이 아닌 블로그 URL로 이동했으면 발행 성공
        if ("PostWriteForm" not in current_url and
                "Redirect=Write" not in current_url and
                blog_id in current_url):
            logger.info(f"[검증] 발행 후 블로그 URL 이동 확인 ✅: {current_url[:60]}")
            return True

        # 블로그 홈으로 이동해서 제목 검색
        blog_url = f"https://blog.naver.com/{blog_id}"
        await page.goto(blog_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)
        content = await page.content()
        found = title in content
        logger.info(f"[검증] 블로그({blog_url}) 에서 '{title[:20]}' {'발견 ✅' if found else '미발견 ❌'}")
        return found
    except Exception as e:
        logger.warning(f"[검증] 블로그 확인 실패: {e}")
        return False


async def _publish(page, run_id: str = ""):
    """발행 버튼 클릭 - SmartEditor ONE (JS 기반, has-text 제거로 timeout 방지)"""
    main_frame = page.frame(name="mainFrame")
    search_frames = []
    if main_frame:
        search_frames.append(main_frame)
        search_frames.extend(main_frame.child_frames)
    for f in page.frames:
        if f not in search_frames:
            search_frames.append(f)

    # 1단계: 발행 버튼 (메인 페이지 → frames 순, JS 텍스트 탐색)
    clicked = False

    # 메인 페이지 먼저
    try:
        result = await page.evaluate(_PUBLISH_JS)
        if result:
            logger.info(f"발행 버튼 클릭(main): {result}")
            await page.wait_for_timeout(3000)
            clicked = True
    except Exception:
        pass

    if not clicked:
        for frame in search_frames:
            try:
                result = await frame.evaluate(_PUBLISH_JS)
                if result:
                    logger.info(f"발행 버튼 클릭(frame): {result}")
                    await page.wait_for_timeout(3000)
                    clicked = True
                    break
            except Exception:
                continue

    if not clicked:
        logger.error("발행 버튼 없음")
        await _screenshot(page, "04_publish_btn_notfound", run_id)
        return False

    # [스크린샷 4] 첫 번째 발행 버튼 클릭 직후 (패널이 열렸는지 확인)
    await _screenshot(page, "04_after_publish_click", run_id)

    # 2단계: 발행 확인 패널 처리 (클릭 후 패널이 열리기까지 대기 후 반복 탐색)
    logger.info("발행 확인 패널 대기 중...")
    await page.wait_for_timeout(3000)  # 패널 애니메이션 대기

    # [스크린샷 5] 패널 대기 후 (패널 내용 확인)
    await _screenshot(page, "05_publish_panel", run_id)

    for attempt in range(8):
        await page.wait_for_timeout(1500)
        confirmed = False

        # 메인 페이지에서 먼저
        try:
            result = await page.evaluate(_CONFIRM_JS)
            if result and not str(result).startswith('not_found'):
                logger.info(f"발행 확인: {result}")
                await page.wait_for_timeout(3000)
                return True
            elif result:
                logger.info(f"발행 확인 탐색중(main): {result}")
        except Exception:
            pass

        # frames에서 탐색
        for frame in search_frames:
            try:
                result = await frame.evaluate(_CONFIRM_JS)
                if result and not str(result).startswith('not_found'):
                    logger.info(f"발행 확인(frame/{frame.name or 'noname'}): {result}")
                    await page.wait_for_timeout(3000)
                    return True
                elif result:
                    logger.info(f"발행 확인 탐색중({frame.name or 'noname'}): {result}")
            except Exception:
                continue

        if attempt == 0:
            logger.info("확인 버튼 미발견, 계속 탐색 중...")

    logger.warning("발행 확인 버튼 미발견 — 발행이 완료되지 않았을 수 있음")
    return False


# ─────────────────────────────────────────
# HTTP API 폴백 (브라우저 없이 requests 사용)
# ─────────────────────────────────────────

def _cookies_to_requests(playwright_cookies):
    """Playwright 쿠키 리스트 → requests CookieJar 호환 dict"""
    return {c["name"]: c["value"] for c in playwright_cookies if "name" in c and "value" in c}


def post_via_http(title, content_html, tags, category, blog_config) -> bool:
    """
    브라우저 없이 requests로 Naver Blog AJAX API 직접 호출.
    저장된 쿠키가 유효해야 동작 (만료 시 False 반환).
    """
    import requests as req

    cookie_data = load_cookies(blog_config["cookie_file"])
    if not cookie_data:
        logger.error("[HTTP] 저장된 쿠키 없음 — first_login.py 실행 필요")
        return False

    blog_id  = blog_config["blog_id"]
    naver_id = blog_config["naver_id"]

    session = req.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://blog.naver.com",
    })
    session.cookies.update(_cookies_to_requests(cookie_data))

    # 로그인 상태 확인
    try:
        check = session.get("https://www.naver.com", timeout=10)
        if naver_id.lower() not in check.text.lower() and "로그아웃" not in check.text:
            logger.error("[HTTP] 쿠키 만료 — first_login.py 로 재로그인 필요")
            return False
    except Exception as e:
        logger.error(f"[HTTP] 로그인 확인 실패: {e}")
        return False

    # 글쓰기 폼 GET → 숨겨진 토큰 추출
    try:
        form_resp = session.get(
            f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}",
            timeout=15,
        )
    except Exception as e:
        logger.error(f"[HTTP] 글쓰기 폼 로드 실패: {e}")
        return False

    # CSRF / blogNo 파싱 시도
    blog_no = ""
    import re
    m = re.search(r'"blogNo"\s*:\s*"?(\d+)"?', form_resp.text)
    if m:
        blog_no = m.group(1)

    # 포스팅 AJAX 요청
    post_data = {
        "blogId":              blog_id,
        "blogNo":              blog_no,
        "logNo":               "0",
        "title":               title,
        "contents":            content_html,
        "categoryNo":          "0",
        "tag":                 tags,
        "type":                "post",
        "status":              "publish",
        "useRssYN":            "Y",
        "allowComment":        "true",
        "allowLike":           "true",
        "allowExternalSearch": "true",
        "addCategoryYN":       "N",
        "addContents":         "",
        "publishDate":         "",
        "publishTime":         "",
        "cclUploadLicense":    "",
        "cclCommercial":       "",
        "cclModification":     "",
    }

    try:
        resp = session.post(
            "https://blog.naver.com/PostSaveAjax.naver",
            data=post_data,
            timeout=30,
        )
        logger.info(f"[HTTP] 응답 {resp.status_code}: {resp.text[:300]}")
        try:
            j = resp.json()
            if j.get("result") == "SUCCESS" or j.get("logNo") or j.get("postNo"):
                logger.info(f"[HTTP] ✅ 포스팅 성공: {j}")
                return True
            logger.error(f"[HTTP] API 오류 응답: {j}")
        except Exception:
            # JSON이 아닌 경우 200이면 성공으로 간주
            if resp.status_code == 200 and "error" not in resp.text.lower():
                logger.info("[HTTP] ✅ 포스팅 성공 (비JSON 200 응답)")
                return True
        return False
    except Exception as e:
        logger.error(f"[HTTP] POST 실패: {e}")
        return False


# ─────────────────────────────────────────
# 동기 래퍼 & 로컬 저장
# ─────────────────────────────────────────

def post_blog(title, content_html, tags, category, blog_config):
    """브라우저 시도 → HTTP API 폴백 → False"""
    # 브라우저 시도
    try:
        return asyncio.run(post_to_naver_blog(title, content_html, tags, category, blog_config))
    except BrowserUnavailableError:
        logger.warning("[post_blog] 브라우저 불가 → HTTP API 폴백")
        return post_via_http(title, content_html, tags, category, blog_config)


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
