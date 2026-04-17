"""
naver_blog/blockers.py
------------------------------------------------------------------
Naver SmartEditor 글쓰기 페이지에서 클릭을 방해하는 UI 요소 제거.
poster/blockers.py 에서 이동 (경로만 변경, 로직 동일).

책임:
  - dismiss_restore_popup  : "작성 중인 글이 있습니다" 팝업 닫기
  - dismiss_help_panel     : 우측 도움말 패널 숨기기
  - clear_publish_blockers : 발행 confirm 버튼 직전에 덮는 모든 요소 제거

반환값:
  모든 함수는 dict 반환:
    {"ok": bool, "action": str, "detail": str}

호출 순서 (권장):
  1. dismiss_restore_popup(page)   -- 글쓰기 페이지 진입 직후
  2. dismiss_help_panel(page)      -- 에디터 조작 전
  3. clear_publish_blockers(page)  -- 발행 confirm 버튼 클릭 직전
------------------------------------------------------------------
"""
import logging

log = logging.getLogger(__name__)


# ==================================================================
# 1. dismiss_restore_popup
# ==================================================================

async def dismiss_restore_popup(page) -> dict:
    """
    "작성 중인 글이 있습니다" HTML 팝업을 닫는다.

    팝업 레이어 컨테이너 안에서만 버튼을 탐색하여
    도움말 패널 닫기 버튼 오탐을 방지한다.

    Returns:
        {"ok": True,  "action": "dismissed", "detail": "새 글 쓰기"}
        {"ok": True,  "action": "no_popup",  "detail": ""}
        {"ok": False, "action": "error",     "detail": "<예외 메시지>"}
    """
    _JS = """
        () => {
            var POPUP_SELS = [
                '[class*="modal"]', '[class*="layer"]', '[class*="dialog"]',
                '[class*="popup"]', '[class*="alert"]', '[class*="confirm"]',
                '[class*="restore"]', '[class*="draft"]',
            ];
            var DISCARD_LABELS = ['새 글 쓰기', '새글 쓰기', '새 글쓰기'];
            var CLOSE_LABELS   = ['취소', '닫기'];

            for (var sel of POPUP_SELS) {
                var containers = Array.from(document.querySelectorAll(sel));
                for (var container of containers) {
                    if (container.style.display === 'none') continue;
                    var r = container.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;

                    var btns = Array.from(container.querySelectorAll('button'));
                    for (var label of DISCARD_LABELS) {
                        var btn = btns.find(function(b) {
                            return b.textContent.trim() === label && b.offsetParent !== null;
                        });
                        if (btn) { btn.click(); return {found: true, label: label}; }
                    }
                    var hasText = container.innerText && container.innerText.length > 20;
                    if (hasText) {
                        for (var cl of CLOSE_LABELS) {
                            var cb = btns.find(function(b) {
                                return b.textContent.trim() === cl && b.offsetParent !== null;
                            });
                            if (cb) { cb.click(); return {found: true, label: cl}; }
                        }
                    }
                }
            }
            return {found: false, label: ''};
        }
    """
    try:
        res = await page.evaluate(_JS)
    except Exception as e:
        log.error(f"[blockers] dismiss_restore_popup JS 실패: {e}")
        return {"ok": False, "action": "error", "detail": str(e)}

    if res["found"]:
        await page.wait_for_timeout(1200)
        log.info(f"[blockers] restore popup dismissed: '{res['label']}'")
        return {"ok": True, "action": "dismissed", "detail": res["label"]}

    log.debug("[blockers] restore popup: 없음 (정상)")
    return {"ok": True, "action": "no_popup", "detail": ""}


# ==================================================================
# 2. dismiss_help_panel
# ==================================================================

async def dismiss_help_panel(page) -> dict:
    """
    SmartEditor 우측 도움말 패널을 숨긴다.

    시도 순서:
      A. 닫기 버튼(.help_close, [aria-label="닫기"]) 클릭
      B. container__HW 클래스 요소 display:none 강제 적용
      C. A·B 모두 해당 요소 없으면 no_panel 반환

    Returns:
        {"ok": True,  "action": "closed",    "detail": "닫기 버튼 클릭"}
        {"ok": True,  "action": "hidden",    "detail": "display:none 적용"}
        {"ok": True,  "action": "no_panel",  "detail": ""}
        {"ok": False, "action": "error",     "detail": "<예외 메시지>"}
    """
    _JS = """
        () => {
            var closeBtn = document.querySelector(
                '.help_close, [aria-label="닫기"], button.ico_close'
            );
            if (!closeBtn) {
                closeBtn = Array.from(document.querySelectorAll('button')).find(function(b) {
                    return !!b.closest('.help_panel, .se-help-panel, [class*="help"]');
                });
            }
            if (closeBtn) {
                closeBtn.click();
                return {action: 'closed', detail: '닫기 버튼 클릭'};
            }

            var panel = document.querySelector(
                '[class*="container__HW"], [class*="helpContainer"], .se-help-panel'
            );
            if (panel) {
                panel.style.display = 'none';
                return {action: 'hidden', detail: 'display:none 적용'};
            }

            return {action: 'no_panel', detail: ''};
        }
    """
    try:
        res = await page.evaluate(_JS)
    except Exception as e:
        log.error(f"[blockers] dismiss_help_panel JS 실패: {e}")
        return {"ok": False, "action": "error", "detail": str(e)}

    if res["action"] == "no_panel":
        log.debug("[blockers] help panel: 없음")
    else:
        await page.wait_for_timeout(300)
        log.info(f"[blockers] help panel {res['action']}: {res['detail']}")

    return {"ok": True, "action": res["action"], "detail": res["detail"]}


# ==================================================================
# 3. clear_publish_blockers
# ==================================================================

async def clear_publish_blockers(page) -> dict:
    """
    발행 confirm 버튼 클릭 직전, 버튼 위를 덮는 요소를 제거한다.

    NOTE: dismiss_help_panel 을 재호출하지 않는다.
    publish 패널이 열린 상태에서 재호출하면 패널 닫기 버튼을 클릭해
    publish 패널 자체가 닫힌다.

    Returns:
        {"ok": True,  "action": "cleared",  "detail": "<제거된 요소 목록>"}
        {"ok": True,  "action": "clean",    "detail": "방해 요소 없음"}
        {"ok": False, "action": "error",    "detail": "<예외 메시지>"}
    """
    _JS = """
        () => {
            var removed = [];

            var confirmBtn = Array.from(document.querySelectorAll('button')).find(function(b) {
                var cls = b.className;
                var r = b.getBoundingClientRect();
                return r.width > 0 && r.height > 0
                    && (cls.includes('confirm_btn') || cls.includes('confirmBtn'))
                    && !cls.includes('publish_btn__');
            });

            if (confirmBtn) {
                var r = confirmBtn.getBoundingClientRect();
                var cx = r.left + r.width / 2;
                var cy = r.top  + r.height / 2;

                var topEl = document.elementFromPoint(cx, cy);
                if (topEl && topEl !== confirmBtn && !confirmBtn.contains(topEl)
                        && !topEl.contains(confirmBtn)) {
                    var info = (topEl.className || topEl.tagName || '').substring(0, 60);
                    topEl.style.display = 'none';
                    removed.push('topEl:' + info);
                }
            }

            var overlaySelectors = [
                '[class*="container__HW"]',
                '[class*="helpContainer"]',
                '.se-help-panel',
                '[class*="modal_dimmed"]',
                '[class*="dimmed"]',
                '[class*="layer_mask"]',
                '.toast_area',
            ];

            overlaySelectors.forEach(function(sel) {
                var els = Array.from(document.querySelectorAll(sel));
                els.forEach(function(el) {
                    if (confirmBtn && (el.contains(confirmBtn) || confirmBtn.contains(el))) return;
                    var style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return;
                    var er = el.getBoundingClientRect();
                    if (er.width > 0 || er.height > 0) {
                        el.style.display = 'none';
                        removed.push(sel + ':' + (el.className || '').substring(0, 40));
                    }
                });
            });

            return removed;
        }
    """
    try:
        removed = await page.evaluate(_JS)
    except Exception as e:
        log.error(f"[blockers] clear_publish_blockers JS 실패: {e}")
        return {"ok": False, "action": "error", "detail": str(e)}

    if removed:
        detail = ", ".join(removed)
        log.info(f"[blockers] publish blockers 제거 ({len(removed)}개): {detail}")
        await page.wait_for_timeout(200)
        return {"ok": True, "action": "cleared", "detail": detail}

    log.debug("[blockers] publish blockers: 없음")
    return {"ok": True, "action": "clean", "detail": "방해 요소 없음"}
