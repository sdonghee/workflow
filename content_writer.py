"""
AI 콘텐츠 생성 모듈
OpenRouter API를 사용하여 저작권에 걸리지 않는 고품질 블로그 포스트를 생성합니다.
"""
import logging
from openai import OpenAI
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

MODEL = "nousresearch/hermes-3-llama-3.1-405b:free"


def generate_blog_post(category, article, image_url="", image_alt=""):
    """
    AI로 블로그 포스트 생성

    Returns:
        dict: {title, content_html, tags, meta_description}
    """
    category_prompts = {
        "여행_항공_호텔": """
당신은 사람들의 시선을 사로잡는 마케팅 전문가이자, 매력적인 여행/항공/호텔 블로그 콘텐츠를 기획·제작하는 AI입니다.
독자들이 여행 계획을 실제로 세울 때 즉시 써먹을 수 있는 실용 정보를 재미있고 친근하게 전달합니다.
딱딱한 뉴스 문체 대신 독자와 대화하듯 구어체로, 이모지와 강조를 풍부하게 활용해 시각적 가독성을 극대화합니다.
""",
        "정부혜택": """
당신은 사람들의 시선을 사로잡는 마케팅 전문가이자, 정부 복지·혜택 정보를 쉽고 매력적으로 전달하는 AI입니다.
놓치면 손해인 정부 지원금, 복지 혜택, 신청 방법을 독자가 즉시 행동하도록 유도하는 문체로 작성합니다.
복잡한 내용은 표·목록·이모지로 단순화하여 누구나 이해할 수 있게 만듭니다.
""",
        "건강": """
당신은 사람들의 시선을 사로잡는 마케팅 전문가이자, 건강 정보 블로그 콘텐츠를 매력적으로 제작하는 AI입니다.
의학적으로 신뢰할 수 있는 정보를 일상 언어로 풀어내고, 독자가 오늘 당장 실천할 수 있는 팁을 강조합니다.
이모지·강조·목록을 적극 활용해 읽기 쉽고 공유하고 싶은 콘텐츠를 만듭니다.
"""
    }

    system_prompt = category_prompts.get(
        category,
        "당신은 사람들의 시선을 사로잡는 마케팅 전문가이자 생활 정보 블로그 콘텐츠 제작 AI입니다. "
        "시각적 가독성과 독자 참여를 극대화하는 매력적인 블로그 포스트를 작성합니다."
    )

    user_prompt = f"""
다음 기사/정보를 바탕으로 네이버 블로그 포스트를 작성해주세요.

참고 기사 제목: {article.get('title', '')}
참고 내용: {article.get('summary', '')}
추가 내용: {article.get('content', '')}
기사 원본 링크: {article.get('link', '')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 핵심 작성 원칙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**[저작권]** 원문 절대 복사 금지. 모든 내용을 완전히 새 문장으로 재구성.
**[리서치]** 참고 기사 내용에만 국한하지 말고, 주제와 관련된 배경 지식·통계·전문가 견해·실용 팁을 추가 보충하여 원본보다 풍부한 콘텐츠를 만들 것.
**[문체]** 딱딱한 뉴스체 금지. 독자와 대화하는 구어체·친근한 어조 사용.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 작성 요건
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 1. 제목 (2개 제안 → 더 매력적인 것 1개를 "title"로 선택)
- 독자 눈길을 즉시 사로잡는 트렌디한 제목
- 핵심 키워드 + 흥미 유발 문구 + 이모지 포함
- 예시 형식: "🚨 당신이 놓치면 후회할 [키워드] 꿀팁 대방출! 🍯"

### 2. 서론 (2~3문장)
- 독자 공감·궁금증 자극
- 핵심 이모지로 시선 집중
- "이거 알고 계셨나요?" 식의 훅(hook)으로 시작

### 3. 본문 구성
- **소제목 최소 4개** (각각 이모지 포함, 폰트 크게 → h2 태그 사용)
- 각 소제목 아래 3~5문장 + 글머리 기호(• 또는 숫자) 목록
- 중요 수치·핵심 팁은 <strong> 볼드 + ⭐ ✅ 🔑 강조 이모지
- 비교·정리 정보는 HTML <table> 활용
- 구어체 표현으로 몰입감 강화 (예: "사실 이게 핵심이에요!", "놀랍죠?")

### 4. 관련 정보 링크 섹션
- 독자가 추가 정보를 얻을 수 있는 공신력 있는 외부 링크 1~2개 제안
- (정부 기관, 공공기관, 학술 자료 등 - 실존 가능한 URL 형식으로)

### 5. 결론 (2~3문장)
- 내용 요약 + 긍정 메시지 + 즉각 행동 유도
- 이모지로 마무리

### 6. 정보 출처
- 포스트 하단에 📌 **정보 출처:** [기사 원본 링크] 표기

### 7. SEO
- 제목·본문에 카테고리({category.replace('_', '/')}) 핵심 키워드 자연스럽게 반복 포함

### 8. 태그 (1만 트래픽 목표)
- 한국어 태그 15개 + 영어 태그 10개 = 총 25개
- 3가지 형식으로 모두 제공:
  - `tags_hash`: "#태그1 #태그2 #태그3 ..." (# + 스페이스 구분)
  - `tags_comma`: "태그1, 태그2, 태그3, ..." (, 구분)
  - `tags_plain`: "태그1 태그2 태그3 ..." (스페이스 구분)
- 고검색량 키워드 위주로 선정

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 출력 형식 (JSON 엄수)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{{
    "title": "최종 선택한 블로그 제목 (이모지 포함)",
    "title_alt": "대안 제목 (이모지 포함)",
    "content_html": "완성된 HTML 본문 (h2, h3, p, ul, ol, li, table, strong, em 태그 적극 활용. 인라인 style로 h2 font-size:1.4em, color:#1a1a2e 적용. 테이블은 border-collapse:collapse, 셀 padding:8px, border:1px solid #ddd 스타일 적용)",
    "tags_hash": "#태그1 #태그2 #태그3 ...",
    "tags_comma": "태그1, 태그2, 태그3, ...",
    "tags_plain": "태그1 태그2 태그3 ...",
    "tags": "태그1,태그2,태그3,...",
    "meta_description": "검색 결과 노출용 설명 (150자 이내, 핵심 키워드 포함)"
}}

반드시 위 JSON 형식으로만 응답하고, JSON 외 다른 텍스트는 절대 포함하지 마세요.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        response_text = response.choices[0].message.content.strip()

        # JSON 파싱
        import json
        import re

        # JSON 블록 추출
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(response_text)

        # 이미지가 있으면 본문 상단에 추가
        if image_url:
            image_html = f'<div style="text-align:center; margin:20px 0;"><img src="{image_url}" alt="{image_alt}" style="max-width:100%; border-radius:10px; box-shadow:0 4px 8px rgba(0,0,0,0.2);"></div>\n'
            result["content_html"] = image_html + result.get("content_html", "")

        logger.info(f"블로그 포스트 생성 완료: {result.get('title', '')}")
        return result

    except Exception as e:
        logger.error(f"블로그 포스트 생성 실패: {e}")
        return None


def generate_visual_summary(topic, category):
    """
    시각화된 정보 요약 섹션 생성 (표, 체크리스트 등)
    """
    prompt = f"""
'{topic}'에 관한 핵심 정보를 HTML 형식의 시각적 요약으로 만들어주세요.

요구사항:
- HTML 표(table) 또는 체크리스트 형식
- 최대 10개 항목
- 카테고리: {category}
- 스타일: 깔끔하고 모바일 친화적

HTML 코드만 반환하세요 (설명 없이).
"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"시각화 요약 생성 실패: {e}")
        return ""


def create_post_from_scratch(category, topic, category_config):
    """
    특정 주제로 처음부터 블로그 포스트 생성 (참고 기사 없을 때)
    """
    keyword = category_config.get("keywords", [topic])[0]

    dummy_article = {
        "title": f"{keyword} 완벽 가이드",
        "summary": f"{keyword}에 관한 최신 정보와 유용한 팁을 정리했습니다.",
        "content": "",
    }

    return generate_blog_post(category, dummy_article)
