"""
일일 포스팅 실행 모듈
orchestrator.py로 위임하는 레거시 진입점 (하위 호환 유지)
"""
import logging
from config import LOG_FILE, LOG_LEVEL
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


def run_daily_posting():
    """레거시 인터페이스 — orchestrator.run_session() 위임"""
    logger.info("[daily_poster] 오케스트레이터 세션 시작")
    summary = run_orchestrator_session()
    posted  = summary.get("total_posted", 0)
    failed  = summary.get("total_failed", 0)
    logger.info(f"[daily_poster] 완료: 성공 {posted}개 / 실패 {failed}개")
    return posted, failed


if __name__ == "__main__":
    run_daily_posting()
