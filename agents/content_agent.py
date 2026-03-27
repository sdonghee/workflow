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
                    "당신은 네이버 블로그 콘텐츠 전문가입니다.\n"
                    "【핵심 원칙 — 반드시 준수】\n"
                    "1. 한 글 = 한 질문만 답한다 (여러 주제 혼합 절대 금지)\n"
                    "2. 핵심 포인트는 최대 3개 (독자는 3개까지만 기억함)\n"
                    "3. 타깃 독자 1명을 명확히 설정 (예: '일정 유연한 20대 솔로 여행자')\n"
                    "4. 과장 수치 금지 — 검증 불가한 '87%', '90% 잡힌다' 같은 표현 사용 말 것\n"
                    "5. 결론을 먼저, 구체적 행동 1가지로 마무리\n"
                    "6. 원문 복사 절대 금지"
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
핵심: {core_kw} | 롱테일: {tail_kw} | 트렌딩: {trend_kw}
카테고리: {category.replace('_', '/')} | 날짜: {date.today().strftime('%Y년 %m월 %d일')}

━━ 작성 요건 ━━

[주제 선택]
기사에서 검색량이 가장 높을 것 같은 질문 하나만 고르세요.
예시: "항공권은 언제 사는 게 가장 싸나?" 또는 "LCC가 정말 더 싸나?" 중 택1
→ 두 주제를 섞으면 독자가 이탈함

[타깃 독자]
이 글을 읽을 독자 1명을 구체적으로 설정 (예: "연 1~2회 여행하는 30대 직장인")

[구조 — 반드시 이 순서로]
1. 제목: 이모지 포함, 클릭 유발하되 과장 없이 (30~40자)
   예) "항공권 싸게 사는 법, 결국 중요한 건 이 3가지" (과장 없이 직관적)
   금지) "90%가 모르는", "절대 안 알려주는" 같은 낚시성 표현
2. 훅: 독자 공감 2문장 + 이 글이 답하는 질문 1문장
3. 핵심 포인트 3개 MAX (절대 4개 이상 금지)
   - 각 포인트: 소제목 + 설명 3~4문장 + 독자가 즉시 할 수 있는 행동 1가지
   - 수치 사용 시: "출발 50일 전이 통계상 유리한 편" (검증 가능한 범위로)
4. 비교표 1개 (있으면 좋음, 없어도 됨)
5. 결론: "이 글의 핵심 한 문장" + 지금 당장 할 수 있는 행동 체크리스트 3개

참고 태그: {', '.join(base_tags)}

JSON으로만 반환:
{{
  "title": "제목 (이모지 포함, 과장 없이 직관적)",
  "title_alt": "대안 제목",
  "target_reader": "타깃 독자 한 줄 설명",
  "hook": "공감 2문장 + 이 글이 답하는 질문 1문장",
  "main_points": [
    {{
      "heading": "소제목 (이모지 포함)",
      "content": "설명 3~4문장 (구어체, 과장 수치 없이)",
      "action": "독자가 지금 당장 할 수 있는 행동 1가지",
      "box_type": "tip|info|warning"
    }}
  ],
  "comparison_data": {{
    "caption": "비교표 제목",
    "headers": ["항목1", "항목2", "항목3"],
    "rows": [["값1", "값2", "값3"]]
  }},
  "conclusion": "이 글의 핵심 한 문장 (이모지 포함)",
  "checklist": ["지금 바로 할 행동1", "할 행동2", "할 행동3"],
  "tags_ko": ["한국어태그1"],
  "tags_en": ["EnglishTag1"]
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
