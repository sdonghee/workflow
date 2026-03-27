"""
에이전트 3 - 블로그 구성 에이전트
콘텐츠 데이터를 네이버 블로그 최적화 HTML로 시각화
★ AI 모델 호출 없이 Python으로 직접 HTML 생성 (토큰 한계 문제 완전 해결)
"""
import re
from typing import Optional
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, GEMMA_27B, MISTRAL_24B, DOLPHIN_24B, NEMOTRON_30B, GEMMA_12B, NEMOTRON_12B, LLAMA_70B, GPT_OSS_20B, HERMES_405B

logger = logging.getLogger(__name__)

# 박스 유형별 스타일
BOX_STYLES = {
    "info":    "background:#EBF5FB;border-left:5px solid #2E86C1;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;",
    "tip":     "background:#E9F7EF;border:1px solid #27AE60;padding:16px 20px;margin:20px 0;border-radius:8px;",
    "warning": "background:#FDEDEC;border-left:5px solid #E74C3C;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;",
}
BASE_FONT = "font-family:'Nanum Gothic','맑은 고딕',sans-serif;"
BODY_STYLE = f"font-size:16px;line-height:1.8;{BASE_FONT}color:#333;margin:12px 0;"
H2_STYLE   = f"font-size:22px;font-weight:bold;color:#1a1a2e;border-bottom:3px solid #3498DB;padding-bottom:10px;margin:35px 0 15px;{BASE_FONT}"
H3_STYLE   = f"font-size:18px;font-weight:bold;color:#2C3E50;margin:20px 0 8px;{BASE_FONT}"
HR         = '<hr style="border:none;border-top:2px solid #EAECEE;margin:35px 0;">'


class StructureAgent(BaseAgent):
    """네이버 블로그 HTML 시각화 에이전트 (Python 직접 생성 방식)"""

    def __init__(self):
        super().__init__(
            model=GEMMA_27B,
            fallback_models=[MISTRAL_24B, DOLPHIN_24B, NEMOTRON_30B, GEMMA_12B, NEMOTRON_12B, LLAMA_70B, GPT_OSS_20B, HERMES_405B],
        )

    def format_html(
        self,
        content_data: dict,
        image_url: str = "",
        image_alt: str = "",
        article_link: str = "",
    ) -> Optional[dict]:
        """
        콘텐츠 데이터 → 네이버 블로그 HTML (Python 직접 생성, AI 호출 없음)

        Returns:
            {title, title_alt, content_html, tags_hash, tags_comma, tags_plain, tags, meta_description}
        """
        title      = content_data.get("title", "")
        hook       = content_data.get("hook", "")
        main_pts   = content_data.get("main_points", [])
        comp_data  = content_data.get("comparison_data", {})
        faq        = content_data.get("faq", [])
        conclusion = content_data.get("conclusion", "")
        cta        = content_data.get("cta", "")
        tags_ko    = content_data.get("tags_ko", [])[:15]
        tags_en    = content_data.get("tags_en", [])[:10]
        all_tags   = tags_ko + tags_en

        parts = []

        # ── [A] 히어로 이미지 ──────────────────────────────────────
        img_html = self._build_image_html(image_url, image_alt)
        if img_html:
            parts.append(img_html)

        # ── [B] 서론 훅 ────────────────────────────────────────────
        if hook:
            parts.append(f'<p style="{BODY_STYLE}">{hook}</p>')

        # ── [C] 목차 박스 ──────────────────────────────────────────
        if main_pts:
            toc_items = "\n".join(
                f'<li style="margin:6px 0;">{i+1}. {p.get("heading","")}</li>'
                for i, p in enumerate(main_pts)
            )
            parts.append(
                f'<div style="{BOX_STYLES["info"]}{BASE_FONT}">'
                f'<p style="font-weight:bold;font-size:16px;margin:0 0 10px;">📌 목차</p>'
                f'<ol style="margin:0;padding-left:20px;">{toc_items}</ol>'
                f'</div>'
            )

        # ── [D] 본문 섹션 ──────────────────────────────────────────
        for point in main_pts:
            heading  = point.get("heading", "")
            content  = point.get("content", "")
            tip      = point.get("tip", "")      # 구형 호환
            action   = point.get("action", tip)  # 신형: 즉시 실행 행동
            box_type = point.get("box_type", "tip")

            parts.append(f'<h2 style="{H2_STYLE}">{heading}</h2>')

            # 문단별 분리 (줄바꿈 기준)
            for para in content.split("\n"):
                para = para.strip()
                if para:
                    parts.append(f'<p style="{BODY_STYLE}">{para}</p>')

            # 즉시 실행 행동 박스
            if action:
                bstyle = BOX_STYLES.get(box_type, BOX_STYLES["tip"])
                parts.append(
                    f'<div style="{bstyle}{BASE_FONT}">'
                    f'<strong style="font-size:15px;">✅ 지금 바로: {action}</strong>'
                    f'</div>'
                )

            parts.append(HR)

        # ── [E] 비교표 ─────────────────────────────────────────────
        if comp_data and comp_data.get("headers") and comp_data.get("rows"):
            caption = comp_data.get("caption", "비교표")
            headers = comp_data.get("headers", [])
            rows    = comp_data.get("rows", [])

            th_cells = "".join(
                f'<th style="background:#2C3E50;color:white;padding:12px 14px;'
                f'text-align:center;border:1px solid #ddd;">{h}</th>'
                for h in headers
            )
            table_rows = ""
            for i, row in enumerate(rows):
                bg = "#ffffff" if i % 2 == 0 else "#F8F9FA"
                td_cells = "".join(
                    f'<td style="padding:11px 14px;border:1px solid #ddd;'
                    f'vertical-align:middle;background:{bg};">{cell}</td>'
                    for cell in row
                )
                table_rows += f"<tr>{td_cells}</tr>"

            parts.append(
                f'<h2 style="{H2_STYLE}">📊 {caption}</h2>'
                f'<table style="width:100%;border-collapse:collapse;margin:20px 0;'
                f'font-size:15px;{BASE_FONT}">'
                f"<thead><tr>{th_cells}</tr></thead>"
                f"<tbody>{table_rows}</tbody></table>"
            )
            parts.append(HR)

        # ── [F] FAQ ────────────────────────────────────────────────
        if faq:
            parts.append(f'<h2 style="{H2_STYLE}">❓ 자주 묻는 질문 (FAQ)</h2>')
            for item in faq:
                q = item.get("q", "")
                a = item.get("a", "")
                if q:
                    parts.append(f'<h3 style="{H3_STYLE}">Q. {q}</h3>')
                if a:
                    parts.append(f'<p style="{BODY_STYLE}padding-left:8px;">A. {a}</p>')
            parts.append(HR)

        # ── [G] 결론 + 행동 체크리스트 ────────────────────────────
        checklist = content_data.get("checklist", [])
        if conclusion or cta or checklist:
            inner = ""
            if conclusion:
                inner += (
                    f'<p style="font-size:17px;font-weight:bold;line-height:1.8;'
                    f'color:#1a1a2e;margin:0 0 14px;">🎯 {conclusion}</p>'
                )
            if checklist:
                items = "".join(
                    f'<li style="margin:8px 0;font-size:15px;">☑ {item}</li>'
                    for item in checklist
                )
                inner += (
                    f'<p style="font-weight:bold;font-size:15px;margin:12px 0 6px;">'
                    f'지금 바로 해보세요:</p>'
                    f'<ul style="margin:0;padding-left:20px;">{items}</ul>'
                )
            if cta:
                inner += (
                    f'<p style="font-size:15px;font-weight:bold;color:#27AE60;'
                    f'margin:14px 0 0;">👉 {cta}</p>'
                )
            parts.append(
                f'<div style="{BOX_STYLES["tip"]}{BASE_FONT}">{inner}</div>'
            )

        # ── [H] 출처 ───────────────────────────────────────────────
        if article_link:
            parts.append(
                f'<p style="font-size:13px;color:#888;margin-top:20px;{BASE_FONT}">'
                f'📌 <strong>정보 출처:</strong> '
                f'<a href="{article_link}" style="color:#3498DB;">{article_link}</a></p>'
            )

        content_html = "\n".join(parts)

        if not content_html.strip():
            logger.error("[StructureAgent] HTML 내용 없음 (content_data 비어있음)")
            return None

        meta_description = f"{title} — {hook[:100]}" if hook else title

        result = {
            "title":            title,
            "title_alt":        content_data.get("title_alt", ""),
            "content_html":     content_html,
            "tags_hash":        " ".join("#" + t for t in all_tags),
            "tags_comma":       ", ".join(all_tags),
            "tags_plain":       " ".join(all_tags),
            "tags":             ",".join(all_tags),
            "meta_description": meta_description,
        }
        logger.info(f"[StructureAgent] HTML 구성 완료 ({len(content_html):,}자)")
        return result

    @staticmethod
    def _build_image_html(image_url: str, image_alt: str) -> str:
        if not image_url:
            return ""
        return (
            f'<div style="text-align:center;margin:0 0 30px;">'
            f'<img src="{image_url}" alt="{image_alt}" '
            f'style="max-width:100%;height:auto;border-radius:12px;'
            f'box-shadow:0 4px 16px rgba(0,0,0,0.15);">'
            f'<p style="font-size:13px;color:#888;margin-top:8px;'
            f"font-family:'Nanum Gothic','맑은 고딕',sans-serif;\">{image_alt}</p>"
            f"</div>"
        )
