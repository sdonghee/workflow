import argparse
import io
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

from config import BLOGS
from naver_poster import post_blog

def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _find_blog_key(blog_name: str) -> str | None:
    for key, cfg in BLOGS.items():
        if cfg.get("name") == blog_name:
            return key
    return None

def main():
    parser = argparse.ArgumentParser(description="Naver 블로그 단건 HTML 보존 발행")
    parser.add_argument(
        "--draft",
        required=True,
        help="발행할 draft JSON 파일 경로 (예: drafts/info/20260407_084941_3.json)",
    )
    parser.add_argument(
        "--blog-key",
        required=False,
        help="BLOGS 키를 직접 지정하고 싶을 때 사용 (예: info)",
    )
    args = parser.parse_args()

    draft_path = args.draft
    if not os.path.isabs(draft_path):
        draft_path = os.path.join(_ROOT, draft_path)

    if not os.path.exists(draft_path):
        print(f"[FAIL] draft 파일 없음: {draft_path}")
        sys.exit(1)

    draft = _load_json(draft_path)

    title = (draft.get("title") or "").strip()
    content_html = (draft.get("content_html") or "").strip()
    tags = (draft.get("tags") or "").strip()
    category = draft.get("category", "")
    blog_name = draft.get("blog", "")

    if not title or not content_html:
        print("[FAIL] draft에 title 또는 content_html 없음")
        sys.exit(1)

    blog_key = args.blog_key or _find_blog_key(blog_name)
    if not blog_key:
        print(f"[FAIL] blog_name '{blog_name}'에 해당하는 BLOGS 키 없음")
        print(f"[INFO] 등록된 BLOGS 키: {list(BLOGS.keys())}")
        sys.exit(1)

    blog_cfg = BLOGS[blog_key]

    print("=" * 60)
    print("[HTML POST] draft 로드 완료")
    print(f"  draft     : {draft_path}")
    print(f"  title     : {title[:80]}")
    print(f"  blog_key  : {blog_key}")
    print(f"  blog_name : {blog_cfg.get('name')}")
    print(f"  category  : {category}")
    print(f"  html bytes: {len(content_html):,}")
    print(f"  tags      : {tags}")
    print("=" * 60)

    ok = post_blog(
        title=title,
        content_html=content_html,
        tags=tags,
        category=category,
        blog_config=blog_cfg,
    )

    if ok:
        print("[OK] HTML 보존 발행 성공")
        sys.exit(0)
    else:
        print("[FAIL] HTML 보존 발행 실패")
        sys.exit(1)

if __name__ == "__main__":
    main()
