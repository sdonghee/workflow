"""
스케줄러 - 하루 2회 자동 포스팅 실행
오전 06:00 (1회차) + 낮 12:00 (2회차)
"""
import argparse
import logging
from datetime import datetime

import schedule
import time

from config import LOG_FILE, LOG_LEVEL, POST_START_HOUR, POST_START_HOUR_2
from orchestrator import run_orchestrator_session

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def scheduled_job(session_label: str = ""):
    """스케줄된 포스팅 세션 실행"""
    label = f" ({session_label})" if session_label else ""
    logger.info(f"🕐 스케줄 세션 시작{label}: {datetime.now().strftime('%H:%M:%S')}")
    try:
        summary = run_orchestrator_session()
        posted  = summary.get("total_posted", 0)
        failed  = summary.get("total_failed", 0)
        logger.info(f"세션 완료{label}: 성공 {posted}개, 실패 {failed}개")
    except Exception as e:
        logger.error(f"세션 오류{label}: {e}", exc_info=True)


def run_scheduler():
    """데몬 모드: 매일 06:00 + 12:00 실행"""
    t1 = f"{POST_START_HOUR:02d}:00"
    t2 = f"{POST_START_HOUR_2:02d}:00"

    logger.info(f"스케줄러 시작 — 매일 {t1}(1회차), {t2}(2회차) 실행")
    logger.info("종료: Ctrl+C")

    schedule.every().day.at(t1).do(scheduled_job, session_label="오전 1회차")
    schedule.every().day.at(t2).do(scheduled_job, session_label="낮 2회차")

    while True:
        schedule.run_pending()
        time.sleep(30)   # 30초 간격으로 pending 확인


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 포스팅 스케줄러")
    parser.add_argument("--now",  action="store_true", help="즉시 1회 실행 (스케줄 없이)")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (콘텐츠 생성만, 실제 게시 안 함)")
    args = parser.parse_args()

    if args.now:
        logger.info("즉시 실행 모드")
        scheduled_job(session_label="즉시 실행")

    elif args.test:
        logger.info("=== 테스트 모드 (게시 없음) ===")
        from content_fetcher import collect_all_content
        from content_writer import generate_blog_post
        from image_finder import get_free_image_url

        logger.info("콘텐츠 수집 중...")
        all_content = collect_all_content()
        for cat, data in all_content.items():
            articles = data.get("articles", [])
            logger.info(f"[{cat}] {len(articles)}개 기사 수집")
            for art in articles[:1]:
                logger.info(f"  기사: {art.get('title', '')[:60]}")
                post = generate_blog_post(cat, art)
                if post:
                    logger.info(f"  생성 제목: {post.get('title', '')}")
                    logger.info(f"  태그(hash): {post.get('tags_hash', '')[:60]}")
        logger.info("테스트 완료")

    else:
        run_scheduler()
