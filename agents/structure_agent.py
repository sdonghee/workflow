"""
에이전트 3 - 블로그 구성 에이전트
콘텐츠 데이터를 네이버 블로그 최적화 HTML로 시각화
모델: google/gemma-3-27b-it:free (HTML 포맷팅 특화)
"""
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, GEMMA_27B, LLAMA_70B
from content_writer import NAVER_HTML_GUIDE

logger = logging.getLogger(__name__)

# 박스 유형별 스타일
BOX_STYLES = {
    "info": "background:#EBF5FB;border-left:5px solid #2E86C1;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;",
    "tip":  "background:#E9F7EF;border:1px solid #27AE60;padding:16px 20px;margin:20px 0;border-radius:8px;",
    "warning": "background:#FDEDEC;border-left:5px solid #E74C3C;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;",
}
BASE_FONT = "font-family:'Nanum Gothic','맑은 고딕',sans-serif;"


class StructureAgent(BaseAgent):
    """네이버 블로그 HTML 시각화 에이전트 (Gemma 27B 메인)"""

    def __init__(self):
        super().__init__(
            model=GEMMA_27B,
            fallback_models=[LLAMA_70B],
        )

    def format_html(
        self,
        content_data: dict,
        image_url: str = "",
        image_alt: str = "",
        article_link: str = "",
    ) -> dict | None:
        """
        콘텐츠 데이터 + 이미지 URL → 완성된 네이버 블로그 HTML + 태그

        Returns:
            {title, title_alt, content_html, tags_hash, tags_comma,
             tags_plain, tags, meta_description}
        """
        # 태그 조합 (한국어 15 + 영어 10)
        tags_ko  = content_data.get("tags_ko", [])[:15]
        tags_en  = content_data.get("tags_en", [])[:10]
        all_tags = tags_ko + tags_en

        # 이미지 HTML
        img_html = self._build_image_html(image_url, image_alt)

        # 박스 HTML 미리 빌드 (프롬프트 명확성 향상)
        boxes_hint = "\n".join([
            f'  - info:    <div style="{BOX_STYLES["info"]}{BASE_FONT}">',
            f'  - tip:     <div style="{BOX_STYLES["tip"]}{BASE_FONT}">',
            f'  - warning: <div style="{BOX_STYLES["warning"]}{BASE_FONT}">',
        ])

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 네이버 블로그 HTML 전문가입니다.\n"
                    "절대 규칙:\n"
                    "1. 인라인 style 속성만 사용 (<style> 태그, class 속성 금지)\n"
                    "2. <script>, <link>, 외부 리소스 금지\n"
                    "3. 모든 font-family는 'Nanum Gothic','맑은 고딕',sans-serif\n"
                    "4. 이미지 max-width:100% 필수\n"
                    "5. 표는 width:100%, border-collapse:collapse 필수"
                ),
            },
            {
                "role": "user",
                "content": f"""다음 콘텐츠 데이터를 완성된 네이버 블로그 HTML로 변환하세요.

━━ 콘텐츠 데이터 ━━
{json.dumps(content_data, ensure_ascii=False, indent=2)}

━━ 히어로 이미지 HTML (본문 맨 위에 삽입) ━━
{img_html or "<!-- 이미지 없음 -->"}

━━ 박스 스타일 패턴 ━━
{boxes_hint}

━━ 네이버 HTML 규칙 ━━
{NAVER_HTML_GUIDE}

━━ 필수 HTML 구조 (이 순서대로) ━━
[A] 히어로 이미지 (img_html 그대로 삽입)
[B] 카테고리 뱃지 + 서브타이틀 + 읽기시간
[C] 목차 박스 (info 스타일 div + ol 목록)
[D] 핵심 통계 3개 카드
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin:20px 0;">
      각 카드: background:#2C3E50;color:white;padding:16px 20px;border-radius:8px;flex:1;min-width:140px;text-align:center;
      숫자: font-size:28px;font-weight:900;
[E] 본문 섹션들 (main_points 기반, 각 섹션마다 h2 + 내용 + 해당 box_type 박스)
    h2 style: font-size:22px;font-weight:bold;color:#1a1a2e;border-bottom:3px solid #3498DB;padding-bottom:10px;margin:35px 0 15px;{BASE_FONT}
[F] 비교 표 (comparison_data 활용)
    헤더: background:#2C3E50;color:white;padding:12px 14px;text-align:center;border:1px solid #ddd;
    짝수행: background:#F8F9FA; 홀수행: background:#ffffff;
    td: padding:11px 14px;border:1px solid #ddd;vertical-align:middle;
[G] FAQ 섹션
    각 Q: h3 style="font-size:17px;font-weight:bold;color:#2C3E50;margin:20px 0 8px;"
    각 A: p style="color:#555;line-height:1.8;margin:0 0 15px;"
[H] 결론 + CTA (tip 스타일 div)
[I] 출처: {article_link or ''}
    <p style="font-size:13px;color:#888;border-top:1px solid #eee;margin-top:30px;padding-top:15px;">
    📌 <strong>정보 출처:</strong> <a href="{article_link}" target="_blank" style="color:#3498DB;">{article_link}</a></p>

<hr style="border:none;border-top:2px solid #EAECEE;margin:35px 0;"> 로 섹션 구분.

최종 JSON으로만 반환:
{{
  "content_html": "완성된 HTML 전체 (위 [A]~[I] 포함, 길이 제한 없음)",
  "tags_hash": "{' '.join('#' + t for t in all_tags)}",
  "tags_comma": "{', '.join(all_tags)}",
  "tags_plain": "{' '.join(all_tags)}",
  "tags": "{','.join(all_tags)}",
  "meta_description": "검색 노출용 설명 140자 이내 (핵심 키워드 포함)"
}}

content_html은 반드시 완전한 HTML이어야 합니다. JSON 외 텍스트 절대 금지.""",
            },
        ]

        result = self.chat_json(messages, max_tokens=10000)

        if isinstance(result, dict) and result.get("content_html"):
            # 제목 필드 추가
            result["title"]     = content_data.get("title", "")
            result["title_alt"] = content_data.get("title_alt", "")
            logger.info(f"[StructureAgent] HTML 구성 완료 ({len(result['content_html'])}자)")
            return result

        logger.error("[StructureAgent] HTML 구성 실패")
        return None

    @staticmethod
    def _build_image_html(image_url: str, image_alt: str) -> str:
        if not image_url:
            return ""
        return (
            f'<div style="text-align:center;margin:0 0 30px;">'
            f'<img src="{image_url}" alt="{image_alt}" '
            f"style=\"max-width:100%;height:auto;border-radius:12px;"
            f'box-shadow:0 4px 16px rgba(0,0,0,0.15);\">'
            f'<p style="font-size:13px;color:#888;margin-top:8px;'
            f"font-family:'Nanum Gothic','맑은 고딕',sans-serif;\">{image_alt}</p>"
            f"</div>"
        )
