"""
설정 관리 모듈
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── AI / 오케스트레이터 ──────────────────────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")   # Claude API (오케스트레이터)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")  # OpenRouter (에이전트들)

# ── 이미지 API ───────────────────────────────────────────────────
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY     = os.getenv("PIXABAY_API_KEY", "")    # Agent 4 이미지 3순위

# ── 이미지 필터링 ────────────────────────────────────────────────
# 이미지 검색 시 제외할 키워드 목록 (소문자로 작성)
IMAGE_EXCLUDE_KEYWORDS = [
    "bible", "religion", "church", "christian", "jesus", "cross",
    "성경", "교회", "종교", "기독교", "예수", "십자가"
]

# ── 검색 API ─────────────────────────────────────────────────────
GOOGLE_SEARCH_API_KEY    = os.getenv("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_ENGINE_ID  = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
NAVER_CLIENT_ID          = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET      = os.getenv("NAVER_CLIENT_SECRET", "")

# ── 알림 (Gmail SMTP) ────────────────────────────────────────────
GMAIL_ADDRESS      = os.getenv("GMAIL_ADDRESS", "")       # Agent 5 실패 알림
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")  # Gmail 앱 비밀번호

# ── 포스팅 타이밍 ────────────────────────────────────────────────
POSTS_PER_DAY      = int(os.getenv("POSTS_PER_DAY", "7"))
POST_START_HOUR    = int(os.getenv("POST_START_HOUR", "9"))    # 1회차 09:00
POST_START_HOUR_2  = int(os.getenv("POST_START_HOUR_2", "12"))  # 2회차 12:00
POST_START_HOUR_3  = int(os.getenv("POST_START_HOUR_3", "15"))  # 3회차 15:00
POST_START_HOUR_4  = int(os.getenv("POST_START_HOUR_4", "18"))  # 4회차 18:00
POST_INTERVAL_MIN  = int(os.getenv("POST_INTERVAL_MIN", "120"))  # 포스트간 최소 대기(분)
POST_INTERVAL_MAX  = int(os.getenv("POST_INTERVAL_MAX", "240"))  # 포스트간 최대 대기(분)
HEADLESS           = os.getenv("HEADLESS", "false").lower() == "true"
LOG_LEVEL          = os.getenv("LOG_LEVEL", "INFO")

# ─────────────────────────────────────────
# 멀티 블로그 설정
# 블로그 추가 시 여기에 항목만 추가하면 됩니다
# ─────────────────────────────────────────
BLOGS = {
    "travel": {
        "name": "여행/항공/호텔 블로그",
        "naver_id": os.getenv("BLOG1_NAVER_ID", ""),
        "naver_pw": os.getenv("BLOG1_NAVER_PW", ""),
        "blog_id": os.getenv("BLOG1_BLOG_ID", ""),
        "cookie_file": "cookies_blog1.json",
        "categories": ["여행_항공_호텔"],
        # 실제 블로그 카테고리 ID 매핑 (categoryNo)
        # 블로그 홈 mainFrame 기준: 항공 뉴스(1), 여행 뉴스(6), 호텔 뉴스(7), 여행기(8), 날씨(9)
        "category_ids": {
            "여행_항공_호텔": 6,  # → 여행 뉴스 (기본 매핑)
            "항공":          1,  # → 항공 뉴스
            "호텔":          7,  # → 호텔 뉴스
            "여행기":        8,  # → 여행기
        },
    },
    "info": {
        "name": "정보/건강 블로그",
        "naver_id": os.getenv("BLOG2_NAVER_ID", ""),
        "naver_pw": os.getenv("BLOG2_NAVER_PW", ""),
        "blog_id": os.getenv("BLOG2_BLOG_ID", ""),
        "cookie_file": "cookies_blog2.json",
        "categories": ["정부혜택", "건강"],
        # 실제 블로그 카테고리 ID 매핑 (categoryNo)
        # 블로그 홈 mainFrame 기준: 낙서장(1), 시사/경제/정책(7), 라이프스타일/생활(9)
        "category_ids": {
            "정부혜택": 7,   # → 시사/경제/정책 관련
            "건강":    9,   # → 라이프스타일/생활
        },
    },
    # 3번째 블로그 추가 시 아래 주석 해제 후 .env에 BLOG3_* 추가
    # "blog3": {
    #     "name": "세 번째 블로그",
    #     "naver_id": os.getenv("BLOG3_NAVER_ID", ""),
    #     "naver_pw": os.getenv("BLOG3_NAVER_PW", ""),
    #     "blog_id": os.getenv("BLOG3_BLOG_ID", ""),
    #     "cookie_file": "cookies_blog3.json",
    #     "categories": ["카테고리명"],
    # },
}

# ─────────────────────────────────────────
# 카테고리별 콘텐츠 설정
# ─────────────────────────────────────────
CATEGORIES = {
    "여행_항공_호텔": {
        "keywords": [
            "해외여행 추천", "국내여행 명소", "항공권 할인", "호텔 추천",
            "여행 팁", "비행기 탑승", "공항 이용", "여행지 후기",
            "호캉스 추천", "가성비 숙소"
        ],
        "rss_feeds": [
            "https://rss.hankyung.com/economy.xml",
            "https://www.hankookilbo.com/rss/section/travel",
        ],
        "search_queries": [
            "2026 해외여행 추천 여행지",
            "국내 여행 명소 추천",
            "항공권 특가 이벤트",
            "호텔 얼리버드 할인",
            "여행 꿀팁 정보",
        ],
        "image_keywords": ["travel", "hotel", "airplane", "vacation", "tourism"],
        "tags": ["여행", "해외여행", "국내여행", "항공", "호텔", "여행팁", "여행추천", "호캉스", "여행정보", "관광"],
        "post_count": 1,
    },
    "정부혜택": {
        "keywords": [
            "정부 지원금", "복지 혜택", "청년 지원", "노인 복지",
            "장애인 지원", "정부 보조금", "사회보험", "복지 신청",
            "정부24", "복지로"
        ],
        "rss_feeds": [
            "https://www.korea.kr/rss/policy.do",
            "https://rss.hankyung.com/society.xml",
        ],
        "search_queries": [
            "2026 정부 지원금 신청",
            "청년 정부 혜택 총정리",
            "노인 복지 혜택 안내",
            "저소득층 지원 정책",
            "정부 보조금 신청 방법",
        ],
        "image_keywords": ["government", "welfare", "support", "community", "Korea"],
        "tags": ["정부혜택", "정부지원금", "복지혜택", "청년지원", "노인복지", "사회보험", "정부보조금", "복지신청", "지원정책", "생활정보"],
        "post_count": 2,
    },
    "건강": {
        "keywords": [
            "건강 정보", "질병 예방", "운동 방법", "다이어트",
            "영양 정보", "건강식품", "의학 정보", "건강검진",
            "정신건강", "수면 건강"
        ],
        "rss_feeds": [
            "https://kormedi.com/feed/",
            "https://rss.hankyung.com/it.xml",
        ],
        "search_queries": [
            "2026 건강 관리 방법",
            "질병 예방 건강 정보",
            "다이어트 운동 효과",
            "건강한 식단 영양",
            "정신건강 관리 팁",
        ],
        "image_keywords": ["health", "fitness", "wellness", "medicine", "exercise"],
        "tags": ["건강", "건강정보", "건강관리", "다이어트", "운동", "영양", "질병예방", "건강식품", "의학정보", "웰빙"],
        "post_count": 1,
    },
}

# 레거시 호환 (daily_poster.py 잔존 코드용)
POSTING_INTERVAL_MINUTES = POST_INTERVAL_MIN

# 로그 파일 경로
LOG_FILE        = "naver_blog_auto.log"
POSTED_LOG_FILE = "posted_articles.json"
