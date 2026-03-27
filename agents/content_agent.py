"""
에이전트 2 - 콘텐츠 작성 에이전트
기사를 깊이 있는 블로그 콘텐츠(구조화된 정보)로 변환
모델: Nous Hermes 405B → Llama 3.3 70B → Gemma 3 27B (폴백 순서)
"""
from typing import Optional, Union
import logging
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, HERMES_405B, NEMOTRON_120B, GPT_OSS_120B, QWEN3_80B, LLAMA_70B, MINIMAX, MISTRAL_24B, GEMMA_27B, DOLPHIN_24B
from config import CATEGORIES
from content_writer import CATEGORY_SEO

logger = logging.getLogger(__name__)


class ContentAgent(BaseAgent):
    """블로그 콘텐츠 작성 전문 에이전트 (Hermes 405B 메인)"""

    def __init__(self):
        # 콘텐츠 품질 최우선 → 대형 모델 우선
        super().__init__(
            model=HERMES_405B,
            fallback_models=[NEMOTRON_120B, GPT_OSS_120B, QWEN3_80B, LLAMA_70B, MINIMAX, MISTRAL_24B, GEMMA_27B, DOLPHIN_24B],
        )

    def generate(self, article: dict, category: str) -> Optional[dict]:
        """
        기사를 구조화된 블로그 콘텐츠 데이터로 변환.
        원본 기사보다 3배 풍부한 정보를 담는 것이 목표.

        Returns:
            {title, title_alt, hook, main_points, comparison_data,
             faq, conclusion, cta, tags_ko, tags_en}
        """
        seo     = CATEGORY_SEO.get(category, {})
        cat_cfg = CATEGORIES.get(category, {})

        core_kw   = ", ".join(seo.get("core", [])[:4])
        tail_kw   = ", ".join(seo.get("long_tail", [])[:3])
        trend_kw  = ", ".join(seo.get("trending", [])[:3])
        base_tags = cat_cfg.get("tags", [])[:6]

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 사람들의 시선을 사로잡는 마케팅 전문가이자, "
                    "매력적인 생활 정보 블로그 콘텐츠를 기획·제작하는 AI입니다.\n"
                    "【핵심 원칙】\n"
                    "1. 원문 복사 절대 금지 — 완전히 새로운 문장으로 재창조\n"
                    "2. 참고 기사보다 3배 풍부한 정보 (리서치로 배경·통계·전문가 견해·실천팁 추가)\n"
                    "3. ★★ 하나의 주제에만 집중 ★★ — 여러 주제를 절대 섞지 말 것\n"
                    "4. 독자와 대화하는 친근한 구어체\n"
                    "5. 독자가 오늘 바로 써먹을 수 있는 실용 정보 중심"
                ),
            },
            {
                "role": "user",
                "content": f"""다음 기사를 씨앗으로 네이버 블로그 1만뷰 콘텐츠를 기획하세요.

━━ 참고 기사 ━━
제목: {article.get('title', '')}
요약: {article.get('summary', '')}
본문 앞부분: {article.get('content', '')[:2000]}
원본 링크: {article.get('link', '')}

━━ SEO 키워드 ━━
핵심: {core_kw}
롱테일: {tail_kw}
트렌딩: {trend_kw}
카테고리: {category.replace('_', '/')}
오늘 날짜: {date.today().strftime('%Y년 %m월 %d일')}

━━ 작성 요건 ━━
★ 주제 단일 집중: 기사에서 가장 강력한 핵심 주제 1개만 골라 깊게 파고들기
  → "항공권 할인"이면 항공권 할인만 / "여행지 추천"이면 여행지만 (섞기 금지)

1. 매력적인 제목 2개: 이모지 포함, 30~45자, "이걸 모르면 손해!" 클릭 유발
2. 서론 훅: 독자 공감 + 궁금증 자극 2~3문장
3. 핵심 포인트 5~7개: 소제목(font-size:22px 강조) + 본문 3~5문장 + 팁
4. 비교표(table) 또는 단계별 가이드(ol) 반드시 포함
5. FAQ 3~4개: 독자들이 가장 많이 검색하는 질문
6. 결론 + 즉각 행동 유도 문구
7. 한국어 태그 15개 + 영어 태그 10개 (고검색량 우선)
   참고 태그: {', '.join(base_tags)}

JSON으로만 반환:
{{
  "title": "최고 제목 (이모지 포함)",
  "title_alt": "대안 제목 (다른 감정/관점)",
  "hook": "서론 훅 (2~3문장)",
  "main_points": [
    {{
      "heading": "소제목 (이모지 포함, 22px 강조)",
      "content": "본문 3~5문장 (구어체, 수치/사실/팁 포함)",
      "tip": "⭐ 핵심 팁 1줄 (굵은 글씨)",
      "box_type": "info|tip|warning"
    }}
  ],
  "comparison_data": {{
    "type": "table",
    "caption": "비교 표 제목",
    "headers": ["항목1", "항목2", "항목3"],
    "rows": [["값1", "값2", "값3"]]
  }},
  "faq": [
    {{"q": "질문?", "a": "명확한 답변 2~3문장"}}
  ],
  "conclusion": "결론 2~3문장 (이모지 포함, 독자 행동 유도)",
  "cta": "지금 바로 행동 유도 문구",
  "tags_ko": ["한국어태그1", ...15개],
  "tags_en": ["EnglishTag1", ...10개]
}}""",
            },
        ]

        result = self.chat_json(messages, max_tokens=7000)

        # 최소 검증
        if isinstance(result, dict) and result.get("title"):
            logger.info(f"[ContentAgent] 콘텐츠 생성 완료: {result['title'][:40]}")
            return result

        logger.error("[ContentAgent] 콘텐츠 생성 실패 또는 형식 오류")
        return None
