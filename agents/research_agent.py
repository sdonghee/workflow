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

from agents.base_agent import BaseAgent, LLAMA_70B, QWEN3_80B, NEMOTRON_120B, GPT_OSS_120B, MINIMAX, HERMES_405B, MISTRAL_24B, GEMMA_27B, GLM_45
from content_fetcher import collect_all_content, fetch_web_content, collect_topic_articles, collect_content_for_category
from config import CATEGORIES

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """트렌딩 기사 수집 및 주제 분석 에이전트"""

    def __init__(self):
        # 검색·분석 특화 → 추론 강한 모델 우선
        super().__init__(
            model=LLAMA_70B,
            fallback_models=[QWEN3_80B, NEMOTRON_120B, GPT_OSS_120B, MINIMAX, HERMES_405B, MISTRAL_24B, GEMMA_27B, GLM_45],
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
        year     = date.today().year

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 한국 블로그 트렌드 전문 리서처입니다. "
                    f"현재 날짜({today})와 계절감을 반영하여, "
                    f"{year}년 현재 독자들이 가장 궁금해하는 최신 주제를 생성합니다. "
                    "오래된 정보나 만료된 제도·이벤트 주제는 절대 생성하지 마세요."
                ),
            },
            {
                "role": "user",
                "content": f"""오늘({today}) 한국 '{category.replace('_', '/')}' 블로그용
1만뷰 가능한 포스팅 주제를 {count}개 생성해주세요.

키워드 참고: {', '.join(keywords)}

조건:
- {year}년 현재 기준 최신 정보로 작성 가능한 주제
- 독자가 즉시 검색할 만한 실용적 주제
- 계절·시사 반영
- 정보가 풍부하게 작성 가능한 주제

JSON 배열로만 반환:
[
  {{
    "title": "포스팅 주제/제목 ({year}년 기준, 구체적으로)",
    "summary": "핵심 내용 요약 200자 ({year}년 최신 기준)",
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

    def find_high_interest_articles(self, category: str, count: int = 5) -> List[dict]:
        """
        카테고리 내에서 오늘 가장 관심도가 높을 만한 기사를 수집.
        Orchestrator가 포스팅 계획을 수립하기 위해 가장 먼저 호출.
        """
        logger.info(f"[ResearchAgent] '{category}' 카테고리 내 관심도 높은 기사 수집 시작")
        
        category_config = CATEGORIES.get(category, {})
        # collect_content_for_category는 내부적으로 중복 및 기포스팅 기사를 제거함
        articles = collect_content_for_category(category, category_config, num_posts=count)
        
        logger.info(f"[ResearchAgent] 관심도 높은 기사 {len(articles)}개 수집 완료.")
        return articles[:count]

    def gather_comprehensive_info(self, topic_hint: str, category: str, source_article: dict = None) -> Dict:
        """
        [최종 업그레이드] '만능 리서처' 파이프라인.
        source_article이 제공되면, 해당 기사를 중심으로 정보 확장.
        """
        logger.info(f"[ResearchAgent] '만능 리서처' 모드 시작 — 주제: '{topic_hint[:40]}'")
        
        # 1단계: AI를 통해 검색 계획 수립 (동일)
        search_plan = self._plan_searches(topic_hint, category)
        
        # 2단계: 핵심 주제 정보 수집 (로직 변경)
        main_topic_articles = []
        if source_article:
            logger.info("제공된 '씨앗 기사'를 핵심 정보로 사용합니다.")
            # '씨앗 기사'의 본문이 비어있을 수 있으므로, 다시 한번 가져온다.
            if source_article.get("link") and not source_article.get("content"):
                source_article['content'] = fetch_web_content(source_article['link'])
            main_topic_articles = [source_article]
        else:
            # 기존 로직 (topic_hint 기반 검색)
            main_topic_articles = collect_topic_articles(topic_hint, CATEGORIES.get(category, {}), max_articles=5)

        if not main_topic_articles:
            logger.warning("[ResearchAgent] 핵심 주제 관련 기사 없음.")
            return {"main_topic_info": [], "sub_topics": {}}
        
        # 3단계: 하위 주제 정보 수집 (동일)
        sub_topics_results = {}
        if "sub_searches" in search_plan:
            for item in search_plan["sub_searches"]:
                sub_category = item.get("category_ko", "기타")
                query = item.get("query", "")
                if not query: continue
                
                logger.info(f"[ResearchAgent] 하위 주제 검색: [{sub_category}] '{query}'")
                articles = collect_topic_articles(query, {}, max_articles=2)
                sub_topics_results[sub_category] = articles
        
        logger.info(f"[ResearchAgent] 종합 정보 수집 완료: 핵심 정보 {len(main_topic_articles)}개, 하위 주제 {len(sub_topics_results)}개")
        
        return {
            "main_topic_info": main_topic_articles,
            "sub_topics": sub_topics_results
        }

    def _plan_searches(self, topic_hint: str, category: str) -> Dict:
        """AI를 사용해 종합 가이드 작성을 위한 하위 검색어 계획 생성"""
        year  = date.today().year
        month = date.today().month
        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 최고의 콘텐츠를 만들기 위해 무엇을 검색해야 하는지 아는 '수석 리서치 플래너'입니다. "
                    f"현재 {year}년 {month}월 기준 최신 정보를 검색할 수 있는 구체적인 검색어를 계획하세요. "
                    "검색어에는 반드시 연도(2026) 또는 '최신', '현재'를 포함해 최신 결과가 나오도록 하세요."
                ),
            },
            {
                "role": "user",
                "content": f"""'**{topic_hint}**' 라는 블로그 포스트 주제를 위한 종합적인 리서치 계획을 세워주세요.
{year}년 {month}월 현재 기준 최신 정보를 검색할 수 있는 구체적인 검색어를 작성하세요.

【정보 카테고리 예시】
날씨 및 옷차림, 교통 (렌트카, 뚜벅이), 추천 맛집, 필수 방문 명소, 할인 꿀팁, 쇼핑 리스트 등

【출력 형식】
반드시 아래의 JSON 형식으로만 응답해주세요. 다른 설명은 절대 추가하지 마세요.
```json
{{
  "location": "주제에서 파악된 핵심 지역 (예: '제주도', '오사카')",
  "sub_searches": [
    {{
      "category_ko": "날씨 및 옷차림",
      "query": "제주도 4월 날씨 {year}"
    }},
    {{
      "category_ko": "교통 정보",
      "query": "제주공항 렌트카 저렴하게 예약 {year} 최신"
    }},
    {{
      "category_ko": "추천 맛집",
      "query": "제주 현지인 추천 맛집 {year} 최신"
    }},
    {{
      "category_ko": "방문 명소",
      "query": "4월 제주도 가볼만한 곳 베스트 {year}"
    }},
    {{
      "category_ko": "쇼핑 정보",
      "query": "제주도 기념품 쇼핑 {year} 추천"
    }}
  ]
}}
```""",
            }
        ]
        result = self.chat_json(messages, max_tokens=2000)
        if isinstance(result, dict) and "sub_searches" in result:
            logger.info(f"[ResearchAgent] AI 검색 계획 수립 완료: {result.get('location', '')}에 대한 {len(result['sub_searches'])}개 하위 주제")
            return result
        
        logger.warning("[ResearchAgent] AI 검색 계획 수립 실패. 기본 계획으로 대체합니다.")
        # AI 계획 수립 실패 시 폴백
        location = topic_hint.split()[0]
        return {
            "location": location,
            "sub_searches": [
                {"category_ko": "날씨", "query": f"{location} 날씨"},
                {"category_ko": "맛집", "query": f"{location} 맛집"},
                {"category_ko": "가볼만한곳", "query": f"{location} 가볼만한곳"},
            ]
        }

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
