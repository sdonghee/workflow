"""
최초 1회 수동 로그인 스크립트
────────────────────────────────────────────────
이 파일은 각 블로그 계정마다 처음 딱 한 번 실행합니다.
브라우저 창이 열리면 직접 네이버에 로그인하세요.
로그인 완료 후 Enter를 누르면 쿠키가 저장됩니다.
이후부터는 자동으로 쿠키를 사용해서 로그인합니다.
────────────────────────────────────────────────
"""
import asyncio
import json
import argparse
from playwright.async_api import async_playwright
from config import BLOGS


async def manual_login(blog_config):
    blog_name = blog_config["name"]
    cookie_file = blog_config["cookie_file"]

    print("=" * 50)
    print(f"  [{blog_name}] 네이버 최초 로그인")
    print("=" * 50)
    print()
    print(f"계정 ID: {blog_config['naver_id']}")
    print("잠시 후 브라우저 창이 열립니다.")
    print("네이버에 직접 로그인해 주세요.")
    print("로그인 완료 후 이 창으로 돌아와서 Enter를 누르세요.")
    print()

    async with async_playwright() as p:
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

        await page.goto("https://nid.naver.com/nidlogin.login")
        print("✅ 브라우저가 열렸습니다. 로그인해 주세요.")
        print()

        input("로그인 완료 후 여기서 Enter를 누르세요...")

        await page.goto("https://www.naver.com")
        await page.wait_for_timeout(2000)

        content = await page.content()
        naver_id = blog_config["naver_id"].lower()
        if "로그아웃" in content or "내정보" in content or naver_id in content.lower():
            cookies = await context.cookies()
            with open(cookie_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)

            print()
            print("=" * 50)
            print(f"✅ [{blog_name}] 로그인 성공! 쿠키 저장 완료.")
            print(f"   저장 위치: {cookie_file}")
            print("=" * 50)
            result = True
        else:
            print()
            print(f"❌ [{blog_name}] 로그인이 확인되지 않습니다.")
            result = False

        await browser.close()
        return result


async def run_all_logins(target_blog=None):
    """모든 블로그(또는 특정 블로그)에 대해 순서대로 로그인"""
    blogs_to_login = {}

    if target_blog:
        if target_blog in BLOGS:
            blogs_to_login = {target_blog: BLOGS[target_blog]}
        else:
            print(f"❌ 블로그 키 '{target_blog}' 를 찾을 수 없습니다.")
            print(f"   사용 가능한 블로그: {', '.join(BLOGS.keys())}")
            return
    else:
        blogs_to_login = BLOGS

    print(f"\n총 {len(blogs_to_login)}개 블로그 로그인을 진행합니다.\n")

    for blog_key, blog_config in blogs_to_login.items():
        if not blog_config.get("naver_id"):
            print(f"⚠️  [{blog_config['name']}] .env에 {blog_key.upper()} 계정 설정이 없습니다. 스킵.")
            continue

        success = await manual_login(blog_config)
        if not success:
            print(f"   다시 시도: python first_login.py --blog {blog_key}")

        if len(blogs_to_login) > 1:
            print("\n다음 블로그 로그인을 진행합니다...")
            print()

    print("\n모든 로그인 완료!")
    print("  테스트: python scheduler.py --test")
    print("  즉시실행: python scheduler.py --now")
    print("  자동실행: python scheduler.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 블로그 최초 로그인")
    parser.add_argument(
        "--blog",
        type=str,
        help=f"특정 블로그만 로그인. 선택 가능: {', '.join(BLOGS.keys())}",
    )
    args = parser.parse_args()

    asyncio.run(run_all_logins(args.blog))
