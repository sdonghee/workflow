"""
AI 콘텐츠 생성 모듈
OpenRouter API를 사용하여 저작권에 걸리지 않는 고품질 블로그 포스트를 생성합니다.
"""
import json
from typing import Optional, Union
import logging
import re

from openai import OpenAI
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

MODEL = "nousresearch/hermes-3-llama-3.1-405b:free"

# ─────────────────────────────────────────────────────────────────────────────
# 네이버 블로그 HTML 렌더링 규칙 (SmartEditor 기준)
#
# ✅ 지원: div·p·span·h2·h3·ul·ol·li·table·tr·th·td·strong·em·a·img·hr·br
#          인라인 style (font-size·color·background-color·padding·margin·
#          border·border-radius·text-align·line-height·font-weight·width·
#          max-width·box-shadow·vertical-align)
# ❌ 미지원: <script> <style> <link> CSS 클래스(외부 시트) JS 이벤트핸들러
#            CSS 애니메이션·transform·calc()
# 📐 레이아웃: PC 본문 폭 최대 760 px / 모바일 자동 반응형
#              이미지 반드시 max-width:100%
# 🔤 폰트: 네이버는 나눔고딕·맑은고딕 시스템 폰트를 기본 사용.
#          font-family 인라인 지정 가능하지만 외부 웹폰트(@import) 불가.
#          권장 font-family: "'Nanum Gothic', '맑은 고딕', sans-serif"
# ─────────────────────────────────────────────────────────────────────────────
NAVER_HTML_GUIDE = """
=== 네이버 블로그 HTML 렌더링 핵심 규칙 ===

[폰트]
- 본문 기본: font-size:16px; line-height:1.8; font-family:'Nanum Gothic','맑은 고딕',sans-serif; color:#333;
- 소제목(h2): font-size:22px; font-weight:bold; color:#1a1a2e; border-bottom:3px solid #3498DB; padding-bottom:10px; margin:35px 0 15px;
- 소소제목(h3): font-size:18px; font-weight:bold; color:#2C3E50; margin:25px 0 10px;
- 강조 숫자: font-size:28px; font-weight:900; color:#E74C3C;
- 뱃지/태그: font-size:13px; background:#3498DB; color:white; padding:3px 10px; border-radius:12px;

[컨테이너 패턴]
① 정보 콜아웃 (파란 테두리):
<div style="background:#EBF5FB;border-left:5px solid #2E86C1;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;font-family:'Nanum Gothic','맑은 고딕',sans-serif;">

② 팁 박스 (초록):
<div style="background:#E9F7EF;border:1px solid #27AE60;padding:16px 20px;margin:20px 0;border-radius:8px;font-family:'Nanum Gothic','맑은 고딕',sans-serif;">

③ 주의/경고 (빨강):
<div style="background:#FDEDEC;border-left:5px solid #E74C3C;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;font-family:'Nanum Gothic','맑은 고딕',sans-serif;">

④ 목차 박스:
<div style="background:#F8F9FA;border:1px solid #DEE2E6;padding:20px 24px;margin:25px 0;border-radius:10px;font-family:'Nanum Gothic','맑은 고딕',sans-serif;">

⑤ 숫자 강조 카드:
<div style="display:inline-block;background:#2C3E50;color:white;padding:10px 20px;border-radius:8px;margin:5px;text-align:center;font-family:'Nanum Gothic','맑은 고딕',sans-serif;">

[표 스타일]
<table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:15px;font-family:'Nanum Gothic','맑은 고딕',sans-serif;">
  <thead><tr>
    <th style="background:#2C3E50;color:white;padding:12px 14px;text-align:center;border:1px solid #ddd;">헤더</th>
  </tr></thead>
  <tbody>
    <tr style="background:#ffffff;"><td style="padding:11px 14px;border:1px solid #ddd;vertical-align:middle;"></td></tr>
    <tr style="background:#F8F9FA;"><td style="padding:11px 14px;border:1px solid #ddd;vertical-align:middle;"></td></tr>
  </tbody>
</table>

[이미지]
<div style="text-align:center;margin:25px 0;">
  <img src="{URL}" alt="{ALT}" style="max-width:100%;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.15);">
  <p style="font-size:13px;color:#888;margin-top:8px;">{캡션}</p>
</div>

[구분선]
<hr style="border:none;border-top:2px solid #EAECEE;margin:35px 0;">
"""

# ─────────────────────────────────────────────────────────────────────────────
# 카테고리별 핵심 SEO 키워드 클러스터
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_SEO = {
    "여행_항공_호텔": {
        "core": ["항공권 할인", "호텔 예약", "여행 꿀팁", "해외여행", "국내여행"],
        "long_tail": ["항공권 싸게 사는 법", "호텔 얼리버드 할인", "여행 경비 절약", "항공 마일리지 적립"],
        "trending": ["가성비 여행지", "숨은 여행지", "혼자 여행", "한달살기"],
    },
    "정부혜택": {
        "core": ["정부 지원금", "복지 혜택", "지원금 신청", "국가 보조금", "복지로"],
        "long_tail": ["정부지원금 신청방법", "놓치기 쉬운 복지혜택", "2024 정부혜택 총정리"],
        "trending": ["청년 지원금", "출산 지원금", "에너지 바우처", "긴급복지지원"],
    },
    "건강": {
        "core": ["건강 관리", "건강 정보", "질병 예방", "건강 검진", "영양제"],
        "long_tail": ["면역력 높이는 방법", "건강검진 항목 총정리", "영양제 올바른 복용법"],
        "trending": ["건강 식품", "운동 루틴", "수면 건강", "장 건강"],
    },
}


def _build_system_prompt(category: str) -> str:
    seo = CATEGORY_SEO.get(category, {})
    core_kw = "·".join(seo.get("core", [])[:3]) or category.replace("_", "/")

    persona = {
        "여행_항공_호텔": (
            "당신은 연 1,000만 PV를 달성한 시니어 여행 블로거입니다. "
            f"'{core_kw}' 분야의 최고 전문가로서, 독자가 읽고 바로 행동에 옮길 수 있는 "
            "압도적으로 유용하고 시각적으로 아름다운 블로그 포스트를 작성합니다."
        ),
        "정부혜택": (
            "당신은 연 1,000만 PV를 달성한 복지·정책 정보 전문 블로거입니다. "
            f"'{core_kw}' 분야에서 복잡한 정부 정보를 누구나 이해하도록 쉽게 풀어내고, "
            "독자가 신청 버튼을 바로 누르도록 강력하게 행동을 유도하는 콘텐츠를 만듭니다."
        ),
        "건강": (
            "당신은 연 1,000만 PV를 달성한 헬스케어 콘텐츠 전문 블로거입니다. "
            f"'{core_kw}' 분야의 의학·과학 정보를 신뢰감 있게 전달하되, "
            "독자가 오늘 당장 실천할 수 있는 구체적인 행동 가이드를 제공합니다."
        ),
    }

    base = persona.get(
        category,
        f"당신은 연 1,000만 PV를 달성한 '{core_kw}' 전문 블로거입니다. "
        "독자를 완전히 사로잡는 시각적으로 아름답고 정보가 풍부한 포스트를 작성합니다.",
    )

    return (
        base
        + "\n\n"
        + "핵심 원칙:\n"
        "1. 독자가 스크롤을 멈추고 저장·공유하고 싶어지는 콘텐츠를 만든다.\n"
        "2. 원본 기사보다 2~3배 풍부한 정보를 담는다 (배경지식·통계·전문가 견해·실용팁 추가).\n"
        "3. 네이버 블로그 HTML 렌더링 규칙을 완벽히 준수하여 실제로 예쁘게 보이게 만든다.\n"
        "4. 원문 복사 절대 금지. 완전히 새 문장으로 재창조.\n"
        "5. 딱딱한 뉴스체 금지. 친근하고 몰입감 있는 구어체 사용."
    )


def _build_user_prompt(category: str, article: dict) -> str:
    seo = CATEGORY_SEO.get(category, {})
    kw_hint = (
        f"핵심 SEO 키워드 클러스터:\n"
        f"  - 주요: {', '.join(seo.get('core', []))}\n"
        f"  - 롱테일: {', '.join(seo.get('long_tail', []))}\n"
        f"  - 트렌딩: {', '.join(seo.get('trending', []))}"
        if seo
        else f"카테고리: {category.replace('_', '/')}"
    )

    return f"""
아래 기사를 씨앗(seed)으로 삼아, 네이버 블로그 1만뷰 포스트를 HTML로 완성해주세요.
원본 기사보다 훨씬 풍부하고 독자에게 더 가치 있는 콘텐츠를 만드는 것이 목표입니다.

──────────────────────────────
📰 참고 기사 정보
──────────────────────────────
제목: {article.get('title', '')}
요약: {article.get('summary', '')}
본문: {article.get('content', '')}
원본 링크: {article.get('link', '')}

──────────────────────────────
🎯 SEO 전략
──────────────────────────────
{kw_hint}
→ 위 키워드를 제목·서론·소제목·본문에 자연스럽게 분산 배치할 것.

──────────────────────────────
🏗️ 필수 콘텐츠 구조 (이 순서대로 HTML 작성)
──────────────────────────────

[A] 히어로 헤드라인 섹션
- 제목 뱃지: <span style="background:#E74C3C;color:white;...">카테고리</span>
- 강력한 서브타이틀 (1문장, 핵심 수치 포함)
- 독자 공감 훅 문장 (2~3문장, "이거 알고 계셨나요?" / "사실 대부분이 모릅니다" 형식)
- 작성일 + 예상 읽기 시간 표시

[B] 목차 박스 (필수)
- 파란 콜아웃 박스 안에 본문 소제목 4~6개를 번호 목록으로 정리
- 독자가 원하는 섹션으로 바로 점프할 수 있도록 안내

[C] 핵심 통계/수치 하이라이트 카드 (선택적, 있으면 강렬함)
- 3개의 숫자 강조 카드 (예: "67% 절약", "연간 120만원", "3단계")
- 배경색: #2C3E50 / 숫자: 크고 흰색 / 설명: 작은 글씨

[D] 본문 섹션 (소제목 최소 4개, 최대 6개)
각 섹션은 다음 패턴으로 구성:
  1. <h2> 소제목 (이모지 + 텍스트, 네이버 h2 스타일 적용)
  2. 도입 문장 2~3개 (구어체, 독자와 대화하듯)
  3. 핵심 정보: 표 또는 ul/ol 목록 (글머리 기호 활용)
  4. 팁 박스 또는 콜아웃 박스 (섹션당 최소 1개)
  5. 마무리 문장 또는 실천 가이드

반드시 포함할 섹션 유형:
  ✅ 비교 분석표 (table): 옵션·방법·상품 등을 한눈에 비교
  ✅ 단계별 가이드 (ol): "STEP 1 → STEP 2 → STEP 3" 형식
  ✅ 주의사항/실수 피하기: 빨간 경고 박스
  ✅ 전문가 팁 or 인사이트: 초록 팁 박스

[E] FAQ 섹션
- 독자들이 가장 많이 묻는 질문 3~4개
- Q: 질문 / A: 간결하고 명확한 답변
- <h3> 스타일로 Q 표시

[F] 결론 + 행동 촉구
- 3~4문장: 핵심 요약 → 독자에게 지금 당장 할 수 있는 행동 1가지 제시
- 이모지로 긍정 에너지 마무리
- 댓글·공유 유도 문구

[G] 관련 정보 링크
- 공신력 있는 외부 링크 1~2개 (정부 기관, 공공기관 등)

[H] 출처 표기
- 📌 **정보 출처:** {article.get('link', '해당 기사 링크')}

──────────────────────────────
🎨 네이버 블로그 HTML 스타일 규칙 (필수 준수)
──────────────────────────────
{NAVER_HTML_GUIDE}

──────────────────────────────
🏷️ 태그 전략 (1만 트래픽 목표)
──────────────────────────────
- 한국어 태그 15개 + 영어 태그 10개 = 총 25개
- 구성: 메인키워드(검색량 높음) + 롱테일키워드 + 트렌딩키워드 + 카테고리키워드
- 태그는 3가지 형식으로 모두 생성:
  · tags_hash  : "#태그1 #태그2 #태그3 ..." (각 태그 앞에 # / 스페이스로 구분)
  · tags_comma : "태그1, 태그2, 태그3, ..." (쉼표+스페이스로 구분)
  · tags_plain : "태그1 태그2 태그3 ..."    (스페이스로만 구분)
  · tags       : "태그1,태그2,태그3,..."    (쉼표만, API 전송용)

──────────────────────────────
📤 출력 형식 (JSON 단독 출력, 다른 텍스트 금지)
──────────────────────────────
{{
  "title": "클릭하고 싶은 최종 제목 (이모지 포함, 30~45자)",
  "title_alt": "대안 제목 (다른 감정·관점으로 접근)",
  "content_html": "완성된 네이버 블로그 HTML 본문 전체 (위 [A]~[H] 포함)",
  "tags_hash": "#태그1 #태그2 ... (25개)",
  "tags_comma": "태그1, 태그2, ... (25개)",
  "tags_plain": "태그1 태그2 ... (25개)",
  "tags": "태그1,태그2,... (25개, 쉼표만)",
  "meta_description": "검색 결과 노출 설명 (핵심 키워드 포함, 140자 이내)"
}}
"""


def generate_blog_post(category: str, article: dict, image_url: str = "", image_alt: str = "") -> Optional[dict]:
    """
    AI로 네이버 블로그 포스트 생성

    Returns:
        dict: {title, title_alt, content_html, tags_hash, tags_comma, tags_plain, tags, meta_description}
    """
    system_prompt = _build_system_prompt(category)
    user_prompt = _build_user_prompt(category, article)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=8000,
            temperature=0.8,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        response_text = response.choices[0].message.content.strip()

        # JSON 블록 추출 (```json ... ``` 혹은 순수 { } 모두 처리)
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            brace_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            result = json.loads(brace_match.group() if brace_match else response_text)

        # 이미지 삽입: 히어로 이미지로 본문 최상단에 배치
        if image_url:
            caption = image_alt or article.get("title", "")
            image_html = (
                f'<div style="text-align:center;margin:0 0 30px;">'
                f'<img src="{image_url}" alt="{image_alt}" '
                f'style="max-width:100%;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.15);">'
                f'<p style="font-size:13px;color:#888;margin-top:8px;'
                f'font-family:\'Nanum Gothic\',\'맑은 고딕\',sans-serif;">{caption}</p>'
                f"</div>\n"
            )
            result["content_html"] = image_html + result.get("content_html", "")

        # tags 필드 누락 방어
        if "tags" not in result and "tags_comma" in result:
            result["tags"] = result["tags_comma"].replace(", ", ",")

        logger.info(f"블로그 포스트 생성 완료: {result.get('title', '')}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {e}\n원문: {response_text[:300]}")
        return None
    except Exception as e:
        logger.error(f"블로그 포스트 생성 실패: {e}")
        return None


def generate_visual_summary(topic: str, category: str) -> str:
    """
    시각화된 정보 요약 섹션 생성 (표·체크리스트)
    네이버 블로그 인라인 스타일 규칙 준수
    """
    prompt = f"""
'{topic}'에 관한 핵심 정보를 네이버 블로그용 HTML로 만들어주세요.

요구사항:
- border-collapse, padding, border 인라인 스타일이 적용된 table 또는 체크리스트(ul)
- 헤더 행: background:#2C3E50; color:white; padding:12px;
- 짝수 행: background:#F8F9FA;
- 최대 10개 항목
- 카테고리: {category}
- font-family: 'Nanum Gothic','맑은 고딕',sans-serif 적용

HTML 코드만 반환하세요 (설명 없이).
"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"시각화 요약 생성 실패: {e}")
        return ""


def create_post_from_scratch(category: str, topic: str, category_config: dict) -> Optional[dict]:
    """
    특정 주제로 처음부터 블로그 포스트 생성 (참고 기사 없을 때)
    """
    seo = CATEGORY_SEO.get(category, {})
    keyword = (seo.get("core") or category_config.get("keywords") or [topic])[0]

    dummy_article = {
        "title": f"{keyword} 완벽 가이드 {__import__('datetime').date.today().year}",
        "summary": (
            f"{keyword}에 관한 최신 정보와 전문가 추천 팁을 총정리했습니다. "
            f"놓치면 손해인 핵심 내용만 엄선했습니다."
        ),
        "content": "",
        "link": "",
    }

    return generate_blog_post(category, dummy_article)
