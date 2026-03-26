"""빠른 테스트 포스팅 - AI 생성 없이 고정 내용으로 바로 포스팅"""
import asyncio
from config import BLOGS
from naver_poster import post_to_naver_blog

TITLE = "테스트 포스팅입니다"
CONTENT = """<p>안녕하세요! 자동 포스팅 테스트입니다.</p>
<p>이 글은 시스템 테스트용으로 작성된 글입니다.</p>
<p>정상적으로 보이면 자동화가 잘 작동하고 있는 것입니다.</p>"""
TAGS = "테스트,자동화"

async def main():
    blog = list(BLOGS.values())[0]
    print(f"블로그: {blog['name']} ({blog['blog_id']})")
    print(f"제목: {TITLE}")
    result = await post_to_naver_blog(TITLE, CONTENT, TAGS, "", blog)
    print(f"결과: {'✅ 성공' if result else '❌ 실패'}")

asyncio.run(main())
