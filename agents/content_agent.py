"""
에이전트 2 - 콘텐츠 작성 에이전트
기사를 깊이 있는 블로그 콘텐츠(구조화된 정보)로 변환
모델: Nous Hermes 405B → Llama 3.3 70B → Gemma 3 27B (폴백 순서)
"""
from typing import Optional, Union, List
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

    def generate(self, articles: Union[dict, List[dict]], category: str) -> Optional[dict]:
        """
        여러 기사를 종합해 구조화된 블로그 콘텐츠 데이터로 변환.
        같은 날 같은 주제 기사 3~5개를 합쳐 각 기사보다 풍부한 정보를 제공한다.

        Args:
            articles: 단일 기사 dict 또는 기사 list (여러 개 권장)
            category: 카테고리명

        Returns:
            {title, title_alt, hook, main_points, comparison_data,
             conclusion, checklist, tags_ko, tags_en}
        """
        # 단일 dict도 리스트로 통일
        if isinstance(articles, dict):
            articles = [articles]

        seo     = CATEGORY_SEO.get(category, {})
        cat_cfg = CATEGORIES.get(category, {})

        core_kw   = ", ".join(seo.get("core", [])[:4])
        tail_kw   = ", ".join(seo.get("long_tail", [])[:3])
        trend_kw  = ", ".join(seo.get("trending", [])[:3])
        base_tags = cat_cfg.get("tags", [])[:6]

        # 기사 텍스트 조합 (최대 5개, 각 1500자)
        articles_block = ""
        for i, a in enumerate(articles[:5], 1):
            articles_block += f"""
[기사 {i}]
제목: {a.get('title', '')}
출처: {a.get('source', '')}
요약: {a.get('summary', '')}
본문: {a.get('content', '')[:1500]}
링크: {a.get('link', '')}
"""

        n = len(articles)
        source_note = (
            f"오늘 발행된 {n}개 기사를 종합"
            if n > 1
            else "기사를 씨앗으로 심화 작성"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 네이버 블로그 콘텐츠 전문가입니다.\n"
                    "【핵심 원칙 — 반드시 준수】\n"
                    "1. 여러 기사를 '재조합'하는 것이 목표 — 각 기사에 없는 통찰을 추가\n"
                    "2. 한 글 = 한 질문만 답한다 (주제 혼합 금지)\n"
                    "3. 핵심 포인트 최대 3개 (독자는 3개까지만 기억함)\n"
                    "4. 타깃 독자 1명 명확히 설정\n"
                    "5. 과장 수치 금지 — '87%', '절대 안 알려주는' 금지\n"
                    "6. 원문 복사 절대 금지 — 반드시 재해석·재구성"
                ),
            },
            {
                "role": "user",
                "content": f"""다음 {n}개 기사({source_note})를 바탕으로 네이버 블로그 콘텐츠를 기획하세요.
독자 입장에서 "이 블로그가 기사보다 낫다"는 느낌을 줘야 합니다.

━━ 참고 기사들 ━━
{articles_block}

━━ SEO 키워드 ━━
핵심: {core_kw} | 롱테일: {tail_kw} | 트렌딩: {trend_kw}
카테고리: {category.replace('_', '/')} | 날짜: {date.today().strftime('%Y년 %m월 %d일')}

━━ 작성 요건 ━━

[주제 선택]
여러 기사 중 공통 핵심 질문 1개를 골라라.
예) 기사 3개가 모두 "봄 여행지"를 다룬다면 → "이번 봄, 어디 가면 후회 없을까?" 로 집중
→ 여러 주제를 섞으면 독자 이탈

[타깃 독자]
구체적으로 1명 설정 (예: "연 1~2회 여행하는 30대 직장인")

[구조 — 반드시 이 순서로]
1. 제목: 이모지 포함, 과장 없이 직관적 (30~40자)
   금지) "90%가 모르는", "절대 안 알려주는" 낚시성 표현
2. 훅: 독자 공감 2문장 + 이 글이 답하는 질문 1문장
3. 핵심 포인트 3개 MAX
   - 각 포인트: 소제목 + 설명 3~4문장 + 즉시 실행 가능한 행동 1가지
   - 여러 기사의 관점을 합쳐서 더 깊이 있게 작성
4. 비교표 (있으면 좋음, 없어도 됨)
5. 결론 핵심 한 문장 + 즉시 실행 체크리스트 3가지

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
            logger.info(f"[ContentAgent] 콘텐츠 생성 완료 (기사 {n}개 종합): {result['title'][:40]}")
            return result

        logger.error("[ContentAgent] 콘텐츠 생성 실패 또는 형식 오류")
        return None
