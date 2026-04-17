"""
poster/image_downloader.py
------------------------------------------------------------------
이미지 URL을 로컬 임시 파일로 다운로드.
네이버 업로드 전 처리 단계. Playwright/브라우저 의존 없음.

공개 API:
  download(url)              -> Path | None
  download_all(urls, limit)  -> list[Path]
  cleanup(paths)             -> None
------------------------------------------------------------------
"""
import hashlib
import logging
import os
import re
from pathlib import Path

import requests

log = logging.getLogger(__name__)

_TMP_DIR = Path(__file__).parent.parent / "tmp" / "images"
_TIMEOUT  = 15          # seconds
_MAX_SIZE = 10 * 1024 * 1024  # 10 MB

# 네이버 허용 이미지 확장자
_ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/gif",
                 "image/webp", "image/bmp", "image/heic", "image/heif"}
_EXT_MAP = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/png":  ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/bmp": ".bmp",
    "image/heic": ".heic", "image/heif": ".heif",
}


def _url_to_filename(url: str) -> str:
    """URL → MD5 해시 기반 파일명 (확장자 제외)"""
    return hashlib.md5(url.encode()).hexdigest()


def _ext_from_response(response) -> str:
    """Content-Type 헤더로 확장자 결정. 실패 시 URL 경로에서 추출."""
    ct = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if ct in _EXT_MAP:
        return _EXT_MAP[ct]
    # URL 경로 끝에서 추출
    path = response.url.split("?")[0].lower()
    for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
        if path.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return ".jpg"  # 기본값


def download(url: str, dest_dir: Path = _TMP_DIR) -> Path | None:
    """
    이미지 URL을 로컬 파일로 다운로드.

    Args:
        url      : 이미지 URL
        dest_dir : 저장 디렉터리 (기본: tmp/images/)

    Returns:
        다운로드된 파일 Path, 실패 시 None
    """
    if not url or not url.startswith("http"):
        log.warning(f"[image_downloader] 유효하지 않은 URL: {url[:60]}")
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)

    # 이미 캐시된 파일이 있으면 재사용
    stem = _url_to_filename(url)
    for cached in dest_dir.glob(f"{stem}.*"):
        log.debug(f"[image_downloader] 캐시 사용: {cached.name}")
        return cached

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=_TIMEOUT, stream=True)
        resp.raise_for_status()

        ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if ct and ct not in _ALLOWED_MIME and not ct.startswith("image/"):
            log.warning(f"[image_downloader] 이미지가 아닌 Content-Type: {ct}")
            return None

        ext  = _ext_from_response(resp)
        path = dest_dir / f"{stem}{ext}"

        size = 0
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                size += len(chunk)
                if size > _MAX_SIZE:
                    log.warning(f"[image_downloader] 파일 크기 초과 ({_MAX_SIZE // 1024 // 1024}MB): {url[:60]}")
                    f.close()
                    path.unlink(missing_ok=True)
                    return None
                f.write(chunk)

        log.info(f"[image_downloader] 다운로드 완료: {path.name} ({size // 1024}KB)")
        return path

    except requests.exceptions.Timeout:
        log.warning(f"[image_downloader] 타임아웃: {url[:60]}")
    except requests.exceptions.RequestException as e:
        log.warning(f"[image_downloader] 요청 실패: {e}")
    except Exception as e:
        log.error(f"[image_downloader] 오류: {e}")

    return None


def download_all(urls: list[str], limit: int = 5) -> list[Path]:
    """
    여러 URL을 순서대로 다운로드. 실패한 항목은 건너뜀.

    Args:
        urls  : 이미지 URL 목록
        limit : 최대 다운로드 수

    Returns:
        성공한 파일 Path 목록
    """
    results = []
    for url in urls[:limit]:
        path = download(url)
        if path:
            results.append(path)
    log.info(f"[image_downloader] {len(results)}/{min(len(urls), limit)} 다운로드 성공")
    return results


def cleanup(paths: list[Path]) -> None:
    """임시 파일 삭제"""
    for p in paths:
        try:
            p.unlink(missing_ok=True)
            log.debug(f"[image_downloader] 삭제: {p.name}")
        except Exception as e:
            log.warning(f"[image_downloader] 삭제 실패 ({p}): {e}")


def extract_urls_from_html(html: str) -> list[str]:
    """
    HTML 문자열에서 img src URL만 추출.
    structure_agent가 생성한 content_html에서 이미지 URL을 꺼낼 때 사용.
    """
    return re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
