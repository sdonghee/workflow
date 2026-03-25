"""
이미지 검색 모듈
Unsplash, Pexels에서 무료 저작권 없는 이미지를 검색합니다.
"""
import requests
import logging
import random
from config import UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY, CATEGORIES

logger = logging.getLogger(__name__)

# 카테고리별 기본 검색 키워드
DEFAULT_IMAGE_KEYWORDS = {
    "여행_항공_호텔": ["travel", "hotel", "airplane", "vacation", "airport"],
    "정부혜택": ["community", "government", "people", "korea city", "social welfare"],
    "건강": ["health", "fitness", "wellness", "exercise", "medical"],
}


def search_unsplash(query, per_page=10):
    """Unsplash에서 이미지 검색"""
    if not UNSPLASH_ACCESS_KEY or UNSPLASH_ACCESS_KEY == "your_unsplash_access_key":
        return []

    try:
        url = "https://api.unsplash.com/search/photos"
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        params = {
            "query": query,
            "per_page": per_page,
            "orientation": "landscape",
            "content_filter": "high",
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()

        images = []
        for photo in data.get("results", []):
            images.append({
                "url": photo["urls"]["regular"],
                "thumb": photo["urls"]["thumb"],
                "alt": photo.get("alt_description", query),
                "photographer": photo["user"]["name"],
                "source": "Unsplash",
                "credit_url": photo["links"]["html"],
            })
        logger.info(f"Unsplash에서 {len(images)}개 이미지 검색: {query}")
        return images
    except Exception as e:
        logger.error(f"Unsplash 검색 실패: {e}")
        return []


def search_pexels(query, per_page=10):
    """Pexels에서 이미지 검색"""
    if not PEXELS_API_KEY or PEXELS_API_KEY == "your_pexels_api_key":
        return []

    try:
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {
            "query": query,
            "per_page": per_page,
            "orientation": "landscape",
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()

        images = []
        for photo in data.get("photos", []):
            images.append({
                "url": photo["src"]["large"],
                "thumb": photo["src"]["medium"],
                "alt": photo.get("alt", query),
                "photographer": photo["photographer"],
                "source": "Pexels",
                "credit_url": photo["url"],
            })
        logger.info(f"Pexels에서 {len(images)}개 이미지 검색: {query}")
        return images
    except Exception as e:
        logger.error(f"Pexels 검색 실패: {e}")
        return []


def search_pixabay(query: str, per_page: int = 10) -> list:
    """Pixabay에서 이미지 검색 (PIXABAY_API_KEY 필요)"""
    if not PIXABAY_API_KEY or PIXABAY_API_KEY == "your_pixabay_api_key":
        return []
    try:
        url = "https://pixabay.com/api/"
        params = {
            "key":         PIXABAY_API_KEY,
            "q":           query,
            "image_type":  "photo",
            "orientation": "horizontal",
            "per_page":    per_page,
            "safesearch":  "true",
            "lang":        "ko",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        images = []
        for hit in data.get("hits", []):
            images.append({
                "url":         hit.get("largeImageURL", hit.get("webformatURL", "")),
                "thumb":       hit.get("previewURL", ""),
                "alt":         query,
                "photographer": hit.get("user", "Pixabay"),
                "source":      "Pixabay",
            })
        logger.info(f"Pixabay에서 {len(images)}개 이미지 검색: {query}")
        return images
    except Exception as e:
        logger.error(f"Pixabay 검색 실패: {e}")
        return []


# 하위 호환 별칭
get_pixabay_image = search_pixabay


def get_free_image_url(category, keywords=None):
    """
    카테고리에 맞는 무료 이미지 URL 반환
    Unsplash -> Pexels -> 기본 이미지 순으로 시도
    """
    search_keywords = keywords or DEFAULT_IMAGE_KEYWORDS.get(category, ["korea"])

    # 랜덤하게 키워드 선택
    query = random.choice(search_keywords)

    # Unsplash 시도
    images = search_unsplash(query)
    if images:
        selected = random.choice(images[:5])
        return selected["url"], selected["alt"], selected["photographer"]

    # Pexels 시도
    images = search_pexels(query)
    if images:
        selected = random.choice(images[:5])
        return selected["url"], selected["alt"], selected["photographer"]

    # 기본 이미지 (Lorem Picsum - 저작권 없는 랜덤 이미지)
    width, height = 1200, 630
    seed = abs(hash(query)) % 1000
    fallback_url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
    logger.info(f"기본 이미지 사용: {fallback_url}")
    return fallback_url, query, "Picsum Photos"


def get_multiple_images(category, count=3):
    """여러 이미지 반환"""
    images = []
    keywords = DEFAULT_IMAGE_KEYWORDS.get(category, ["korea"])

    for i in range(count):
        query = keywords[i % len(keywords)]
        url, alt, photographer = get_free_image_url(category, [query])
        images.append({"url": url, "alt": alt, "photographer": photographer})

    return images
