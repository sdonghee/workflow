"""
콘텐츠 수집 모듈
RSS 피드와 웹 검색을 통해 최신 정보를 수집합니다.
"""
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import logging
import json
import os
import re
import hashlib
from datetime import datetime, timedelta
from config import CATEGORIES, POSTED_LOG_FILE

logger = logging.getLogger(__name__)


def load_posted_articles():
    """이미 포스팅된 글 목록 로드"""
    if os.path.exists(POSTED_LOG_FILE):
        with open(POSTED_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"articles": [], "last_updated": ""}


def save_posted_article(article_hash):
    """포스팅된 글 해시 저장"""
    data = load_posted_articles()
    if article_hash not in data["articles"]:
        data["articles"].append(article_hash)
    # 최근 1000개만 유지
    data["articles"] = data["articles"][-1000:]
    data["last_updated"] = datetime.now().isoformat()
    with open(POSTED_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_article_hash(title, content):
    """글 중복 체크용 해시 생성"""
    text = f"{title}{content[:200]}"
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_already_posted(title, content):
    """이미 포스팅된 글인지 확인"""
    data = load_posted_articles()
    article_hash = get_article_hash(title, content)
    return article_hash in data["articles"]


def fetch_rss_articles(rss_url, max_articles=5):
    """RSS 피드에서 최신 기사 수집"""
    articles = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        response = requests.get(rss_url, headers=headers, timeout=10)
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            # 한국 RSS 피드의 인코딩 문제 처리 (예: & 미이스케이프)
            encoding = response.apparent_encoding or "utf-8"
            text = response.content.decode(encoding, errors="replace")
            text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", text)
            root = ET.fromstring(text.encode("utf-8"))

        # RSS 2.0 또는 Atom 형식 처리
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items[:max_articles]:
            def get_text(tag):
                # ElementTree에서 자식 없는 Element는 bool() = False이므로 'or' 사용 금지
                el = item.find(tag)
                if el is None:
                    el = item.find(f"atom:{tag}", ns)
                return el.text.strip() if el is not None and el.text else ""

            link_el = item.find("link")
            link = link_el.text if link_el is not None and link_el.text else (link_el.get("href", "") if link_el is not None else "")

            article = {
                "title": get_text("title"),
                "link": link,
                "summary": get_text("description") or get_text("summary"),
                "published": get_text("pubDate") or get_text("published"),
                "source": rss_url,
            }
            if article["title"]:
                articles.append(article)

        logger.info(f"RSS에서 {len(articles)}개 기사 수집: {rss_url}")
    except Exception as e:
        logger.error(f"RSS 수집 실패 {rss_url}: {e}")
    return articles


def fetch_web_content(url, max_chars=3000):
    """웹 페이지 본문 내용 추출"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "lxml")

        # 불필요한 태그 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "ad"]):
            tag.decompose()

        # 본문 추출 (article, main, content 등)
        content = ""
        for selector in ["article", "main", ".content", "#content", ".article-body", ".news-body"]:
            element = soup.select_one(selector)
            if element:
                content = element.get_text(separator="\n", strip=True)
                break

        if not content:
            content = soup.get_text(separator="\n", strip=True)

        # 너무 짧은 줄 제거
        lines = [line.strip() for line in content.split("\n") if len(line.strip()) > 20]
        content = "\n".join(lines[:50])

        return content[:max_chars]
    except Exception as e:
        logger.error(f"웹 콘텐츠 수집 실패 {url}: {e}")
        return ""


def search_naver_news(query, display=5):
    """네이버 뉴스 검색 (공개 검색 - API 키 불필요)"""
    articles = []
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={requests.utils.quote(query)}&sort=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": "https://www.naver.com/",
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "lxml")

        # 여러 셀렉터 패턴 시도 (네이버 UI 업데이트 대응)
        news_items = (
            soup.select("ul.list_news > li.bx") or
            soup.select(".news_area") or
            soup.select(".news_wrap") or
            soup.select("li.bx")
        )
        for item in news_items[:display]:
            title_el = (
                item.select_one("a.news_tit") or
                item.select_one(".news_tit") or
                item.select_one("a[class*='title']")
            )
            desc_el = (
                item.select_one(".dsc_txt_wrap") or
                item.select_one(".dsc_txt") or
                item.select_one(".news_dsc") or
                item.select_one("a.api_txt_lines")
            )
            if title_el:
                articles.append({
                    "title": title_el.get_text(strip=True),
                    "link": title_el.get("href", ""),
                    "summary": desc_el.get_text(strip=True) if desc_el else "",
                    "source": "naver_search",
                })
        logger.info(f"네이버 검색 '{query}'에서 {len(articles)}개 기사 수집")
    except Exception as e:
        logger.error(f"네이버 검색 실패 '{query}': {e}")
    return articles


def search_google_news(query, num=5):
    """구글 뉴스 RSS 검색"""
    articles = []
    try:
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        articles = fetch_rss_articles(url, max_articles=num)
        for a in articles:
            a["source"] = "google_news"
        logger.info(f"구글 뉴스 '{query}'에서 {len(articles)}개 기사 수집")
    except Exception as e:
        logger.error(f"구글 뉴스 검색 실패 '{query}': {e}")
    return articles


def collect_content_for_category(category_name, category_config, num_posts=3):
    """카테고리별 콘텐츠 수집"""
    all_articles = []

    # RSS 피드 수집
    for rss_url in category_config.get("rss_feeds", []):
        articles = fetch_rss_articles(rss_url, max_articles=3)
        all_articles.extend(articles)

    # 구글 뉴스 검색
    for query in category_config.get("search_queries", [])[:3]:
        articles = search_google_news(query, num=3)
        all_articles.extend(articles)

    # 네이버 뉴스 검색
    for keyword in category_config.get("keywords", [])[:2]:
        articles = search_naver_news(keyword, display=3)
        all_articles.extend(articles)

    # 중복 제거 (제목 기준)
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article["title"][:30]
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    # 이미 포스팅된 것 제외
    filtered = []
    for article in unique_articles:
        if not is_already_posted(article["title"], article.get("summary", "")):
            filtered.append(article)

    logger.info(f"[{category_name}] 최종 {len(filtered)}개 기사 선택 (전체 {len(unique_articles)}개 중)")
    return filtered[:num_posts * 2]  # 여유 있게 수집


def collect_all_content():
    """전체 카테고리 콘텐츠 수집"""
    all_content = {}
    for category_name, category_config in CATEGORIES.items():
        num_posts = category_config.get("post_count", 3)
        articles = collect_content_for_category(category_name, category_config, num_posts)
        all_content[category_name] = {
            "articles": articles,
            "config": category_config,
            "post_count": num_posts,
        }
    return all_content
