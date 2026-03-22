# 네이버 블로그 자동 포스팅 시스템

매일 10개의 블로그 포스트를 자동으로 수집, 생성, 게시하는 시스템입니다.

## 📋 기능

- **자동 콘텐츠 수집**: RSS 피드, 구글 뉴스, 네이버 뉴스에서 최신 정보 수집
- **AI 콘텐츠 생성**: Claude AI로 저작권 없이 완전히 새로운 글 작성
- **무료 이미지**: Unsplash, Pexels의 저작권 없는 고품질 이미지 자동 첨부
- **자동 포스팅**: Playwright로 네이버 블로그에 자동 게시
- **스케줄링**: 매일 지정 시간에 자동 실행

## 📂 카테고리 구성

| 카테고리 | 일일 포스트 수 |
|---------|-------------|
| 여행/항공/호텔 | 4개 |
| 정부혜택 | 3개 |
| 건강 | 3개 |
| **합계** | **10개** |

## 🚀 설치 방법

```bash
# 1. 설치 스크립트 실행
chmod +x setup.sh
./setup.sh

# 2. .env 파일 설정
nano .env
```

## ⚙️ 필수 설정 (.env 파일)

```
ANTHROPIC_API_KEY=sk-ant-...    # Claude AI API 키
NAVER_ID=your_id                # 네이버 아이디
NAVER_PW=your_password          # 네이버 비밀번호
NAVER_BLOG_ID=your_blog_id      # 블로그 ID
```

### 선택 설정 (이미지 품질 향상)
```
UNSPLASH_ACCESS_KEY=...   # https://unsplash.com/developers
PEXELS_API_KEY=...        # https://www.pexels.com/api/
```

## 🔑 API 키 발급 방법

### Claude AI API 키
1. https://console.anthropic.com 접속
2. 회원가입 후 API Keys 메뉴에서 발급

### Unsplash API (무료)
1. https://unsplash.com/developers 접속
2. New Application 생성 → Access Key 복사

### Pexels API (무료)
1. https://www.pexels.com/api/ 접속
2. API Key 발급

## 💻 실행 방법

```bash
# 가상환경 활성화
source venv/bin/activate

# 테스트 (포스팅 없이 동작 확인)
python scheduler.py --test

# 즉시 실행 (지금 바로 10개 포스팅)
python scheduler.py --now

# 스케줄 모드 (매일 오전 9시 자동 실행)
python scheduler.py
```

## 🔄 자동 실행 설정 (cron)

시스템이 재시작되어도 자동으로 실행되도록 설정:

```bash
crontab -e
```

다음 줄 추가:
```
@reboot cd /path/to/workflow && source venv/bin/activate && python scheduler.py >> logs/cron.log 2>&1 &
```

## 📁 디렉토리 구조

```
workflow/
├── config.py              # 설정 관리
├── content_fetcher.py     # 콘텐츠 수집
├── content_writer.py      # AI 콘텐츠 생성
├── image_finder.py        # 이미지 검색
├── naver_poster.py        # 네이버 블로그 포스팅
├── daily_poster.py        # 일일 포스팅 오케스트레이터
├── scheduler.py           # 스케줄러
├── requirements.txt       # Python 패키지 목록
├── .env.example           # 환경 변수 예시
├── setup.sh               # 설치 스크립트
├── logs/                  # 실행 로그
├── drafts/                # 임시 저장된 포스트
└── posted_articles.json   # 포스팅 기록 (중복 방지)
```

## ⚠️ 주의사항

1. **네이버 2단계 인증**: 2단계 인증이 설정된 경우 자동 로그인이 안될 수 있습니다. 비활성화하거나 신뢰할 수 있는 기기로 등록하세요.
2. **포스팅 간격**: 스팸 방지를 위해 포스트 사이에 일정 간격을 둡니다.
3. **저작권**: AI가 완전히 새롭게 작성하지만, 참고한 정보의 출처가 민감한 경우 확인이 필요합니다.
4. **API 비용**: Claude AI API 사용 시 비용이 발생합니다 (포스트당 약 $0.01~0.05).

## 🐛 문제 해결

### 로그인 실패
- 네이버 캡차가 뜨는 경우: HEADLESS=false로 설정 후 처음 한 번 수동 로그인
- 2단계 인증 비활성화 필요

### 포스팅 실패
- drafts/ 폴더에 임시 저장됨
- `python scheduler.py --retry` 로 재시도 가능

### 이미지 없음
- Unsplash/Pexels API 키 미설정 시 Lorem Picsum 기본 이미지 사용
