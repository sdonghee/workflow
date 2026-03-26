"""
실제 블로그 포스팅 테스트
Research → Content → Image → Structure → Naver 발행
사용법: python test_full_pipeline.py [travel|info]
"""
import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, '/app')
os.chdir('/app')

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("test_pipeline")

from config import BLOGS, CATEGORIES
from agents.research_agent import ResearchAgent
from agents.content_agent import ContentAgent
from agents.image_agent import ImageAgent
from agents.structure_agent import StructureAgent
from naver_poster import post_to_naver_blog

# ── 블로그 선택 ──────────────────────────────────────────────────
blog_key = sys.argv[1] if len(sys.argv) > 1 else "travel"
blog_cfg = BLOGS.get(blog_key)
if not blog_cfg:
    print(f"❌ 알 수 없는 블로그 키: {blog_key}. 사용 가능: {list(BLOGS.keys())}")
    sys.exit(1)

category = blog_cfg["categories"][0]
logger.info(f"블로그: {blog_cfg['name']} / 카테고리: {category}")

# ── Step 1: ResearchAgent - 실제 기사 수집 ───────────────────────
logger.info("\n" + "="*55)
logger.info("[1/4] ResearchAgent — RSS + 웹 기사 수집")
logger.info("="*55)

research = ResearchAgent()
articles = research.get_articles(category, max_count=3)

if articles:
    article = articles[0]
    logger.info(f"  수집된 기사 수: {len(articles)}")
    logger.info(f"  선택 기사: {article.get('title', '')[:70]}")
    logger.info(f"  출처: {article.get('source', '')} | {article.get('link', '')[:60]}")
else:
    logger.warning("  기사 수집 실패 → 주제 기반 생성")
    article = {
        "title": f"오늘의 {category} 트렌드",
        "summary": f"{category} 분야의 최신 정보와 유용한 팁",
        "link": "",
        "content": ""
    }

# ── Step 2: ContentAgent - AI 콘텐츠 생성 ───────────────────────
logger.info("\n" + "="*55)
logger.info("[2/4] ContentAgent — AI 블로그 콘텐츠 작성")
logger.info("="*55)

content_agent = ContentAgent()
content_data = content_agent.generate(article, category)

if not content_data:
    logger.error("❌ 콘텐츠 생성 실패")
    sys.exit(1)

title = content_data.get("title", article["title"])
logger.info(f"  제목: {title[:70]}")
logger.info(f"  섹션 수: {len(content_data.get('sections', []))}")
logger.info(f"  태그(KO): {', '.join(content_data.get('tags_ko', [])[:5])}...")

# ── Step 3: ImageAgent - 이미지 검색 ────────────────────────────
logger.info("\n" + "="*55)
logger.info("[3/4] ImageAgent — Unsplash/Pexels 이미지 검색")
logger.info("="*55)

image_agent = ImageAgent()
img_url, img_alt, photographer = image_agent.get_image(title, category)

logger.info(f"  이미지: {img_url[:80]}")
logger.info(f"  출처: {photographer}")

# ── Step 4: StructureAgent - HTML 구성 ──────────────────────────
logger.info("\n" + "="*55)
logger.info("[4/4] StructureAgent — 네이버 최적화 HTML 생성")
logger.info("="*55)

structure_agent = StructureAgent()
post_data = structure_agent.format_html(
    content_data,
    image_url=img_url,
    image_alt=img_alt,
    article_link=article.get("link", ""),
)

if not post_data:
    logger.error("❌ HTML 구성 실패")
    sys.exit(1)

final_title   = post_data.get("title") or title
content_html  = post_data.get("content_html", "")
tags          = post_data.get("tags", "")

# 포토그래퍼 크레딧 추가
if photographer:
    content_html += (
        f'\n<p style="font-size:12px;color:#aaa;text-align:right;'
        f"font-family:'Nanum Gothic','맑은 고딕',sans-serif;margin-top:8px;\">"
        f"{photographer}</p>"
    )

logger.info(f"  최종 제목: {final_title[:70]}")
logger.info(f"  HTML 길이: {len(content_html):,} bytes")
logger.info(f"  태그: {tags[:80]}")

# ── Step 5: 네이버 발행 ─────────────────────────────────────────
logger.info("\n" + "="*55)
logger.info("[5/5] 네이버 블로그 발행")
logger.info("="*55)

async def publish():
    result = await post_to_naver_blog(
        final_title, content_html, tags, category, blog_cfg
    )
    return result

success = asyncio.run(publish())

logger.info("\n" + "="*55)
if success:
    logger.info(f"✅ 포스팅 성공!")
    logger.info(f"   블로그: {blog_cfg['name']}")
    logger.info(f"   제목: {final_title[:70]}")
    logger.info(f"   URL: https://blog.naver.com/{blog_cfg['blog_id']}")
else:
    logger.error(f"❌ 포스팅 실패")
logger.info("="*55)
