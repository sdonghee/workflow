"""
runners/run_image_upload_test.py
------------------------------------------------------------------
이미지 업로드 단독 검증 스크립트.
confirm 버튼 클릭 없음 — 업로드 성공 여부만 확인.

실행:
  python runners/run_image_upload_test.py --blog info

성공 기준:
  - #hidden-file set_input_files 성공
  - 에디터 내 blogfiles.naver.net 이미지 count 증가 확인
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
from naver_blog import navigator
from naver_blog.blockers import dismiss_restore_popup, dismiss_help_panel
from poster.image_downloader import download
from poster.image_uploader import upload_image, _editor_image_count

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("image_upload_test")

# 테스트용 이미지 URL (Unsplash 안정적 URL)
_TEST_IMAGE_URL = "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&q=80"

_SHOT_DIR = os.path.join(_ROOT, "screenshots", "image_upload_test")


async def _shot(page, step: str, run_id: str):
    dirpath = os.path.join(_SHOT_DIR, run_id)
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, f"{step}.png")
    try:
        await page.screenshot(path=path)
        log.info(f"  [shot] {path}")
    except Exception as e:
        log.warning(f"  [shot] 실패: {e}")


async def run_test(blog_key: str) -> bool:
    blog_cfg = BLOGS.get(blog_key)
    if not blog_cfg:
        log.error(f"blog_key '{blog_key}' 없음")
        return False

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{blog_key}"
    results = {}

    async with async_playwright() as p:
        browser, context, page = await session_manager.build_context(p)
        try:
            # STEP 1: 로그인
            log.info("\n[STEP 1] 쿠키 로그인")
            ok = await session_manager.login_with_cookies(
                context, page, blog_cfg["cookie_file"], blog_cfg["naver_id"]
            )
            results["step1_login"] = ok
            if not ok:
                log.error("  로그인 실패")
                return False
            log.info("  [PASS] 로그인")

            # STEP 2: 글쓰기 페이지
            log.info("\n[STEP 2] 글쓰기 페이지 + SmartEditor")
            ok = await navigator.go_to_write_page(page, blog_cfg["blog_id"])
            if ok:
                ok = await navigator.wait_for_editor(page)
            results["step2_editor"] = ok
            if not ok:
                log.error("  SmartEditor 로드 실패")
                return False
            log.info("  [PASS] SmartEditor 로드")
            await _shot(page, "step2_write_page", run_id)

            # STEP 3: blockers
            log.info("\n[STEP 3] blockers 제거")
            await dismiss_restore_popup(page)
            await dismiss_help_panel(page)
            await page.wait_for_timeout(800)
            log.info("  [PASS] blockers 제거")

            # STEP 4: 제목 + 본문 입력 (업로드 전 커서 위치 확보)
            log.info("\n[STEP 4] 제목 + 본문 입력")
            await page.locator(".se-title-text").first.click(timeout=5000)
            await page.keyboard.type("이미지 업로드 테스트", delay=30)
            await page.wait_for_timeout(500)

            await page.locator(".se-placeholder").first.click(timeout=5000)
            await page.wait_for_timeout(300)
            await page.keyboard.type("이미지 업로드 테스트 본문입니다.", delay=30)
            await page.wait_for_timeout(500)
            log.info("  [PASS] 텍스트 입력")
            await _shot(page, "step4_text_input", run_id)

            # STEP 5: 이미지 다운로드
            log.info(f"\n[STEP 5] 이미지 다운로드: {_TEST_IMAGE_URL[:60]}")
            local_path = download(_TEST_IMAGE_URL)
            results["step5_download"] = bool(local_path)
            if not local_path:
                log.error("  [FAIL] 다운로드 실패")
                return False
            log.info(f"  [PASS] 다운로드: {local_path.name} ({local_path.stat().st_size // 1024}KB)")

            # STEP 6: SmartEditor 업로드
            log.info("\n[STEP 6] SmartEditor 이미지 업로드")
            before = await _editor_image_count(page)
            log.info(f"  업로드 전 에디터 이미지: {before}개")

            ok = await upload_image(page, local_path)
            results["step6_upload"] = ok

            after = await _editor_image_count(page)
            log.info(f"  업로드 후 에디터 이미지: {after}개")

            if ok:
                log.info("  [PASS] 이미지 업로드 성공 (blogfiles 이미지 에디터 삽입 확인)")
            else:
                log.error("  [FAIL] 이미지 업로드 실패")

            await _shot(page, "step6_after_upload", run_id)

            # STEP 7: 에디터 내 이미지 src 확인
            log.info("\n[STEP 7] 에디터 이미지 src 확인")
            await page.wait_for_timeout(500)  # 렌더링 완료 대기
            img_srcs = await page.evaluate("""
                () => Array.from(
                    document.querySelectorAll('.se-main-container img, [class*="se-image"] img')
                ).map(img => img.src)
            """)
            for src in img_srcs:
                is_blog = "blogfiles" in src
                log.info(f"  {'[blogfiles]' if is_blog else '[external]'} {src[:80]}")
            results["step7_blogfiles"] = any("blogfiles" in s for s in img_srcs)

            if results["step7_blogfiles"]:
                log.info("  [PASS] blogfiles.naver.net 이미지 에디터에 삽입됨")
            else:
                log.error("  [FAIL] blogfiles 이미지 없음")

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
    log.info(f"스크린샷: screenshots/image_upload_test/{run_id}/")
    log.info(f"{'='*60}")
    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog", required=True)
    args = parser.parse_args()
    ok = asyncio.run(run_test(args.blog))
    sys.exit(0 if ok else 1)
