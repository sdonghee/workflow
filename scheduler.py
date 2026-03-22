"""
스케줄러 - 매일 자동으로 포스팅 실행
"""
import schedule
import time
import logging
import argparse
from datetime import datetime
from daily_poster import run_daily_posting
from config import POST_START_HOUR, LOG_FILE, LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


def scheduled_job():
    """스케줄된 포스팅 작업"""
    logger.info(f"🕐 스케줄 작업 시작: {datetime.now()}")
    try:
        posted, failed = run_daily_posting()
        logger.info(f"스케줄 작업 완료: 성공 {posted}개, 실패 {failed}개")
    except Exception as e:
        logger.error(f"스케줄 작업 중 오류: {e}", exc_info=True)


def run_scheduler():
    """스케줄러 실행"""
    run_time = f"{POST_START_HOUR:02d}:00"
    logger.info(f"스케줄러 시작 - 매일 {run_time}에 포스팅 실행")
    logger.info("종료하려면 Ctrl+C를 누르세요")

    schedule.every().day.at(run_time).do(scheduled_job)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 포스팅 스케줄러")
    parser.add_argument(
        "--now",
        action="store_true",
        help="지금 즉시 포스팅 실행 (스케줄 없이)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="테스트 모드 (포스팅 없이 콘텐츠 생성만 확인)"
    )
    args = parser.parse_args()

    if args.now:
        logger.info("즉시 실행 모드")
        run_daily_posting()
    elif args.test:
        logger.info("테스트 모드 - 콘텐츠 수집 및 생성 확인")
        from content_fetcher import collect_all_content
        from content_writer import generate_blog_post
        from image_finder import get_free_image_url

        logger.info("콘텐츠 수집 중...")
        all_content = collect_all_content()
        for cat, data in all_content.items():
            logger.info(f"[{cat}] {len(data['articles'])}개 기사 수집")
            for article in data["articles"][:1]:
                logger.info(f"  - {article.get('title', '')[:60]}")
                post = generate_blog_post(cat, article)
                if post:
                    logger.info(f"  → 생성된 제목: {post.get('title', '')}")
                    logger.info(f"  → 태그: {post.get('tags', '')[:60]}")
        logger.info("테스트 완료")
    else:
        run_scheduler()
