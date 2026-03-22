"""
메인 일일 포스팅 오케스트레이터
매일 10개의 블로그 포스트를 자동으로 생성하고 게시합니다.
"""
import logging
import json
import time
import os
from datetime import datetime
from content_fetcher import collect_all_content, fetch_web_content, save_posted_article, get_article_hash
from content_writer import generate_blog_post, create_post_from_scratch
from image_finder import get_free_image_url
from naver_poster import post_blog, save_post_locally
from config import CATEGORIES, POSTING_INTERVAL_MINUTES, LOG_FILE, LOG_LEVEL

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


def process_article(category_name, category_config, article):
    """
    단일 기사를 블로그 포스트로 변환하고 게시

    Returns:
        bool: 성공 여부
    """
    try:
        logger.info(f"처리 시작: [{category_name}] {article.get('title', '')[:50]}")

        # 원본 기사 내용 보강 (링크가 있으면 전체 내용 수집)
        if article.get("link"):
            full_content = fetch_web_content(article["link"])
            article["content"] = full_content

        # 이미지 검색
        image_keywords = category_config.get("image_keywords", ["korea"])
        image_url, image_alt, photographer = get_free_image_url(category_name, image_keywords)

        # AI로 블로그 포스트 생성
        post_data = generate_blog_post(
            category=category_name,
            article=article,
            image_url=image_url,
            image_alt=image_alt,
        )

        if not post_data:
            logger.error(f"포스트 생성 실패: {article.get('title', '')}")
            return False

        title = post_data.get("title", article.get("title", ""))
        content_html = post_data.get("content_html", "")
        tags = post_data.get("tags", ",".join(category_config.get("tags", [])))

        # 사진 출처 표시 (저작권 준수)
        if photographer:
            content_html += f'\n<p style="font-size:12px; color:#999; text-align:right;">📸 사진: {photographer} (무료 이미지)</p>'

        # 네이버 블로그에 게시
        logger.info(f"포스팅 시도: {title}")
        success = post_blog(title, content_html, tags, category_name)

        if success:
            # 게시된 글 기록
            article_hash = get_article_hash(article.get("title", ""), article.get("summary", ""))
            save_posted_article(article_hash)
            logger.info(f"✅ 포스팅 완료: {title}")
        else:
            # 실패 시 로컬 저장
            save_post_locally(title, content_html, tags, category_name)
            logger.warning(f"⚠️ 포스팅 실패, 임시 저장: {title}")

        return success

    except Exception as e:
        logger.error(f"기사 처리 중 오류: {e}", exc_info=True)
        return False


def run_daily_posting():
    """
    하루치 포스팅 실행 (총 10개)
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"일일 포스팅 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 콘텐츠 수집
    logger.info("📡 콘텐츠 수집 중...")
    all_content = collect_all_content()

    total_posted = 0
    total_failed = 0
    posting_results = []

    # 카테고리별로 포스팅
    for category_name, category_data in all_content.items():
        articles = category_data["articles"]
        category_config = category_data["config"]
        target_count = category_data["post_count"]

        logger.info(f"\n📂 카테고리: {category_name} (목표: {target_count}개)")

        posted_count = 0
        for i, article in enumerate(articles):
            if posted_count >= target_count:
                break

            success = process_article(category_name, category_config, article)

            if success:
                posted_count += 1
                total_posted += 1
                posting_results.append({
                    "category": category_name,
                    "status": "success",
                    "article": article.get("title", "")[:50],
                })
            else:
                total_failed += 1
                posting_results.append({
                    "category": category_name,
                    "status": "failed",
                    "article": article.get("title", "")[:50],
                })

            # 포스팅 간격 (네이버 스팸 방지)
            if i < len(articles) - 1 and posted_count < target_count:
                wait_minutes = max(5, POSTING_INTERVAL_MINUTES)
                logger.info(f"⏳ {wait_minutes}분 대기 중...")
                time.sleep(wait_minutes * 60)

        # 수집된 기사가 부족한 경우 처음부터 생성
        if posted_count < target_count:
            for _ in range(target_count - posted_count):
                logger.info(f"📝 기사 부족으로 신규 콘텐츠 생성")
                post_data = create_post_from_scratch(category_name, category_name, category_config)
                if post_data:
                    title = post_data.get("title", "")
                    content_html = post_data.get("content_html", "")
                    tags = post_data.get("tags", "")
                    success = post_blog(title, content_html, tags, category_name)
                    if success:
                        posted_count += 1
                        total_posted += 1
                    else:
                        save_post_locally(title, content_html, tags, category_name)
                        total_failed += 1
                time.sleep(POSTING_INTERVAL_MINUTES * 60)

    # 결과 요약
    end_time = datetime.now()
    duration = (end_time - start_time).seconds // 60

    logger.info("\n" + "=" * 60)
    logger.info("📊 일일 포스팅 결과")
    logger.info("=" * 60)
    logger.info(f"✅ 성공: {total_posted}개")
    logger.info(f"❌ 실패: {total_failed}개")
    logger.info(f"⏱️ 소요 시간: {duration}분")
    logger.info("=" * 60)

    # 결과 저장
    result_log = {
        "date": start_time.strftime("%Y-%m-%d"),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "total_posted": total_posted,
        "total_failed": total_failed,
        "results": posting_results,
    }

    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/result_{start_time.strftime('%Y%m%d')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(result_log, f, ensure_ascii=False, indent=2)

    return total_posted, total_failed


if __name__ == "__main__":
    run_daily_posting()
