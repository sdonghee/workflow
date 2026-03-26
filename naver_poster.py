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
            # 실제 글쓰기 URL: blog.naver.com/{blog_id}?Redirect=Write&categoryNo=0
            # 이 URL이 mainFrame iframe을 포함한 올바른 구조를 반환함
            blog_id = blog_config["blog_id"]
            write_url = f"https://blog.naver.com/{blog_id}?Redirect=Write&categoryNo=0"
            await page.goto(write_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            if len(context.pages) > 1:
                page = context.pages[-1]
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)

            logger.info(f"[{blog_config['name']}] 글쓰기 페이지: {page.url}")

            # mainFrame 로드 대기 (iframe이 async로 삽입되므로 DOM에 나타날 때까지 대기)
            try:
                await page.wait_for_selector(
                    "iframe[name='mainFrame'], iframe#mainFrame",
                    timeout=15000
                )
                await page.wait_for_timeout(2000)
            except Exception:
                logger.warning("mainFrame iframe DOM 미발견, 계속 진행")

            # 모든 frame 목록 로그 (디버깅)
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

            # 4. 제목 입력
            await _enter_title(page, title)
            await page.wait_for_timeout(1500)

            # 5. 본문 입력 (태그를 본문 끝 해시태그로 추가 - Naver 자동 인식)
            tag_list = [t.strip() for t in tags.split(",") if t.strip()][:10]
            if tag_list:
                tag_line = " ".join(f"#{t}" for t in tag_list)
                content_with_tags = content_html + f"<p>{tag_line}</p>"
            else:
                content_with_tags = content_html
            await _enter_content(page, content_with_tags)
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
    """제목 입력 - SmartEditor ONE"""
    main_frame = page.frame(name="mainFrame")
    if not main_frame:
        logger.warning("제목 입력 실패: mainFrame 없음")
        return

    await page.wait_for_timeout(1000)

    # JS로 mainFrame에서 제목 요소 탐색 (선택자 우선순위 순, 디버그 정보 반환)
    result = await main_frame.evaluate("""
        (title) => {
            var selectors = [
                '.se-title-input',
                'div[contenteditable="true"][class*="title"]',
                'div[contenteditable="true"][aria-multiline="false"]',
                'div[contenteditable="true"][data-placeholder]',
            ];
            var el = null;
            for (var sel of selectors) {
                el = document.querySelector(sel);
                if (el) break;
            }
            // Fallback: mainFrame 내 첫 번째 contenteditable (body 제외)
            if (!el) {
                var all = Array.from(document.querySelectorAll('[contenteditable="true"]'));
                el = all.find(function(e) { return e.tagName !== 'BODY'; });
            }
            if (!el) {
                var allInfo = Array.from(document.querySelectorAll('[contenteditable]'));
                return 'not_found:count=' + allInfo.length + ':' +
                    allInfo.map(function(e) { return e.tagName + '.' + (e.className || '').substring(0, 40); }).join('|');
            }
            el.focus();
            el.innerHTML = '';
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, title);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            return 'ok:' + (el.className || el.tagName);
        }
    """, title)

    if result and result.startswith('ok:'):
        logger.info(f"제목 입력 완료: {title[:30]} ({result})")
    else:
        logger.warning(f"제목 입력 실패: {result}")


async def _enter_content(page, content_html):
    """본문 입력 - SmartEditor ONE (body[contenteditable] 우선 탐색)"""
    safe_html = content_html.replace("`", "'").replace("\\", "\\\\").replace("\n", "")

    # input_buffer 프레임 우선 탐색 (SmartEditor ONE의 실제 편집 iframe)
    input_frame = None
    for f in page.frames:
        if f.name.startswith("input_buffer"):
            input_frame = f
            break

    main_frame = page.frame(name="mainFrame")

    # 탐색 순서: input_buffer → mainFrame child_frames → mainFrame → 나머지
    search_frames = []
    if input_frame:
        search_frames.append(input_frame)
    if main_frame:
        for cf in main_frame.child_frames:
            if cf not in search_frames:
                search_frames.append(cf)
        if main_frame not in search_frames:
            search_frames.append(main_frame)
    for f in page.frames:
        if f not in search_frames:
            search_frames.append(f)

    for frame in search_frames:
        try:
            result = await frame.evaluate(f"""
                (function() {{
                    // 1) body 자체가 contenteditable (input_buffer 프레임)
                    if (document.body && document.body.contentEditable === 'true') {{
                        document.body.innerHTML = `{safe_html}`;
                        document.body.dispatchEvent(new Event('input', {{bubbles: true}}));
                        document.body.dispatchEvent(new InputEvent('input', {{bubbles: true, inputType: 'insertText'}}));
                        return 'body-editable';
                    }}
                    // 2) .se-content 내 editable 영역
                    var seContent = document.querySelector('.se-content');
                    if (seContent) {{
                        var editable = seContent.querySelector('[contenteditable="true"]');
                        if (editable) {{
                            editable.innerHTML = `{safe_html}`;
                            editable.dispatchEvent(new Event('input', {{bubbles: true}}));
                            return 'se-content';
                        }}
                    }}
                    // 3) 제목 제외 마지막 contenteditable
                    var all = Array.from(document.querySelectorAll('[contenteditable="true"]'));
                    var nonTitle = all.filter(function(el) {{
                        return !el.className.includes('title') && el.tagName !== 'INPUT';
                    }});
                    if (nonTitle.length > 0) {{
                        var target = nonTitle[nonTitle.length - 1];
                        target.innerHTML = `{safe_html}`;
                        target.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return 'last-editable';
                    }}
                    return false;
                }})()
            """)
            if result:
                logger.info(f"본문 입력 완료: {result} (frame: {frame.name or frame.url[:40]})")
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
    // Naver 발행 확인 패널: '공개발행', '전체공개', '발행하기', '확인' 버튼 탐색
    var keywords = ['공개발행', '발행하기', '전체공개', '확인'];
    var all = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"]'));
    for (var kw of keywords) {
        var btn = all.find(function(b) {
            var t = (b.textContent || b.value || '').trim();
            return t === kw || t.includes(kw);
        });
        if (btn && btn.offsetParent !== null) {
            // offsetParent !== null 이면 실제로 보이는 요소
            btn.click();
            return 'confirm:' + kw;
        }
    }
    // CSS class 기반
    for (var cls of ['.btn_confirm', '.btn_ok', '.btn-primary', '.publish_btn']) {
        var el = document.querySelector(cls);
        if (el && el.offsetParent !== null) { el.click(); return 'css-confirm:' + cls; }
    }
    return false;
})()
"""


async def _publish(page):
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
        return False

    # 2단계: 발행 확인 패널 처리 (클릭 후 패널이 열리기까지 대기 후 반복 탐색)
    # Naver: 발행 버튼 → 공개 설정 패널 → '공개발행' 또는 '발행하기' 버튼
    logger.info("발행 확인 패널 대기 중...")
    await page.wait_for_timeout(3000)  # 패널 애니메이션 대기

    for attempt in range(8):
        await page.wait_for_timeout(1500)
        confirmed = False

        # 메인 페이지에서 먼저
        try:
            result = await page.evaluate(_CONFIRM_JS)
            if result:
                logger.info(f"발행 확인: {result}")
                await page.wait_for_timeout(3000)
                return True
        except Exception:
            pass

        # frames에서 탐색
        for frame in search_frames:
            try:
                result = await frame.evaluate(_CONFIRM_JS)
                if result:
                    logger.info(f"발행 확인(frame/{frame.name or 'noname'}): {result}")
                    await page.wait_for_timeout(3000)
                    return True
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
