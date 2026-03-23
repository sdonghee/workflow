#!/bin/bash
# ==========================================
# 네이버 블로그 자동 포스팅 시스템 설치 스크립트
# Synology NAS 호환 버전
# ==========================================

echo "========================================"
echo "  네이버 블로그 자동 포스팅 시스템 설치"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Python 버전 확인
python3 --version || { echo "Python3가 필요합니다"; exit 1; }

# 가상환경 생성
echo "📦 가상환경 생성 중..."
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
echo "📥 패키지 설치 중..."
pip install --upgrade pip
pip install -r requirements.txt

# Playwright 브라우저 설치
echo "🌐 Playwright Chromium 설치 중..."
playwright install chromium

# Playwright 시스템 의존성 설치 (Synology에서는 실패할 수 있음 - 무시)
echo "🔧 시스템 의존성 설치 시도 중 (Synology는 건너뜁니다)..."
playwright install-deps chromium 2>/dev/null || echo "   ⚠️  install-deps 건너뜀 (Synology 환경 - 정상)"

# 환경 파일 설정
if [ ! -f ".env" ]; then
    echo "⚙️  환경 파일 생성 중..."
    cp .env.example .env
    echo ""
    echo "⚠️  .env 파일을 열어 다음 항목을 반드시 입력하세요:"
    echo "   - NAVER_ID: 네이버 아이디"
    echo "   - NAVER_PW: 네이버 비밀번호"
    echo "   - NAVER_BLOG_ID: 블로그 ID (blog.naver.com/[여기])"
    echo ""
else
    echo "✅ .env 파일 이미 존재"
fi

# 디렉토리 생성
mkdir -p logs drafts

echo ""
echo "========================================"
echo "✅ 설치 완료!"
echo "========================================"
echo ""

# 네이버 계정 입력 여부 확인
NAVER_ID_VAL=$(grep "^NAVER_ID=" .env | cut -d'=' -f2)
if [ -z "$NAVER_ID_VAL" ]; then
    echo "⚠️  다음 단계: .env 파일에 네이버 계정 입력"
    echo "   vi .env"
    echo ""
    echo "   NAVER_ID=네이버아이디"
    echo "   NAVER_PW=네이버비밀번호"
    echo "   NAVER_BLOG_ID=블로그ID"
    echo ""
    echo "입력 후 최초 로그인 쿠키 설정:"
    echo "   source venv/bin/activate"
    echo "   python3 first_login.py   # 브라우저에서 한 번만 로그인"
else
    echo "다음 단계:"
    echo "  source venv/bin/activate"
    echo "  python3 first_login.py     # 최초 1회 쿠키 저장"
    echo "  python3 scheduler.py --test  # 동작 확인"
    echo "  python3 scheduler.py --now   # 즉시 포스팅"
    echo "  python3 scheduler.py         # 매일 자동 실행"
fi
echo ""
echo "cron 자동실행 설정 (재부팅 후 자동 시작):"
echo "  crontab -e 에서 추가:"
echo "  @reboot cd $SCRIPT_DIR && source venv/bin/activate && python3 scheduler.py >> logs/cron.log 2>&1 &"
