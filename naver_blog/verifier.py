"""
naver_blog/verifier.py
------------------------------------------------------------------
발행 결과 판정. 페이지 조작 없음 -- URL·캡처 목록만 본다.

성공 기준 (우선순위):
  1. page.url에 "PostView.naver" 포함
  2. captured_posts 중 "RabbitWrite.naver" 포함

공개 API:
  is_published(page, captured_posts) -> bool
------------------------------------------------------------------
"""
import logging

log = logging.getLogger(__name__)


def is_published(page_url: str, captured_posts: list[str]) -> bool:
    """
    Args:
        page_url       : page.url (str)
        captured_posts : POST 요청 URL 리스트 (str list)

    Returns:
        True  -- PostView 도달 또는 RabbitWrite 캡처
        False -- 둘 다 없음
    """
    postview_ok = "PostView.naver" in page_url
    rabbit_ok   = any("RabbitWrite" in u for u in captured_posts)

    log.info(f"[verifier] PostView={postview_ok}  RabbitWrite={rabbit_ok}")
    log.info(f"[verifier] URL: {page_url[:100]}")

    return postview_ok or rabbit_ok
