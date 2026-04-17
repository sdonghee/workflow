"""
runners/run_publish_smoke_test.py
------------------------------------------------------------------
발행 UI를 STEP 1~7까지만 검증한다. confirm 버튼은 클릭하지 않는다.

실행:
  python runners/run_publish_smoke_test.py --blog info

성공 기준:
  STEP 1~7 모두 PASS (exit 0)
  confirm 버튼 좌표를 로깅하고 종료
------------------------------------------------------------------
"""
import argparse
import asyncio
import io
import logging
import os
import sys
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from config import BLOGS
from auth import session_manager
from naver_blog import blockers, navigator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("smoke_test")

_SHOT_DIR = os.path.join(_ROOT, "screenshots", "smoke_test")


def _pass(step: str):
    log.info(f"  [PASS] {step}")


def _fail(step: str, reason: str):
    log.error(f"  [FAIL] {step}: {reason}")


async def _shot(page, name: str, run_id: str):
    dirpath = os.path.join(_SHOT_DIR, run_id)
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, f"{name}.png")
    try:
        await page.screenshot(path=path)
        log.info(f"    [shot] {path}")
    except Exception as e:
        log.warning(f"    [shot] 실패: {e}")


async def run_smoke(blog_key: str) -> bool:
    blog_cfg = BLOGS.get(blog_key)
    if not blog_cfg:
        log.error(f"blog_key '{blog_key}' 없음. 등록된 키: {list(BLOGS.keys())}")
        return False

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{blog_key}"
    results: dict[str, bool] = {}

    async with async_playwright() as p:
        browser, context, page = await session_manager.build_context(p)
        try:
            # STEP 1: 쿠키 로그인
            log.info("\n[STEP 1] 쿠키 로그인")
            ok = await session_manager.login_with_cookies(
                context, page, blog_cfg["cookie_file"], blog_cfg["naver_id"]
            )
            results["step1_login"] = ok
            _pass("쿠키 로그인") if ok else _fail("쿠키 로그인", "쿠키 만료 또는 파일 없음")
            if not ok:
                return False

            # STEP 2: 글쓰기 페이지 이동 + SmartEditor 로드
            log.info("\n[STEP 2] 글쓰기 페이지 + SmartEditor")
            ok = await navigator.go_to_write_page(page, blog_cfg["blog_id"])
            if ok:
                ok = await navigator.wait_for_editor(page)
            results["step2_editor"] = ok
            _pass("SmartEditor 로드") if ok else _fail("SmartEditor 로드", "DOM 미매칭")
            await _shot(page, "step2_write_page", run_id)
            if not ok:
                return False

            # STEP 3: restore popup 제거
            log.info("\n[STEP 3] restore popup")
            r = await blockers.dismiss_restore_popup(page)
            ok = r["ok"]
            results["step3_popup"] = ok
            _pass(f"restore popup: {r['action']}") if ok else _fail("restore popup", r["detail"])

            # STEP 4: help panel 제거
            log.info("\n[STEP 4] help panel")
            r = await blockers.dismiss_help_panel(page)
            ok = r["ok"]
            results["step4_help"] = ok
            _pass(f"help panel: {r['action']}") if ok else _fail("help panel", r["detail"])
            await _shot(page, "step4_after_blockers", run_id)

            # 에디터 visible 대기
            for sel in [".se-title-text", ".se-placeholder"]:
                try:
                    await page.locator(sel).first.wait_for(state="visible", timeout=12000)
                    break
                except Exception:
                    continue

            # STEP 5: 1차 발행 버튼(패널 열기) 탐색
            log.info("\n[STEP 5] 1차 발행 버튼 탐색")
            publish_cls = await page.evaluate("""
                () => {
                    var btn = Array.from(document.querySelectorAll('button[class*="publish_btn"]'))
                        .find(b =>
                            !b.className.includes('publish_btn_area') &&
                            b.getBoundingClientRect().width > 0
                        );
                    return btn ? btn.className : null;
                }
            """)
            ok = bool(publish_cls)
            results["step5_publish_btn"] = ok
            _pass(f"발행 버튼: {(publish_cls or '')[:50]}") if ok else _fail("발행 버튼", "DOM 없음")
            if not ok:
                await _shot(page, "step5_FAIL", run_id)
                return False

            # STEP 6: 패널 열기 + confirm 버튼 탐색
            log.info("\n[STEP 6] 발행 패널 열기 + confirm 버튼 탐색")
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(400)
            await page.evaluate("""
                () => {
                    var btn = Array.from(document.querySelectorAll('button[class*="publish_btn"]'))
                        .find(b =>
                            !b.className.includes('publish_btn_area') &&
                            b.getBoundingClientRect().width > 0
                        );
                    if (btn) btn.click();
                }
            """)
            await page.wait_for_timeout(2500)
            await _shot(page, "step6_panel_open", run_id)

            confirm_info = await page.evaluate("""
                () => {
                    var btn = Array.from(document.querySelectorAll('button')).find(function(b) {
                        var cls = b.className;
                        var r = b.getBoundingClientRect();
                        return r.width > 0 && r.height > 0
                            && (cls.includes('confirm_btn') || cls.includes('confirmBtn'))
                            && !cls.includes('publish_btn__');
                    });
                    if (!btn) return null;
                    var r = btn.getBoundingClientRect();
                    return {cls: btn.className, x: r.left, y: r.top, w: r.width, h: r.height};
                }
            """)
            ok = bool(confirm_info)
            results["step6_confirm_btn"] = ok
            if ok:
                _pass(f"confirm 버튼: {confirm_info['cls'][:50]} @ ({confirm_info['x']:.0f},{confirm_info['y']:.0f})")
            else:
                _fail("confirm 버튼", "DOM 없음")
            if not ok:
                return False

            # STEP 7: clear_publish_blockers 확인 (클릭 없이)
            log.info("\n[STEP 7] clear_publish_blockers 확인")
            r = await blockers.clear_publish_blockers(page)
            ok = r["ok"]
            results["step7_blockers"] = ok
            _pass(f"blockers: {r['action']} / {r['detail'][:60]}") if ok else _fail("blockers", r["detail"])
            await _shot(page, "step7_ready_to_confirm", run_id)

            log.info(f"\n  현재 URL: {page.url}")
            log.info("  confirm 버튼 클릭하지 않고 종료 (smoke test)")

        except Exception as e:
            log.error(f"[!] 예외: {e}", exc_info=True)
            await _shot(page, "99_exception", run_id)
            return False
        finally:
            await browser.close()

    passed = sum(1 for v in results.values() if v)
    total  = len(results)
    log.info(f"\n{'='*60}")
    log.info(f"결과: {passed}/{total} PASS")
    for k, v in results.items():
        log.info(f"  {'PASS' if v else 'FAIL'}  {k}")
    log.info(f"{'='*60}")
    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Naver 발행 UI smoke test")
    parser.add_argument("--blog", required=True, help="BLOGS 딕셔너리 키 (예: info)")
    args = parser.parse_args()

    ok = asyncio.run(run_smoke(args.blog))
    sys.exit(0 if ok else 1)
