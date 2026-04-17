"""
에이전트 2 - 콘텐츠 작성 에이전트
기사를 깊이 있는 블로그 콘텐츠(구조화된 정보)로 변환
모델: Nous Hermes 405B → Llama 3.3 70B → Gemma 3 27B (폴백 순서)
"""
from typing import Optional
import logging
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, HERMES_405B, NEMOTRON_120B, GPT_OSS_120B, QWEN3_80B, LLAMA_70B, MINIMAX, MISTRAL_24B, GEMMA_27B, DOLPHIN_24B
from config import CATEGORIES

logger = logging.getLogger(__name__)


class ContentAgent(BaseAgent):
    """블로그 콘텐츠 작성 전문 에이전트 (Hermes 405B 메인)"""

    def __init__(self):
        super().__init__(
            model=HERMES_405B,
            fallback_models=[NEMOTRON_120B, GPT_OSS_120B, QWEN3_80B, LLAMA_70B, MINIMAX, MISTRAL_24B, GEMMA_27B, DOLPHIN_24B],
        )

    def generate(self, research_data: dict, category: str, content_type: str = "뉴스 분석") -> Optional[dict]:
        """기사 1개를 중심으로 읽고 싶은 블로그 글 생성."""
        main_topic_info = research_data.get("main_topic_info", [])
        sub_topics      = research_data.get("sub_topics", {})

        if not main_topic_info:
            logger.error("[ContentAgent] 생성 실패: 핵심 주제 정보가 없습니다.")
            return None

        today = date.today().strftime("%Y년 %m월 %d일")

        core_article = main_topic_info[0]
        core_block = (
            f"[핵심 기사]\n"
            f"제목: {core_article.get('title', '')}\n"
            f"내용: {core_article.get('content') or core_article.get('summary', '')}"
        )[:1200]

        sub_info_lines = []
        for sub_cat, articles in sub_topics.items():
            for a in articles[:2]:
                sub_info_lines.append(f"[{sub_cat}] {a.get('title', '')}: {(a.get('summary') or '')[:150]}")
        sub_block = "[참고 정보]\n" + "\n".join(sub_info_lines) if sub_info_lines else ""

        system_prompt = f"""당신은 네이버 블로그 전문 작가입니다.
오늘({today}) 기준으로 실제 독자 1명에게 카카오톡 메시지 보내듯 씁니다.

[절대 금지 — 이 문장 패턴이 나오면 즉시 다시 써야 합니다]
- "~할 수 있습니다" → "~해요" 또는 "~됩니다"로
- "~하는 것이 중요합니다" → "이게 핵심이에요"로
- "살펴보겠습니다" → 그냥 바로 내용 시작
- "정리합니다" → 금지
- "파악할 수 있습니다" → 금지
- "실현합니다" → 금지
- 보고서처럼 들리는 문장 → 전부 금지

[반드시 지켜야 할 말투 예시]
나쁜 예: "이를 미리 체크하면 현지에서 불편을 줄일 수 있습니다."
좋은 예: "미리 체크해두면 현지에서 당황할 일이 없어요."

나쁜 예: "세미패키지는 항공·숙소는 사전 예약하고 현지 일정을 자유롭게 선택할 수 있는 형태입니다."
좋은 예: "쉽게 말하면 비행기랑 호텔만 미리 잡고, 나머지는 현지에서 알아서 하는 거예요."

나쁜 예: "독자는 패키지의 특징을 한눈에 파악할 수 있습니다."
좋은 예: "이 글 읽으면 5분 안에 다 이해돼요."

[도입부 규칙]
반드시 아래 셋 중 하나로 시작:
- 공감형: "혹시 이런 경험 있으세요?"
- 반전형: "사실 대부분이 반대로 알고 있어요."
- 직진형: "결론부터 말할게요."
절대로 "이 글에서는..." "본 포스팅은..." 같은 메타 설명으로 시작하지 마세요.

[링크 문장 규칙]
링크([텍스트](url)) 뒤에 오는 문장은 반드시 짧고 자연스럽게 끝내세요.
- 나쁜 예: "자세한 내용은 [고용24](url)에서 확인할 수 있습니다."
- 좋은 예: "자세한 내용은 [고용24](url)에서 확인해보세요."
- 나쁜 예: "[기관명](url)에서 알아볼 수 있습니다."
- 좋은 예: "[기관명](url)에서 바로 보세요."
링크 뒤에 "확인할 수 있습니다", "알아볼 수 있습니다", "파악할 수 있습니다" 절대 금지.

[구조 규칙]
- sections는 3~4개
- 각 section body는 2~3문장, 짧고 명확하게
- compare_items는 표로 만들 내용이 있을 때만 사용
- conclusion은 독자가 지금 당장 할 수 있는 행동 1가지로 끝내기
"""

        user_prompt = f"""아래 기사를 바탕으로 '{content_type}' 형식의 블로그 글을 작성해주세요.

{core_block}

{sub_block}

━━ JSON 출력 (유효한 JSON만, 다른 텍스트 없이) ━━

```json
{{
  "title": "이모지 1개 포함, 40자 이내 제목",
  "intro": "도입부 2~3문장. 공감·의외 사실·문제 제기 중 하나로 시작.",
  "sections": [
    {{
      "heading": "소제목 (번호 없이, 이모지 1개)",
      "body": "본문 2~4문장. **굵게** 강조, [기관명](url) 링크 포함.",
      "compare_items": [
        {{"label": "항목명", "value": "내용"}}
      ],
      "needs_link": true,
      "link_topic": "고용24",
      "needs_image": true,
      "image_hint": "english keywords 2-3 words"
    }}
  ],
  "conclusion": "체크리스트 또는 행동 제안 또는 선택 기준 — 2~5줄",
  "main_image_hint": "글 전체 주제 대표 이미지 영어 키워드 2~3단어",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5", "태그6", "태그7", "태그8", "태그9", "태그10"]
}}
```

규칙:
- sections는 3~5개
- compare_items는 비교 정보가 없으면 빈 배열 []
- needs_link가 false이면 link_topic은 빈 문자열
- needs_image가 false이면 image_hint는 빈 문자열
- 해시태그(#)는 tags 배열에만. intro·body·conclusion에 넣지 마세요.
- 링크 사용 규칙:
  금지: "[기관명](url)에서 확인할 수 있습니다" / "에서 볼 수 있습니다" / "에서 알아볼 수 있습니다"
  허용: "[기관명](url)를 참고하세요" / "[기관명](url)를 확인해보세요" / "[기관명](url) 참조"
  허용: "자세한 내용은 [고용24](url)를 참고하세요"
  허용: "신청 조건은 [고용24](url)를 확인해보세요"
  링크 뒤에 "~할 수 있습니다" 계열 문장 절대 금지."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        result = self.chat_json(messages, max_tokens=8000)

        if not (isinstance(result, dict) and result.get("title") and result.get("sections")):
            logger.error(f"[ContentAgent] '{content_type}' 생성 실패 또는 필수 필드 누락")
            return None

        logger.info(f"[ContentAgent] '{content_type}' 완료: {result.get('title', '')[:50]}")
        return result
