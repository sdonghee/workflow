"""
실제 블로그 포스팅 테스트 — 오케스트레이터 기반
당일 기사 복수 수집 → 종합 → 네이버 발행

사용법:
  python test_full_pipeline.py [travel|info|all]
  travel : 여행/항공/호텔 블로그 3개 포스팅
  info   : 정보/건강 블로그 3개 포스팅
  all    : 양쪽 블로그 모두 실행 (기본값)
"""
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
from orchestrator import BlogOrchestrator

# ── 실행 대상 결정 ───────────────────────────────────────────────
mode = sys.argv[1] if len(sys.argv) > 1 else "all"

if mode not in ("travel", "info", "all"):
    print(f"❌ 알 수 없는 모드: {mode}. 사용 가능: travel | info | all")
    sys.exit(1)

logger.info("=" * 60)
logger.info(f"🚀 블로그 자동 포스팅 시작 (모드: {mode})")
logger.info("=" * 60)

orch = BlogOrchestrator()

# 1. 오늘 포스팅 계획 수립
plan = orch.plan_session()

# 2. 모드에 따라 필터링
if mode != "all":
    plan = [t for t in plan if t["blog_key"] == mode]

if not plan:
    logger.error(f"❌ '{mode}' 에 해당하는 포스팅 계획 없음")
    sys.exit(1)

logger.info(f"📋 오늘 계획: {len(plan)}개 포스팅")
for i, t in enumerate(plan, 1):
    logger.info(f"  {i}. [{t['blog_key']}] {t['category']} — {t.get('topic_hint','')[:50]}")

# 3. 각 포스팅 실행 (인터벌 없이 — 테스트 모드)
import time
import random

posted = 0
failed = 0

for i, task in enumerate(plan, 1):
    logger.info(f"\n{'─'*60}")
    logger.info(f"[{i}/{len(plan)}] 포스팅 실행: {task.get('topic_hint','')[:50]}")
    logger.info(f"{'─'*60}")

    result = orch.run_post_pipeline(task)

    if result["success"]:
        posted += 1
        blog_id = BLOGS.get(task["blog_key"], {}).get("blog_id", "")
        logger.info(f"✅ 성공: {result['title'][:55]}")
        logger.info(f"   👉 https://blog.naver.com/{blog_id}")
    else:
        failed += 1
        logger.error(f"❌ 실패: {result['title'][:55]}")

    # 포스트 사이에 짧은 대기 (마지막 제외)
    if i < len(plan):
        wait = random.randint(30, 60)
        logger.info(f"⏳ 다음 포스팅까지 {wait}초 대기...")
        time.sleep(wait)

# 4. 결과 요약
logger.info("\n" + "=" * 60)
logger.info(f"🏁 완료: 성공 {posted}개 / 실패 {failed}개")
for r in orch._results:
    status = "✅" if r["success"] else "❌"
    blog_id = BLOGS.get(r["blog_key"], {}).get("blog_id", "")
    logger.info(f"  {status} [{r['blog_key']}] {r['title'][:50]}")
    if r["success"] and blog_id:
        logger.info(f"     → https://blog.naver.com/{blog_id}")
logger.info("=" * 60)
