"""
최초 1회 자동 로그인 스크립트 (headless)
────────────────────────────────────────────────
.env의 ID/PW로 자동 로그인 후 쿠키를 저장합니다.
이후 자동화에서는 저장된 쿠키를 사용합니다.
────────────────────────────────────────────────
"""
import asyncio
import json
import argparse
from playwright.async_api import async_playwright
from config import BLOGS


async def auto_login(blog_config):
    blog_name = blog_config["name"]
    naver_id  = blog_config["naver_id"]
    naver_pw  = blog_config["naver_pw"]
    cookie_file = blog_config["cookie_file"]

    print(f"\n[{blog_name}] 자동 로그인 시작 (ID: {naver_id})")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = await context.new_page()

        try:
            await page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # ID 입력 (자연스러운 타이핑으로 봇 감지 우회)
            await page.click("#id")
            await page.wait_for_timeout(500)
            for char in naver_id:
                await page.type("#id", char, delay=80)
            await page.wait_for_timeout(700)

            # PW 입력
            await page.click("#pw")
            await page.wait_for_timeout(500)
            for char in naver_pw:
                await page.type("#pw", char, delay=80)
            await page.wait_for_timeout(700)

            # 로그인 버튼
            await page.click(".btn_login")
            await page.wait_for_timeout(5000)

            current_url = page.url
            if "nidlogin" in current_url:
                print(f"❌ [{blog_name}] 로그인 실패 — 캡차 또는 계정 오류")
                print("   → Naver에서 새 기기 로그인 차단 중일 수 있습니다.")
                print("   → naver.com에서 직접 로그인 후 '이 기기 신뢰'를 선택해 주세요.")
                await browser.close()
                return False

            # 로그인 확인
            await page.goto("https://www.naver.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            content = await page.content()

            if "로그아웃" in content or naver_id.lower() in content.lower():
                cookies = await context.cookies()
                with open(cookie_file, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                print(f"✅ [{blog_name}] 로그인 성공! 쿠키 저장: {cookie_file}")
                await browser.close()
                return True
            else:
                print(f"❌ [{blog_name}] 로그인 확인 실패 (보안 문자 등)")
                await browser.close()
                return False

        except Exception as e:
            print(f"❌ [{blog_name}] 오류: {e}")
            await browser.close()
            return False


async def run_all_logins(target_blog=None):
    blogs_to_login = {}

    if target_blog:
        if target_blog in BLOGS:
            blogs_to_login = {target_blog: BLOGS[target_blog]}
        else:
            print(f"❌ 블로그 키 '{target_blog}' 를 찾을 수 없습니다.")
            print(f"   사용 가능한 블로그: {', '.join(BLOGS.keys())}")
            return
    else:
        blogs_to_login = {k: v for k, v in BLOGS.items() if v.get("naver_id")}

    print(f"\n총 {len(blogs_to_login)}개 블로그 자동 로그인을 진행합니다.")

    for blog_key, blog_config in blogs_to_login.items():
        success = await auto_login(blog_config)
        if not success:
            print(f"   재시도: python first_login.py --blog {blog_key}")

    print("\n완료!")
    print("  즉시실행: python scheduler.py --now")
    print("  자동실행: python scheduler.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 로그인 및 쿠키 저장")
    parser.add_argument("--blog", type=str, help=f"특정 블로그만: {', '.join(BLOGS.keys())}")
    args = parser.parse_args()
    asyncio.run(run_all_logins(args.blog))
