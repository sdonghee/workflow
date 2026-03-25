"""
테스트 실행 스크립트 — 포스트 1개 생성 후 로컬 저장
OpenRouter 불가 환경: BaseAgent가 Claude API로 폴백
Naver 불가 환경: drafts/ 폴더에 저장
"""
import json, logging, os, re, sys
from datetime import date

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("test")

import anthropic
from config import ANTHROPIC_API_KEY, BLOGS, CATEGORIES
from agents.research_agent import ResearchAgent
from agents.content_agent import ContentAgent
from agents.image_agent import ImageAgent
from agents.structure_agent import StructureAgent
from naver_poster import save_post_locally

# ── Step 1: Claude로 포스팅 계획 수립 ──────────────────────────────
logger.info("=" * 55)
logger.info("[1/5] Claude 포스팅 계획 수립")
logger.info("=" * 55)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
today  = date.today().strftime("%Y년 %m월 %d일")

blogs_info = {
    k: {"name": v["name"], "categories": v.get("categories", [])}
    for k, v in BLOGS.items() if v.get("naver_id")
}

resp = claude.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1000,
    messages=[{
        "role": "user",
        "content": f"""오늘({today}) 블로그 포스팅 계획 1개만 JSON으로 반환하세요.
블로그: {json.dumps(blogs_info, ensure_ascii=False)}

[{{"blog_key": "travel", "category": "여행_항공_호텔", "topic_hint": "구체적 주제", "priority": 1}}]
JSON 배열만 반환."""
    }]
)

text = resp.content[0].text.strip()
arr  = re.search(r"\[.*\]", text, re.DOTALL)
plan = json.loads(arr.group() if arr else text)
task = plan[0]

logger.info(f"계획: [{task['blog_key']}] {task['category']} — {task['topic_hint'][:60]}")

# ── Step 2: 리서치 ──────────────────────────────────────────────────
logger.info("\n[2/5] ResearchAgent — 기사 수집 (RSS 불가 시 AI 보완)")
research = ResearchAgent()
articles = research.get_articles(task["category"], max_count=2)
article  = articles[0] if articles else {
    "title": task["topic_hint"], "summary": task["topic_hint"], "link": "", "content": ""
}
logger.info(f"  → 기사: {article.get('title', '')[:60]}")

# ── Step 3: 콘텐츠 생성 ─────────────────────────────────────────────
logger.info("\n[3/5] ContentAgent — 블로그 콘텐츠 작성")
content_agent = ContentAgent()
content_data  = content_agent.generate(article, task["category"])

if not content_data:
    logger.error("콘텐츠 생성 실패 — 종료")
    sys.exit(1)

logger.info(f"  → 제목: {content_data.get('title', '')[:60]}")

# ── Step 4: 이미지 ──────────────────────────────────────────────────
logger.info("\n[4/5] ImageAgent — 이미지 URL 생성")
image_agent = ImageAgent()
img_url, img_alt, photographer = image_agent.get_image(
    content_data.get("title", task["topic_hint"]), task["category"]
)
logger.info(f"  → {photographer}")
logger.info(f"  → URL: {img_url[:80]}...")

# ── Step 5: HTML 구성 ───────────────────────────────────────────────
logger.info("\n[5/5] StructureAgent — HTML 포맷팅")
structure_agent = StructureAgent()
post_data = structure_agent.format_html(
    content_data,
    image_url=img_url,
    image_alt=img_alt,
    article_link=article.get("link", ""),
)

if not post_data:
    logger.error("HTML 구성 실패 — 종료")
    sys.exit(1)

title        = post_data.get("title") or content_data.get("title", "")
content_html = post_data.get("content_html", "")
tags         = post_data.get("tags", "")

if photographer:
    content_html += (
        f'\n<p style="font-size:12px;color:#aaa;text-align:right;">{photographer}</p>'
    )

# ── 로컬 저장 (Naver 접속 불가 환경) ──────────────────────────────────
blog_cfg = BLOGS[task["blog_key"]]
saved    = save_post_locally(title, content_html, tags, task["category"], blog_cfg)

logger.info("\n" + "=" * 55)
logger.info("테스트 완료!")
logger.info(f"  제목  : {title}")
logger.info(f"  태그  : {tags[:80]}")
logger.info(f"  저장  : {saved}")
logger.info(f"  HTML  : {len(content_html)} bytes")
logger.info("=" * 55)
