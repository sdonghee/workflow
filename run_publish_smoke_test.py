"""
run_publish_smoke_test.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
목적: 실제 발행 없이 Naver 블로그 발행 UI 각 단계를 검증
      어느 단계에서 막히는지 스크린샷·로그로 확인

실행:
  python run_publish_smoke_test.py            # 기본 (info 블로그)
  python run_publish_smoke_test.py --blog travel

성공 기준:
  STEP 1~7 모두 PASS → 발행 UI 흐름 정상
  어느 단계든 FAIL → 해당 단계 스크린샷 + 이유 출력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime

from playwright.async_api import async_playwright

# ── config 로드 (workflow/ 루트 기준)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import BLOGS

# ── 로깅
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("smoke")

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots", "smoke")


# ══════════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════════

def _load_cookies(cookie_file: str):
    if not os.path.exists(cookie_file):
        return None
    with open(cookie_file, encoding="utf-8") as f:
        data = f.read().strip()
    return json.loads(data) if data else None


async def _shot(page, name: str, run_id: str):
    """스크린샷을 screenshots/smoke/{run_id}/{name}.png 에 저장"""
    dirpath = os.path.join(SCREENSHOT_DIR, run_id)
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, f"{name}.png")
    try:
        await page.screenshot(path=path)
        log.info(f"  [screenshot] {path}")
    except Exception as e:
        log.warning(f"  스크린샷 실패 ({name}): {e}")


def _pass(step: str):
    log.info(f"  [PASS] PASS  {step}")


def _fail(step: str, reason: str):
    log.error(f"  [FAIL] FAIL  {step} -- {reason}")


# ══════════════════════════════════════════════════════════
# 메인 스모크 테스트
# ══════════════════════════════════════════════════════════

async def run_smoke(blog_key: str) -> bool:
    blog_cfg = BLOGS.get(blog_key)
    if not blog_cfg:
        log.error(f"알 수 없는 블로그 키: {blog_key}  (가능: {list(BLOGS.keys())})")
        return False

    blog_id     = blog_cfg["blog_id"]
    naver_id    = blog_cfg["naver_id"]
    cookie_file = blog_cfg["cookie_file"]
    write_url   = f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"

    run_id  = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{blog_key}"
    results = {}

    log.info("=" * 60)
    log.info(f"Naver 발행 UI 스모크 테스트")
    log.info(f"  블로그: {blog_cfg['name']}  ({blog_id})")
    log.info(f"  쿠키  : {cookie_file}")
    log.info(f"  스크린: screenshots/smoke/{run_id}/")
    log.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await context.new_page()

        # beforeunload 다이얼로그 자동 허용 (페이지 이탈 시 차단 방지)
        page.on("dialog", lambda d: asyncio.ensure_future(
            d.accept() if d.type == "beforeunload" else d.dismiss()
        ))

        # ── STEP 1: 쿠키 로드 및 로그인 확인 ─────────────────────────
        step = "STEP 1 | 쿠키 로그인 확인"
        log.info(f"\n{step}")

        cookies = _load_cookies(cookie_file)
        if not cookies:
            _fail(step, f"쿠키 파일 없음: {cookie_file}")
            results[1] = False
            await browser.close()
            return False

        await context.add_cookies(cookies)
        log.info(f"  쿠키 {len(cookies)}개 로드 완료")

        await page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)

        content = await page.content()
        login_ok = naver_id.lower() in content.lower() or "로그아웃" in content
        await _shot(page, "01_naver_home", run_id)

        if login_ok:
            _pass(step)
            results[1] = True
        else:
            _fail(step, f"로그인 상태 미확인 -- 쿠키 만료 가능성 (ID: {naver_id})")
            results[1] = False
            await browser.close()
            return False

        # ── STEP 2: 글쓰기 페이지 진입 ────────────────────────────────
        step = "STEP 2 | 글쓰기 페이지 진입"
        log.info(f"\n{step}")
        log.info(f"  → {write_url}")

        await page.goto(write_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(8000)   # SmartEditor 초기화 대기

        current_url = page.url
        log.info(f"  현재 URL: {current_url}")

        # 로그인 페이지로 튕겼는지 확인
        if "nidlogin" in current_url or "login" in current_url.lower():
            _fail(step, f"로그인 페이지 리다이렉트: {current_url}")
            results[2] = False
            await _shot(page, "02_FAIL_login_redirect", run_id)
            await browser.close()
            return False

        # SmartEditor 로드 확인
        editor_ok = await page.evaluate("""
            () => !!(
                document.querySelector('.se-title-text') ||
                document.querySelector('.se-placeholder') ||
                document.querySelector('[class*="se-title"]')
            )
        """)
        await _shot(page, "02_write_page", run_id)

        if editor_ok:
            _pass(step)
            results[2] = True
        else:
            _fail(step, "SmartEditor 요소를 찾지 못함 (.se-title-text / .se-placeholder)")
            results[2] = False
            await browser.close()
            return False

        # ── STEP 3: 작성 중인 글 팝업 제거 ───────────────────────────
        step = "STEP 3 | 작성 중인 글 팝업 제거"
        log.info(f"\n{step}")

        popup_result = await page.evaluate("""
            () => {
                var LABELS = ['새 글 쓰기', '새글 쓰기', '새 글쓰기', '취소', '닫기'];
                var btns = Array.from(document.querySelectorAll('button'));
                for (var label of LABELS) {
                    var btn = btns.find(b =>
                        b.textContent.trim() === label && b.offsetParent !== null
                    );
                    if (btn) { btn.click(); return 'dismissed:' + label; }
                }
                return 'no_popup';
            }
        """)

        log.info(f"  팝업 결과: {popup_result}")
        if popup_result.startswith("dismissed"):
            await page.wait_for_timeout(1500)
        await _shot(page, "03_after_popup", run_id)

        # 팝업이 없어도 PASS (팝업 자체가 없을 수 있음)
        _pass(step)
        results[3] = True

        # ── STEP 4: 도움말 패널 제거 ──────────────────────────────────
        step = "STEP 4 | 도움말 패널 제거"
        log.info(f"\n{step}")

        help_result = await page.evaluate("""
            () => {
                // container__HW_tc (도움말 컨테이너) 숨기기
                var help = document.querySelector('[class*="container__HW"]');
                if (help) { help.style.display = 'none'; return 'hidden'; }
                // 닫기 버튼 시도
                var close = document.querySelector('.help_close, [aria-label="닫기"]');
                if (close) { close.click(); return 'closed'; }
                return 'no_panel';
            }
        """)

        log.info(f"  도움말 결과: {help_result}")
        await _shot(page, "04_after_help_panel", run_id)
        _pass(step)
        results[4] = True

        # ── STEP 5: 1차 발행 버튼 찾기 ───────────────────────────────
        step = "STEP 5 | 1차 발행 버튼 (패널 열기) 찾기"
        log.info(f"\n{step}")

        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(300)

        btn_info = await page.evaluate("""
            () => {
                // publish_btn__m9KHH 같은 실제 <button> 탐색 (컨테이너 div 제외)
                var btn = Array.from(document.querySelectorAll('button[class*="publish_btn"]'))
                    .find(b =>
                        !b.className.includes('publish_btn_area') &&
                        b.getBoundingClientRect().width > 0
                    );
                // 텍스트 기반 폴백
                if (!btn) {
                    btn = Array.from(document.querySelectorAll('button'))
                        .find(b =>
                            b.textContent.trim() === '발행' &&
                            b.getBoundingClientRect().width > 0
                        );
                }
                if (!btn) return null;
                var r = btn.getBoundingClientRect();
                return {
                    cls  : btn.className.substring(0, 80),
                    text : btn.textContent.trim(),
                    x    : Math.round(r.x),
                    y    : Math.round(r.y),
                    w    : Math.round(r.width),
                    h    : Math.round(r.height),
                };
            }
        """)

        await _shot(page, "05_before_publish_btn", run_id)

        if btn_info:
            log.info(f"  버튼 발견: cls={btn_info['cls']}")
            log.info(f"  위치: ({btn_info['x']}, {btn_info['y']}) / 크기: {btn_info['w']}×{btn_info['h']}")
            _pass(step)
            results[5] = True
        else:
            _fail(step, "publish_btn 클래스 버튼을 DOM에서 찾지 못함")
            results[5] = False
            await browser.close()
            return False

        # ── STEP 6: 발행 패널 열기 + 최종 confirm 버튼 찾기 ──────────
        step = "STEP 6 | 발행 패널 열기 및 confirm 버튼 찾기"
        log.info(f"\n{step}")

        # 1차 버튼 JS 클릭 (패널 열기)
        open_cls = await page.evaluate("""
            () => {
                var btn = Array.from(document.querySelectorAll('button[class*="publish_btn"]'))
                    .find(b =>
                        !b.className.includes('publish_btn_area') &&
                        b.getBoundingClientRect().width > 0
                    );
                if (!btn) {
                    btn = Array.from(document.querySelectorAll('button'))
                        .find(b => b.textContent.trim() === '발행' &&
                                   b.getBoundingClientRect().width > 0);
                }
                if (btn) { btn.click(); return btn.className; }
                return null;
            }
        """)

        if not open_cls:
            _fail(step, "1차 발행 버튼 클릭 실패")
            results[6] = False
            await _shot(page, "06_FAIL_panel_open", run_id)
            await browser.close()
            return False

        log.info(f"  1차 버튼 클릭: {open_cls[:60]}")
        await page.wait_for_timeout(2500)   # 패널 애니메이션 완료

        # 도움말 패널 재제거 (패널 열린 후 다시 나타날 수 있음)
        await page.evaluate("""
            () => {
                var help = document.querySelector('[class*="container__HW"]');
                if (help) help.style.display = 'none';
            }
        """)
        await _shot(page, "06_panel_open", run_id)

        # 패널 안의 가시 버튼 목록 로깅
        panel_btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button'))
                .filter(b => b.getBoundingClientRect().width > 0)
                .map(b => ({
                    text: b.textContent.trim().substring(0, 20),
                    cls : b.className.substring(0, 60),
                    inPanel: !!b.closest('[class*="publish_btn_area"]'),
                }))
        """)
        log.info(f"  현재 가시 버튼 ({len(panel_btns)}개):")
        for b in panel_btns:
            marker = " ← 패널" if b["inPanel"] else ""
            log.info(f"    [{b['text'][:15]:15s}] {b['cls'][:50]}{marker}")

        # confirm_btn 탐색
        confirm_info = await page.evaluate("""
            () => {
                // confirm_btn__WEaBq 같은 확인 버튼
                var btn = Array.from(document.querySelectorAll('button'))
                    .find(b => {
                        var cls = b.className;
                        var r   = b.getBoundingClientRect();
                        return r.width > 0 && r.height > 0
                            && (cls.includes('confirm_btn') || cls.includes('confirmBtn'))
                            && !cls.includes('publish_btn__');
                    });
                // 텍스트 '발행' + 패널 안에 있는 버튼 폴백
                if (!btn) {
                    btn = Array.from(document.querySelectorAll('button'))
                        .find(b => {
                            var r = b.getBoundingClientRect();
                            return b.textContent.trim() === '발행'
                                && !b.className.includes('publish_btn__')
                                && !b.className.includes('fold')
                                && r.width >= 30 && r.height >= 20;
                        });
                }
                if (!btn) return null;
                var r = btn.getBoundingClientRect();
                return {
                    cls  : btn.className.substring(0, 80),
                    text : btn.textContent.trim(),
                    x    : Math.round(r.x),
                    y    : Math.round(r.y),
                    w    : Math.round(r.width),
                    h    : Math.round(r.height),
                };
            }
        """)

        if confirm_info:
            log.info(f"  [found] confirm 버튼 발견: cls={confirm_info['cls']}")
            log.info(f"    위치: ({confirm_info['x']}, {confirm_info['y']}) / 크기: {confirm_info['w']}×{confirm_info['h']}")
            _pass(step)
            results[6] = True
        else:
            _fail(step, "confirm_btn 클래스 버튼을 패널에서 찾지 못함")
            results[6] = False
            await _shot(page, "06_FAIL_confirm_not_found", run_id)
            await browser.close()
            return False

        # ── STEP 7: URL 변화 기록 (confirm 버튼 클릭 없이 현재 상태만) ──
        step = "STEP 7 | 현재 URL 상태 및 최종 스크린샷"
        log.info(f"\n{step}")

        url_before = page.url
        log.info(f"  현재 URL: {url_before}")
        log.info("  [warn] confirm 버튼을 클릭하지 않습니다 (smoke test -- 실제 발행 없음)")

        await _shot(page, "07_final_state", run_id)
        _pass(step)
        results[7] = True

        await browser.close()

    # ── 결과 요약 ─────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("스모크 테스트 결과 요약")
    log.info("=" * 60)
    steps = {
        1: "쿠키 로그인 확인",
        2: "글쓰기 페이지 진입",
        3: "작성 중인 글 팝업 제거",
        4: "도움말 패널 제거",
        5: "1차 발행 버튼 찾기",
        6: "발행 패널 + confirm 버튼",
        7: "URL 상태 기록",
    }
    all_pass = True
    for n, label in steps.items():
        ok = results.get(n, False)
        mark = "[PASS] PASS" if ok else "[FAIL] FAIL"
        log.info(f"  {mark}  STEP {n}: {label}")
        if not ok:
            all_pass = False

    log.info("=" * 60)
    log.info(f"스크린샷 위치: screenshots/smoke/{run_id}/")
    if all_pass:
        log.info("[OK] 전체 PASS -- 발행 UI 흐름 정상 확인")
    else:
        first_fail = next((n for n, ok in results.items() if not ok), "?")
        log.error(f"[ERR] FAIL -- STEP {first_fail}에서 중단")
    log.info("=" * 60)

    return all_pass


# ══════════════════════════════════════════════════════════
# 진입점
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Naver 발행 UI 스모크 테스트")
    parser.add_argument(
        "--blog",
        default="info",
        choices=list(BLOGS.keys()),
        help=f"테스트할 블로그 키 (기본: info)",
    )
    args = parser.parse_args()

    ok = asyncio.run(run_smoke(args.blog))
    sys.exit(0 if ok else 1)
