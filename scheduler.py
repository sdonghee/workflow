"""
스케줄러 - 하루 4회 자동 포스팅 실행
09:00 (1회차) + 12:00 (2회차) + 15:00 (3회차) + 18:00 (4회차)
"""
import argparse
import logging
from datetime import datetime

import schedule
import time

from config import LOG_FILE, LOG_LEVEL, POST_START_HOUR, POST_START_HOUR_2, POST_START_HOUR_3, POST_START_HOUR_4
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
    """데몬 모드: 매일 09:00 + 12:00 + 15:00 + 18:00 실행"""
    t1 = f"{POST_START_HOUR:02d}:00"
    t2 = f"{POST_START_HOUR_2:02d}:00"
    t3 = f"{POST_START_HOUR_3:02d}:00"
    t4 = f"{POST_START_HOUR_4:02d}:00"

    logger.info(f"스케줄러 시작 — 매일 {t1}(1회차), {t2}(2회차), {t3}(3회차), {t4}(4회차) 실행")
    logger.info("종료: Ctrl+C")

    schedule.every().day.at(t1).do(scheduled_job, session_label="오전 1회차")
    schedule.every().day.at(t2).do(scheduled_job, session_label="낮 2회차")
    schedule.every().day.at(t3).do(scheduled_job, session_label="오후 3회차")
    schedule.every().day.at(t4).do(scheduled_job, session_label="저녁 4회차")

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
        logger.info("=== 테스트 모드 (orchestrator 파이프라인) ===")
        logger.info("첫 번째 포스트만 생성 및 발행...")
        from orchestrator import run_single_post_via_orchestrator
        result = run_single_post_via_orchestrator()
        logger.info(f"테스트 완료: {result}")
        if result.get("success"):
            logger.info(f"✅ 성공: {result.get('title', '')}")
        else:
            logger.warning(f"❌ 실패")

    else:
        run_scheduler()
