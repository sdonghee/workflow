"""
naver_blog/editor.py
------------------------------------------------------------------
SmartEditor ONE 제목/본문 입력.

공개 API:
  enter_title(page, title)           -> bool
  enter_body_html(page, html)        -> bool
------------------------------------------------------------------
"""
import logging
import re
import sys

log = logging.getLogger(__name__)

_TITLE_SELECTORS = [
    ".se-title-text",
    ".se-title-input",
    'div[contenteditable="true"][class*="title"]',
]

_BODY_CLICK_SELECTORS = [
    ".se-content",
    "[class*='se-section-editor']",
    ".se-placeholder",
    ".se-component:not(.se-component-title)",
]

_EDITOR_LEN_JS = """
    () => {
        var eds = Array.from(document.querySelectorAll('[contenteditable="true"]'));
        var total = 0;
        for (var ed of eds) {
            if (ed.contentEditable !== 'true') continue;
            var cls = (ed.className || '').toLowerCase();
            if (cls.includes('title')) continue;
            var ph = (ed.getAttribute('data-placeholder') || '').toLowerCase();
            if (ph.includes('제목') || ph.includes('title')) continue;
            total += ed.innerText.trim().length;
        }
        return total;
    }
"""

# SmartEditor iframe 안에 직접 HTML 주입
# execCommand('insertHTML')는 포커스된 contenteditable 또는 iframe body에 작동함
_INJECT_HTML_JS = """
    (html) => {
        // 1. .se-content 또는 editor 관련 iframe 탐색
        var iframeSelectors = [
            '.se-content iframe',
            '[class*="se-"] iframe',
            'iframe[id*="ir"]',
            'iframe[id*="editor"]',
            'iframe[id*="smart"]',
        ];
        var iframe = null;
        for (var sel of iframeSelectors) {
            iframe = document.querySelector(sel);
            if (iframe) break;
        }

        if (iframe) {
            var doc = iframe.contentDocument ||
                      (iframe.contentWindow && iframe.contentWindow.document);
            if (doc && doc.body) {
                // iframe body에 paste 이벤트 dispatch
                var dt = new DataTransfer();
                dt.setData('text/html', html);
                dt.setData('text/plain', html.replace(/<[^>]+>/g, ' '));
                var evt = new ClipboardEvent('paste', {
                    bubbles: true, cancelable: true, clipboardData: dt
                });
                iframe.contentWindow.focus();
                doc.body.focus();
                doc.body.dispatchEvent(evt);

                // paste 이벤트가 처리되지 않으면 execCommand 시도
                var len1 = (doc.body.innerText || '').trim().length;
                if (len1 < 5) {
                    doc.execCommand('insertHTML', false, html);
                }
                var len2 = (doc.body.innerText || '').trim().length;
                return 'iframe:paste+exec len=' + len2;
            }
            return 'iframe:no_doc';
        }

        // 2. iframe 없으면 page에서 직접 시도
        var editorSelectors = [
            '.se-content [contenteditable="true"]',
            '[class*="se-section"] [contenteditable="true"]',
            '[contenteditable="true"]:not([class*="title"])',
        ];
        var editor = null;
        for (var s of editorSelectors) {
            editor = document.querySelector(s);
            if (editor) break;
        }

        if (editor) {
            editor.focus();
            var dt2 = new DataTransfer();
            dt2.setData('text/html', html);
            dt2.setData('text/plain', html.replace(/<[^>]+>/g, ' '));
            var evt2 = new ClipboardEvent('paste', {
                bubbles: true, cancelable: true, clipboardData: dt2
            });
            editor.dispatchEvent(evt2);
            var len3 = (editor.innerText || '').trim().length;
            if (len3 < 5) {
                document.execCommand('insertHTML', false, html);
                len3 = (editor.innerText || '').trim().length;
            }
            // React 상태 동기화: input + change 이벤트로 React onChange 트리거
            editor.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));
            editor.dispatchEvent(new Event('change', { bubbles: true }));
            return 'page:paste+exec len=' + len3;
        }

        return 'no_editor_found';
    }
"""

_SET_CLIPBOARD_HTML_JS = """
    async (html) => {
        const blob = new Blob([html], { type: 'text/html' });
        await navigator.clipboard.write([new ClipboardItem({ 'text/html': blob })]);
    }
"""


def _set_win32_clipboard_html(html: str) -> bool:
    """Windows CF_HTML 포맷으로 시스템 클립보드에 HTML 설정."""
    try:
        import win32clipboard
    except ImportError:
        return False
    try:
        html_bytes = html.encode("utf-8")
        header_template = (
            "Version:0.9\r\n"
            "StartHTML:{start:08d}\r\n"
            "EndHTML:{end:08d}\r\n"
            "StartFragment:{start:08d}\r\n"
            "EndFragment:{end:08d}\r\n"
        )
        dummy = header_template.format(start=0, end=0)
        header_len = len(dummy.encode("utf-8"))
        end_pos = header_len + len(html_bytes)
        header = header_template.format(start=header_len, end=end_pos)
        data = header.encode("utf-8") + html_bytes

        cf = win32clipboard.RegisterClipboardFormat("HTML Format")
        win32clipboard.OpenClipboard(0)
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(cf, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        log.warning(f"[editor] win32clipboard 설정 실패: {e}")
        try:
            import win32clipboard as _wc
            _wc.CloseClipboard()
        except Exception:
            pass
        return False


async def enter_title(page, title: str) -> bool:
    """제목 입력"""
    for sel in _TITLE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.click(timeout=5000)
            await page.keyboard.press("Control+a")
            await page.keyboard.type(title, delay=40)
            log.info(f"[editor] 제목 입력 완료 ({sel}): {title[:40]}")
            return True
        except Exception:
            continue

    log.error("[editor] enter_title: 모든 selector 미매칭")
    return False


async def enter_body_html(page, html: str) -> bool:
    """
    SmartEditor 본문에 HTML 삽입.

    시도 순서:
      1. JS 직접 주입 (iframe 탐색 → paste 이벤트 + execCommand)
      2. win32clipboard CF_HTML + Ctrl+V (포커스 후)
      3. navigator.clipboard + Ctrl+V (폴백)
    """
    # ── 1. JS 직접 주입 ──────────────────────────────────────────
    # iframe 내부 주입만 React 상태를 반영할 가능성 있음.
    # page: 레벨 paste+execCommand는 DOM만 수정, React state 미반영 → 발행 시 빈 글.
    try:
        result = await page.evaluate(_INJECT_HTML_JS, html)
        log.info(f"[editor] JS 주입 결과: {result}")

        if result.startswith('iframe:') and 'len=' in result:
            injected_len = int(result.split('len=')[-1])
            if injected_len > 50:
                log.info(f"[editor] ✅ 본문 입력 완료 (JS iframe 주입, {injected_len}자)")
                return True
            log.warning(f"[editor] iframe 주입 후 len={injected_len} (≤50) → 다음 방법 시도")
        else:
            # page: 레벨 결과는 React 상태 반영 미보장 → 항상 낙하
            log.warning(f"[editor] JS 주입 React 미반영 추정 ({result}) → keyboard.type으로 낙하")
    except Exception as e:
        log.warning(f"[editor] JS 주입 예외: {e}")

    # ── 본문 포커스 (방법 2, 3 공통) ─────────────────────────────
    for sel in _BODY_CLICK_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.click(timeout=5000)
            await page.wait_for_timeout(800)
            log.info(f"[editor] 본문 포커스 ({sel})")
            break
        except Exception:
            continue
    else:
        await page.mouse.click(640, 450)
        await page.wait_for_timeout(800)
        log.warning("[editor] 본문 selector 실패 — 좌표 클릭 폴백")

    # ── 2. win32clipboard CF_HTML + Ctrl+V ────────────────────────
    # DOM은 업데이트되지만 SmartEditor React state 반영 미보장 → 항상 낙하
    if sys.platform == "win32" and _set_win32_clipboard_html(html):
        await page.wait_for_timeout(300)
        await page.keyboard.press("Control+v")
        await page.wait_for_timeout(2000)
        ed_len = await page.evaluate(_EDITOR_LEN_JS)
        log.warning(f"[editor] win32clipboard CF_HTML ed_len={ed_len} — React 미반영 추정 → keyboard.type으로 낙하")

    # ── 3. navigator.clipboard + Ctrl+V ──────────────────────────
    # DOM은 업데이트되지만 SmartEditor React state 반영 미보장 → 항상 낙하
    try:
        await page.evaluate(_SET_CLIPBOARD_HTML_JS, html)
        await page.keyboard.press("Control+v")
        await page.wait_for_timeout(1000)
        log.warning("[editor] navigator.clipboard Ctrl+V — React 미반영 추정 → keyboard.type으로 낙하")
    except Exception as e:
        log.warning(f"[editor] navigator.clipboard 실패 ({e}) → keyboard.type 시도")

    # ── 4. keyboard.type (plain text, React 상태 직접 동기화) ──────────
    plain = re.sub(r'<br\s*/?>', '\n', html)
    plain = re.sub(r'<[^>]+>', '', plain).strip()
    plain = plain[:3000]

    if not plain:
        log.error("[editor] keyboard.type: plain text 변환 결과 없음")
        return False

    # 본문 포커스 재시도
    for sel in _BODY_CLICK_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.click(timeout=5000)
            await page.wait_for_timeout(500)
            log.info(f"[editor] keyboard.type 포커스 ({sel})")
            break
        except Exception:
            continue

    await page.keyboard.press("Control+a")
    await page.wait_for_timeout(200)
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(200)

    await page.keyboard.type(plain, delay=15)
    await page.wait_for_timeout(1000)

    ed_len = await page.evaluate(_EDITOR_LEN_JS)
    if ed_len > 50:
        log.info(f"[editor] ✅ 본문 입력 완료 (keyboard.type, {ed_len}자)")
        return True

    log.error(f"[editor] keyboard.type 후 ed_len={ed_len} — 본문 입력 최종 실패")
    return False
