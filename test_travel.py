"""flighttravel (travel) 블로그 단일 포스팅 테스트"""
import asyncio
import logging
import sys
import os
sys.path.insert(0, '/home/user/workflow')
os.chdir('/home/user/workflow')

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from config import BLOGS
from naver_poster import post_to_naver_blog

TITLE = "여행 테스트 포스팅"
CONTENT = """<p>안녕하세요! 여행/항공/호텔 블로그 자동 포스팅 테스트입니다.</p>
<p>이 글은 시스템 테스트용으로 작성된 글입니다.</p>
<p>flighttravel 블로그에 정상적으로 게시되면 자동화가 작동하는 것입니다.</p>"""
TAGS = "여행,테스트,자동화"

async def main():
    blog = BLOGS["travel"]
    print(f"블로그: {blog['name']} ({blog['blog_id']})")
    print(f"제목: {TITLE}")
    result = await post_to_naver_blog(TITLE, CONTENT, TAGS, "여행_항공_호텔", blog)
    print(f"결과: {'✅ 성공' if result else '❌ 실패'}")

asyncio.run(main())
