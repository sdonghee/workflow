"""
에이전트 1 - 리서치 에이전트
트렌딩 기사 수집 + AI 주제 보강 담당
모델: meta-llama/llama-3.3-70b-instruct:free (검색·분석 특화)
"""
import logging
import sys
import os
from datetime import date
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, LLAMA_70B, HERMES_405B
from content_fetcher import collect_all_content, fetch_web_content
from config import CATEGORIES

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """트렌딩 기사 수집 및 주제 분석 에이전트"""

    def __init__(self):
        super().__init__(
            model=LLAMA_70B,
            fallback_models=[HERMES_405B],
        )

    def get_articles(self, category: str, max_count: int = 5) -> List[dict]:
        """
        카테고리별 기사 수집.
        실제 RSS/뉴스 수집 → 부족하면 AI가 주제 생성 → 각 기사 전문 보강.
        """
        logger.info(f"[ResearchAgent] '{category}' 기사 수집 시작")

        # 1. 실제 RSS/뉴스 수집
        try:
            all_content = collect_all_content()
            articles = all_content.get(category, {}).get("articles", [])[:max_count]
        except Exception as e:
            logger.warning(f"[ResearchAgent] 수집 오류: {e}")
            articles = []

        # 2. 부족분은 AI로 주제 생성
        if len(articles) < max_count:
            need = max_count - len(articles)
            logger.info(f"[ResearchAgent] 기사 {need}개 AI 생성으로 보완")
            ai_topics = self._generate_topics(category, need)
            articles.extend(ai_topics)

        # 3. 링크가 있는 기사는 전문 수집
        enriched = []
        for article in articles[:max_count]:
            if article.get("link"):
                try:
                    full = fetch_web_content(article["link"])
                    if full:
                        article["content"] = full
                except Exception:
                    pass
            enriched.append(article)

        logger.info(f"[ResearchAgent] '{category}': {len(enriched)}개 준비 완료")
        return enriched

    def _generate_topics(self, category: str, count: int) -> List[dict]:
        """기사가 없을 때 AI가 한국 트렌드 기반으로 주제 직접 생성"""
        cat_cfg  = CATEGORIES.get(category, {})
        keywords = cat_cfg.get("keywords", [category])[:6]
        today    = date.today().strftime("%Y년 %m월 %d일")

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 한국 블로그 트렌드 전문 리서처입니다. "
                    "현재 날짜와 계절감을 반영하여 독자들이 가장 궁금해하는 주제를 생성합니다."
                ),
            },
            {
                "role": "user",
                "content": f"""오늘({today}) 한국 '{category.replace('_', '/')}' 블로그용
1만뷰 가능한 포스팅 주제를 {count}개 생성해주세요.

키워드 참고: {', '.join(keywords)}

조건:
- 독자가 즉시 검색할 만한 실용적 주제
- 계절·시사 반영
- 정보가 풍부하게 작성 가능한 주제

JSON 배열로만 반환:
[
  {{
    "title": "포스팅 주제/제목 (구체적으로)",
    "summary": "핵심 내용 요약 200자",
    "link": "",
    "source": "AI 리서치"
  }}
]""",
            },
        ]

        result = self.chat_json(messages, max_tokens=2000)
        if isinstance(result, list):
            return result

        # 최종 폴백: 키워드로 기본 주제 구성
        return [
            {
                "title": f"{kw} 완벽 가이드 {date.today().year}",
                "summary": f"{kw}에 관한 최신 트렌드와 실용 팁 정리",
                "link": "",
                "source": "기본 주제",
            }
            for kw in keywords[:count]
        ]

    def analyze_todays_trends(self, categories: List[str]) -> dict:
        """
        오늘의 카테고리별 트렌드 키워드 분석.
        orchestrator가 계획 수립 시 참고용으로 호출.
        """
        today = date.today().strftime("%Y년 %m월")
        messages = [
            {
                "role": "user",
                "content": f"""{today} 기준 한국에서 다음 카테고리들의 트렌딩 키워드를 분석하세요:
{', '.join(categories)}

각 카테고리별 트렌딩 키워드 3개와 트렌딩 이유를 JSON으로 반환:
{{
  "카테고리명": {{
    "keywords": ["키워드1", "키워드2", "키워드3"],
    "reason": "트렌딩 이유 (30자 이내)"
  }}
}}""",
            }
        ]
        result = self.chat_json(messages, max_tokens=1000)
        return result if isinstance(result, dict) else {}
