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
당신은 여행 전문 블로거입니다. 여행, 항공, 호텔에 관한 유용한 정보와 후기를 씁니다.
독자들이 실제로 여행 계획을 세울 때 도움이 되는 실용적인 정보를 포함해야 합니다.
""",
        "정부혜택": """
당신은 정부 복지 및 혜택 정보를 전문으로 하는 블로거입니다.
일반 시민들이 놓치기 쉬운 정부 지원금, 복지 혜택, 신청 방법 등을 쉽게 설명합니다.
""",
        "건강": """
당신은 건강 정보를 전문으로 하는 블로거입니다.
의학적으로 검증된 건강 정보와 일상에서 실천할 수 있는 건강 관리 방법을 알려줍니다.
"""
    }

    system_prompt = category_prompts.get(category, "당신은 유용한 정보를 전달하는 블로거입니다.")

    user_prompt = f"""
다음 기사/정보를 참고하여 네이버 블로그에 올릴 포스트를 작성해주세요.

참고 기사 제목: {article.get('title', '')}
참고 내용: {article.get('summary', '')}
추가 내용: {article.get('content', '')}

## 작성 요건:
1. **제목**: 클릭하고 싶은 매력적인 제목 (30자 이내, 핵심 키워드 포함)
2. **본문**: 1500~2500자 분량의 상세한 내용
3. **구조**: 서론-본론(3~5개 섹션)-결론 구조
4. **가독성**:
   - 각 섹션에 이모지 포함 (✈️🏨🌟💡🏥 등)
   - 중요 정보는 표(HTML table) 또는 목록으로 정리
   - 핵심 키워드는 **볼드** 처리
5. **저작권**: 원본을 그대로 복사하지 말고 완전히 새롭게 재작성
6. **SEO**: 카테고리 관련 핵심 키워드 자연스럽게 포함
7. **태그**: 관련 태그 10개 (쉼표로 구분)
8. **카테고리**: {category.replace('_', '/')}

## 출력 형식 (JSON):
{{
    "title": "블로그 포스트 제목",
    "content_html": "HTML 형식의 본문 내용 (h2, h3, p, ul, table 태그 사용)",
    "tags": "태그1,태그2,태그3,...",
    "meta_description": "검색 결과에 표시될 설명 (150자 이내)"
}}

반드시 위 JSON 형식으로만 응답하세요.
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
