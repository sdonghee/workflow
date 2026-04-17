"""
auth/cookie_store.py
------------------------------------------------------------------
쿠키 파일 직렬화/역직렬화.
네트워크·브라우저 의존 없음.

공개 API:
  load(path)           -> list | None
  save(path, cookies)  -> None
------------------------------------------------------------------
"""
import json
import logging
import os

log = logging.getLogger(__name__)


def load(path: str) -> list | None:
    """쿠키 파일 로드. 파일 없거나 빈 경우 None 반환."""
    if not os.path.exists(path):
        log.debug(f"[cookie_store] 파일 없음: {path}")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = f.read().strip()
        if not data:
            log.debug(f"[cookie_store] 빈 파일: {path}")
            return None
        cookies = json.loads(data)
        log.debug(f"[cookie_store] {len(cookies)}개 쿠키 로드: {path}")
        return cookies
    except Exception as e:
        log.error(f"[cookie_store] 로드 실패 ({path}): {e}")
        return None


def save(path: str, cookies: list) -> None:
    """쿠키 리스트를 JSON 파일로 저장."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log.info(f"[cookie_store] {len(cookies)}개 쿠키 저장: {path}")
    except Exception as e:
        log.error(f"[cookie_store] 저장 실패 ({path}): {e}")
