# SENSE 데이터 구조 전체 정리

> 작성: 2026-04-14 | 기준: 회의록(1조 전반부) + 뉴스 데이터 골드레이어.md + 데이터 사전
>
> **범위**: ADLS Gen2 (Bronze → Silver) + PostgreSQL (Gold)

---

## 1. ADLS Gen2 — 컨테이너 / 경로 구조

> **스토리지 계정**: `3dtteam1adls` (HNS 활성화, 한국중부)
> az CLI 기준 실제 확인: 2026-04-14

```
3dtteam1adls/
├── raw/                              # Bronze — 원본 수집 그대로
│   ├── news/
│   │   ├── google/                   # Parquet (snappy), Google News ACI 크롤러
│   │   ├── naver/                    # JSON → Parquet 변환 예정
│   │   └── bing/                     # JSON / Parquet
│   ├── yfinance/
│   │   └── year=2026/                # 연도별 파티션
│   ├── fx/                           # Parquet, Open Exchange Rates + Frankfurter
│   ├── fred_macro_data/              # ⚠️ 문서명 'fred/' 와 다름 — 실제 경로
│   └── public_data/
│       ├── finance/                  # kfinance 원본
│       └── semiconductor/            # 관세청 수출입 원본
│
├── curated/                          # Silver — 정제 + 파생 컬럼 (정형 데이터)
│   ├── fred/                         # FRED 금리 Forward Fill (year=2025~2026)
│   ├── fx/                           # FX 일별 집계 (year=2025~2026)
│   ├── kfinance/                     # 코스피200 파생 (year=2024~2026)
│   ├── semiconductor/                # 관세청 + kfinance Forward Fill (year=2024~2026)
│   └── yfinance/                     # 주가 시차 정렬 (year=2025~2026)
│   ⚠️ 누락: news/, macro/, equity/, quant/, customs/ — 실제 미존재
│
├── silver/                           # ⚠️ 데이터사전 미기재 — 뉴스 Silver 전용 컨테이너
│   └── news/
│       ├── google_bing/
│       │   └── preprocessed_google&bing/  # Google + Bing 통합 전처리
│       ├── naver/
│       │   └── preprocessed/             # Naver 전처리
│       └── feature/
│           └── year_month=2026-04/       # ABSA/벡터 등 피처 추출 결과
│
└── feature/                          # Gold ADLS 중간 저장 (정형 데이터)
    ├── gold_macro_1y/                # ⚠️ 문서명 'sense/' 와 다름
    ├── macro_semiconductor/          # ⚠️ 문서명 'sense/' 와 다름
    └── sense_macro/                  # (year=2025~2026 파티션)
```

---

## 2. ADLS Gen2 — Bronze 스키마 요약

### 2-1. `raw/news/google/` (Parquet, snappy)

| 컬럼 | 타입 | 내용 |
|---|---|---|
| `source` | String | 검색 키워드 ("SK Hynix", "Samsung Electronics") |
| `news_id` | String | URL SHA-256 해시 앞 16자 |
| `url` | String | 기사 원문 링크 |
| `pub_date` | String | YYYY-MM-DD |
| `adjusted_date` | String | YYYY-MM (파티셔닝 키) |
| `headline` | String | 영문 기사 제목 |
| `press` | String | 언론사명 |
| `description` | String | Google RSS 요약문 |
| `body` | String | Playwright 수집 본문 전체 |
| `fetched_at` | String | ISO 8601 UTC 타임스탬프 |

### 2-2. `raw/news/naver/` (JSON → Parquet 변환 예정)

| 컬럼 | 타입 | 내용 |
|---|---|---|
| `source` | String | "samsung" / "skhynix" |
| `news_id` | String | naver_/yna_/hankyung_ 접두사 |
| `url` | String | 기사 원본 링크 |
| `naver_url` | String | 네이버 뉴스 플랫폼 링크 |
| `pub_date` | String | YYYY-MM-DD (KST) |
| `adjusted_date` | String | YYYY-MM-DD (파티셔닝) |
| `headline` | String | 한국어 기사 제목 |
| `description` | String | 네이버 검색 API 요약문 |
| `body` | String | Playwright 선택자 파싱 본문 |
| `fetched_at` | String | ISO 8601 UTC 타임스탬프 |

### 2-3. `raw/news/bing/` (JSON, Parquet)

| 컬럼 | 타입 | 내용 |
|---|---|---|
| `source` | String | "samsung" / "skhynix" |
| `news_id` | String | bing_ 접두사 + URL SHA-256 해시 16자 |
| `url` | String | 기사 원문 링크 (200 OK 검증) |
| `pub_date` | String | YYYY-MM-DD (UTC) |
| `adjusted_date` | String | YYYY-MM (파티셔닝 키) |
| `headline` | String | 영문 기사 제목 |
| `press` | String | 언론사명 |
| `body` | String | Bing Grounding 기반 핵심 수치 포함 요약본 |
| `fetched_at` | String | ISO 8601 UTC 타임스탬프 |

### 2-4. `raw/yfinance/` (CSV, UTF-8-BOM)

| 컬럼 | 타입 | 내용 |
|---|---|---|
| `date` | Datetime | 거래일 (인덱스) |
| `ticker` | String | Yahoo Finance 티커 (005930.KS, NVDA 등) |
| `name` | String | 종목명 |
| `open` / `high` / `low` / `close` | Float64 | OHLC |
| `volume` | Float64 | 당일 거래량 |

### 2-5. `raw/fx/` (Parquet) — Open Exchange Rates

| 컬럼 | 타입 | 내용 |
|---|---|---|
| `provider` | String | "openexchangerates" |
| `base_currency` | String | "USD" |
| `quote_currency` | String | "KRW" |
| `rate` | Float64 | USD/KRW 환율 |
| `provider_timestamp_utc` | Timestamp | 제공사 산출 시각 (UTC) |
| `collected_at_utc` | Timestamp | 수집 시각 (UTC) |
| `collected_at_kst` | Timestamp | 수집 시각 (KST) |
| `provider_timestamp_unix` | Integer | UNIX 초 타임스탬프 |
| `raw_payload_json` | String | API 원본 JSON 전체 |

> Frankfurter(최근 1년 히스토리) + Open Exchange Rates(실시간, 매시 03분 Timer Trigger)

### 2-6. `raw/fred_macro_data/` (Parquet)

> ⚠️ **실제 경로**: `raw/fred_macro_data/` — 문서 표기 `raw/fred/` 와 다름

| 컬럼 | 타입 | 내용 |
|---|---|---|
| `observed_date` | Date | 관측 일자 |
| `series_code` | String | DGS10, DGS2, T10Y2Y, BAMLH0A0HYM2, DFF, DFII10 |
| `rate_value` | Number | 금리 수치값 |
| `collected_at_utc` | Timestamp | 수집 일시 (UTC) |

> 매일 01:00 UTC (10:00 KST) Timer Trigger

### 2-7. `raw/public_data/` — 관세청 반도체 수출입 (Parquet)

| 컬럼 | 타입 | 내용 |
|---|---|---|
| `stat_date` | DATE | 통계 기준 년/월 (예: 2024-01-01) |
| `hs_code` | VARCHAR(10) | HS코드 (8542 = 반도체) |
| `stat_kor` | VARCHAR(255) | 품목 국문명 |
| `exp_dlr` | BIGINT | 수출금액 (USD) |
| `exp_wgt` | NUMERIC | 수출 중량 (KG) |
| `imp_dlr` | BIGINT | 수입금액 (USD) |
| `imp_wgt` | NUMERIC | 수입 중량 (KG) |
| `bal_payments` | BIGINT | 무역수지 (수출 - 수입) |
| `collected_at` | TIMESTAMP | Azure Function 수집 시각 |

---

## 3. ADLS Gen2 — Silver 스키마 요약

> ⚠️ **뉴스 Silver 위치**: `curated/news/` 는 실제로 존재하지 않음. 뉴스 Silver는 별도 `silver/` 컨테이너에 저장됨 (`silver/news/google_bing/`, `silver/news/naver/`, `silver/news/feature/`)

### 3-1. `silver/news/` — 2026-04 기준 실제 컬럼

> 실제 경로: `silver/news/google_bing/preprocessed_google&bing/`, `silver/news/naver/preprocessed/`, `silver/news/feature/year_month=2026-04/`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `news_id` | String | Bronze 승계 고유 ID |
| `news_source` | String | "google" / "naver" / "bing" |
| `pub_date` | Date | 정규화 발행일 |
| `headline` | String | 기사 제목 |
| `description` | String | RSS/API 요약문 |
| `clean_text` | String | 정제 본문 |
| `body` | String | RAG용 원본 본문 |
| `url` | String | 원문 링크 |
| `press` | String | 언론사명 |
| `stock_keyword` | String | "samsung" / "skhynix" |
| `category` | String | Azure OpenAI 분류 카테고리 |
| `absa_aspect` | String | ABSA 속성 (제조원가, 공급망 등) |
| `absa_score` | Float | 감성 점수 (-1.0 ~ 1.0) |
| `dynamic_keywords` | String (JSON Array) | TF-IDF/LLM 핵심 키워드 배열 |
| `keyword_momentum` | String (JSON Object) | 키워드별 언급 급증률 (%) |
| `summary_vector` | Array(Float, 1536) | description 임베딩 벡터 |

### 3-2. `curated/` — yfinance Silver (2,488행 · 15컬럼)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DateType | 원래 거래일 |
| `Ticker` | StringType | 종목 코드 (005930.KS, NVDA 등 10종목) |
| `Name` | StringType | 종목명 |
| `Open` / `High` / `Low` / `Close` | DoubleType | OHLC |
| `Volume` | DoubleType | 거래량 |
| `effective_kr_date` | DateType | 한국 유효 영업일 (미국 +1영업일 시프트) |
| `log_return` | DoubleType | 로그 수익률 ln(Pt/Pt-1), 첫 행 0 |
| `volatility_gk` | DoubleType | Garman-Klass 일별 변동성 |
| `volatility_5d` | DoubleType | 5일 실현 변동성, 첫 행 0 |
| `year` / `month` / `day` | IntegerType | 파티션 컬럼 |

> 노트북: `01_yfinance_raw_to_silver` | 주기: 일별 | 날짜기준: `effective_kr_date`

### 3-3. `curated/fred/` — FRED Silver (250행 · 12컬럼)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DateType | 미국 영업일 |
| `DGS10` | DoubleType | 10년물 국채금리 |
| `DGS2` | DoubleType | 2년물 국채금리 |
| `T10Y2Y` | DoubleType | 10년-2년 금리차 (FRED 원본) |
| `DFF` | DoubleType | 연방기금금리 (FFR) |
| `DFII10` | DoubleType | 10년물 실질금리 (TIPS) |
| `BAMLH0A0HYM2` | DoubleType | 하이일드 스프레드 (신용위험) |
| `yield_spread` | DoubleType | DGS10 - DGS2 (직접 계산) |
| `yield_spread_change` | DoubleType | 금리차 일별 변화량, 첫 행 0 |
| `stagnation_pressure` | DoubleType | DGS10 + DFII10 (스태그플레이션 압력) |
| `year` / `month` | IntegerType | 파티션 컬럼 |

> 노트북: `02_fred_raw_to_silver` | Forward Fill + 영업일 보정

### 3-4. `curated/` — FX Silver (10컬럼)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DateType | 한국 영업일 |
| `usd_krw` | DoubleType | 일별 평균 환율 |
| `usd_krw_low` / `usd_krw_high` | DoubleType | 일중 최저·최고 환율 |
| `수집횟수` | LongType | 하루 수집 건수 (최대 24) |
| `usd_krw_change` | DoubleType | 전일 대비 변화량 (원), 첫 행 0 |
| `usd_krw_pct` | DoubleType | 전일 대비 변화율 (%), 첫 행 0 |
| `risk_off_flag` | IntegerType | 달러 급등 신호 (≥1% 상승 시 1) |
| `year` / `month` | IntegerType | 파티션 컬럼 |

> 노트북: `03_fx_raw_to_silver` | 일별 평균 집계

### 3-4b. `feature/sense_macro/` — FX Gold 중간 저장 (신규 6컬럼 — 2026-04 간소화)

> ⚠️ **실제 경로**: `feature/sense_macro/` — 문서 표기 `feature/sense/` 와 다름  
> 기존 10컬럼에서 `usd_krw_low`, `usd_krw_high`, `수집횟수` 제거 후 6컬럼으로 간소화됨.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DateType | 기준일자 (한국 영업일) |
| `usd_krw` | DoubleType | 일별 환율 |
| `usd_krw_change` | DoubleType | 전일 대비 변화량 (원) |
| `usd_krw_pct` | DoubleType | 전일 대비 변화율 (%) |
| `risk_off_flag` | IntegerType | 달러 급등 신호 (≥1% 시 1) |
| `year` / `month` | IntegerType | 파티션 컬럼 |

### 3-5. `curated/semiconductor/` — semiconductor Silver (511행 · 6컬럼)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DateType | 한국 영업일 (Forward Fill 완료) |
| `export_usd` | DoubleType | 월별 반도체 수출액 (USD, HS8542 합산) |
| `export_change_pct` | DoubleType | 전월 대비 수출 변화율 (%), 첫 행 0 |
| `export_momentum` | IntegerType | 수출 급감 경보 (≤-10% 시 1) |
| `year` / `month` | IntegerType | 파티션 컬럼 |

> 노트북: `04_semiconductor_raw_to_silver` | 일별 (Forward Fill) | 날짜기준: `date`

### 3-6. `curated/semiconductor/` — kfinance Silver (28행 · 9컬럼, 월별)

> ⚠️ **PCR 계산 불가** (2026-04 확인): 코스피200 풋옵션 없음, 월별 스냅샷

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | DateType | 기준일자 (해당 월 마지막 영업일) |
| `call_volume` | DoubleType | 코스피200 콜 거래량 합계 |
| `call_oi` | DoubleType | 코스피200 콜 미결제약정 합계 |
| `avg_iv` | DoubleType | 거래량 가중평균 내재변동성 (VIX 대용) |
| `iv_change` | DoubleType | IV 전월 대비 변화량, 첫 행 0 |
| `vol_change_pct` | DoubleType | 거래량 전월 대비 변화율 (%), 첫 행 0 |
| `iv_surge_flag` | IntegerType | IV 급등 신호 (전월비 +5 이상 시 1) |
| `year` / `month` | IntegerType | 파티션 컬럼 |

> 노트북: `05_kfinance_raw_to_silver` | 날짜기준: `date` (한국 영업일)

### Silver 처리 요약

| # | 실제 경로 | 노트북 | 주기 | 날짜 기준 |
|---|---|---|---|---|
| 1 | `curated/yfinance/` | `01_yfinance_raw_to_silver` | 일별 | `effective_kr_date` |
| 2 | `curated/fred/` | `02_fred_raw_to_silver` | 일별 | `date` (미국 영업일) |
| 3 | `curated/fx/` | `03_fx_raw_to_silver` | 일별 | `date` (한국 영업일) |
| 4 | `curated/semiconductor/` | `04_semiconductor_raw_to_silver` | 일별 (FF) | `date` (한국 영업일) |
| 5 | `curated/kfinance/` | `05_kfinance_raw_to_silver` | 월별 | `date` (한국 영업일) |
| 6 | `silver/news/` | 뉴스 전처리 파이프라인 | 기간별 | `pub_date` |

---

## 4. PostgreSQL (Gold) — 테이블 구조

### Gold 처리 흐름

```
Silver (curated/fred/, curated/fx/, curated/kfinance/, curated/semiconductor/, curated/yfinance/)
  → Databricks 02_curated_to_feature
  → feature/sense_macro/ (⚠️ 실제 경로: feature/sense/ 아님)
  → PostgreSQL

Silver (silver/news/)
  → 뉴스 ABSA/벡터 파이프라인
  → PostgreSQL (Gold 뉴스 테이블)
```

Gold JOIN 기준: `date` (한국 영업일 기준으로 3개 Silver 통합)

파생 컬럼 (소스 간 결합 필요):
- NVDA 수익률 × 금리 변화 상관도
- `risk_off_flag` (금 급등 + DXY 강세 동시 발생)
- `is_high_risk` (volatility_5d 기준 라벨링)

### 4-1. 뉴스 Gold (2026-04 재설계)

| 테이블 | 트랙 | 설명 |
|---|---|---|
| `dim_news_display` | Web App / Power BI | 뉴스 리스트 서빙용 (Text 타입, 무거운 본문 제외) |
| `agg_market_sentiment_daily` | EDA / 통계 분석 | 일별 집계, PK: (base_date, stock_code) |
| `fact_feature_vector_store` | ML / RAG | pgvector HNSW 인덱스, keyword_momentum JSONB |

#### `dim_news_display`

| 필드명 | 타입 | Silver 소스 | 비고 |
|---|---|---|---|
| `news_id` | UUID | `news_id` | PK |
| `display_title` | Text | `headline` | - |
| `core_summary` | Text | `description` | AI 3줄 요약 |
| `sentiment_class` | Varchar(10) | `absa_score` | ≥0.3→호재, ≤-0.3→악재 |
| `category` | Varchar(30) | `category` | - |
| `press` | Text | `press` | - |
| `original_url` | Text | `url` | - |
| `stock_keyword` | Text | `stock_keyword` | 삼성/SK하이닉스 구분 |
| `pub_date` | Date | `pub_date` | - |
| `is_surge` | BOOLEAN | `dynamic_keywords` | 급증 여부 |

#### `agg_market_sentiment_daily`

| 필드명 | 타입 | Silver 소스 | 비고 |
|---|---|---|---|
| `base_date` | Date | `pub_date` | PK 후보 |
| `stock_code` | Text | `stock_keyword` | PK 후보 |
| `avg_sentiment` | Float | `absa_score` | 일 평균 |
| `news_vol` | Integer | `news_id` | 건수 카운트 |
| `main_aspect` | Text | `absa_aspect` | 최빈값 |
| `daily_keywords` | JSONB | `dynamic_keywords` | TOP 10, 8개 필드 포함 |

`daily_keywords` 구조:
```json
[
  {
    "rank": 1,
    "keyword": "HBM",
    "mention_count": 18,
    "avg_sentiment": 0.62,
    "sentiment_label": "positive",
    "mention_delta": 7,
    "mention_delta_pct": 63.6,
    "sentiment_delta": 0.14
  }
]
```

#### `fact_feature_vector_store`

| 필드명 | 타입 | Silver 소스 | 비고 |
|---|---|---|---|
| `news_id` | UUID | `news_id` | PK |
| `summary_vec` | Vector(1536) | `summary_vector` | HNSW 인덱스 |
| `search_context` | Text | `body` | RAG LLM 주입용 |
| `feature_score` | Float | `absa_score` | ML 독립 변수 |
| `aspect_tag` | Text | `absa_aspect` | 리스크 가중치용 |
| `keyword_momentum` | JSONB | `keyword_momentum` | `{"키워드": 급증률%}` |

### 4-2. 매크로 Gold (`gold_macro` 스키마)

| 테이블 | PK | 설명 |
|---|---|---|
| `gold_macro.dim_macro_metadatas` | `unified_id` | 지표 메타데이터 레지스트리 (설계: `dim_macro_series`) |
| `gold_macro.fact_macro_all` | `base_date` | 매크로 통합 Wide 테이블 (설계: `fact_macro_daily`) |
| `gold_macro.fact_yf_fx_fred_1y` | `standard_date` | Yahoo Finance + FX + FRED 1년 통합 |
| `gold_macro.fact_kfinance` | `(base_date, ticker)` | 한국 금융 파생상품 |
| `gold_macro.fact_semiconductor_trade` | `(base_date, hs_code)` | 반도체 수출입 통계 |

### 4-3. 주가 Gold (`gold_equity` 스키마)

| 테이블 | PK | 설명 |
|---|---|---|
| `gold_equity.dim_equity` | `equity_id` | 종목 메타데이터 (seed 9개 종목) |
| `gold_equity.fact_equity_ohlcv` | `(equity_id, trade_date)` | 일별 OHLCV |
| `gold_equity.fact_equity_target` | `(equity_id, trade_date)` | ML 타겟 변수 (downside_flag, upside_flag, regime) |
| `gold_equity.fact_equity_signals` | `(equity_id, trade_date, signal_name)` | 파생 기술 지표 |

### 4-4. 퀀트 / ML Gold (`gold_ml` 스키마)

> ⚠️ PCR 보류 처리했으나 실제로는 `gold_quant_pcr_signals` 생성됨

| 테이블 | PK | 설명 |
|---|---|---|
| `gold_ml.fact_quant_sox_sync` | `us_trade_date` | SOX ↔ SK하이닉스 동조화 |
| `gold_ml.fact_quant_memory_proxy` | `trade_date` | MU/WDC 기반 메모리 심리 지수 |
| `gold_ml.gold_customs_semiconductor` | `(stat_year, stat_month, hs_code)` | 관세청 반도체 수출 (중복 테이블 주의) |
| `gold_ml.gold_ml_feature_set` | `trade_date` | ML 통합 피처 세트 (설계에 없던 신규 테이블) |
| `gold_ml.gold_quant_pcr_signals` | `trade_date` | PCR 퀀트 시그널 (설계: 보류 → 실제 생성) |

### 4-5. 보고서 연동 뷰

> 2026-04-14 기준 6개 뷰 모두 생성됨

| 뷰 | 스키마 | 소스 | 설명 |
|---|---|---|---|
| `v_forecast_latest` | `public` | `fact_ensemble_forecast` | 티커·기간별 최신 run 앙상블 예측 |
| `v_daily_report_summary` | `public` | `v_forecast_latest` + 감성 + 매크로 | 일간 보고서 종합 |
| `v_model_comparison_latest` | `public` | `v_forecast_latest` + `fact_stat_forecast` | 앙상블 vs 통계 기준선 비교 |
| `v_news_sentiment_trend` | `gold_news` | `agg_market_sentiment_daily` | 일별 감성 + 7일 이동평균 |
| `v_macro_latest` | `gold_macro` | `fact_yf_fx_fred_1y` | 최신 매크로 1행 스냅샷 (`standard_date` 기준) |
| `v_quant_daily_signals` | `gold_ml` | sox + 메모리 + PCR LEFT JOIN | 퀀트 통합 시그널 (`signal_date` 컬럼) |

---

## 5. 데이터사전 vs 실제 구조 차이점

### 5-1. ADLS Gen2 경로 차이 (az CLI 실제 확인, 2026-04-14)

| # | 항목 | 문서 경로 | 실제 경로 | 상태 |
|---|---|---|---|---|
| 1 | FRED Bronze | `raw/fred/` | `raw/fred_macro_data/` | ❌ 경로 다름 |
| 2 | 뉴스 Silver 위치 | `curated/news/` | `silver/news/{google_bing,naver,feature}/` | ❌ 컨테이너 다름 |
| 3 | Gold ADLS 경로 | `feature/sense/` | `feature/sense_macro/`, `feature/gold_macro_1y/`, `feature/macro_semiconductor/` | ❌ 경로 다름 |
| 4 | `silver/` 컨테이너 | 미기재 | `silver/news/feature/`, `silver/news/google_bing/`, `silver/news/naver/` | ❌ 완전 누락 |
| 5 | `raw/public_data/` 서브 | 단일 경로 | `raw/public_data/finance/`, `raw/public_data/semiconductor/` | ℹ️ 서브디렉토리 추가 |
| 6 | `curated/macro/` | 문서에 있음 | 미존재 | ❌ 미생성 |
| 7 | `curated/equity/` | 문서에 있음 | 미존재 | ❌ 미생성 |
| 8 | `curated/quant/` | 문서에 있음 | 미존재 | ❌ 미생성 |
| 9 | `curated/news/` | 문서에 있음 | 미존재 — `silver/` 컨테이너 사용 | ❌ |

### 5-2. PostgreSQL 실제 스키마 구조 (2026-04-14 확인)

> **확인 방법**: pgAdmin / PostgreSQL MCP 직접 조회
> **실제 스키마 4개**: `gold_equity`, `gold_macro`, `gold_ml`, `gold_news`  
> ※ 데이터사전에는 스키마 분리 없이 단일 `public` 스키마로 설계되어 있었으나,  
> 실제 구현 시 스키마를 분리하여 생성됨

#### 실제 PostgreSQL 스키마·테이블 목록

| 스키마 | 테이블 | 상태 | 비고 |
|---|---|---|---|
| `gold_equity` | `dim_equity` | ✅ 생성됨 | 종목 메타데이터 (seed 9행) |
| `gold_equity` | `fact_equity_ohlcv` | ✅ 생성됨 | 일별 OHLCV |
| `gold_equity` | `fact_equity_target` | ✅ 생성됨 | ML 타겟 변수 |
| `gold_equity` | `fact_equity_signals` | ✅ 생성됨 | 파생 기술 지표 |
| `gold_macro` | `dim_macro_metadatas` | ✅ 생성됨 | 지표 메타 |
| `gold_macro` | `fact_kfinance` | ✅ 생성됨 | 금융 파생상품 |
| `gold_macro` | `fact_macro_all` | ✅ 생성됨 | 매크로 통합 |
| `gold_macro` | `fact_semiconductor_trade` | ✅ 생성됨 | 반도체 수출입 |
| `gold_macro` | `fact_yf_fx_fred_1y` | ✅ 생성됨 | Yahoo Finance + FX + FRED 1년 |
| `gold_ml` | `fact_quant_memory_proxy` | ✅ 생성됨 | MU/WDC 기반 메모리 프록시 |
| `gold_ml` | `fact_quant_sox_sync` | ✅ 생성됨 | SOX ↔ SK하이닉스 동조화 |
| `gold_ml` | `gold_customs_semiconductor` | ✅ 생성됨 | 관세청 반도체 수출 |
| `gold_ml` | `gold_ml_feature_set` | ✅ 생성됨 | ML 통합 피처 세트 |
| `gold_ml` | `gold_quant_pcr_signals` | ✅ 생성됨 | PCR 퀀트 시그널 |
| `gold_news` | `agg_market_sentiment_daily` | ✅ 생성됨 | 일별 감성 집계 |
| `gold_news` | `dim_news_display` | ✅ 생성됨 | 뉴스 서빙용 |
| `gold_news` | `fact_feature_vector_store` | ✅ 생성됨 | pgvector RAG/ML용 |

#### 데이터사전 vs 실제 차이 비교

| 항목 | 데이터사전 설계 | 실제 PostgreSQL | 상태 |
|---|---|---|---|
| 스키마 구조 | `public` 단일 스키마 | `gold_equity`, `gold_macro`, `gold_ml`, `gold_news` 4개 | ❌ 설계 불일치 |
| 뉴스 Gold | `dim_news_display`, `agg_market_sentiment_daily`, `fact_feature_vector_store` | `gold_news` 스키마에 동일하게 존재 | ✅ 테이블명 일치 |
| 매크로 Gold | `dim_macro_series`, `fact_macro_daily`, `fact_macro_derived`, `fact_macro_fred` | `gold_macro.dim_macro_metadatas`, `fact_macro_all`, `fact_yf_fx_fred_1y` | ⚠️ 테이블명 불일치 |
| kfinance Gold | `fact_kfinance` (미기재) | `gold_macro.fact_kfinance` | ❌ 데이터사전 누락 |
| 반도체 Gold | `fact_quant_customs` | `gold_macro.fact_semiconductor_trade`, `gold_ml.gold_customs_semiconductor` | ⚠️ 이름·스키마 다름 |
| 주가 Gold | `dim_equity`, `fact_equity_ohlcv` 등 | `gold_equity` 4개 테이블 모두 생성됨 | ✅ 생성됨 |
| 퀀트 Gold | `fact_quant_sox_sync`, `fact_quant_memory_proxy`, `fact_quant_pcr` | `gold_ml`에 모두 존재 + `gold_quant_pcr_signals` 생성됨 | ✅ (PCR 보류 → 실제 생성) |
| ML 피처 | 미기재 | `gold_ml.gold_ml_feature_set` | ❌ 데이터사전 누락 |
| ML 예측 (public) | 미기재 | `fact_ensemble_forecast` (15컬럼, 160행), `fact_stat_forecast` (9컬럼) | ❌ 데이터사전 누락 |

#### 실제 존재하는 주요 테이블 스키마

**`fact_ensemble_forecast`** (TimesFM 앙상블 예측 결과, 160행)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `date` | timestamp | 예측 대상 일자 |
| `ticker` | text | 종목 코드 |
| `base_date` | timestamp | 예측 기준일 |
| `horizon_day` | bigint | 예측 기간 (일) |
| `trend_score` | float8 | 추세 점수 |
| `mean_rev_score` | float8 | 평균회귀 점수 |
| `trend_pred` | float8 | 추세 예측값 |
| `meanrev_pred` | float8 | 평균회귀 예측값 |
| `final_pred` | float8 | 최종 앙상블 예측값 |
| `pi_lower` / `pi_upper` | float8 | 예측 구간 (하단/상단) |
| `confidence_score` | float8 | 신뢰도 점수 |
| `regime_flag` | bigint | 시장 국면 코드 |
| `regime_label` | text | 시장 국면 레이블 |
| `run_timestamp` | timestamp | 모델 실행 시각 |

**`fact_stat_forecast`** (통계 기준선 예측 결과)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `ticker` | text | 종목 코드 |
| `base_date` | timestamp | 예측 기준일 |
| `horizon` | bigint | 예측 기간 |
| `model` | text | 모델명 |
| `model_type` | text | 모델 유형 |
| `prediction` | float8 | 예측값 |
| `change_pct` | float8 | 변화율 (%) |
| `scenario` | text | 시나리오 레이블 |
| `run_timestamp` | timestamp | 모델 실행 시각 |

### 5-3. 데이터사전 내 기존 변경 이력 (본 문서 작성 전 완료)

| 항목 | 변경 전 | 변경 후 | 반영 여부 |
|---|---|---|---|
| 뉴스 Gold 테이블 | `dim_news_master` + `fact_news_analytics` | `dim_news_display` + `agg_market_sentiment_daily` + `fact_feature_vector_store` | ✅ 완료 |
| 뉴스 Silver 컬럼 수 | 7개 | 16개 (OpenAI 분석 결과 포함) | ✅ 완료 |
| `news_source` 범위 | "google", "naver" | "google", "naver", "bing" | ✅ 완료 |
| `keyword_momentum` 타입 | Float | JSONB `{"키워드": 급증률%}` | ✅ 완료 |
| `daily_keywords` 구조 | 단순 배열 | 8개 필드 포함 JSONB 배열 | ✅ 완료 |
| kfinance Silver 컬럼 | 미기재 | 9컬럼 (`call_oi`, `avg_iv` 등) | ✅ 완료 |
| semiconductor Silver 컬럼 | 미기재 | 6컬럼 (`export_usd`, `export_momentum` 등) | ✅ 완료 |
| `fact_quant_pcr` 상태 | 구현 예정 | **구현 보류** (kfinance로 PCR 불가) | ✅ 완료 |

---

## 6. 인덱스 설계 요약

| 테이블 | 인덱스 유형 | 대상 컬럼 | 목적 |
|---|---|---|---|
| `fact_feature_vector_store` | HNSW | `summary_vec` | pgvector 코사인 유사도 RAG 검색 |
| `agg_market_sentiment_daily` | BTREE | `(base_date, stock_code)` | 시계열 + 종목 필터링 |
| `fact_equity_ohlcv` | BRIN | `trade_date` | 날짜 범위 스캔 |
| `fact_macro_daily` | BRIN | `trade_date` | 날짜 범위 스캔 |
| `dim_news_display` | GIN | `daily_keywords` | 키워드 포함 검색 |

---

## 7. 파이프라인 실행 순서

```
Phase 1: 수집 (ADF Timer Trigger)
  Google News (ACI) ───────┐
  Naver News (Functions) ──┤
  Bing News (Functions) ───┼──→ ADLS raw/  [Bronze]
  Yahoo Finance (Script) ──┤
  FX Collector (Functions)─┤
  FRED (Functions) ────────┤
  관세청 (Script, 월 1회) ──┘

Phase 2: 전처리 (Databricks)
  01_raw_to_curated  → ADLS curated/  [Silver]
  02_curated_to_feature → ADLS feature/ + PostgreSQL  [Gold]

Phase 3: 모델링 (ML Studio Batch Endpoint)
  XGBoost (downside_flag) + LightGBM (upside_flag)
  → 예측 결과 + 피처 중요도 → PostgreSQL

Phase 4: 서빙
  Power BI (DirectQuery) + Web App (RAG) + 정기 보고서 자동 생성
```
