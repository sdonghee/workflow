"""
poster/image_uploader.py
------------------------------------------------------------------
네이버 SmartEditor ONE 사진 추가 기능으로 실제 이미지 업로드.

검증된 방법 (2026-04-08):
  - Playwright expect_file_chooser() 로 OS 파일 다이얼로그를 가로챈다.
  - 사진 버튼: button[data-name="image"]  (force click 필요)
  - 업로드 완료 URL: https://blogfiles.pstatic.net/...
  - 감지 기준: .se-main-container img[src*="pstatic.net"] 개수 증가

공개 API:
  upload_image(page, file_path)               -> bool
  insert_images(page, image_urls, max_count)  -> int
  insert_images_from_html(page, html, n)      -> int
------------------------------------------------------------------
"""
import logging
from pathlib import Path
from urllib.parse import urlparse

from poster.image_downloader import download, extract_urls_from_html

log = logging.getLogger(__name__)

_PHOTO_BTN_SEL  = 'button[data-name="image"]'
_UPLOAD_TIMEOUT = 20_000   # ms - 업로드 완료 대기
_CHOOSER_TIMEOUT = 5_000   # ms - 파일 다이얼로그 등장 대기


async def _editor_image_count(page) -> int:
    """에디터 본문 내 네이버 서버 업로드 이미지 수"""
    try:
        return await page.evaluate("""
            () => Array.from(
                document.querySelectorAll('.se-main-container img, [class*="se-image"] img')
            ).filter(img => img.src.includes('pstatic.net') || img.src.includes('blogfiles')).length
        """)
    except Exception:
        return 0


async def upload_image(page, file_path: Path) -> bool:
    """
    SmartEditor 사진 추가 버튼을 통해 로컬 파일을 업로드한다.

    흐름:
      1. page.expect_file_chooser() 컨텍스트 열기
      2. button[data-name="image"] force click → OS 파일 다이얼로그 가로채기
      3. file_chooser.set_files(file_path) 로 파일 주입
      4. pstatic.net 이미지가 에디터에 삽입될 때까지 폴링 대기

    Args:
        page      : Playwright Page (본문 입력 완료 상태)
        file_path : 업로드할 로컬 이미지 파일 경로

    Returns:
        True  -- 네이버 서버 이미지가 에디터에 삽입됨
        False -- 타임아웃 또는 오류
    """
    if not file_path or not file_path.exists():
        log.error(f"[image_uploader] 파일 없음: {file_path}")
        return False

    before = await _editor_image_count(page)

    try:
        # OS 파일 다이얼로그를 가로채서 파일 설정
        async with page.expect_file_chooser(timeout=_CHOOSER_TIMEOUT) as fc_info:
            await page.locator(_PHOTO_BTN_SEL).first.click(force=True, timeout=3000)

        file_chooser = await fc_info.value
        await file_chooser.set_files(str(file_path))
        log.info(f"[image_uploader] 파일 전달: {file_path.name}")

    except Exception as e:
        log.error(f"[image_uploader] 파일 다이얼로그 처리 실패: {e}")
        return False

    # 업로드 완료 폴링 (pstatic.net 이미지 에디터 삽입 확인)
    elapsed = 0
    interval = 500
    while elapsed < _UPLOAD_TIMEOUT:
        await page.wait_for_timeout(interval)
        elapsed += interval
        after = await _editor_image_count(page)
        if after > before:
            log.info(
                f"[image_uploader] 업로드 완료: {file_path.name} "
                f"({before} → {after}개)"
            )
            return True

    log.warning(
        f"[image_uploader] {_UPLOAD_TIMEOUT // 1000}초 내 업로드 미완료: {file_path.name}"
    )
    return False


async def upload_and_get_info(page, file_path: Path) -> dict | None:
    """
    SmartEditor 파일 선택기로 업로드 후 DOM에서 pstatic.net URL + 크기 반환.

    documentModel 이미지 component 생성에 필요한 src/width/height를 함께 반환.
    upload_image() 와 달리 bool 대신 dict를 반환하며, 업로드된 이미지 정보를 포함.

    Args:
        page      : Playwright Page (PostWriteForm.naver, SmartEditor 로드 완료)
        file_path : 업로드할 로컬 이미지 파일

    Returns:
        {"src", "width", "height", "fileName", "path", "domain", "fileSize"} 또는 None
        src    : ?type=w1 쿼리 포함 전체 URL (documentModel 실측 포맷 준수)
        path   : URL path 부분 (e.g. /MjAy.../filename.jpg)
        domain : "https://blogfiles.pstatic.net"
        fileSize: 로컬 파일 바이트 크기
    """
    if not file_path or not file_path.exists():
        log.error(f"[image_uploader] 파일 없음: {file_path}")
        return None

    file_size = file_path.stat().st_size

    # 업로드 전 이미지 목록 스냅샷
    before_imgs: list = await page.evaluate("""
        () => Array.from(
            document.querySelectorAll('.se-main-container img, [class*="se-image"] img')
        )
        .filter(img => img.src.includes('pstatic.net') || img.src.includes('blogfiles'))
        .map(img => img.src)
    """)
    before_set = set(before_imgs)

    try:
        async with page.expect_file_chooser(timeout=_CHOOSER_TIMEOUT) as fc_info:
            await page.locator(_PHOTO_BTN_SEL).first.click(force=True, timeout=3000)
        file_chooser = await fc_info.value
        await file_chooser.set_files(str(file_path))
        log.info(f"[image_uploader] 파일 전달: {file_path.name}")
    except Exception as e:
        log.error(f"[image_uploader] 파일 다이얼로그 처리 실패: {e}")
        return None

    # 새 이미지가 DOM에 나타날 때까지 폴링
    elapsed = 0
    interval = 500
    while elapsed < _UPLOAD_TIMEOUT:
        await page.wait_for_timeout(interval)
        elapsed += interval
        imgs = await page.evaluate("""
            () => Array.from(
                document.querySelectorAll('.se-main-container img, [class*="se-image"] img')
            )
            .filter(img => img.src.includes('pstatic.net') || img.src.includes('blogfiles'))
            .map(img => ({
                src:    img.src,
                width:  img.naturalWidth  || img.getAttribute('data-original-width')  || 0,
                height: img.naturalHeight || img.getAttribute('data-original-height') || 0,
            }))
        """)
        new_imgs = [i for i in imgs if i["src"] not in before_set]
        if new_imgs:
            info      = new_imgs[-1]   # 가장 마지막에 삽입된 이미지
            full_src  = info["src"]    # ?type=w1 포함 전체 URL
            base_src  = full_src.split("?")[0]
            parsed    = urlparse(base_src)
            url_path  = parsed.path    # /MjAy.../filename.jpg
            file_name = Path(url_path).name
            result = {
                "src":      full_src,                         # ?type=w1 포함
                "width":    int(info["width"]  or 0),
                "height":   int(info["height"] or 0),
                "fileName": file_name,
                "path":     url_path,                         # URL path 부분
                "domain":   "https://blogfiles.pstatic.net",  # 전체 URL
                "fileSize": file_size,
            }
            log.info(
                f"[image_uploader] ✅ 업로드+DOM 추출 완료: {base_src[-55:]} "
                f"({result['width']}×{result['height']}, {file_size}B)"
            )
            return result

    log.warning(f"[image_uploader] {_UPLOAD_TIMEOUT // 1000}초 내 이미지 미감지: {file_path.name}")
    return None


async def insert_images(page, image_urls: list[str], max_count: int = 3) -> int:
    """
    이미지 URL 목록을 다운로드 후 SmartEditor에 순서대로 삽입.
    실패한 이미지는 건너뜀 — 텍스트 발행 경로 보존.

    Args:
        page        : Playwright Page (본문 입력 완료 상태)
        image_urls  : 업로드할 이미지 URL 목록
        max_count   : 최대 업로드 수 (기본 3)

    Returns:
        성공한 업로드 수
    """
    if not image_urls:
        log.info("[image_uploader] 업로드할 이미지 없음 — 텍스트만 발행")
        return 0

    success = 0
    targets = image_urls[:max_count]
    for i, url in enumerate(targets):
        log.info(f"[image_uploader] [{i+1}/{len(targets)}] {url[:70]}")

        local_path = download(url)
        if not local_path:
            log.warning(f"[image_uploader] 다운로드 실패 — 건너뜀")
            continue

        ok = await upload_image(page, local_path)
        if ok:
            success += 1
            await page.wait_for_timeout(600)   # 이미지 간 간격
        else:
            log.warning(f"[image_uploader] 업로드 실패 — 건너뜀: {local_path.name}")

    log.info(f"[image_uploader] 완료: {success}/{len(targets)}개 성공")
    return success


async def insert_images_from_html(page, content_html: str, max_count: int = 3) -> int:
    """
    content_html에서 <img src> URL을 추출해 SmartEditor에 삽입.

    Returns:
        성공한 업로드 수
    """
    urls = extract_urls_from_html(content_html)
    if not urls:
        log.info("[image_uploader] content_html에 img src 없음 — 이미지 생략")
        return 0
    log.info(f"[image_uploader] HTML에서 {len(urls)}개 URL 추출")
    return await insert_images(page, urls, max_count=max_count)
