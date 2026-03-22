"""
최초 1회 수동 로그인 스크립트
────────────────────────────────────────────────
이 파일은 처음 딱 한 번만 실행합니다.
브라우저 창이 열리면 직접 네이버에 로그인하세요.
로그인 완료 후 Enter를 누르면 쿠키가 저장됩니다.
이후부터는 자동으로 쿠키를 사용해서 로그인합니다.
────────────────────────────────────────────────
"""
import asyncio
import json
from playwright.async_api import async_playwright
from config import NAVER_BLOG_ID

COOKIE_FILE = "naver_cookies.json"


async def manual_login():
    print("=" * 50)
    print("  네이버 최초 로그인 설정")
    print("=" * 50)
    print()
    print("잠시 후 브라우저 창이 열립니다.")
    print("네이버에 직접 로그인해 주세요.")
    print("로그인 완료 후 이 창으로 돌아와서 Enter를 누르세요.")
    print()

    async with async_playwright() as p:
        # 화면이 보이는 브라우저로 실행
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--start-maximized"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = await context.new_page()

        # 네이버 로그인 페이지 열기
        await page.goto("https://nid.naver.com/nidlogin.login")
        print("✅ 브라우저가 열렸습니다. 로그인해 주세요.")
        print()

        # 사용자가 로그인할 때까지 대기
        input("로그인 완료 후 여기서 Enter를 누르세요...")

        # 로그인 확인
        await page.goto("https://www.naver.com")
        await page.wait_for_timeout(2000)

        content = await page.content()
        if "로그아웃" in content or "내정보" in content:
            # 쿠키 저장
            cookies = await context.cookies()
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)

            print()
            print("=" * 50)
            print("✅ 로그인 성공! 쿠키가 저장되었습니다.")
            print(f"   저장 위치: {COOKIE_FILE}")
            print()
            print("이제 자동 포스팅을 시작할 수 있습니다!")
            print("  테스트: python scheduler.py --test")
            print("  즉시실행: python scheduler.py --now")
            print("  자동실행: python scheduler.py")
            print("=" * 50)
        else:
            print()
            print("❌ 로그인이 확인되지 않습니다.")
            print("   다시 시도해 주세요: python first_login.py")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(manual_login())
