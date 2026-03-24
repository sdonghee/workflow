"""
메인 일일 포스팅 오케스트레이터
멀티 블로그 지원: BLOGS 설정에 등록된 모든 블로그에 자동 포스팅
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
from config import CATEGORIES, BLOGS, POSTING_INTERVAL_MINUTES, LOG_FILE, LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


def process_article(category_name, category_config, article, blog_config):
    """
    단일 기사를 블로그 포스트로 변환하고 게시

    Returns:
        bool: 성공 여부
    """
    try:
        logger.info(f"[{blog_config['name']}] 처리 시작: [{category_name}] {article.get('title', '')[:50]}")

        if article.get("link"):
            full_content = fetch_web_content(article["link"])
            article["content"] = full_content

        image_keywords = category_config.get("image_keywords", ["korea"])
        image_url, image_alt, photographer = get_free_image_url(category_name, image_keywords)

        post_data = generate_blog_post(
            category=category_name,
            article=article,
            image_url=image_url,
            image_alt=image_alt,
        )

        if not post_data:
            logger.error(f"[{blog_config['name']}] 포스트 생성 실패: {article.get('title', '')}")
            return False

        title = post_data.get("title", article.get("title", ""))
        content_html = post_data.get("content_html", "")
        tags = post_data.get("tags", ",".join(category_config.get("tags", [])))

        if photographer:
            content_html += f'\n<p style="font-size:12px; color:#999; text-align:right;">📸 사진: {photographer} (무료 이미지)</p>'

        logger.info(f"[{blog_config['name']}] 포스팅 시도: {title}")
        success = post_blog(title, content_html, tags, category_name, blog_config)

        if success:
            article_hash = get_article_hash(article.get("title", ""), article.get("summary", ""))
            save_posted_article(article_hash)
            logger.info(f"[{blog_config['name']}] ✅ 포스팅 완료: {title}")
        else:
            save_post_locally(title, content_html, tags, category_name, blog_config)
            logger.warning(f"[{blog_config['name']}] ⚠️ 포스팅 실패, 임시 저장: {title}")

        return success

    except Exception as e:
        logger.error(f"[{blog_config['name']}] 기사 처리 중 오류: {e}", exc_info=True)
        return False


def run_blog_posting(blog_config, all_content):
    """
    단일 블로그의 하루치 포스팅 실행

    Returns:
        (posted_count, failed_count)
    """
    blog_name = blog_config["name"]
    assigned_categories = blog_config["categories"]

    logger.info(f"\n{'='*60}")
    logger.info(f"📝 블로그 포스팅 시작: {blog_name}")
    logger.info(f"   담당 카테고리: {', '.join(assigned_categories)}")
    logger.info(f"{'='*60}")

    total_posted = 0
    total_failed = 0

    for category_name in assigned_categories:
        if category_name not in all_content:
            logger.warning(f"[{blog_name}] 카테고리 없음: {category_name}")
            continue

        category_data = all_content[category_name]
        articles = category_data["articles"]
        category_config = category_data["config"]
        target_count = category_data["post_count"]

        logger.info(f"\n📂 [{blog_name}] 카테고리: {category_name} (목표: {target_count}개)")

        posted_count = 0
        for i, article in enumerate(articles):
            if posted_count >= target_count:
                break

            success = process_article(category_name, category_config, article, blog_config)

            if success:
                posted_count += 1
                total_posted += 1
            else:
                total_failed += 1

            if i < len(articles) - 1 and posted_count < target_count:
                wait_minutes = max(5, POSTING_INTERVAL_MINUTES)
                logger.info(f"⏳ {wait_minutes}분 대기 중...")
                time.sleep(wait_minutes * 60)

        # 기사 부족 시 처음부터 생성
        if posted_count < target_count:
            for _ in range(target_count - posted_count):
                logger.info(f"[{blog_name}] 📝 기사 부족으로 신규 콘텐츠 생성")
                post_data = create_post_from_scratch(category_name, category_name, category_config)
                if post_data:
                    title = post_data.get("title", "")
                    content_html = post_data.get("content_html", "")
                    tags = post_data.get("tags", "")
                    success = post_blog(title, content_html, tags, category_name, blog_config)
                    if success:
                        posted_count += 1
                        total_posted += 1
                    else:
                        save_post_locally(title, content_html, tags, category_name, blog_config)
                        total_failed += 1
                time.sleep(POSTING_INTERVAL_MINUTES * 60)

    return total_posted, total_failed


def run_daily_posting():
    """
    전체 블로그 하루치 포스팅 실행
    BLOGS에 등록된 모든 블로그를 순서대로 처리
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"일일 포스팅 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"등록된 블로그: {len(BLOGS)}개 - {', '.join(b['name'] for b in BLOGS.values())}")
    logger.info("=" * 60)

    # 콘텐츠 수집 (전체 카테고리 한 번에)
    logger.info("📡 콘텐츠 수집 중...")
    all_content = collect_all_content()

    grand_total_posted = 0
    grand_total_failed = 0
    blog_results = {}

    for blog_key, blog_config in BLOGS.items():
        if not blog_config.get("naver_id") or not blog_config.get("blog_id"):
            logger.warning(f"[{blog_config['name']}] .env 설정 미완료, 스킵")
            continue

        posted, failed = run_blog_posting(blog_config, all_content)
        grand_total_posted += posted
        grand_total_failed += failed
        blog_results[blog_key] = {"posted": posted, "failed": failed}

    # 결과 요약
    end_time = datetime.now()
    duration = (end_time - start_time).seconds // 60

    logger.info("\n" + "=" * 60)
    logger.info("📊 전체 일일 포스팅 결과")
    logger.info("=" * 60)
    for blog_key, result in blog_results.items():
        name = BLOGS[blog_key]["name"]
        logger.info(f"  {name}: 성공 {result['posted']}개 / 실패 {result['failed']}개")
    logger.info(f"✅ 총 성공: {grand_total_posted}개")
    logger.info(f"❌ 총 실패: {grand_total_failed}개")
    logger.info(f"⏱️ 소요 시간: {duration}분")
    logger.info("=" * 60)

    # 결과 저장
    result_log = {
        "date": start_time.strftime("%Y-%m-%d"),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "total_posted": grand_total_posted,
        "total_failed": grand_total_failed,
        "blogs": blog_results,
    }

    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/result_{start_time.strftime('%Y%m%d')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(result_log, f, ensure_ascii=False, indent=2)

    return grand_total_posted, grand_total_failed


if __name__ == "__main__":
    run_daily_posting()
