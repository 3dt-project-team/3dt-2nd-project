"""
Google News 크롤러 컨테이너 진입점

환경변수로 키워드·날짜를 주입받아 결과를 ADLS Gen2에 저장한다.

필수 환경변수:
  KEY_VAULT_URL  : Azure Key Vault URL (https://<name>.vault.azure.net/)

선택 환경변수 (기본값 있음):
  KEYWORDS   : 콤마 구분 키워드  (기본: "SK Hynix,Samsung Electronics")
  DATE_START : 수집 시작일 YYYY-MM-DD  (기본: "2025-04-01")
  DATE_END   : 수집 종료일 YYYY-MM-DD  (기본: 오늘)

결과 ADLS 경로:
  raw/news/google/keyword={safe_keyword}/year={YYYY}/month={MM}/articles.parquet
"""

import asyncio

from crawling_google_news import main

if __name__ == "__main__":
    asyncio.run(main())
