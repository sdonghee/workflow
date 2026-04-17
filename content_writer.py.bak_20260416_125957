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
        "여행_항공_호텔": f"당신은 '{core_kw}' 전문 블로거입니다.",
        "정부혜택": f"당신은 '{core_kw}' 전문 블로거입니다.",
        "건강": f"당신은 '{core_kw}' 전문 블로거입니다.",
    }

    base = persona.get(category, f"당신은 '{core_kw}' 전문 블로거입니다.")

    return (
        base
        + "\n\n"
        "【반드시 지켜야 할 원칙】\n"
        "1. 한 글 = 한 질문만 답한다 (주제 혼합 절대 금지)\n"
        "2. 핵심 포인트는 최대 3개 (독자는 3개까지만 기억함, 7개 나열 금지)\n"
        "3. 타깃 독자 1명을 명확히 정한다\n"
        "4. 과장 수치 금지 ('90%가 모른다', '87% 정확도' 등 검증 불가 수치 사용 말 것)\n"
        "5. 결론을 먼저 제시하고, 독자가 지금 당장 할 행동 1가지로 마무리\n"
        "6. 원문 복사 절대 금지\n"
        "7. 네이버 블로그 HTML: 인라인 style만, script/class 금지"
    )


def _build_user_prompt(category: str, article: dict) -> str:
    seo = CATEGORY_SEO.get(category, {})
    kw_hint = (
        f"핵심 SEO 키워드:\n"
        f"  - 주요: {', '.join(seo.get('core', []))}\n"
        f"  - 롱테일: {', '.join(seo.get('long_tail', []))}\n"
        f"  - 트렌딩: {', '.join(seo.get('trending', []))}"
        if seo
        else f"카테고리: {category.replace('_', '/')}"
    )

    return f"""
아래 기사를 씨앗(seed)으로 삼아, 네이버 블로그 **1만 트래픽** 포스트를 HTML로 작성하세요.
원본 기사보다 리서치를 통해 더욱 확충된 내용으로 만드는 것이 목표입니다.

──────────────────────────────
📰 참고 기사
──────────────────────────────
제목: {article.get('title', '')}
요약: {article.get('summary', '')}
본문: {article.get('content', '')}
원본 링크: {article.get('link', '')}

──────────────────────────────
🎯 핵심 지침 (반드시 준수)
──────────────────────────────
★★★ 주제 단일 집중 원칙 ★★★
기사에서 가장 강력한 하나의 핵심 주제만 골라 깊게 파고드세요.
예) 기사가 "항공권 할인 + 여행지 추천"을 섞어도, 포스트는 둘 중 더 검색량 높은
    하나만 집중 → "항공권 최저가 예약법" OR "3월 국내 여행지 베스트 5" 중 택1
→ 두 주제를 섞으면 독자가 무엇을 얻어가는지 모르게 됨 → 이탈률 급상승

리서치 보강 원칙:
- 기사 내용을 3배 확충 (배경 설명, 구체적 수치, 비교 데이터, 실천 단계 추가)
- 독자가 "이거 진짜 도움 됐다! 저장해야겠다"고 느낄 만큼 상세하게
- 내가 기사를 보고 직접 리서치해서 쓴 것처럼 구체적인 정보 제공

──────────────────────────────
🎯 SEO 전략
──────────────────────────────
{kw_hint}
→ 제목·서론·소제목·본문에 핵심 키워드 자연스럽게 분산 배치

──────────────────────────────
🏗️ 필수 콘텐츠 구조 (이 순서대로 HTML 작성)
──────────────────────────────

[A] 히어로 헤드라인 섹션
- 카테고리 뱃지: <span style="background:#E74C3C;color:white;padding:4px 12px;border-radius:12px;font-size:13px;">카테고리명</span>
- 클릭 유발 제목 2개 제안 후 최고 1개 선택 (이모지 포함, "이걸 모르면 손해!" 스타일)
  예) "🚨 항공권 70% 싸게 사는 법, 여행사도 안 알려주는 타이밍 공개!"
      "💸 호텔비 35% 아끼는 얼리버드 비법 — 2026년 최신 데이터"
- 핵심 수치가 들어간 서브타이틀 1문장
- 독자 공감 훅 2~3문장 ("혹시 이런 경험 있으신가요?" / "사실 대부분이 모릅니다" 형식)
- 📖 소요시간: 약 X분 표시

[B] 목차 박스 (필수)
- 파란 콜아웃 박스 안에 소제목 4~6개를 번호 목록으로

[C] 핵심 수치 카드 3개 (강렬함)
- 예: "최대 절약률 70%" / "예약 최적 타이밍 45일 전" / "추천 지역 5곳"
- 배경: #2C3E50, 숫자: 크고 흰색 (#E74C3C), 설명: 작은 흰 글씨

[D] 본문 섹션 (소제목 4~6개, 각 소제목은 font-size:22px로 강조)
각 섹션 구성:
  1. <h2 style="font-size:22px;font-weight:bold;color:#1a1a2e;border-bottom:3px solid #3498DB;padding-bottom:10px;margin:35px 0 15px;">이모지 소제목</h2>
  2. 도입 문장 2~3개 (구어체, 독자와 대화하듯)
  3. 핵심 정보: • 글머리 기호 목록 또는 표 (글자보다 구조화된 정보 선호)
  4. ⭐ / ✅ / 🔑 등 강조 이모티콘으로 핵심 팁 1줄 강조 (굵은 글씨)
  5. 팁 박스 또는 콜아웃 박스 1개 이상

반드시 포함:
  ✅ 비교표 (table): 옵션/방법을 한눈에 비교 — 헤더 배경 #2C3E50
  ✅ 단계별 가이드 (ol): STEP 1 → 2 → 3 형식
  ✅ 경고 박스 (빨간): 주의사항/흔한 실수
  ✅ 팁 박스 (초록): 전문가 팁/인사이트

[E] FAQ 3~4개
- 독자들이 가장 많이 검색하는 질문
- Q: <h3 style="font-size:18px;font-weight:bold;color:#2C3E50;">Q. 질문?</h3>
- A: 명확한 답변 2~3문장

[F] 결론 + 즉각 행동 유도
- 핵심 요약 2~3문장
- 독자가 지금 당장 할 수 있는 행동 1가지 제시
- 이모지 긍정 마무리 + 댓글·공유 유도

[G] 정보 출처 표기
- 📌 **정보 출처:** {article.get('link', '해당 기사 링크')}

──────────────────────────────
🎨 네이버 블로그 HTML 스타일 규칙 (필수 준수)
──────────────────────────────
{NAVER_HTML_GUIDE}

──────────────────────────────
🏷️ 1만 트래픽 태그 전략 (한국어 15개 + 영어 10개 = 25개)
──────────────────────────────
구성: 메인키워드(고검색량) + 롱테일키워드 + 트렌딩키워드 + 카테고리키워드
3가지 형식 모두 생성:
  · tags_hash  : "#태그1 #태그2 #태그3 ..."  (# + 스페이스 구분)
  · tags_comma : "태그1, 태그2, 태그3, ..."  (쉼표+스페이스)
  · tags_plain : "태그1 태그2 태그3 ..."     (스페이스만)
  · tags       : "태그1,태그2,태그3,..."     (쉼표만, API용)

──────────────────────────────
📤 출력 형식 (JSON만 출력, 다른 텍스트 금지)
──────────────────────────────
{{
  "title": "최종 선택 제목 (이모지 포함, 30~45자)",
  "title_alt": "대안 제목 (다른 감정·관점)",
  "content_html": "완성된 HTML 전체 ([A]~[G] 포함, 최소 5,000자)",
  "tags_hash": "#태그1 #태그2 ... (25개)",
  "tags_comma": "태그1, 태그2, ... (25개)",
  "tags_plain": "태그1 태그2 ... (25개)",
  "tags": "태그1,태그2,... (25개, 쉼표만)",
  "meta_description": "검색 노출 설명 (핵심 키워드 포함, 140자 이내)"
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
