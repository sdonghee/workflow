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

        # 배경 정보 조합 — "기사" 표현 없이 주제·내용만 추출
        info_block = ""
        for a in articles[:5]:
            title   = a.get("title", "").strip()
            summary = a.get("summary", "").strip()
            body    = a.get("content", "").strip()[:1200]
            if title:
                info_block += f"\n[정보]\n주제: {title}\n내용: {summary}\n{body}\n"

        n = len(articles)

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 여행/생활정보 전문 블로거입니다.\n"
                    "독자에게 직접 경험과 지식을 전하는 글을 씁니다.\n"
                    "【절대 규칙】\n"
                    "1. '기사', '출처', '보도', '링크', '원본' 등 언급 금지 — 내가 아는 정보로 쓸 것\n"
                    "2. 한 글 = 한 질문 (주제 혼합 금지)\n"
                    "3. 핵심 포인트 최대 3개\n"
                    "4. 타깃 독자 1명 명확히\n"
                    "5. 과장 수치 금지 — '87%', '절대 안 알려주는' 금지\n"
                    "6. 제공된 배경 정보를 내 지식으로 녹여 쓸 것 (복사 금지)"
                ),
            },
            {
                "role": "user",
                "content": f"""다음 배경 정보를 참고해 네이버 블로그 글을 써주세요.
이 블로그는 직접 경험·정보를 공유하는 채널입니다. 기사 냄새 없이 전문가의 언어로 작성하세요.

━━ 배경 정보 ━━
{info_block}

━━ SEO 키워드 ━━
핵심: {core_kw} | 롱테일: {tail_kw} | 트렌딩: {trend_kw}
카테고리: {category.replace('_', '/')} | 날짜: {date.today().strftime('%Y년 %m월 %d일')}

━━ 작성 요건 ━━

[주제]
배경 정보에서 독자가 가장 궁금해할 질문 1개만 골라라.
예) "유류할증료 올랐는데, 지금 항공권 사는 게 맞을까?" → 이 질문 하나에만 집중

[타깃 독자]
구체적으로 1명 설정 (예: "연 1~2회 여행하는 30대 직장인")

[구조]
1. 제목: 이모지 포함, 직관적 (30~40자)
   금지) "90%가 모르는", "절대 안 알려주는" 낚시 표현
2. 훅: 독자 공감 2문장 + 이 글이 답하는 질문 1문장
3. 핵심 포인트 3개 MAX
   - 소제목 + 설명 3~4문장 + 독자가 즉시 할 수 있는 행동 1가지
4. 비교표 (선택)
5. 결론 한 문장 + 즉시 실행 체크리스트 3가지

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
