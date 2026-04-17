"""
naver_blog/publisher.py
------------------------------------------------------------------
발행 패널 열기 + confirm 버튼 클릭.
발행 성공 여부 판정은 verifier 책임.

공개 API:
  open_publish_panel(page)           -> bool
  click_confirm(page)                -> bool
------------------------------------------------------------------
"""
import logging

from naver_blog.blockers import clear_publish_blockers

log = logging.getLogger(__name__)

_CONFIRM_SELECTORS = [
    "[class*='confirm_btn']",
    "[class*='confirmBtn']",
    "[class*='publish_confirm']",
]


async def open_publish_panel(page) -> bool:
    """
    헤더의 '발행' 버튼(publish_btn__*)을 클릭해 발행 패널을 연다.
    JS .click() 사용 (패널 열기는 React 상태 변경이므로 충분).

    Returns:
        True  -- 버튼 찾아 클릭
        False -- 버튼 없음
    """
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(400)

    clicked_cls = await page.evaluate("""
        () => {
            var btn = Array.from(document.querySelectorAll('button[class*="publish_btn"]'))
                .find(b =>
                    !b.className.includes('publish_btn_area') &&
                    b.getBoundingClientRect().width > 0
                );
            if (!btn) {
                btn = Array.from(document.querySelectorAll('button')).find(b =>
                    b.textContent.trim() === '발행' &&
                    b.getBoundingClientRect().width > 0
                );
            }
            if (btn) { btn.click(); return btn.className; }
            return null;
        }
    """)

    if not clicked_cls:
        log.error("[publisher] open_publish_panel: 발행 버튼 없음")
        return False

    log.info(f"[publisher] 발행 패널 열기: {clicked_cls[:60]}")
    await page.wait_for_timeout(2500)   # 패널 애니메이션
    return True


async def click_confirm(page) -> bool:
    """
    발행 패널 내 confirm 버튼을 클릭한다.
    클릭 전 clear_publish_blockers 로 overlay 제거.

    시도 순서:
      A. Playwright locator.click() (실제 pointer 이벤트)
      B. JS .click() 폴백

    Returns:
        True  -- 클릭 완료 (발행 성공 여부는 verifier 판정)
        False -- confirm 버튼 없음
    """
    blocker_res = await clear_publish_blockers(page)
    log.info(f"[publisher] blockers: {blocker_res['action']} / {blocker_res['detail']}")

    # A. Playwright locator click
    for sel in _CONFIRM_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            cls = await loc.get_attribute("class") or ""
            # 패널 열기 버튼(publish_btn__)은 건너뜀
            if "publish_btn__" in cls and "confirm" not in cls:
                continue
            await loc.scroll_into_view_if_needed()
            await page.wait_for_timeout(200)
            await loc.click(timeout=5000)
            log.info(f"[publisher] confirm 클릭 (Playwright): {cls[:60]}")
            return True
        except Exception as e:
            log.debug(f"[publisher] locator 실패 ({sel}): {e}")

    # B. JS .click() 폴백
    log.warning("[publisher] locator 실패 -> JS .click() 폴백")
    fallback_cls = await page.evaluate("""
        () => {
            var btn = Array.from(document.querySelectorAll('button')).find(function(b) {
                var cls = b.className;
                var r = b.getBoundingClientRect();
                return r.width > 0 && r.height > 0
                    && (cls.includes('confirm_btn') || cls.includes('confirmBtn'))
                    && !cls.includes('publish_btn__');
            });
            if (!btn) {
                btn = Array.from(document.querySelectorAll('button')).find(function(b) {
                    var r = b.getBoundingClientRect();
                    return b.textContent.trim() === '발행'
                        && !b.className.includes('publish_btn__')
                        && !b.className.includes('fold')
                        && r.width >= 30 && r.height >= 20;
                });
            }
            if (btn) { btn.click(); return btn.className; }
            return null;
        }
    """)

    if fallback_cls:
        log.info(f"[publisher] confirm 클릭 (JS): {fallback_cls[:60]}")
        return True

    log.error("[publisher] click_confirm: confirm 버튼 없음")
    return False
