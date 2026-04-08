"""
Google News 해외 뉴스 크롤러 설정 모듈
- 1차 메타데이터: Google News RSS 피드 (CAPTCHA 없음)
- 2차 본문: Playwright + stealth (원문 링크 방문)

환경변수:
  KEYWORDS    : 콤마 구분 검색 키워드 (기본: "SK Hynix,Samsung Electronics")
  DATE_START  : 수집 시작일 YYYY-MM-DD (기본: "2025-04-01")
  DATE_END    : 수집 종료일 YYYY-MM-DD (기본: 실행 당일)
"""

import os
from datetime import datetime

# ── 검색 대상 (env 주입 가능 — 콤마 구분) ────────────────────
KEYWORDS: list[str] = [
    k.strip() for k in os.getenv("KEYWORDS", "SK Hynix,Samsung Electronics").split(",") if k.strip()
]

# ── 검색 기간 ─────────────────────────────────────────────────
DATE_START: str = os.getenv("DATE_START", "2025-04-01")
DATE_END: str = os.getenv("DATE_END", datetime.today().strftime("%Y-%m-%d"))

# ── 딜레이 설정 (초) ──────────────────────────────────────────
RSS_DELAY_MIN = 1.0  # RSS 요청 간 최소 대기
RSS_DELAY_MAX = 3.0  # RSS 요청 간 최대 대기
BODY_MIN_DELAY = 0.3  # 본문 수집 시 기사 간 최소 대기
BODY_MAX_DELAY = 1.0  # 본문 수집 시 기사 간 최대 대기
PAGE_LOAD_TIMEOUT = 30_000  # ms — Playwright 타임아웃

# ── 재시도 설정 ───────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # 지수 백오프 배수

# ── 브라우저 설정 (본문 수집용) ───────────────────────────────
HEADLESS = True  # 컨테이너 환경에서는 항상 headless
VIEWPORT = {"width": 1920, "height": 1080}
LOCALE = "en-US"
TIMEZONE = "America/New_York"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

# ── Google News RSS 설정 ─────────────────────────────────────
#    news.google.com/rss/search — CAPTCHA 없이 최대 100건/요청
GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"
RSS_LANG = "en-US"  # hl 파라미터
RSS_COUNTRY = "US"  # gl 파라미터
RSS_CEID = "US:en"  # ceid 파라미터
