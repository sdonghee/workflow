"""
에이전트 5 - 배포 + 자가복구 에이전트
네이버 블로그 자동 업로드, 최대 3회 재시도, Gmail 실패 알림
모델: meta-llama/llama-3.3-70b-instruct:free
"""
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, LLAMA_70B, HERMES_405B
from naver_poster import post_blog, save_post_locally, BrowserUnavailableError
from config import BLOGS, GMAIL_ADDRESS, GMAIL_APP_PASSWORD

logger = logging.getLogger(__name__)

MAX_RETRIES   = 3
RETRY_DELAYS  = [30, 90, 180]   # 초 (0.5분 → 1.5분 → 3분)


class DeployAgent(BaseAgent):
    """배포 자동화 + 자가복구 에이전트"""

    def __init__(self):
        super().__init__(
            model=LLAMA_70B,
            fallback_models=[HERMES_405B],
        )

    def publish(
        self,
        blog_key: str,
        title: str,
        content_html: str,
        tags: str,
        category: str,
    ) -> dict:
        """
        포스트 게시 (최대 3회 재시도).

        Returns:
            {success: bool, attempts: int, message: str}
        """
        blog_cfg = BLOGS.get(blog_key)
        if not blog_cfg:
            return {"success": False, "attempts": 0, "message": f"알 수 없는 블로그 키: {blog_key}"}
        if not blog_cfg.get("naver_id") or not blog_cfg.get("blog_id"):
            return {"success": False, "attempts": 0, "message": "블로그 자격증명 미설정 (.env 확인)"}

        last_error = "알 수 없는 오류"
        blog_name  = blog_cfg["name"]

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"[DeployAgent] [{blog_name}] 게시 시도 {attempt}/{MAX_RETRIES}: {title[:40]}"
                )
                success = post_blog(title, content_html, tags, category, blog_cfg)

                if success:
                    logger.info(f"[DeployAgent] ✅ 게시 성공 (시도 {attempt}회): {title[:40]}")
                    return {"success": True, "attempts": attempt, "message": "게시 완료"}

                last_error = "post_blog 반환값 False (로그인 실패 또는 UI 변경 가능성)"

            except Exception as e:
                last_error = str(e)
                logger.error(f"[DeployAgent] 시도 {attempt} 예외: {e}")

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1]
                logger.info(f"[DeployAgent] {delay}초 후 재시도...")
                time.sleep(delay)

        # ── 3회 모두 실패 ──────────────────────────────────
        logger.error(f"[DeployAgent] ❌ {MAX_RETRIES}회 모두 실패: {title[:40]}")
        save_post_locally(title, content_html, tags, category, blog_cfg)
        self._alert_failure(blog_name, title, category, last_error)

        return {
            "success": False,
            "attempts": MAX_RETRIES,
            "message": f"3회 실패. drafts/ 폴더에 저장됨. 마지막 오류: {last_error}",
        }

    # ── Gmail 실패 알림 ──────────────────────────────────────────
    def _alert_failure(self, blog_name: str, title: str, category: str, error: str):
        """Gmail SMTP (SSL 465포트)로 실패 알림 전송"""
        if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
            logger.warning("[DeployAgent] Gmail 미설정 — 이메일 알림 생략")
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"⚠️ [블로그 자동화] 게시 실패: {blog_name}"
            msg["From"]    = GMAIL_ADDRESS
            msg["To"]      = GMAIL_ADDRESS

            html_body = f"""
<html>
<body style="font-family:'Nanum Gothic',sans-serif;padding:20px;max-width:600px;">
  <h2 style="color:#E74C3C;border-bottom:2px solid #E74C3C;padding-bottom:8px;">
    ⚠️ 네이버 블로그 게시 실패 알림
  </h2>
  <table style="width:100%;border-collapse:collapse;margin:16px 0;">
    <tr>
      <td style="width:140px;padding:10px;border:1px solid #ddd;background:#f8f9fa;font-weight:bold;">발생 시각</td>
      <td style="padding:10px;border:1px solid #ddd;">{now}</td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #ddd;background:#f8f9fa;font-weight:bold;">블로그</td>
      <td style="padding:10px;border:1px solid #ddd;">{blog_name}</td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #ddd;background:#f8f9fa;font-weight:bold;">카테고리</td>
      <td style="padding:10px;border:1px solid #ddd;">{category}</td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #ddd;background:#f8f9fa;font-weight:bold;">포스트 제목</td>
      <td style="padding:10px;border:1px solid #ddd;">{title}</td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #ddd;background:#f8f9fa;font-weight:bold;">재시도 횟수</td>
      <td style="padding:10px;border:1px solid #ddd;">{MAX_RETRIES}회</td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #ddd;background:#f8f9fa;font-weight:bold;">오류 내용</td>
      <td style="padding:10px;border:1px solid #ddd;color:#E74C3C;">{error}</td>
    </tr>
  </table>
  <div style="background:#FEF9E7;border:1px solid #F1C40F;padding:12px 16px;border-radius:6px;">
    <strong>📁 조치:</strong> 실패한 포스트는 <code>drafts/</code> 폴더에 자동 저장되었습니다.
    수동으로 확인 후 재업로드하거나 로그를 점검해주세요.
  </div>
</body>
</html>"""
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
                server.send_message(msg)

            logger.info(f"[DeployAgent] 실패 알림 이메일 발송 완료 → {GMAIL_ADDRESS}")

        except Exception as e:
            logger.error(f"[DeployAgent] 이메일 발송 실패: {e}")
