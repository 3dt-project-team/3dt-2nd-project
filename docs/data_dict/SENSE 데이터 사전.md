## 목차

1. [뉴스 데이터](https://www.notion.so/33583637774b8095ba47f8258269f960?pvs=21)
2. [매크로 지표 데이터](https://www.notion.so/33583637774b8095ba47f8258269f960?pvs=21)
3. [주가 및 수급 데이터](https://www.notion.so/33583637774b8095ba47f8258269f960?pvs=21)
4. [퀀트 선행 지표 데이터](https://www.notion.so/33583637774b8095ba47f8258269f960?pvs=21)
5. [보고서 연동 뷰](https://www.notion.so/33583637774b8095ba47f8258269f960?pvs=21)
6. [분석 워크플로](https://www.notion.so/33583637774b8095ba47f8258269f960?pvs=21)

---

# 1. 뉴스 데이터

## 🥉 Bronze — `raw/news/google/`

> Google News ACI 크롤러 출력 (Parquet, snappy)
> 

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `source` | 검색 키워드 | String | 수집 시 사용한 검색어임 ("SK Hynix", "Samsung Electronics") | Not Null |
| `news_id` | 뉴스 ID | String | URL SHA-256 해시 앞 16자로 생성하는 기사 고유 식별자임 | Not Null, Unique |
| `url` | 원문 URL | String | 기사 원문 링크임 | Not Null |
| `pub_date` | 발행 일자 | String | 기사 발행 날짜임 (YYYY-MM-DD) | Not Null |
| `adjusted_date` | 조정 월 | String | 월 단위 파티셔닝 키로 사용하는 조정 일자임 (YYYY-MM) | Not Null |
| `headline` | 기사 제목 | String | 영문 기사 제목임 | Not Null |
| `press` | 언론사명 | String | 기사 발행 언론사 이름임 | - |
| `description` | RSS 요약문 | String | Google News RSS가 제공하는 요약문임 | - |
| `body` | 기사 본문 | String | Playwright로 수집한 기사 본문 전체 텍스트임 | - |
| `fetched_at` | 수집 시점 | String | 기사를 수집한 시점의 ISO 8601 UTC 타임스탬프임 | Not Null |

## 🥉 Bronze — `raw/news/naver/`

> 네이버 뉴스 Azure Functions 크롤러 출력 (JSON → Parquet 변환 예정)
> 

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `source` | 검색 키워드 | String | 수집 대상 기업 코드임 ("samsung", "skhynix") | Not Null |
| `news_id` | 뉴스 ID | String | 언론사별 고유 ID (naver_, yna_, hankyung_ 등 접두사)로 생성한 식별자임 | Not Null, Unique |
| `url` | 원본 URL | String | 기사 원본 링크임 | Not Null |
| `naver_url` | 네이버 뉴스 URL | String | 네이버 뉴스 플랫폼 내 기사 링크임 | - |
| `pub_date` | 발행 일자 | String | 기사 발행 날짜임 (YYYY-MM-DD, KST) | Not Null |
| `adjusted_date` | 조정 일자 | String | 파티셔닝용 조정 날짜임 (YYYY-MM-DD) | Not Null |
| `headline` | 기사 제목 | String | 한국어 기사 제목임 | Not Null |
| `description` | API 요약문 | String | 네이버 검색 API가 반환하는 요약문임 | - |
| `body` | 기사 본문 | String | Playwright 선택자 기반으로 파싱한 본문 텍스트임 | - |
| `fetched_at` | 수집 시점 | String | 수집 시점의 ISO 8601 UTC 타임스탬프임 | Not Null |

## 🥉 Bronze — `raw/news/bing/`

> bing news, Grounding with Bing Search 활용하여 크롤러 출력 (JSON, Parquet)
> 

| 필드명(물리) | **필드명(논리)** | **데이터 타입** | **설명** | **제약사항** |
| --- | --- | --- | --- | --- |
| `source` | 검색 키워드 | String | 수집 시 사용한 검색어임 ("samsung", "skhynix") | Not Null |
| `news_id` | 뉴스 ID | String | URL SHA-256 해시 앞 16자로 생성하는 고유 식별자임 (접두사 'bing_' 사용) | Not Null, Unique |
| `url` | 원문 URL | String | 기사 원문 링크이며 유효성 검증(200 OK)을 통과한 주소임 | Not Null |
| `pub_date` | 발행 일자 | String | 기사 발행 날짜임 (YYYY-MM-DD, UTC 기준) | Not Null |
| `adjusted_date` | 조정 월 | String | 월 단위 파티셔닝 키로 사용하는 조정 일자임 (YYYY-MM) | Not Null |
| `headline` | 기사 제목 | String | 영문 기사 제목임 | Not Null |
| `press` | 언론사명 | String | 기사를 발행한 언론사 명칭임 | - |
| `body` | 기사 본문 | String | Bing Grounding 기반으로 생성된 핵심 수치 포함 상세 요약본임 | Not Null |
| `fetched_at` | 수집 시점 | String | ISO 8601 UTC 형식의 수집 타임스탬프임 | Not Null |

## 🥈 Silver — `curated/news/`

> Databricks 01_raw_to_curated 노트북 출력 (Parquet)
> 

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `news_id` | 뉴스 ID | String | Bronze에서 승계한 기사 고유 식별자임 | PK, Not Null |
| `news_source` | 데이터 소스 | String | 원본 소스 구분자임 ("google", "naver") | Not Null |
| `pub_date` | 발행 일자 | Date | 정규화된 발행 날짜임 | Not Null |
| `headline` | 기사 제목 | String | 원본 그대로 보존한 기사 제목임 | Not Null |
| `clean_text` | 정제 본문 | String | HTML 태그·특수문자 제거 후 정규화한 본문 텍스트임 | Not Null |
| `url` | 원문 URL | String | 기사 원문 링크임 | - |
| `press` | 언론사명 | String | 기사 발행 언론사 이름임 | - |

## 🥇 Gold — `feature/sense/` + PostgreSQL

> Databricks 02_curated_to_feature 노트북 출력 → PostgreSQL 적재
> 

### `dim_news_master` (뉴스 원문 및 검색 벡터)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `news_id` | 뉴스 ID | UUID | 기사를 고유하게 식별하기 위한 해시 기반 ID임 | PK, Not Null |
| `published_date` | 발행 일자 | Date | 시계열 조인 및 BI 필터링 기준 날짜임 | Not Null |
| `published_time` | 발행 시각 | Timestamp | 장중/장마감 후 판단에 사용하는 정확한 발행 시각임 | - |
| `news_source` | 언론사명 | Varchar(50) | 뉴스 출처 언론사 이름임 (신뢰도 파악용) | - |
| `title` | 기사 제목 | Varchar(255) | 대시보드 리스트 표출용 기사 제목임 | Not Null |
| `full_text` | 기사 본문 | Text | 유저에게 원문을 보여줄 때 호출하는 서빙용 전체 본문임 | Not Null |
| `core_summary` | 핵심 요약 | Text | Azure OpenAI가 3줄로 요약한 핵심 내용임 (RAG 컨텍스트 주입용) | Not Null |
| `category` | 뉴스 카테고리 | Varchar(30) | Azure OpenAI가 요약 시 함께 분류한 기사 카테고리임 (예: 실적, 공급망, 규제, 기술, 거시경제, 수급, 기타). 카테고리별 노이즈 필터링 및 분석에 활용함 | Not Null |
| `summary_vector` | 요약 벡터 | Vector(1536) | `core_summary`를 임베딩한 1536차원 벡터임 (pgvector 코사인 유사도 검색용) | Not Null |
| `original_url` | 원문 링크 | Varchar(500) | 원문 기사로 이동할 수 있는 아웃링크임 | - |

### `fact_news_analytics` (동적 키워드 및 ABSA 감성 점수)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `analytics_id` | 분석 ID | Bigserial | 분석 기록의 고유 식별 번호임 (자동 증가) | PK, Not Null |
| `news_id` | 뉴스 ID | UUID | `dim_news_master` 테이블의 `news_id`를 참조하는 외래키임 | FK, Not Null |
| `analyzed_date` | 분석 기준일 | Date | 분석을 수행한 기준 일자임 | Not Null |
| `dynamic_keywords` | 동적 키워드 | JSONB | TF-IDF/LLM으로 추출한 당일 핵심 키워드 배열임 (예: `["트럼프_관세", "HBM_수율"]`). GIN 인덱스로 검색함 | Not Null |
| `keyword_momentum` | 키워드 모멘텀 | JSONB | 키워드별 전일 대비 언급 급증률(%) 매핑임 (예: `{"트럼프_관세": 350.0}`). 300% 이상 시 경고 표시함 | - |
| `absa_aspect` | ABSA 속성 | Varchar(50) | LLM이 분류한 뉴스 속성 카테고리임 (제조원가, 양산일정, 공급망 등) | - |
| `absa_score` | ABSA 감성 점수 | Float | 해당 키워드·속성에 대한 양방향 감성 점수임 (-1.0 강한 부정 ~ 1.0 강한 긍정). 하방 리스크(< -0.3) 및 상승 모멘텀(> +0.3) 모두 탐지함 | Not Null |

---

# 2. 매크로 지표 데이터

## 🥉 Bronze — `raw/yfinance/` + `raw/fx/` + `raw/fred/`

### Yahoo Finance 매크로 (CSV)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `date` | 거래일 | Datetime | 거래가 발생한 날짜임 (인덱스) | Not Null |
| `ticker` | 티커 코드 | String | Yahoo Finance 원본 티커 코드임 (`CL=F`, `GC=F` 등) | Not Null |
| `name` | 종목명 | String | 지표 표시명임 | Not Null |
| `open` | 시가 | Float64 | 당일 시작 가격임 | - |
| `high` | 고가 | Float64 | 당일 최고 가격임 | - |
| `low` | 저가 | Float64 | 당일 최저 가격임 | - |
| `close` | 종가 | Float64 | 당일 마감 가격임 | Not Null |
| `volume` | 거래량 | Float64 | 당일 거래량임 (선물에만 존재) | - |

### Open Exchange Rates 환율 (Parquet)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `provider` | 제공사 | String | 데이터 제공사 이름임 ("openexchangerates") | Not Null |
| `base_currency` | 기준 통화 | String | 기준 통화 코드임 ("USD") | Not Null |
| `quote_currency` | 상대 통화 | String | 상대 통화 코드임 ("KRW") | Not Null |
| `rate` | 환율 | Float64 | USD 대비 KRW 환율 값임 | Not Null |
| `provider_timestamp_utc` | 제공사 시각 (UTC) | Timestamp | 제공사가 환율을 계산한 시점의 UTC 타임스탬프임 | Not Null |
| `collected_at_utc` | 수집 시각 (UTC) | Timestamp | SENSE 시스템이 수집한 시점의 UTC 타임스탬프임 | Not Null |
| `collected_at_kst` | 수집 시각 (KST) | Timestamp | 수집 시점의 한국 표준시 타임스탬프임 | Not Null |
| `provider_timestamp_unix` | UNIX 타임스탬프 | Integer | 제공사 시점의 UNIX 초 단위 타임스탬프임 | Not Null |
| `raw_payload_json` | 원본 응답 | String | API 원본 JSON 응답 전체를 보존한 문자열임 | - |
- 환율 제공처: Frankfurter(최근 1년), Open Exchange Rates(실시간)

### FRED 금리 (Parquet)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `observed_date` | 관측일자 | Date | 경제지표 값이 관측된 기준 일자임 | PK 후보, Not Null |
| `series_code` | 지표코드 | String | FRED 시계열 식별 코드임 | PK 후보, Not Null |
| `rate_value` | 금리값 | Number | 관측일자 기준 지표의 수치 값임 | Not Null |
| `collected_at_utc` | 수집일시(UTC) | Timestamp | 서버가 데이터를 수집한 UTC 기준 시각임 | - |

> 대상 시계열 코드
> 
> - `DGS10` (일간): 미국 10년물 국채 금리 (10-Year Treasury Constant Maturity Rate)
> - `DGS2` (일간): 미국 2년물 국채 금리 (2-Year Treasury Constant Maturity Rate)
> - `T10Y2Y` (일간): 장단기 금리차 (10-Year Minus 2-Year Treasury Yield Spread)
> - `BAMLH0A0HYM2` (일간): 하이일드 채권 스프레드 (ICE BofA US High Yield Index Option-Adjusted Spread)
> - `DFF` (일간): 실효 연방기금금리 (Effective Federal Funds Rate)
> - `DFII10` (일간): 10년물 실질 금리 (10-Year Treasury Inflation-Indexed Security)

## 🥈 Silver — `curated/macro/`

> Databricks에서 시계열 정합 처리 (Forward Fill + 일별 집계)
> 

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `record_id` | 통합 레코드 ID | String | 원천 데이터 조합으로 생성한 통합 레코드 식별자임 | PK, Not Null |
| `observation_date` | 관측일자 | Date | 시장 데이터 또는 경제지표가 유효한 기준 일자임 | PK 후보, Not Null |
| `source_provider` | 제공사 | String | 데이터 제공사 또는 원천 시스템명임 | Not Null |
| `source_dataset` | 원천 데이터셋 | String | 원본 데이터셋 구분값임 (`yahoo_finance`, `open_exchange_rates`, `fred`) | Not Null |
| `indicator_category` | 지표 분류 | String | 지표 유형 구분값임 (`commodity`, `fx`, `rate`) | Not Null |
| `indicator_code` | 지표 코드 | String | 원천 시스템 기준 지표 식별 코드임 | PK 후보, Not Null |
| `indicator_name` | 지표명 | String | 분석용 표준 지표명임 | Not Null |
| `base_currency` | 기준 통화 | String | 기준 통화 코드임 | FX 행에서 Not Null |
| `quote_currency` | 상대 통화 | String | 상대 통화 코드 또는 정산 통화 코드임 | FX 행에서 Not Null |
| `price_open` | 시가 | Float64 | 당일 시작 가격임 | - |
| `price_high` | 고가 | Float64 | 당일 최고 가격임 | - |
| `price_low` | 저가 | Float64 | 당일 최저 가격임 | - |
| `price_close` | 종가 | Float64 | 당일 마감 가격임 | - |
| `trading_volume` | 거래량 | Float64 | 당일 거래량임 | - |
| `provider_timestamp_utc` | 제공사 시각(UTC) | Timestamp | 제공사가 값을 산출하거나 게시한 UTC 기준 시각임 | - |
| `collected_at_utc` | 수집 시각(UTC) | Timestamp | 시스템이 원천 데이터를 수집한 UTC 기준 시각임 | Not Null |
| `collected_at_kst` | 수집 시각(KST) | Timestamp | 시스템이 원천 데이터를 수집한 KST 기준 시각임 | Not Null |

## 🥈 Silver — `curated/fred/`

> Databricks에서 FRED 금리 시계열 정합 처리 (Forward Fill, 영업일 보정)
> 

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `series_code` | 지표코드 | String | FRED 시계열 식별 코드임 (DGS10, DGS2 등) | Not Null |
| `observed_date` | 관측일자 | Date | 정합된 거래일임 (영업일 기준 Forward Fill 적용) | Not Null |
| `rate_value` | 금리값 | Float | 해당 일자의 금리 수치 값임 | Not Null |
| `is_filled` | 보간 여부 | Boolean | Forward Fill 보간으로 채워진 값인지 여부를 나타내는 플래그임 | Not Null, Default: false |

## 🥇 Gold — PostgreSQL

### `dim_macro_series` (지표 메타데이터)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `series_id` | 지표 ID | Smallint | 매크로 지표를 고유하게 식별하는 ID임 | PK |
| `ticker` | 티커 코드 | Varchar(20) | 원본 티커 코드임 (`CL=F`, `GC=F` 등) | Not Null, Unique |
| `display_name` | 표시명 | Varchar(50) | 대시보드와 보고서에 표시되는 한글 지표명임 | Not Null |
| `category` | 카테고리 | Varchar(20) | 지표 분류임 (commodity, bond, currency, index) | Not Null |
| `unit` | 단위 | Varchar(20) | 지표 단위임 (USD/bbl, USD/oz, %, index) | Not Null |
| `data_source` | 데이터 출처 | Varchar(30) | 원천 데이터 소스명임 (yahoo_finance, open_exchange_rates, fred) | Not Null |

### `fact_macro_daily` (일별 시계열)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `series_id` | 지표 ID | Smallint | `dim_macro_series.series_id`를 참조하는 외래키임 | FK, Not Null |
| `trade_date` | 거래일 | Date | 거래가 발생한 날짜임 | Not Null |
| `open` | 시가 | Float | 시가임 (일부 지표는 NULL) | - |
| `high` | 고가 | Float | 고가임 | - |
| `low` | 저가 | Float | 저가임 | - |
| `close` | 종가 | Float | 종가이며 모든 지표의 기본값임 | Not Null |
| `volume` | 거래량 | Bigint | 거래량임 (선물에만 존재) | - |
| `is_filled` | 보간 여부 | Boolean | Forward Fill 보간 여부를 나타내는 플래그임 | Not Null, Default: false |

> **UNIQUE:** `(series_id, trade_date)`
> 

### `fact_macro_derived` (파생 기술 지표)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `series_id` | 지표 ID | Smallint | `dim_macro_series.series_id`를 참조하는 외래키임 | FK, Not Null |
| `trade_date` | 기준일 | Date | 파생 지표 연산 기준 날짜임 | Not Null |
| `indicator_name` | 지표명 | Varchar(30) | 파생 지표 이름임 (ma_5, ma_20, rsi_14, return_1d, return_5d, z_score_20d) | Not Null |
| `indicator_value` | 지표값 | Float | 파생 지표 연산 결과값임 | Not Null |

> **UNIQUE:** `(series_id, trade_date, indicator_name)`
> 

### `fact_macro_fred` (FRED 금리 시계열)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `series_code` | 지표코드 | Varchar(20) | FRED 시계열 식별 코드임 (DGS10, DGS2, T10Y2Y, BAMLH0A0HYM2, DFF, DFII10) | Not Null |
| `observed_date` | 관측일자 | Date | 금리 값이 관측된 기준 날짜임 | Not Null |
| `rate_value` | 금리값 | Float | 관측일자 기준 금리 수치(%)임 | Not Null |
| `is_filled` | 보간 여부 | Boolean | Forward Fill 보간으로 채워진 값인지 여부를 나타내는 플래그임 | Not Null, Default: false |

> **UNIQUE:** `(series_code, observed_date)`
> 
> 
> 대상 시계열: `DGS10` (10년물 국채금리), `DGS2` (2년물 국채금리), `T10Y2Y` (장단기 금리차), `BAMLH0A0HYM2` (하이일드 스프레드), `DFF` (실효 연방기금금리), `DFII10` (10년물 실질금리)
> 

---

# 3. 주가 및 수급 데이터

## 🥉 Bronze — `raw/yfinance/`

> Yahoo Finance 크롤러 출력 (CSV, UTF-8-BOM)
> 

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `date` | 거래일 | Datetime | 거래가 발생한 날짜임 (인덱스) | Not Null |
| `ticker` | 티커 코드 | String | Yahoo Finance 종목 티커 코드임 (005930.KS, NVDA 등) | Not Null |
| `name` | 종목명 | String | 종목 표시명임 (한글/영문) | Not Null |
| `open` | 시가 | Float64 | 당일 시작 가격임 | - |
| `high` | 고가 | Float64 | 당일 최고 가격임 | - |
| `low` | 저가 | Float64 | 당일 최저 가격임 | - |
| `close` | 종가 | Float64 | 당일 마감 가격임 | Not Null |
| `volume` | 거래량 | Float64 | 당일 총 거래량임 | - |

## 🥈 Silver — `curated/equity/`

> Databricks에서 시차 정렬 + Forward Fill + 이상치 태깅
> 

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `equity_id` | 종목 ID | Smallint | `dim_equity`에서 참조하는 종목 식별자임 | FK, Not Null |
| `trade_date` | 거래일 | Date | 정합된 거래일임 | Not Null |
| `kr_effective_date` | 한국 반영일 | Date | 미국 종목의 종가가 한국 시장에 반영되는 시점임 (미국 T → 한국 T+1 영업일) | Not Null |
| `open` | 시가 | Float | 시가임 | - |
| `high` | 고가 | Float | 고가임 | - |
| `low` | 저가 | Float | 저가임 | - |
| `close` | 종가 | Float | 종가임 | Not Null |
| `volume` | 거래량 | Bigint | 거래량임 | - |
| `is_filled` | 보간 여부 | Boolean | Forward Fill 보간 여부 플래그임 | Not Null, Default: false |
| `is_anomaly` | 이상치 여부 | Boolean | 서킷 브레이커 등 이상 거래일 태깅 플래그임 | Not Null, Default: false |

## 🥇 Gold — PostgreSQL

### `dim_equity` (종목 메타데이터)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `equity_id` | 종목 ID | Smallint | 종목을 고유하게 식별하는 ID임 | PK |
| `ticker` | 티커 코드 | Varchar(20) | Yahoo Finance 원본 티커 코드임 | Not Null, Unique |
| `name_kr` | 한국어 종목명 | Varchar(50) | 종목의 한국어 이름임 | - |
| `name_en` | 영어 종목명 | Varchar(50) | 종목의 영어 이름임 | Not Null |
| `market` | 시장 | Varchar(10) | 종목이 거래되는 시장 구분임 (KOSPI, NASDAQ, CME) | Not Null |
| `asset_type` | 자산 유형 | Varchar(15) | 자산 타입 구분임 (stock, futures, etf) | Not Null |
| `role` | 역할 | Varchar(20) | 프로젝트 내 역할 구분임 (target: 예측 대상, leading: 선행 지표) | Not Null |

### `fact_equity_ohlcv` (일별 OHLCV)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `equity_id` | 종목 ID | Smallint | `dim_equity.equity_id`를 참조하는 외래키임 | FK, Not Null |
| `trade_date` | 거래일 | Date | 거래일임 | Not Null |
| `open` | 시가 | Float | 시가임 | - |
| `high` | 고가 | Float | 고가임 | - |
| `low` | 저가 | Float | 저가임 | - |
| `close` | 종가 | Float | 종가임 | Not Null |
| `volume` | 거래량 | Bigint | 거래량임 | - |
| `is_filled` | 보간 여부 | Boolean | 휴장일 Forward Fill 보간 여부를 나타내는 플래그임 | Not Null, Default: false |

> **UNIQUE:** `(equity_id, trade_date)`
> 

### `fact_equity_target` (ML 타겟 변수 — 양방향)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `equity_id` | 종목 ID | Smallint | `dim_equity.equity_id`를 참조하는 외래키임 (삼성전자·SK하이닉스만) | FK, Not Null |
| `trade_date` | 기준일 | Date | 타겟 변수 연산 기준일 (T)임 | Not Null |
| `return_1d` | 1일 수익률 | Float | T+1일 수익률(%)임 | Not Null |
| `return_5d` | 5일 수익률 | Float | T+5일 누적 수익률(%)임 | - |
| `realized_vol_5d` | 5일 변동성 | Float | T 기준 과거 5일 실현 변동성임 | - |
| `max_drawdown_5d` | 5일 최대 낙폭 | Float | T+1~T+5 구간 내 최대 낙폭(%)임 | - |
| `max_gain_5d` | 5일 최대 상승폭 | Float | T+1~T+5 구간 내 최대 상승폭(%)임 | - |
| `downside_flag` | 하방 리스크 플래그 | Boolean | `max_drawdown_5d < -3%` 시 TRUE이며, 하방 리스크 ML 타겟 변수임 | Not Null |
| `upside_flag` | 상승 모멘텀 플래그 | Boolean | `max_gain_5d > +3%` 시 TRUE이며, 상승 모멘텀 ML 타겟 변수임 | Not Null |
| `regime` | 시장 국면 | Varchar(10) | 시장 국면 판정 라벨임 (risk, opportunity, neutral, high_vol). 보고서 자동 생성에 사용함 | Not Null |

> **UNIQUE:** `(equity_id, trade_date)`
> 

### `fact_equity_signals` (파생 기술 지표)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `equity_id` | 종목 ID | Smallint | `dim_equity.equity_id`를 참조하는 외래키임 | FK, Not Null |
| `trade_date` | 기준일 | Date | 기술 지표 연산 기준일임 | Not Null |
| `signal_name` | 시그널명 | Varchar(30) | 기술 지표 이름임 (ma_5, ma_20, rsi_14, bollinger_upper, bollinger_lower, volume_ma_20, volume_ratio) | Not Null |
| `signal_value` | 시그널값 | Float | 기술 지표 연산 결과값임 | Not Null |

> **UNIQUE:** `(equity_id, trade_date, signal_name)`
> 

---

# 4. 퀀트 선행 지표 데이터

## 🥉 Bronze — `raw/yfinance/` + `raw/public_data/`

### SOX / NVDA / SOXL / MU / WDC (Yahoo Finance CSV — 주가 Bronze와 동일 파일)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `date` | 거래일 | Datetime | 미국 거래일임 | Not Null |
| `ticker` | 티커 코드 | String | Yahoo Finance 티커임 (^SOX, NVDA, SOXL, MU, WDC) | Not Null |
| `close` | 종가 | Float64 | 당일 종가임 (파생 지표 연산 기준) | Not Null |
| `volume` | 거래량 | Float64 | 당일 거래량임 | - |

### 관세청 수출입 통계 (Parquet)

### 관세청 “반도체” 수출입 실적

| **필드명(물리)** | **필드명(논리)** | **데이터 타입** | **설명** | **제약사항** |
| --- | --- | --- | --- | --- |
| **`stat_date`** | **통계연월** | `DATE` | 통계 데이터가 집계된 기준 년/월 (예: 2024-01-01) | PK 후보, Not Null |
| **`hs_code`** | **HS코드** | `VARCHAR(10)` | 반도체 품목 식별을 위한 국제 표준 분류 번호 | PK 후보, Not Null |
| **`stat_kor`** | **품목명** | `VARCHAR(255)` | 해당 HS코드의 구체적인 국문 명칭 | Not Null |
| **`exp_dlr`** | **수출금액** | `BIGINT` | 당월 총 수출액 (단위: USD) | Not Null |
| **`exp_wgt`** | **수출중량** | `NUMERIC` | 당월 총 수출 물량 무게 (단위: KG) | Not Null |
| **`imp_dlr`** | **수입금액** | `BIGINT` | 당월 총 수입액 (단위: USD) | Not Null |
| **`imp_wgt`** | **수입중량** | `NUMERIC` | 당월 총 수입 물량 무게 (단위: KG) | Not Null |
| **`bal_payments`** | **무역수지** | `BIGINT` | 수출금액 - 수입금액 (무역 흑자/적자 규모) | Not Null |
| **`collected_at`** | **수집일시** | `TIMESTAMP` | Azure Function을 통해 수집된 시스템 시각 | Default NOW() |

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `year` | 통계 연도 | Integer | 수출 통계 기준 연도임 | Not Null |
| `stat_mm` | 통계 월 | Integer | 수출 통계 기준 월임 | Not Null |
| `hs_sgn` | HS CODE | String | 관세 품목 분류 코드임 (8542 = 반도체) | Not Null |
| `hs_dsc` | 품목 설명 | String | HS CODE에 해당하는 품목 설명임 | - |
| `trde_quanty` | 거래 수량 | Numeric | 수출 수량임 | - |
| `trde_amount` | 거래 금액 | Numeric | 수출 금액임 (USD) | Not Null |

### PCR (⚠️ 구현 예정)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `trd_dd` | 거래일 | String | 옵션 거래일임 (YYYYMMDD) | Not Null |
| `opt_type` | 옵션 유형 | String | 옵션 종류 구분자임 (put, call) | Not Null |
| `tot_trd_vol` | 총 거래량 | Integer | 해당 옵션 유형의 일간 총 거래량임 | Not Null |
| `tot_trd_amt` | 총 거래대금 | Float | 해당 옵션 유형의 일간 총 거래대금임 | - |

## 🥈 Silver — `curated/quant/`

> Databricks에서 시차 보정 + 복합 지수 연산
> 

### SOX 동조화 (Silver)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `us_trade_date` | 미국 거래일 | Date | 미국 장 거래일임 (T) | Not Null |
| `kr_effective_date` | 한국 반영일 | Date | 한국 시장 반영일임 (T+1 영업일, 시차 자동 보정) | Not Null |
| `sox_close` | SOX 종가 | Float | ^SOX 지수 종가임 | Not Null |
| `sox_return_1d` | SOX 일간 수익률 | Float | ^SOX 일간 수익률(%)임 | Not Null |
| `nvda_return_1d` | NVDA 일간 수익률 | Float | NVIDIA 일간 수익률(%)임 | - |
| `soxl_return_1d` | SOXL 일간 수익률 | Float | SOXL 3x 레버리지 일간 수익률(%)이며, 변동성 증폭 감지에 사용함 | - |

### 메모리 Proxy (Silver)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `trade_date` | 거래일 | Date | 미국 장 거래일임 | Not Null |
| `mu_close` | MU 종가 | Float | Micron 주가 종가임 | Not Null |
| `mu_return_1d` | MU 일간 수익률 | Float | Micron 일간 수익률(%)임 | Not Null |
| `wdc_close` | WDC 종가 | Float | Western Digital 주가 종가임 | Not Null |
| `wdc_return_1d` | WDC 일간 수익률 | Float | Western Digital 일간 수익률(%)임 | Not Null |
| `memory_sentiment_index` | 메모리 심리 지수 | Float | 시가총액 가중 복합 지수임 (0.6×MU + 0.4×WDC) | Not Null |

### 관세청 (Silver)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `stat_year` | 통계 연도 | Smallint | 수출 통계 연도임 | Not Null |
| `stat_month` | 통계 월 | Smallint | 수출 통계 월임 | Not Null |
| `hs_code` | HS CODE | Varchar(10) | 품목 코드임 (8542 = 반도체) | Not Null |
| `export_usd_amt` | 수출 금액 (USD) | Float | 해당 월 반도체 수출 금액임 | Not Null |
| `yoy_change_pct` | 전년 동월 대비 | Float | 전년 동월 대비 증감률(%)임 | - |
| `mom_change_pct` | 전월 대비 | Float | 전월 대비 증감률(%)임 | - |

## 🥇 Gold — PostgreSQL

### `fact_quant_sox_sync` (글로벌 피어 동조화)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `us_trade_date` | 미국 거래일 | Date | 미국 장 거래일임 (T) | Not Null, Unique |
| `kr_effective_date` | 한국 반영일 | Date | 한국 시장 반영일임 (T+1 영업일) | Not Null |
| `sox_close` | SOX 종가 | Float | ^SOX 지수 종가임 | Not Null |
| `sox_return_1d` | SOX 일간 수익률 | Float | ^SOX 일간 수익률(%)임 | Not Null |
| `nvda_return_1d` | NVDA 일간 수익률 | Float | NVIDIA 일간 수익률(%)임 | - |
| `soxl_return_1d` | SOXL 일간 수익률 | Float | SOXL 3x 레버리지 수익률(%)임 | - |
| `correlation_30d` | 30일 롤링 상관 | Float | SOX ↔ SK하이닉스 30일 롤링 상관계수임 | - |
| `spillover_flag` | 하방 전이 플래그 | Boolean | SOX 일간 하락률 > 2% 시 TRUE이며, 한국 하방 경고 시그널임 | Not Null |
| `upside_surge_flag` | 상승 전이 플래그 | Boolean | SOX 일간 상승률 > 2% 시 TRUE이며, 한국 상승 모멘텀 시그널임 | Not Null |

### `fact_quant_memory_proxy` (메모리 기업 Proxy)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `trade_date` | 거래일 | Date | 미국 장 거래일임 | Not Null, Unique |
| `mu_close` | MU 종가 | Float | Micron 주가 종가임 | Not Null |
| `mu_return_1d` | MU 일간 수익률 | Float | Micron 일간 수익률(%)임 | Not Null |
| `wdc_close` | WDC 종가 | Float | Western Digital 주가 종가임 | Not Null |
| `wdc_return_1d` | WDC 일간 수익률 | Float | Western Digital 일간 수익률(%)임 | Not Null |
| `memory_sentiment_index` | 메모리 심리 지수 | Float | 시가총액 가중 복합 지수임 (0.6×MU + 0.4×WDC). 양방향 시그널로 활용함 | Not Null |
| `memory_ma5` | 심리 지수 MA5 | Float | `memory_sentiment_index`의 5일 이동평균임 | - |
| `memory_trend_flag` | 메모리 추세 | Varchar(10) | 추세 판정 라벨임 (bearish: MA5 하향 3일 연속, neutral, bullish: MA5 상향 3일 연속) | Not Null |

### `fact_quant_customs` (관세청 10일 수출 통계)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `stat_year` | 통계 연도 | Smallint | 수출 통계 연도임 | Not Null |
| `stat_month` | 통계 월 | Smallint | 수출 통계 월임 | Not Null |
| `hs_code` | HS CODE | Varchar(10) | 관세 품목 코드임 (8542 = 반도체) | Not Null |
| `export_usd_amt` | 수출 금액 (USD) | Float | 반도체 수출 금액(USD)임 | Not Null |
| `export_qty` | 수출 수량 | Float | 반도체 수출 수량임 | - |
| `yoy_change_pct` | 전년 동월 대비 | Float | 전년 동월 대비 증감률(%)임 | - |
| `mom_change_pct` | 전월 대비 | Float | 전월 대비 증감률(%)임 | - |
| `export_trend_flag` | 수출 추세 | Varchar(10) | 추세 판정 라벨임 (declining: 3개월 연속 감소, stable, growing: 3개월 연속 증가) | - |

> **UNIQUE:** `(stat_year, stat_month, hs_code)`
> 

### `fact_quant_pcr` (Put/Call Ratio)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `id` | PK | Bigserial | 자동 증가하는 기본키임 | PK |
| `trade_date` | 거래일 | Date | KOSPI 200 옵션 거래일임 | Not Null, Unique |
| `put_volume` | 풋 거래량 | Bigint | 풋옵션 일간 총 거래량임 | Not Null |
| `call_volume` | 콜 거래량 | Bigint | 콜옵션 일간 총 거래량임 | Not Null |
| `pcr_ratio` | PCR 비율 | Float | `put_volume / call_volume`으로 산출한 풋콜 비율임 | Not Null |
| `pcr_ma5` | PCR MA5 | Float | PCR 5일 이동평균임 | - |
| `pcr_ma20` | PCR MA20 | Float | PCR 20일 이동평균임 | - |
| `pcr_breakout_flag` | 하방 돌파 플래그 | Boolean | PCR MA5 > MA20 상향 돌파 시 TRUE이며, 하방 리스크 경고 시그널임 | Not Null |
| `pcr_bullish_flag` | 상승 돌파 플래그 | Boolean | PCR MA5 < MA20 하향 돌파 시 TRUE이며, 상승 모멘텀(콜 매집 증가) 시그널임 | Not Null |

---

# 5. 보고서 연동 뷰

## `v_quant_daily_signals` (퀀트 통합 시그널)

4개 퀀트 팩트를 일자 기준 LEFT JOIN하여 정기 보고서의 **퀀트 시그널 요약** 섹션에 사용하는 통합 뷰임.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `trade_date` | 기준일 | Date | 보고서 기준 날짜임 | - |
| `spillover_flag` | SOX 하방 전이 | Boolean | SOX 급락 시 한국 하방 전이 시그널임 | - |
| `upside_surge_flag` | SOX 상승 전이 | Boolean | SOX 급등 시 한국 상승 전이 시그널임 | - |
| `sox_return_1d` | SOX 일간 수익률 | Float | ^SOX 전일 대비 수익률(%)임 | - |
| `correlation_30d` | 30일 롤링 상관 | Float | SOX↔SK하이닉스 상관계수임 | - |
| `memory_sentiment_index` | 메모리 심리 지수 | Float | MU/WDC 시총가중 복합 지수값임 | - |
| `memory_trend_flag` | 메모리 추세 | Varchar(10) | bearish, neutral, bullish 추세 판정임 | - |
| `pcr_ratio` | PCR 비율 | Float | 당일 풋콜 비율임 | - |
| `pcr_breakout_flag` | PCR 하방 돌파 | Boolean | 풋옵션 과매집 시그널임 | - |
| `pcr_bullish_flag` | PCR 상승 돌파 | Boolean | 콜옵션 과매집 시그널임 | - |
| `customs_yoy` | 관세청 YoY | Float | 반도체 수출 전년 동월 대비 증감률(%)임 | - |
| `customs_trend` | 관세청 추세 | Varchar(10) | 수출 추세 판정 라벨임 | - |
| `composite_signal` | 복합 시그널 | Varchar(20) | triple_risk, triple_opportunity, caution, promising, neutral 중 하나의 종합 판정임 | - |

## `v_daily_report_summary` (일간 보고서 통합 뷰 — 설계 제안)

정기 보고서 자동 생성 시 참조하는 **일별 종합 뷰**임. 모든 데이터셋의 핵심 지표를 일자 기준으로 통합함.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `report_date` | 보고서 기준일 | Date | 보고서 발행 기준 날짜임 | - |
| `regime` | 시장 국면 | Varchar(10) | risk, opportunity, neutral, high_vol 중 하나의 시장 국면 판정값임 | - |
| `composite_signal` | 퀀트 복합 시그널 | Varchar(20) | v_quant_daily_signals에서 산출한 종합 판정값임 | - |
| `avg_absa_score` | 평균 뉴스 감성 | Float | 당일 전체 뉴스 ABSA 점수의 평균값임 | - |
| `top_keyword` | 최다 언급 키워드 | Varchar(100) | 당일 keyword_momentum 최고인 동적 키워드임 | - |
| `sox_return_1d` | SOX 일간 수익률 | Float | 미국 반도체지수 전일 대비 수익률(%)임 | - |
| `dxy_return_1d` | DXY 일간 변동 | Float | 달러 인덱스 전일 대비 변동률(%)임 | - |
| `usd_krw_rate` | 원달러 환율 | Float | 당일 USD/KRW 환율임 | - |
| `memory_trend_flag` | 메모리 추세 | Varchar(10) | MU/WDC 기반 메모리 시장 추세 판정임 | - |

---

# 6. 분석 워크플로

## 📋 6-1. 데이터 사전 작성 워크플로

새로운 데이터셋이 추가되거나 기존 스키마가 변경될 때 아래 워크플로를 따릅니다.

```
1. 데이터 소스 식별
   └─ API 문서 확인, 샘플 응답 수집, 실제 크롤러 코드 확인

2. Bronze 스키마 확정
   └─ 수집기 출력 필드 1:1 매핑 (원본 보존 원칙)
   └─ 포맷(CSV/JSON/Parquet), ADLS 경로, 파티셔닝 키 결정

3. Silver 변환 규칙 정의
   └─ 타입 캐스팅: String → Date, Float 등
   └─ 결측치 처리: Forward Fill, NULL, Default 중 선택
   └─ 시차 보정: kr_effective_date 생성 여부
   └─ 파생 지표: 이동평균, 수익률, 복합 지수 등

4. Gold 서빙 스키마 설계
   └─ Dim 테이블 vs Fact 테이블 분리
   └─ ML 타겟 변수 정의 (양방향: downside + upside)
   └─ 보고서 연동 컬럼 (regime, flag 등)
   └─ 인덱스 설계 (BRIN, UNIQUE, GIN, HNSW)

5. 데이터 사전 문서화
   └─ 본 컨벤션에 따라 마크다운 테이블 작성
   └─ ref/ 폴더에 저장 (git 미추적)
```

## 🔄 6-2. 파이프라인 분석 워크플로 (일간 운영)

매일 ADF 타이머 트리거가 실행된 후 아래 순서로 데이터가 처리되고 최종 보고서가 생성됩니다.

```
┌──────────────────────────────────────────────────────────────┐
│ Phase 1: 수집 (ADF Timer Trigger → ACI / Functions / Script) │
├──────────────────────────────────────────────────────────────┤
│  Google News (ACI) ────────┐                                 │
│  Naver News (Functions) ───┤                                 │
│  Yahoo Finance (Script) ───┼──→ ADLS raw/  [Bronze]          │
│  FX Collector (Functions) ─┤                                 │
│  관세청 (Script, 월 1회) ───┘                                 │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 2: 전처리 (Databricks Notebooks)                       │
├──────────────────────────────────────────────────────────────┤
│  01_raw_to_curated                                           │
│  ├─ HTML/특수문자 제거                                        │
│  ├─ 시계열 Forward Fill + is_filled 플래그                    │
│  ├─ 한·미 시차 정렬 (kr_effective_date)                       │
│  └─ 출력 → ADLS curated/  [Silver]                           │
│                                                              │
│  02_curated_to_feature                                       │
│  ├─ TF-IDF 동적 키워드 추출                                   │
│  ├─ Azure OpenAI 요약 + ABSA 감성 분석                        │
│  ├─ 요약본 벡터 임베딩 (1536차원)                              │
│  ├─ ML 타겟 변수 연산 (downside + upside + regime)            │
│  ├─ 파생 기술 지표 연산 (MA, RSI, 복합 지수)                   │
│  └─ 출력 → ADLS feature/  [Gold]                             │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 3: 모델링 + 적재                                       │
├──────────────────────────────────────────────────────────────┤
│  ML Studio Batch Endpoint                                    │
│  ├─ 하방 리스크 모델 (XGBoost: downside_flag)                 │
│  ├─ 상승 모멘텀 모델 (LightGBM: upside_flag)                  │
│  └─ 예측 결과 + 피처 중요도 → PostgreSQL                      │
│                                                              │
│  Gold → PostgreSQL 적재                                      │
│  ├─ dim_* / fact_* 테이블 Upsert                             │
│  ├─ pgvector 벡터 인덱스 갱신                                 │
│  └─ v_quant_daily_signals / v_daily_report_summary 자동 갱신  │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 4: 서빙 + 보고서                                       │
├──────────────────────────────────────────────────────────────┤
│  Power BI 대시보드                                            │
│  ├─ DirectQuery → PostgreSQL                                 │
│  ├─ 시장 국면 (regime) 카드                                   │
│  ├─ 복합 시그널 (composite_signal) 게이지                     │
│  ├─ ABSA 감성 추이 시계열 차트                                │
│  └─ 동적 키워드 워드 클라우드                                  │
│                                                              │
│  정기 보고서 자동 생성                                         │
│  ├─ 일간: v_daily_report_summary 기반 요약                    │
│  ├─ 주간: 금주 regime 타임라인 + 모델 예측 vs 실현 비교        │
│  └─ 월간: 월간 누적 수익률 + 예측 정확도 트렌드               │
│                                                              │
│  Web App + AI Agent (RAG)                                    │
│  ├─ pgvector 코사인 유사도 검색                               │
│  ├─ 관련 뉴스 원문 + 요약 제시                                │
│  └─ XAI 피처 중요도 해석 제시                                 │
└──────────────────────────────────────────────────────────────┘
```

## 📝 6-3. 테이블 변경 시 체크리스트

| 단계 | 확인 항목 | 담당 |
| --- | --- | --- |
| 1 | Bronze 크롤러/수집기 코드에 새 필드 추가 여부 확인 | 수집 담당 |
| 2 | Silver 변환 노트북에 새 필드 타입 캐스팅·변환 로직 추가 | 전처리 담당 |
| 3 | Gold PostgreSQL DDL에 ALTER TABLE / CREATE TABLE 반영 | DB 담당 |
| 4 | 데이터 사전 마크다운 (본 문서) 업데이트 | 공통 |
| 5 | Power BI 데이터셋 새로 고침 + 시각화 반영 확인 | BI 담당 |
| 6 | ML 피처 파이프라인에 새 피처 포함 여부 검토 | 모델링 담당 |
| 7 | 정기 보고서 템플릿에 새 섹션/지표 반영 | 보고서 담당 |