"""
오케스트레이터 - Claude API (claude-sonnet-4-6) 기반 지휘자
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할: 전체 작업 계획 수립 → 에이전트 지시 → 결과 품질 검토
실행: OpenRouter 무료 모델 에이전트들이 실제 작업 처리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import json
import logging
import os
import random
import re
import time
from datetime import date, datetime

import anthropic

from agents.content_agent import ContentAgent
from agents.deploy_agent import DeployAgent
from agents.image_agent import ImageAgent
from agents.research_agent import ResearchAgent
from agents.structure_agent import StructureAgent
from config import (
    ANTHROPIC_API_KEY,
    BLOGS,
    CATEGORIES,
    LOG_FILE,
    LOG_LEVEL,
    POST_INTERVAL_MAX,
    POST_INTERVAL_MIN,
)
from content_fetcher import get_article_hash, save_posted_article

# ── 로깅 ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"


class BlogOrchestrator:
    """
    Claude API 기반 멀티 에이전트 블로그 자동화 오케스트레이터.

    파이프라인:
    ① Claude가 오늘의 포스팅 계획 수립 (blog × category × 주제)
    ② 각 태스크를 5개 에이전트로 순차 실행
       Research → Content → Image → Structure → Deploy
    ③ Claude가 세션 결과 검토 + 개선 제안
    """

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY가 .env에 설정되지 않았습니다.")

        self.claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.research = ResearchAgent()
        self.content  = ContentAgent()
        self.image    = ImageAgent()
        self.structure = StructureAgent()
        self.deploy   = DeployAgent()
        self._results: list[dict] = []

    # ═══════════════════════════════════════════════════════════════
    # STEP 1: Claude가 오늘의 포스팅 계획 수립
    # ═══════════════════════════════════════════════════════════════
    def plan_session(self) -> list[dict]:
        """
        Claude API를 사용해 오늘의 포스팅 계획 생성.

        Returns:
            [{"blog_key", "category", "topic_hint", "priority"}]
        """
        today = date.today()

        # 유효한 블로그만 추출
        valid_blogs = {
            k: v for k, v in BLOGS.items()
            if v.get("naver_id") and v.get("blog_id")
        }
        if not valid_blogs:
            logger.warning("[Orchestrator] 유효한 블로그 설정 없음 — .env 확인 필요")
            return []

        # 트렌드 분석 (리서치 에이전트)
        all_categories = list({c for b in valid_blogs.values() for c in b.get("categories", [])})
        trends = self.research.analyze_todays_trends(all_categories)

        # 블로그·카테고리·목표 수 정리
        blogs_info = {}
        for key, cfg in valid_blogs.items():
            cats = {}
            for cat in cfg.get("categories", []):
                cats[cat] = CATEGORIES.get(cat, {}).get("post_count", 2)
            blogs_info[key] = {
                "name": cfg["name"],
                "categories": cats,
                "trend_insights": {c: trends.get(c, {}) for c in cats},
            }

        prompt = f"""당신은 네이버 블로그 자동화 시스템의 오케스트레이터입니다.
오늘({today.strftime('%Y년 %m월 %d일, %A')}) 포스팅 계획을 수립하세요.

등록된 블로그 정보:
{json.dumps(blogs_info, ensure_ascii=False, indent=2)}

요구사항:
1. 각 블로그의 카테고리별 목표 수만큼 포스팅 계획
2. 오늘의 트렌드·계절감을 반영한 구체적인 topic_hint
3. 독자가 가장 많이 검색할 주제 우선 (priority 1이 가장 중요)
4. topic_hint는 실제 검색 키워드처럼 구체적으로

JSON 배열만 반환 (다른 텍스트 없음):
[
  {{
    "blog_key": "travel",
    "category": "여행_항공_호텔",
    "topic_hint": "2026년 4월 제주도 벚꽃 여행 완벽 가이드 — 핫플레이스와 숙소 추천",
    "priority": 1
  }}
]"""

        try:
            resp = self.claude.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            arr  = re.search(r"\[.*\]", text, re.DOTALL)
            plan = json.loads(arr.group() if arr else text)
            plan = sorted(plan, key=lambda x: x.get("priority", 99))
            logger.info(f"[Orchestrator] Claude 계획 수립 완료: {len(plan)}개 포스팅")
            return plan

        except Exception as e:
            logger.error(f"[Orchestrator] 계획 수립 실패: {e} — 폴백 계획 사용")
            return self._fallback_plan(valid_blogs)

    def _fallback_plan(self, blogs: dict) -> list[dict]:
        """Claude 실패 시 config 기반 기본 계획"""
        plan, priority = [], 1
        for key, cfg in blogs.items():
            for cat in cfg.get("categories", []):
                count = CATEGORIES.get(cat, {}).get("post_count", 2)
                for _ in range(count):
                    plan.append({
                        "blog_key":   key,
                        "category":   cat,
                        "topic_hint": "",
                        "priority":   priority,
                    })
                    priority += 1
        return plan

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: 단일 포스트 파이프라인
    # ═══════════════════════════════════════════════════════════════
    def run_post_pipeline(self, task: dict) -> dict:
        """
        Research → Content → Image → Structure → Deploy
        각 단계 실패 시 에러 기록 후 계속 진행 (완전 실패만 중단).
        """
        blog_key   = task["blog_key"]
        category   = task["category"]
        topic_hint = task.get("topic_hint", "")
        blog_name  = BLOGS.get(blog_key, {}).get("name", blog_key)

        step_log = []
        result   = {
            "blog_key": blog_key, "category": category,
            "title": "", "success": False, "steps": step_log,
        }

        logger.info(f"\n{'─' * 55}")
        logger.info(f"[Pipeline] [{blog_name}] {category}")
        logger.info(f"[Pipeline] 주제 힌트: {topic_hint[:60]}")

        # ── 1. 리서치 ──────────────────────────────────────────────
        logger.info("[1/5] ResearchAgent 실행")
        articles = self.research.get_articles(category, max_count=3)
        article  = articles[0] if articles else {
            "title": topic_hint or category, "summary": topic_hint, "link": "", "content": ""
        }
        if topic_hint and not article.get("summary"):
            article["summary"] = topic_hint
        step_log.append({"step": "research", "ok": bool(articles)})

        # ── 2. 콘텐츠 생성 ────────────────────────────────────────
        logger.info("[2/5] ContentAgent 실행")
        content_data = self.content.generate(article, category)
        step_log.append({"step": "content", "ok": bool(content_data)})
        if not content_data:
            logger.error("[Pipeline] 콘텐츠 생성 실패 — 태스크 중단")
            return result

        result["title"] = content_data.get("title", "")

        # ── 3. 이미지 ──────────────────────────────────────────────
        logger.info("[3/5] ImageAgent 실행")
        img_url, img_alt, photographer = self.image.get_image(
            content_data.get("title", topic_hint), category
        )
        step_log.append({"step": "image", "ok": bool(img_url), "source": photographer})

        # ── 4. HTML 구성 ───────────────────────────────────────────
        logger.info("[4/5] StructureAgent 실행")
        post_data = self.structure.format_html(
            content_data,
            image_url=img_url,
            image_alt=img_alt,
            article_link=article.get("link", ""),
        )
        step_log.append({"step": "structure", "ok": bool(post_data)})
        if not post_data:
            logger.error("[Pipeline] HTML 구성 실패 — 태스크 중단")
            return result

        # 포토그래퍼 크레딧 추가
        if photographer:
            post_data["content_html"] += (
                f'\n<p style="font-size:12px;color:#aaa;text-align:right;'
                f"font-family:'Nanum Gothic','맑은 고딕',sans-serif;margin-top:8px;\">"
                f"{photographer}</p>"
            )

        title        = post_data.get("title") or content_data.get("title", article.get("title", ""))
        content_html = post_data.get("content_html", "")
        tags         = post_data.get("tags", "")
        result["title"] = title

        # ── 5. 배포 ────────────────────────────────────────────────
        logger.info("[5/5] DeployAgent 실행")
        deploy_result = self.deploy.publish(blog_key, title, content_html, tags, category)
        step_log.append({"step": "deploy", **deploy_result})
        result["success"] = deploy_result["success"]

        # 포스팅 기록 (중복 방지)
        if deploy_result["success"]:
            hash_key = get_article_hash(
                article.get("title", ""), article.get("summary", "")
            )
            save_posted_article(hash_key)

        return result

    # ═══════════════════════════════════════════════════════════════
    # STEP 3: 전체 세션 실행
    # ═══════════════════════════════════════════════════════════════
    def run_session(self) -> dict:
        """
        하루 포스팅 세션 전체 실행.
        plan → (pipeline × N, 랜덤 인터벌) → Claude 검토 → 결과 저장
        """
        start = datetime.now()
        logger.info("=" * 60)
        logger.info(f"[Orchestrator] 세션 시작: {start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"[Orchestrator] 모델: {CLAUDE_MODEL} (계획·검토)")
        logger.info("=" * 60)

        # 1. 계획 수립
        plan = self.plan_session()
        if not plan:
            logger.error("[Orchestrator] 포스팅 계획 없음 — 세션 종료")
            return {"success": False, "posted": 0, "failed": 0}

        total = len(plan)
        logger.info(f"[Orchestrator] 오늘 목표: {total}개 포스팅")

        # 2. 계획 순서대로 실행
        posted = failed = 0
        for i, task in enumerate(plan, start=1):
            result = self.run_post_pipeline(task)
            self._results.append(result)

            if result["success"]:
                posted += 1
                logger.info(f"✅ [{i}/{total}] 완료: {result['title'][:45]}")
            else:
                failed += 1
                logger.warning(f"❌ [{i}/{total}] 실패: {result['title'][:45]}")

            # 마지막 포스트가 아니면 랜덤 인터벌 대기
            if i < total:
                wait_sec = random.randint(
                    POST_INTERVAL_MIN * 60,
                    POST_INTERVAL_MAX * 60,
                )
                logger.info(f"⏳ 다음 포스팅까지 {wait_sec // 60}분 대기...")
                time.sleep(wait_sec)

        # 3. Claude 결과 검토
        review = self._review_with_claude(posted, failed)

        # 4. 결과 저장
        end = datetime.now()
        summary = {
            "date":          start.strftime("%Y-%m-%d"),
            "session_start": start.isoformat(),
            "session_end":   end.isoformat(),
            "duration_min":  int((end - start).seconds / 60),
            "total_posted":  posted,
            "total_failed":  failed,
            "posts":         self._results,
            "claude_review": review,
        }

        os.makedirs("logs", exist_ok=True)
        log_path = f"logs/session_{start.strftime('%Y%m%d_%H%M')}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        logger.info("\n" + "=" * 60)
        logger.info("[Orchestrator] 세션 완료")
        logger.info(f"  ✅ 성공: {posted}개  ❌ 실패: {failed}개  ⏱ {summary['duration_min']}분")
        logger.info(f"  📄 결과: {log_path}")
        if review:
            logger.info(f"  🤖 Claude 검토: {review}")
        logger.info("=" * 60)

        return summary

    # ═══════════════════════════════════════════════════════════════
    # 보조: Claude 결과 검토
    # ═══════════════════════════════════════════════════════════════
    def _review_with_claude(self, posted: int, failed: int) -> str:
        """세션 결과를 Claude가 검토하고 짧은 평가 반환"""
        if not self._results:
            return ""
        try:
            failed_titles = [r["title"] for r in self._results if not r["success"]]
            prompt = (
                f"블로그 자동화 결과: 성공 {posted}개, 실패 {failed}개.\n"
                f"실패 포스트: {failed_titles}\n\n"
                "한 줄 평가와 내일 개선 포인트 1가지를 60자 이내로."
            )
            resp = self.claude.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.debug(f"[Orchestrator] Claude 검토 실패: {e}")
            return ""


# ── 외부 진입점 ────────────────────────────────────────────────────
def run_orchestrator_session() -> dict:
    """scheduler.py 및 daily_poster.py가 호출하는 진입점"""
    orch = BlogOrchestrator()
    return orch.run_session()
