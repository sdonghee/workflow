#!/bin/bash
# ==========================================
# 네이버 블로그 자동 포스팅 시스템 설치 스크립트
# ==========================================

set -e

echo "========================================"
echo "  네이버 블로그 자동 포스팅 시스템 설치"
echo "========================================"
echo ""

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
echo "🌐 Playwright 브라우저 설치 중..."
playwright install chromium
playwright install-deps chromium

# 환경 파일 설정
if [ ! -f ".env" ]; then
    echo "⚙️  환경 파일 생성 중..."
    cp .env.example .env
    echo ""
    echo "⚠️  .env 파일을 열어 다음 항목을 반드시 입력하세요:"
    echo "   - ANTHROPIC_API_KEY: Claude AI API 키"
    echo "   - NAVER_ID: 네이버 아이디"
    echo "   - NAVER_PW: 네이버 비밀번호"
    echo "   - NAVER_BLOG_ID: 블로그 ID"
    echo "   - UNSPLASH_ACCESS_KEY: Unsplash API 키 (선택)"
    echo "   - PEXELS_API_KEY: Pexels API 키 (선택)"
    echo ""
fi

# 디렉토리 생성
mkdir -p logs drafts

echo ""
echo "✅ 설치 완료!"
echo ""
echo "다음 단계:"
echo "1. .env 파일에 API 키와 네이버 계정 정보 입력"
echo "2. 테스트: python scheduler.py --test"
echo "3. 즉시 실행: python scheduler.py --now"
echo "4. 자동 스케줄: python scheduler.py"
echo ""
echo "cron으로 시스템 재시작 시 자동 실행:"
echo "  crontab -e 에서 다음 줄 추가:"
echo "  @reboot cd $(pwd) && source venv/bin/activate && python scheduler.py >> logs/cron.log 2>&1 &"
