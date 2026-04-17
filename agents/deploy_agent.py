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
import subprocess

# 누락된 import 추가
from agents.base_agent import BaseAgent, LLAMA_70B, HERMES_405B
from naver_poster import save_post_locally
from config import BLOGS, GMAIL_ADDRESS, GMAIL_APP_PASSWORD

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [30, 90, 180]  # 초 (0.5분 → 1.5분 → 3분)


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
        sections: list | None = None,
    ) -> dict:
        """
        [수정] 포스트 게시 로직: subprocess로 naver_poster.py를 완전히 분리하여 실행
        1. 포스트 내용을 임시 JSON draft 파일로 저장
        2. `subprocess.run(['python', 'naver_poster.py', '--draft_path', ...])` 실행
        3. 반환 코드(returncode)로 성공/실패 판단
        """
        blog_cfg = BLOGS.get(blog_key)
        if not blog_cfg:
            return {"success": False, "attempts": 0, "message": f"알 수 없는 블로그 키: {blog_key}"}
        if not blog_cfg.get("naver_id") or not blog_cfg.get("blog_id"):
            return {"success": False, "attempts": 0, "message": "블로그 자격증명 미설정 (.env 확인)"}

        # 1. 임시 draft 파일 생성
        draft_path = save_post_locally(title, content_html, tags, category, blog_cfg, sections=sections)
        if not draft_path:
            return {"success": False, "attempts": 0, "message": "draft 파일 저장 실패"}
        logger.info(f"[DeployAgent] 임시 draft 생성: {draft_path}")

        last_error = "알 수 없는 오류"
        blog_name = blog_cfg["name"]

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"[DeployAgent] [{blog_name}] 게시 시도 {attempt}/{MAX_RETRIES} (외부 프로세스): {title[:40]}"
                )

                # 2. subprocess로 외부 스크립트 실행
                # sys.executable은 현재 실행 중인 파이썬 인터프리터를 가리킴
                process = subprocess.run(
                    [sys.executable, "run_single_post_html.py", "--draft", draft_path],
                    capture_output=True,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), # workflow 폴더
                    timeout=600
                )

                # stdout/stderr 디코딩 (run_single_post.py는 utf-8 출력)
                stdout = process.stdout.decode("utf-8", errors="replace")
                stderr = process.stderr.decode("utf-8", errors="replace")

                if stdout:
                    logger.info(f"[run_single_post_html.py stdout]\n{stdout}")
                if stderr:
                    logger.warning(f"[naver_poster.py stderr]\n{stderr}")

                if process.returncode == 0:
                    logger.info(f"[DeployAgent] ✅ 게시 성공 (시도 {attempt}회, exit 0): {title[:40]}")
                    return {"success": True, "attempts": attempt, "message": "게시 완료"}
                
                last_error = f"naver_poster.py가 exit code {process.returncode}로 실패했습니다.\n오류: {stderr}"

            except subprocess.TimeoutExpired:
                last_error = "naver_poster.py 실행 시간 초과 (10분)"
                logger.error(f"[DeployAgent] 시도 {attempt} 시간 초과")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[DeployAgent] 시도 {attempt} 예외: {e}")

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1]
                logger.info(f"[DeployAgent] {delay}초 후 재시도...")
                time.sleep(delay)

        # ── 3회 모두 실패 ──────────────────────────────────
        logger.error(f"[DeployAgent] ❌ {MAX_RETRIES}회 모두 실패: {title[:40]}")
        # 임시 파일은 이미 저장되어 있으므로 추가 저장 호출 필요 없음
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
