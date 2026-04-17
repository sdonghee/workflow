"""
에이전트 4 - 이미지 에이전트
포스트 주제에 맞는 이미지 수집 또는 AI 생성
우선순위: Unsplash → Pexels → Pixabay → Pollinations.ai (AI 생성, 무료·키 없음)
모델: google/gemma-3-27b-it:free (프롬프트 생성용)
"""
import logging
import random
import urllib.parse
import sys
import os
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, GEMMA_12B, GEMMA_27B, NEMOTRON_12B, NEMOTRON_9B, MISTRAL_24B, GPT_OSS_20B, STEPFUN, LLAMA_70B
from config import IMAGE_EXCLUDE_KEYWORDS
from image_finder import search_unsplash, search_pexels, search_pixabay

logger = logging.getLogger(__name__)


class ImageAgent(BaseAgent):
    """이미지 수집 및 AI 생성 에이전트"""

    def __init__(self):
        # ... (생성자 내용은 기존과 동일)
        super().__init__(
            model=GEMMA_12B,
            fallback_models=[GEMMA_27B, NEMOTRON_12B, NEMOTRON_9B, MISTRAL_24B, GPT_OSS_20B, STEPFUN, LLAMA_70B],
        )

    def get_images(self, image_keywords_list: list, category: str, max_images: int = 3) -> list:
        """
        [수정됨] 여러 개의 키워드로 여러 장의 이미지 검색.
        - 대표 이미지 키워드 + 소주제별 키워드를 받아 리스트로 반환.
        - URL 중복을 방지하며 max_images 개수만큼 채워지면 중단.
        """
        found_images = []
        found_urls = set()

        # 필터링 키워드 준비
        negative_keywords = " ".join([f"-{kw}" for kw in IMAGE_EXCLUDE_KEYWORDS])

        for query in image_keywords_list:
            if len(found_images) >= max_images:
                break
            if not query:
                continue

            query_with_exclusion = f"{query} {negative_keywords}".strip()
            logger.info(f"[ImageAgent] 이미지 검색: '{query_with_exclusion}'")

            # 이미지 소스 순회 (Unsplash -> Pexels -> Pixabay)
            for search_func in [search_unsplash, search_pexels, search_pixabay]:
                if len(found_images) >= max_images:
                    break
                
                try:
                    # Unsplash는 제외 쿼리 직접 사용, 나머지는 결과 필터링
                    search_query = query_with_exclusion if search_func == search_unsplash else query
                    imgs = search_func(search_query)
                    imgs = self._filter_results(imgs)

                    for img in imgs:
                        if img["url"] not in found_urls:
                            source = "Unsplash"
                            if search_func == search_pexels: source = "Pexels"
                            if search_func == search_pixabay: source = "Pixabay"
                            
                            photographer_credit = ""
                            if source in ["Unsplash", "Pexels"]:
                                photographer_credit = f"📸 Photo by {img['photographer']} on {source}"
                            else:
                                photographer_credit = f"📸 Image from {source}"

                            found_images.append({
                                "url": img["url"],
                                "alt": img.get("alt", query),
                                "credit": photographer_credit
                            })
                            found_urls.add(img["url"])
                            
                            if len(found_images) >= max_images:
                                break
                except Exception as e:
                    logger.warning(f"[ImageAgent] {search_func.__name__} 검색 중 오류: {e}")

        # 이미지를 하나도 못 찾았으면 AI로 대표 이미지 생성
        if not found_images:
            logger.info("[ImageAgent] 무료 이미지 없음 → Pollinations.ai로 AI 이미지 생성")
            # 대표 키워드가 리스트의 첫 번째 항목이라고 가정
            main_topic_or_keyword = image_keywords_list[0] if image_keywords_list else category
            url, alt, credit = self._generate_with_pollinations(main_topic_or_keyword, category)
            if url:
                found_images.append({"url": url, "alt": alt, "credit": credit})
        
        logger.info(f"[ImageAgent] 최종 {len(found_images)}개 이미지 수집 완료.")
        return found_images

    def _filter_results(self, images: list) -> list:
        """결과 리스트에서 제외 키워드가 포함된 이미지 필터링"""
        if not images:
            return []
        
        filtered = []
        for img in images:
            alt_text = img.get("alt", "").lower()
            # any()는 하나라도 True이면 True를 반환
            if not any(kw in alt_text for kw in IMAGE_EXCLUDE_KEYWORDS):
                filtered.append(img)
        
        if len(images) > len(filtered):
            logger.debug(f"[ImageAgent] 필터링: {len(images)}개 → {len(filtered)}개 (제외 키워드 적용)")
        return filtered

    def _get_search_query(self, topic: str, category: str) -> str:
        """AI로 이미지 검색에 최적화된 영어 키워드 생성"""
        messages = [
            {
                "role": "user",
                "content": (
                    f"'{topic}' ({category}) 블로그 대표 이미지 검색 키워드를 2~3단어 영어로만 반환하세요.\n"
                    "규칙: 연도/숫자/뉴스 단어 없이. 시간이 지나도 어울리는 범용 사진 키워드로.\n"
                    "예) '항공권 할인' → 'airplane window seat' / '여행지 추천' → 'travel destination landscape'\n"
                    "단어만, 설명 없이."
                ),
            }
        ]
        result = self.chat(messages, max_tokens=30, temperature=0.3)
        if result:
            query = result.split("\n")[0].strip()[:40]
            # 연도 숫자 제거 (2024, 2025, 2026 등)
            import re
            query = re.sub(r'\b20\d{2}\b', '', query).strip()
            if query:
                return query
        # 폴백: 카테고리 기본 키워드
        fallback = {
            "여행_항공_호텔": "travel destination landscape",
            "정부혜택":       "community support people",
            "건강":          "healthy lifestyle wellness",
        }
        return fallback.get(category, "korea lifestyle")

    def _generate_with_pollinations(
        self, topic: str, category: str
    ) -> Tuple[str, str, str]:
        """
        Pollinations.ai로 AI 이미지 생성.
        URL 형식: https://image.pollinations.ai/prompt/{encoded}?width=1200&height=630&nologo=true
        """
        # AI로 이미지 생성 프롬프트 작성
        messages = [
            {
                "role": "user",
                "content": (
                    f"'{topic}' 주제 블로그 썸네일용 Stable Diffusion 프롬프트를 1줄(40단어 이하)로 작성하세요.\n"
                    "규칙: 연도/숫자/텍스트/로고 없는 사진. 시간이 지나도 어울리는 범용 여행·생활 이미지.\n"
                    "스타일: professional photography, bright natural light, clean composition, no text, no year.\n"
                    "프롬프트만, 설명 없이."
                ),
            }
        ]
        prompt_text = self.chat(messages, max_tokens=80, temperature=0.5)
        if not prompt_text:
            prompt_text = f"travel lifestyle photography, bright natural light, clean composition, no text"

        # 첫 줄만 사용, 연도 제거
        import re
        prompt_text = prompt_text.split("\n")[0].strip()
        prompt_text = re.sub(r'\b20\d{2}\b', '', prompt_text).strip()
        prompt_text += ", no text, no logo, no year"

        seed    = random.randint(1, 99999)
        encoded = urllib.parse.quote(prompt_text)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1200&height=630&nologo=true&seed={seed}"
        )

        logger.info(f"[ImageAgent] Pollinations.ai 이미지 생성: {url[:80]}...")
        return url, topic, "🎨 AI Generated (Pollinations.ai)"
