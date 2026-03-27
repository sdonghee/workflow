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
from image_finder import search_unsplash, search_pexels, search_pixabay

logger = logging.getLogger(__name__)


class ImageAgent(BaseAgent):
    """이미지 수집 및 AI 생성 에이전트"""

    def __init__(self):
        # 이미지 프롬프트 생성 → 경량 모델로도 충분
        super().__init__(
            model=GEMMA_12B,
            fallback_models=[GEMMA_27B, NEMOTRON_12B, NEMOTRON_9B, MISTRAL_24B, GPT_OSS_20B, STEPFUN, LLAMA_70B],
        )

    def get_image(self, topic: str, category: str) -> Tuple[str, str, str]:
        """
        주제에 맞는 이미지 URL, alt 텍스트, 크레딧 반환.
        Unsplash → Pexels → Pixabay → Pollinations.ai 순서로 시도.
        """
        # AI로 최적 영어 검색 키워드 생성
        query = self._get_search_query(topic, category)
        logger.info(f"[ImageAgent] 이미지 검색 쿼리: '{query}'")

        # 1순위: Unsplash
        imgs = search_unsplash(query)
        if imgs:
            img = random.choice(imgs[:5])
            return img["url"], img.get("alt", query), f"📸 Photo by {img['photographer']} on Unsplash"

        # 2순위: Pexels
        imgs = search_pexels(query)
        if imgs:
            img = random.choice(imgs[:5])
            return img["url"], img.get("alt", query), f"📸 Photo by {img['photographer']} on Pexels"

        # 3순위: Pixabay
        imgs = search_pixabay(query)
        if imgs:
            img = random.choice(imgs[:5])
            return img["url"], img.get("alt", query), "📸 Image from Pixabay"

        # 4순위: Pollinations.ai (AI 이미지 생성, 완전 무료·키 없음)
        logger.info("[ImageAgent] 무료 이미지 없음 → Pollinations.ai로 AI 이미지 생성")
        return self._generate_with_pollinations(topic, category)

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
