"""
SmartEditor 구조 진단 스크립트
- 글쓰기 페이지 열기
- 모든 버튼/iFrame/contenteditable 요소 덤프
- 스크린샷 저장
- 소스코드 버튼 탐색
- 클립보드 방식 vs 소스코드 방식 테스트
"""
import asyncio
import json
import os
import sys
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COOKIE_FILE = os.environ.get("BLOG1_COOKIE_FILE", "cookies_blog1.json")
BLOG_ID     = os.environ.get("BLOG1_BLOG_ID", "flighttravel")
NAVER_ID    = os.environ.get("BLOG1_NAVER_ID", "flighttravel")
NAVER_PW    = os.environ.get("BLOG1_NAVER_PW", "")

TEST_HTML = """<h2>테스트 제목입니다</h2>
<p>이것은 테스트 본문입니다. SmartEditor에 HTML이 제대로 삽입되는지 확인합니다.</p>
<p>두 번째 단락입니다. 이미지와 함께 내용이 풍부한 블로그 포스트를 자동으로 만들 수 있어야 합니다.</p>
<h3>소제목</h3>
<p>세 번째 단락입니다. 내용이 충분히 길어야 진짜 블로그 포스트처럼 보입니다.</p>"""


def load_cookies(path):
    if not os.path.exists(path):
        return None
    content = open(path).read().strip()
    if not content:
        return None
    return json.loads(content)


async def main():
    cookies = load_cookies(COOKIE_FILE)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        if cookies:
            await context.add_cookies(cookies)
            logger.info(f"쿠키 로드: {len(cookies)}개")

        page = await context.new_page()
        write_url = f"https://blog.naver.com/{BLOG_ID}?Redirect=Write"

        logger.info(f"글쓰기 페이지 이동: {write_url}")
        await page.goto(write_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # mainFrame 확인
        main_frame = page.frame(name="mainFrame")
        logger.info(f"mainFrame URL: {main_frame.url[:80] if main_frame else 'None'}")
        logger.info(f"전체 프레임: {[f.name for f in page.frames]}")

        await page.screenshot(path="/tmp/debug_01_initial.png")
        logger.info("스크린샷 저장: /tmp/debug_01_initial.png")

        if not main_frame:
            logger.error("mainFrame 없음 - 종료")
            await browser.close()
            return

        # ── SmartEditor 로드 대기 ────────────────────────────────
        for i in range(20):
            se_ready = await main_frame.evaluate("""
                () => !!document.querySelector('.se-main-section, .se-toolbar, [class*="se-"]')
            """)
            if se_ready:
                logger.info(f"SmartEditor 감지 ({i+1}회)")
                break
            await page.wait_for_timeout(500)

        await page.wait_for_timeout(2000)
        await page.screenshot(path="/tmp/debug_02_se_loaded.png")

        # ── 모든 버튼 덤프 ────────────────────────────────────────
        logger.info("=== mainFrame 버튼 목록 ===")
        buttons = await main_frame.evaluate("""
            () => {
                var btns = Array.from(document.querySelectorAll('button'));
                return btns.map(b => ({
                    text: b.textContent.trim().substring(0, 30),
                    title: b.title || '',
                    ariaLabel: b.getAttribute('aria-label') || '',
                    dataType: b.getAttribute('data-type') || '',
                    className: (b.className || '').substring(0, 60),
                    id: b.id || ''
                })).filter(b => b.text || b.title || b.ariaLabel);
            }
        """)
        for i, btn in enumerate(buttons):
            logger.info(f"  버튼[{i}]: text='{btn['text']}' title='{btn['title']}' "
                       f"aria='{btn['ariaLabel']}' data-type='{btn['dataType']}' "
                       f"class='{btn['className'][:40]}'")

        # ── SE 툴바 분석 ───────────────────────────────────────────
        logger.info("=== SE 툴바 분석 ===")
        toolbar_info = await main_frame.evaluate("""
            () => {
                var toolbar = document.querySelector('.se-toolbar');
                if (!toolbar) return {found: false};
                var items = Array.from(toolbar.querySelectorAll('button, [role="button"], li'));
                return {
                    found: true,
                    html: toolbar.innerHTML.substring(0, 2000),
                    items: items.slice(0, 30).map(el => ({
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 20),
                        title: el.title || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        class: (el.className || '').substring(0, 50)
                    }))
                };
            }
        """)
        if toolbar_info.get('found'):
            logger.info(f"툴바 HTML (첫 500자): {toolbar_info['html'][:500]}")
            for item in toolbar_info['items']:
                if item['text'] or item['title'] or item['ariaLabel']:
                    logger.info(f"  툴바항목: tag={item['tag']} text='{item['text']}' "
                               f"title='{item['title']}' aria='{item['ariaLabel']}'")
        else:
            logger.warning("툴바 없음")

        # ── '소스' 관련 요소 찾기 ─────────────────────────────────
        logger.info("=== '소스' 키워드 탐색 ===")
        source_elements = await main_frame.evaluate("""
            () => {
                var all = Array.from(document.querySelectorAll('*'));
                var found = all.filter(el => {
                    var txt = el.textContent.trim();
                    var title = el.title || '';
                    var aria = el.getAttribute('aria-label') || '';
                    var cls = el.className || '';
                    return (txt === '소스코드' || txt.includes('소스') ||
                            title.includes('소스') || aria.includes('소스') ||
                            cls.includes('source') || cls.includes('Source') ||
                            el.getAttribute('data-type') === 'source');
                });
                return found.slice(0, 10).map(el => ({
                    tag: el.tagName,
                    text: el.textContent.trim().substring(0, 30),
                    title: el.title || '',
                    class: (el.className || '').substring(0, 60),
                    dataType: el.getAttribute('data-type') || '',
                    outerHTML: el.outerHTML.substring(0, 150)
                }));
            }
        """)
        if source_elements:
            for el in source_elements:
                logger.info(f"  소스 요소: {el['tag']} text='{el['text']}' "
                           f"title='{el['title']}' class='{el['class']}'")
                logger.info(f"    outerHTML: {el['outerHTML']}")
        else:
            logger.warning("'소스' 관련 요소 없음!")

        # ── 클립보드 방식 테스트 ──────────────────────────────────
        logger.info("\n=== 클립보드(Ctrl+V) 방식 테스트 ===")
        # 본문 클릭
        body_sel = ['.se-placeholder', '.se-main-section', '.se-component:not(.se-component-title)']
        for sel in body_sel:
            try:
                loc = main_frame.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(force=True)
                    logger.info(f"본문 클릭: {sel}")
                    await page.wait_for_timeout(500)
                    break
            except Exception as e:
                logger.debug(f"클릭 실패 {sel}: {e}")

        # input_buffer 확인
        await page.wait_for_timeout(1000)
        input_frame = next((f for f in page.frames if f.name.startswith("input_buffer")), None)
        logger.info(f"input_buffer: {input_frame.name if input_frame else '없음'}")

        # 클립보드에 HTML 텍스트 복사 후 붙여넣기
        if input_frame:
            # 클립보드 방식: execCommand('copy') 우회 - JS clipboard API 사용
            logger.info("클립보드 API로 HTML 설정 시도")
            try:
                await page.evaluate("""
                    async (html) => {
                        try {
                            await navigator.clipboard.writeText(html);
                            return 'clipboard_ok';
                        } catch(e) {
                            return 'clipboard_fail:' + e.message;
                        }
                    }
                """, TEST_HTML)
            except Exception as e:
                logger.debug(f"clipboard API 실패: {e}")

            # 포커스 후 Ctrl+V
            await input_frame.locator("body").click()
            await page.wait_for_timeout(300)
            before_len = await input_frame.evaluate("document.body.innerHTML.length")
            await page.keyboard.press("Control+v")
            await page.wait_for_timeout(1000)
            after_len = await input_frame.evaluate("document.body.innerHTML.length")
            logger.info(f"Ctrl+V 결과: {before_len} → {after_len} (증가={after_len - before_len})")

            body_content = await input_frame.evaluate("document.body.innerHTML.substring(0, 200)")
            logger.info(f"body 내용: {body_content}")

        await page.screenshot(path="/tmp/debug_03_after_paste.png")
        logger.info("스크린샷: /tmp/debug_03_after_paste.png")

        # ── 제목 입력 ────────────────────────────────────────────
        title_input = main_frame.locator(".se-title-input, #title, [placeholder*='제목']").first
        if await title_input.count() > 0:
            await title_input.click()
            await title_input.fill("SmartEditor 진단 테스트")
            logger.info("제목 입력 완료")

        await page.screenshot(path="/tmp/debug_04_final.png")
        logger.info("최종 스크린샷: /tmp/debug_04_final.png")

        logger.info("\n=== 진단 완료 ===")
        logger.info("스크린샷 위치:")
        logger.info("  /tmp/debug_01_initial.png  - 초기 로드")
        logger.info("  /tmp/debug_02_se_loaded.png - SmartEditor 로드 후")
        logger.info("  /tmp/debug_03_after_paste.png - Ctrl+V 후")
        logger.info("  /tmp/debug_04_final.png - 최종")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
