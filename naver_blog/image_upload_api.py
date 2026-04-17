"""
naver_blog/image_upload_api.py
------------------------------------------------------------------
Naver 블로그 이미지 업로드 → documentModel용 정보 반환.

방법: SmartEditor 파일 선택기(file chooser) 경유.
  - phup.js 라이브러리 내부 업로드 방식 사용 → 세션/토큰 이슈 없음
  - 업로드 완료 후 에디터 DOM에서 src + naturalWidth/Height 추출
  - poster/image_uploader.upload_and_get_info() 위임

비고:
  직접 API 방식(session-key → upphoto POST)은 phup.js의 내부 토큰 방식과 달라
  404 응답 발생. 파일 선택기 방식이 가장 안정적으로 확인됨.

공개 API:
  async upload_image(page, file_path) -> dict | None
      반환값: {src, path, fileName, width, height, domain}
  async upload_images(page, file_paths) -> list[dict]
------------------------------------------------------------------
"""
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


async def upload_image(page, file_path) -> Optional[dict]:
    """
    파일 선택기로 Naver CDN에 업로드 후 DOM에서 URL + 크기 반환.

    Args:
        page      : Playwright page (PostWriteForm.naver + SmartEditor 로드 완료)
        file_path : 업로드할 로컬 이미지 파일 (Path 또는 str)

    Returns:
        {"src", "path", "fileName", "width", "height", "domain"} 또는 None
    """
    from poster.image_uploader import upload_and_get_info
    return await upload_and_get_info(page, Path(file_path))


async def upload_images(page, file_paths: list) -> list:
    """
    여러 파일 순서대로 업로드. 실패 항목은 건너뜀.

    Returns:
        성공한 업로드 결과 list[dict]
    """
    results = []
    for fp in file_paths:
        r = await upload_image(page, fp)
        if r:
            results.append(r)
    log.info(f"[image_upload] {len(results)}/{len(file_paths)} 업로드 성공")
    return results
