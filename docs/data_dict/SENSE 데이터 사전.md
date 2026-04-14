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
> Gold 3개 테이블(`dim_news_display`, `agg_market_sentiment_daily`, `fact_feature_vector_store`)의 소스. Azure OpenAI 호출 결과가 Silver 단계에서 추가됨.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `news_id` | 뉴스 ID | String | Bronze에서 승계한 기사 고유 식별자임 | PK, Not Null |
| `news_source` | 데이터 소스 | String | 원본 소스 구분자임 ("google", "naver", "bing") | Not Null |
| `pub_date` | 발행 일자 | Date | 정규화된 발행 날짜임 | Not Null |
| `headline` | 기사 제목 | String | 원본 그대로 보존한 기사 제목임 | Not Null |
| `description` | RSS/API 요약문 | String | Bronze RSS/API 요약문 (Azure OpenAI 요약 소스) | - |
| `clean_text` | 정제 본문 | String | HTML 태그·특수문자 제거 후 정규화한 본문 텍스트임 | Not Null |
| `body` | 원본 본문 | String | RAG 검색 컨텍스트 주입용 원문 | - |
| `url` | 원문 URL | String | 기사 원문 링크임 | - |
| `press` | 언론사명 | String | 기사 발행 언론사 이름임 | - |
| `stock_keyword` | 대상 키워드 | String | 수집 대상 기업 구분 ("samsung", "skhynix") | Not Null |
| `category` | 뉴스 카테고리 | String | Azure OpenAI 분류 카테고리 (실적, 공급망, 규제, 기술, 거시경제, 수급, 기타) | - |
| `absa_aspect` | ABSA 속성 | String | LLM이 분류한 뉴스 속성 카테고리 (제조원가, 양산일정, 공급망 등) | - |
| `absa_score` | ABSA 감성 점수 | Float | 양방향 감성 점수 (-1.0 강한 부정 ~ 1.0 강한 긍정) | - |
| `dynamic_keywords` | 동적 키워드 | String (JSON Array) | TF-IDF/LLM으로 추출한 당일 핵심 키워드 배열 (예: `["트럼프_관세", "HBM_수율"]`) | - |
| `keyword_momentum` | 키워드 모멘텀 | String (JSON Object) | 키워드별 전일 대비 언급 급증률(%) 매핑 (예: `{"트럼프_관세": 350.0}`) | - |
| `summary_vector` | 요약 벡터 | Array(Float, 1536) | `description` 임베딩 1536차원 벡터 (pgvector 소스) | - |

## 🥇 Gold — `feature/sense/` + PostgreSQL

> Databricks 02_curated_to_feature 노트북 출력 → PostgreSQL 적재
>
> **[2026-04 재설계]** 기존 `dim_news_master` + `fact_news_analytics` 구조에서 3개 트랙 특화 테이블로 재편. 상세 설계: `ref/뉴스 데이터 골드레이어.md` 참고.

### `dim_news_display` (Track: Web App & Power BI 뉴스 리스트)

> 유저에게 보여줄 뉴스 리스트 및 상세 정보를 서빙하는 테이블. Varchar 길이 제한 문제로 Text 타입으로 통일.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | Silver 소스 컬럼 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- | --- |
| `news_id` | 뉴스 ID | UUID | `news_id` | 기사 고유 식별자 | PK, Not Null |
| `display_title` | 표출 제목 | Text | `headline` | 기사 제목 (길이 제한 없음) | Not Null |
| `core_summary` | AI 핵심 요약 | Text | `description` | Azure OpenAI 3줄 요약 (RAG 컨텍스트 주입용) | Not Null |
| `sentiment_class` | 감성 등급 | Varchar(10) | `absa_score` | score ≥ 0.3 → '호재', ≤ -0.3 → '악재' (UI 색상 분류용) | Not Null |
| `category` | 카테고리 | Varchar(30) | `category` | 뉴스 도메인 분류 (실적, 공급망, 규제, 기술, 거시경제, 수급, 기타) | Not Null |
| `press` | 언론사 | Text | `press` | 뉴스 발행 언론사명 | - |
| `original_url` | 원문 링크 | Text | `url` | 클릭 시 이동할 기사 원본 링크 | - |
| `stock_keyword` | 대상 키워드 | Text | `stock_keyword` | 삼성전자/SK하이닉스 구분 필터 | Not Null |
| `pub_date` | 발행 일자 | Date | `pub_date` | 날짜별 리스트 정렬 및 필터링 기준 | Not Null |
| `is_surge` | 급증 여부 | BOOLEAN | `dynamic_keywords` (가공) | 모멘텀 300% 이상 키워드 포함 여부 (UI 알람용) | - |

### `agg_market_sentiment_daily` (Track: EDA 및 통계 분석)

> 일 단위 집계 테이블. 3조가 주가 데이터와 상관관계 분석 시 메인으로 사용하며, Power BI 메인 리스크 차트 소스.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | Silver 소스 컬럼 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- | --- |
| `base_date` | 분석 기준일 | Date | `pub_date` | 일자별 그룹화 기준 | PK 후보, Not Null |
| `stock_code` | 대상 키워드 | Text | `stock_keyword` | 기업별 표준화된 대문자 명칭 | PK 후보, Not Null |
| `avg_sentiment` | 평균 감성 점수 | Float | `absa_score` | 당일 해당 종목 뉴스들의 평균 점수 | Not Null |
| `news_vol` | 뉴스 언급량 | Integer | `news_id` | 당일 발행된 총 뉴스 건수 카운트 | Not Null |
| `main_aspect` | 주요 리스크 요인 | Text | `absa_aspect` | 당일 가장 많이 언급된 속성 (최빈값) | - |
| `daily_keywords` | 핵심 키워드 상세 | JSONB | `dynamic_keywords` | 키워드별 집계값이 담긴 JSONB 배열 (구조 아래 참고) | Not Null |

> **UNIQUE:** `(base_date, stock_code)`
>
> **`daily_keywords` JSONB 구조** (TOP 10, 전일 비교 포함):
> ```json
> [
>   {
>     "rank": 1,
>     "keyword": "HBM",
>     "mention_count": 18,
>     "avg_sentiment": 0.62,
>     "sentiment_label": "positive",
>     "mention_delta": 7,
>     "mention_delta_pct": 63.6,
>     "sentiment_delta": 0.14
>   }
> ]
> ```

### `fact_feature_vector_store` (Track: ML 예측 모델 및 RAG 검색)

> 하방 리스크 예측 모델 학습 Input + RAG 기반 챗봇 지식 베이스. pgvector 인덱스(HNSW) 적용.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | Silver 소스 컬럼 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- | --- |
| `news_id` | 뉴스 ID | UUID | `news_id` | 고유 식별자 | PK, Not Null |
| `summary_vec` | 요약 벡터 | Vector(1536) | `summary_vector` | pgvector 코사인 유사도 검색(RAG) 핵심 데이터 | Not Null |
| `search_context` | 검색 컨텍스트 | Text | `body` | RAG 답변 생성 시 LLM 주입용 원문 | Not Null |
| `feature_score` | 분석 수치 | Float | `absa_score` | ML 모델 학습용 독립 변수 | Not Null |
| `aspect_tag` | 속성 태그 | Text | `absa_aspect` | 리스크 카테고리 가중치 부여용 | - |
| `keyword_momentum` | 키워드 모멘텀 | JSONB | `keyword_momentum` | 키워드별 언급 급증률 (300% 이상 경고). 구조: `{"트럼프_관세": 350.0}` | - |

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

## 🥇 Gold — PostgreSQL (`gold_macro` 스키마)

> ⚠️ **실제 테이블 구조 주의**: 팀원이 별도 설계한 테이블로, 데이터사전 설계와 테이블명 및 컬럼 구조가 다름 (2026-04-14 실제 확인)

### `gold_macro.dim_macro_metadatas` (지표 메타데이터 레지스트리)

> 설계 원본: `dim_macro_series` (6컬럼) → 실제: `dim_macro_metadatas` (17컬럼, PK: `unified_id`)
>
> Gold 테이블 내 모든 매크로 시계열 컬럼의 메타 정보를 등록하는 중앙 레지스트리.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `unified_id` | 통합 ID | Bigint | 메타데이터 행 고유 식별자 | PK, Not Null |
| `series_key` | 시계열 키 | Text | 소스 테이블+컬럼 조합 고유 키임 | Not Null, Unique |
| `source_table` | 소스 테이블 | Text | 원천 Gold 테이블명임 (예: fact_macro_all) | Not Null |
| `date_column_name` | 날짜 컬럼명 | Text | 소스 테이블의 기준 날짜 컬럼명임 | Not Null |
| `source_column_name` | 소스 컬럼명 | Text | 소스 테이블의 값 컬럼명임 | Not Null |
| `series_code` | 지표 코드 | Text | 외부 원천 지표 코드임 (예: DGS10, NVDA) | - |
| `display_name` | 표시명 | Text | 대시보드·보고서용 표시명임 | Not Null |
| `category` | 카테고리 | Text | 지표 분류임 (equity, rate, fx, macro 등) | Not Null |
| `subcategory` | 서브카테고리 | Text | 세부 분류임 | - |
| `unit` | 단위 | Text | 지표 단위임 (USD, %, index 등) | - |
| `data_source` | 데이터 출처 | Text | 원천 소스명임 (yahoo_finance, fred, openexchange 등) | Not Null |
| `frequency` | 수집 주기 | Text | 수집 주기임 (daily, monthly 등) | - |
| `market_scope` | 시장 범위 | Text | 적용 시장 범위임 (us, kr, global 등) | - |
| `description` | 설명 | Text | 지표 상세 설명임 | - |
| `is_active` | 활성 여부 | Boolean | 현재 수집·사용 중인 지표 여부임 | Not Null, Default: true |
| `created_at_utc` | 생성 시각 | Timestamptz | 메타데이터 등록 시각 (UTC)임 | Not Null |
| `updated_at_utc` | 수정 시각 | Timestamptz | 메타데이터 최종 수정 시각 (UTC)임 | Not Null |

### `gold_macro.fact_macro_all` (매크로 통합 Wide 테이블)

> 설계 원본: Narrow FK 구조 `fact_macro_daily` → 실제: Wide Pivot 구조 (PK: `base_date`, 45컬럼)
>
> 일별 1행에 모든 매크로 지표(미국 반도체 종가, FRED 금리, FX, 수출, 옵션)를 Pivot하여 저장하는 핵심 적재 테이블.

| 컬럼 그룹 | 필드명(물리) | 데이터 타입 | 설명 |
| --- | --- | --- | --- |
| 기준일 | `base_date` | Date | **PK**. 기준 날짜 (한국 영업일 기준) |
| 반도체 종가 | `nvda_close`, `tsm_close`, `amd_close`, `intc_close`, `asml_close`, `mu_close`, `wdc_close` | Float8 | 미국 반도체 종목 종가 |
| 반도체 종가 | `sox_index_close`, `samsung_close`, `skhynix_close` | Float8 | SOX 인덱스, 삼성전자, SK하이닉스 종가 |
| 주가 파생 | `nvda_log_return`, `nvda_volatility_gk`, `nvda_volatility_5d` | Float8 | NVDA 로그수익률, GK 변동성, 5일 실현변동성 |
| 주가 파생 | `sox_log_return`, `sox_volatility_5d` | Float8 | SOX 로그수익률, 5일 실현변동성 |
| FRED 금리 | `dgs10`, `dgs2`, `dff`, `dfii10`, `t10y2y`, `bamlh0a0hym2` | Float8 | 10년물/2년물 국채금리, 연방기금금리, 실질금리, 장단기 금리차, 하이일드 스프레드 |
| 금리 파생 | `yield_spread`, `yield_spread_change`, `stagnation_pressure` | Float8 | 금리차, 금리차 변화량, 스태그플레이션 압력 |
| FX | `usd_krw`, `usd_krw_change`, `usd_krw_pct` | Float8 | USD/KRW 환율 및 전일 대비 변화 |
| FX 시그널 | `risk_off_flag` | Integer | 달러 급등 경보 (≥1% 상승 시 1) |
| 수출 | `export_usd`, `export_change_pct` | Float8 | 반도체 수출액(USD), 전월 대비 변화율 |
| 수출 시그널 | `export_momentum` | Integer | 수출 급감 경보 (≤-10% 시 1) |
| 옵션 | `call_volume`, `call_oi`, `avg_iv`, `iv_change`, `vol_change_pct` | Float8 | 콜 거래량, 미결제약정, 내재변동성 및 파생 |
| 옵션 시그널 | `iv_surge_flag` | Integer | IV 급등 신호 (전월비 +5 이상 시 1) |
| 복합 시그널 | `risk_off_composite`, `macro_stress_score`, `fear_composite` | Float8 | 리스크오프 복합 지수, 매크로 스트레스 점수, 공포 복합 지수 |
| 복합 시그널 | `semi_risk_signal`, `korea_sensitivity`, `global_risk_regime`, `is_high_risk` | Float8/Integer | 반도체 리스크 시그널, 한국 민감도, 글로벌 리스크 레짐, 고위험 여부 |
| 메타 | `created_at_utc` | Timestamptz | 행 생성 시각 |

> **PK:** `base_date`

### `gold_macro.fact_yf_fx_fred_1y` (Yahoo Finance + FX + FRED 1년 와이드 테이블)

> 최근 1년 캘린더 날짜별 (주말 포함) 종가·환율·금리를 단일 행에 통합. 뷰 `v_macro_latest`의 소스 테이블.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `standard_date` | 기준일 | Date | **PK**. 캘린더 날짜 (주말·휴장일 포함) | PK, Not Null |
| `day_of_week` | 요일 | Integer | 요일 코드 (0=월요일, 6=일요일) | - |
| `is_weekend` | 주말 여부 | Boolean | 주말 날짜 여부 | - |
| `is_kr_market_holiday` | 한국 휴장 | Boolean | 한국 주식시장 휴장일 여부 | - |
| `is_us_market_holiday` | 미국 휴장 | Boolean | 미국 주식시장 휴장일 여부 | - |
| `usd_krw_rate` | USD/KRW 환율 | Float8 | 당일 USD/KRW 환율임 | - |
| `yfinance_nvda_close` | NVDA 종가 | Float8 | NVIDIA 종가 | - |
| `yfinance_tsm_close` | TSM 종가 | Float8 | Taiwan Semiconductor 종가 | - |
| `yfinance_amd_close` | AMD 종가 | Float8 | AMD 종가 | - |
| `yfinance_intc_close` | INTC 종가 | Float8 | Intel 종가 | - |
| `yfinance_asml_close` | ASML 종가 | Float8 | ASML 종가 | - |
| `yfinance_mu_close` | MU 종가 | Float8 | Micron 종가 | - |
| `yfinance_wdc_close` | WDC 종가 | Float8 | Western Digital 종가 | - |
| `yfinance_sox_close` | SOX 종가 | Float8 | SOX 반도체 지수 종가 | - |
| `yfinance_samsung_close` | 삼성전자 종가 | Float8 | 삼성전자 (005930.KS) 종가 | - |
| `yfinance_skhynix_close` | SK하이닉스 종가 | Float8 | SK하이닉스 (000660.KS) 종가 | - |
| `fred_dgs10` | 10년물 국채금리 | Float8 | FRED DGS10 | - |
| `fred_dgs2` | 2년물 국채금리 | Float8 | FRED DGS2 | - |
| `fred_dff` | 연방기금금리 | Float8 | FRED DFF | - |
| `fred_dfii10` | 10년물 실질금리 | Float8 | FRED DFII10 | - |
| `fred_t10y2y` | 장단기 금리차 | Float8 | FRED T10Y2Y | - |
| `fred_bamlh0a0hym2` | 하이일드 스프레드 | Float8 | FRED BAMLH0A0HYM2 | - |
| `created_at` | 생성 시각 | Timestamptz | 행 생성 시각 | - |
| `updated_at` | 수정 시각 | Timestamptz | 행 최종 수정 시각 | - |

### `gold_macro.fact_kfinance` (한국 금융 파생상품)

> 설계에 없던 신규 테이블. kfinance 수집 결과 (코스피200 옵션 등) 적재용.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `base_date` | 기준일 | Date | 기준 날짜 | PK(부분), Not Null |
| `ticker` | 티커 코드 | Text | 종목 코드 | PK(부분), Not Null |
| `close_price` | 종가 | Float8 | 당일 종가 | - |
| `collected_at_utc` | 수집 시각 | Timestamptz | 수집 시각 (UTC) | - |
| `created_at` | 생성 시각 | Timestamptz | 행 생성 시각 | - |

### `gold_macro.fact_semiconductor_trade` (반도체 수출입 통계)

> 관세청 반도체 수출입 실적 적재 테이블.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `base_date` | 기준일 | Date | 기준 날짜 (통계 연월) | PK(부분), Not Null |
| `hs_code` | HS 코드 | Bigint | 반도체 품목 HS 코드 (예: 8542) | PK(부분), Not Null |
| `stat_kor` | 품목 국문명 | Text | 해당 HS코드의 국문 품목명 | - |
| `export_dollar` | 수출 금액 (USD) | Bigint | 수출 금액 (USD) | - |
| `import_dollar` | 수입 금액 (USD) | Bigint | 수입 금액 (USD) | - |
| `collected_at_utc` | 수집 시각 | Timestamptz | 수집 시각 (UTC) | - |
| `created_at` | 생성 시각 | Timestamptz | 행 생성 시각 | - |

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

### PCR (⚠️ 구현 보류 — 별도 데이터 소스 필요)

> **[2026-04 회의록]** kfinance 수집 데이터(코스피200 옵션)는 콜 96.6%/풋 3.4% 분포에 월별 스냅샷으로, 코스피200 PCR 계산에 사용 불가. 일별 코스피200 콜/풋 거래량 데이터 별도 확보 필요.

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

### kfinance (Silver) — `curated/semiconductor/`

> Databricks 05_kfinance_raw_to_silver 노트북 출력 (월별, 28행 · 9컬럼). 코스피200 옵션 파생 지표 포함.
> ⚠️ PCR 계산 불가 확인 (2026-04 회의록): 수집 데이터에 코스피200 풋옵션 없음.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `date` | DateType | 기준일자 (해당 월 마지막 영업일) |
| `call_volume` | DoubleType | 코스피200 콜 거래량 합계 |
| `call_oi` | DoubleType | 코스피200 콜 미결제약정 합계 |
| `avg_iv` | DoubleType | 거래량 가중평균 내재변동성 (VIX 대용) |
| `iv_change` | DoubleType | IV 전월 대비 변화량 (첫 행 0) |
| `vol_change_pct` | DoubleType | 거래량 전월 대비 변화율 (%, 첫 행 0) |
| `iv_surge_flag` | IntegerType | IV 급등 신호 (전월비 +5 이상 시 1) |
| `year` / `month` | IntegerType | 파티션 컬럼 |

### semiconductor (Silver) — `curated/semiconductor/`

> Databricks 04_semiconductor_raw_to_silver 출력 (일별 Forward Fill, 511행 · 6컬럼).

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `date` | DateType | 한국 영업일 (Forward Fill 완료) |
| `export_usd` | DoubleType | 월별 반도체 수출액 (USD, HS8542 합산) |
| `export_change_pct` | DoubleType | 전월 대비 수출 변화율 (%, 첫 행 0) |
| `export_momentum` | IntegerType | 수출 급감 경보 (≤-10% 시 1) |
| `year` / `month` | IntegerType | 파티션 컬럼 |

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

### `gold_ml.gold_customs_semiconductor` (관세청 반도체 수출입)

> 설계 원본: `fact_quant_customs` → 실제 테이블명: `gold_ml.gold_customs_semiconductor`

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `stat_year` | 통계 연도 | Smallint | 수출 통계 기준 연도임 | PK(부분), Not Null |
| `stat_month` | 통계 월 | Smallint | 수출 통계 기준 월임 | PK(부분), Not Null |
| `hs_code` | HS CODE | Varchar | 관세 품목 코드임 (8542 = 반도체) | PK(부분), Not Null |
| `export_usd_amt` | 수출 금액 (USD) | Numeric | 반도체 수출 금액(USD)임 | Not Null |
| `import_usd_amt` | 수입 금액 (USD) | Numeric | 반도체 수입 금액(USD)임 | - |
| `trade_balance` | 무역수지 | Numeric | 수출 - 수입 (USD)임 | - |
| `yoy_change_pct` | 전년 동월 대비 | Float8 | 전년 동월 대비 증감률(%)임 | - |
| `export_trend` | 수출 추세 | Varchar | 추세 판정 라벨임 (declining, stable, growing) | - |
| `updated_at` | 수정 시각 | Timestamp | 행 최종 수정 시각임 | - |

> **PK:** `(stat_year, stat_month, hs_code)`
> 

### `gold_ml.gold_quant_pcr_signals` (Put/Call Ratio 퀀트 시그널)

> 설계 원본: `fact_quant_pcr` (구현 보류) → 실제: `gold_ml.gold_quant_pcr_signals` **생성됨** (2026-04-14 확인)

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `trade_date` | 거래일 | Date | KOSPI 200 옵션 거래일임 | PK, Not Null |
| `put_volume` | 풋 거래량 | Bigint | 풋옵션 일간 총 거래량임 | Not Null |
| `call_volume` | 콜 거래량 | Bigint | 콜옵션 일간 총 거래량임 | Not Null |
| `pcr_ratio` | PCR 비율 | Float8 | `put_volume / call_volume`으로 산출한 풋콜 비율임 | Not Null |
| `pcr_ma5` | PCR MA5 | Float8 | PCR 5일 이동평균임 | - |
| `pcr_ma20` | PCR MA20 | Float8 | PCR 20일 이동평균임 | - |
| `fear_greed_idx` | 공포-탐욕 지수 | Varchar | 공포-탐욕 판정 레이블임 | - |
| `is_downside_warning` | 하방 경보 | Boolean | PCR 기반 하방 경보 시 TRUE임 | - |
| `pcr_breakout_flag` | 하방 돌파 플래그 | Boolean | PCR MA5 > MA20 상향 돌파 시 TRUE이며, 하방 리스크 경고 시그널임 | Not Null |
| `pcr_bullish_flag` | 상승 돌파 플래그 | Boolean | PCR MA5 < MA20 하향 돌파 시 TRUE이며, 상승 모멘텀 시그널임 | Not Null |
| `updated_at` | 수정 시각 | Timestamp | 행 최종 수정 시각임 | - |

> **PK:** `trade_date`

### `gold_ml.gold_ml_feature_set` (ML 통합 피처 세트)

> 설계에 없던 신규 테이블. ML 모델 학습 및 운영 추론용 핵심 피처 통합 테이블.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 | 제약사항 |
| --- | --- | --- | --- | --- |
| `base_date` | 기준일 | Date | 피처 기준 날짜임 | PK, Not Null |
| `semi_export_yoy` | 반도체 수출 YoY | Float8 | 반도체 수출 전년 동월 대비 증감률(%)임 | - |
| `pcr_val` | PCR 값 | Float8 | 당일 Put/Call Ratio 값임 | - |
| `usd_krw_rate` | USD/KRW 환율 | Float8 | 당일 USD/KRW 환율임 | - |
| `us_10y_yield` | 미국 10년물 금리 | Float8 | FRED DGS10 값임 | - |
| `avg_absa_score` | 평균 감성 점수 | Float8 | 당일 뉴스 ABSA 평균 점수임 | - |
| `target_return_5d` | 5일 수익률 (타겟) | Float8 | ML 예측 타겟 변수 — 5일 수익률(%)임 | - |
| `regime_label` | 시장 국면 | Varchar | 시장 국면 레이블임 (risk, opportunity, neutral 등) | - |

> **PK:** `base_date`

---

# 5. 보고서 연동 뷰

> 2026-04-14 기준 6개 뷰 모두 생성됨. 스키마 위치 주의 (`public`, `gold_news`, `gold_macro`, `gold_ml`).

## `public.v_forecast_latest` (티커별 최신 앙상블 예측)

`fact_ensemble_forecast`에서 티커·예측 기간별 가장 최신 run 기준 결과를 추출하는 뷰임.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 |
| --- | --- | --- | --- |
| `ticker` | 종목 코드 | Text | 예측 대상 종목 코드임 |
| `base_date` | 예측 기준일 | Date | 모델이 학습 기준으로 삼은 날짜임 |
| `forecast_date` | 예측 목표일 | Date | 예측 대상 날짜임 |
| `horizon_day` | 예측 기간 | Bigint | 기준일 기준 예측 일수임 |
| `final_pred` | 앙상블 예측값 | Float8 | 최종 앙상블 예측 수익률(%)임 |
| `pi_lower` | 예측 구간 하단 | Float8 | 신뢰 구간 하단임 |
| `pi_upper` | 예측 구간 상단 | Float8 | 신뢰 구간 상단임 |
| `confidence_score` | 신뢰도 점수 | Float8 | 모델 신뢰도 점수임 |
| `regime_label` | 시장 국면 | Text | 시장 국면 레이블임 |
| `run_timestamp` | 실행 시각 | Timestamp | 모델 실행 시각임 |

## `public.v_daily_report_summary` (일간 보고서 통합 뷰)

예측(`v_forecast_latest`) + 감성(`agg_market_sentiment_daily`) + 매크로(`fact_yf_fx_fred_1y`)를 일자·종목 기준으로 통합하는 일간 보고서 소스 뷰임.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 |
| --- | --- | --- | --- |
| `base_date` | 기준일 | Timestamp | 보고서 기준 날짜임 |
| `ticker` | 종목 코드 | Text | 종목 코드임 (삼성전자·SK하이닉스) |
| `final_pred` | 앙상블 예측값 | Float8 | 최종 앙상블 예측 수익률(%)임 |
| `confidence_score` | 신뢰도 점수 | Float8 | 모델 신뢰도 점수임 |
| `regime_label` | 시장 국면 | Text | 시장 국면 레이블임 |
| `avg_sentiment` | 평균 감성 점수 | Float8 | 당일 뉴스 ABSA 평균 점수임 |
| `news_vol` | 뉴스 건수 | Integer | 당일 뉴스 건수임 |
| `usd_krw_rate` | USD/KRW 환율 | Float8 | 당일 환율임 |
| `fred_dgs10` | 10년물 금리 | Float8 | FRED DGS10 값임 |
| `fred_t10y2y` | 장단기 금리차 | Float8 | FRED T10Y2Y 값임 |
| `fred_bamlh0a0hym2` | 하이일드 스프레드 | Float8 | FRED BAMLH0A0HYM2 값임 |

## `public.v_model_comparison_latest` (앙상블 vs 통계 기준선 비교)

앙상블 예측(`v_forecast_latest`)과 통계 기준선 예측(`fact_stat_forecast`)을 종목·기간·기준일 기준으로 비교하는 뷰임.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 |
| --- | --- | --- | --- |
| `ticker` | 종목 코드 | Text | 종목 코드임 |
| `base_date` | 예측 기준일 | Date | 모델 기준일임 |
| `horizon` | 예측 기간 | Bigint | 예측 일수임 |
| `ensemble_pred` | 앙상블 예측값 | Float8 | TimesFM 앙상블 예측 수익률(%)임 |
| `confidence_score` | 신뢰도 점수 | Float8 | 앙상블 모델 신뢰도임 |
| `regime_label` | 시장 국면 | Text | 시장 국면 레이블임 |
| `model` | 통계 모델명 | Text | 비교 대상 통계 모델명임 |
| `stat_pred` | 통계 예측값 | Float8 | 통계 기준선 예측 수익률(%)임 |
| `change_pct` | 통계 변화율 | Float8 | 통계 모델 예측 변화율(%)임 |
| `model_gap` | 모델 차이 | Float8 | `ensemble_pred - stat_pred`임 |

## `gold_news.v_news_sentiment_trend` (뉴스 감성 추이)

`agg_market_sentiment_daily`에 7일 이동평균(윈도우 함수)을 추가한 뷰임.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 |
| --- | --- | --- | --- |
| `base_date` | 기준일 | Date | 뉴스 집계 기준 날짜임 |
| `stock_code` | 종목 코드 | Text | 종목 구분 코드임 (SAMSUNG, SKHYNIX) |
| `avg_sentiment` | 평균 감성 점수 | Float8 | 당일 ABSA 평균 점수임 |
| `news_vol` | 뉴스 건수 | Integer | 당일 뉴스 건수임 |
| `main_aspect` | 주요 리스크 요인 | Text | 당일 최빈 속성 카테고리임 |
| `sentiment_ma7` | 감성 7일 이동평균 | Float8 | 종목별 감성 7일 이동평균임 |

## `gold_macro.v_macro_latest` (최신 매크로 스냅샷)

`fact_yf_fx_fred_1y`에서 `standard_date` 기준 최신 1행을 조회하는 뷰임.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 |
| --- | --- | --- | --- |
| `trade_date` | 기준일 | Date | 최신 매크로 기준 날짜임 (`standard_date` 별칭) |
| `usd_krw_rate` | USD/KRW 환율 | Float8 | 최신 환율임 |
| `fred_dgs10` | 10년물 금리 | Float8 | 최신 FRED DGS10 값임 |
| `fred_dgs2` | 2년물 금리 | Float8 | 최신 FRED DGS2 값임 |
| `fred_t10y2y` | 장단기 금리차 | Float8 | 최신 FRED T10Y2Y 값임 |
| `fred_dff` | 연방기금금리 | Float8 | 최신 FRED DFF 값임 |
| `fred_bamlh0a0hym2` | 하이일드 스프레드 | Float8 | 최신 FRED BAMLH0A0HYM2 값임 |

## `gold_ml.v_quant_daily_signals` (퀀트 통합 시그널)

SOX 동조화(`fact_quant_sox_sync`) + 메모리 심리(`fact_quant_memory_proxy`) + PCR 시그널(`gold_quant_pcr_signals`)을 `signal_date` 기준으로 LEFT JOIN한 퀀트 통합 뷰임.

| 필드명(물리) | 필드명(논리) | 데이터 타입 | 설명 |
| --- | --- | --- | --- |
| `signal_date` | 기준일 | Date | SOX 미국 거래일 기준 (`us_trade_date` 별칭)임 |
| `sox_return_1d` | SOX 일간 수익률 | Float8 | ^SOX 전일 대비 수익률(%)임 |
| `sox_downside_flag` | SOX 하방 전이 | Boolean | SOX 급락 시 한국 하방 전이 시그널임 (`spillover_flag` 별칭) |
| `sox_upside_flag` | SOX 상승 전이 | Boolean | SOX 급등 시 한국 상승 전이 시그널임 (`upside_surge_flag` 별칭) |
| `memory_sentiment_index` | 메모리 심리 지수 | Float8 | MU/WDC 시총가중 복합 지수값임 |
| `memory_trend_flag` | 메모리 추세 | Varchar | bearish, neutral, bullish 추세 판정임 |
| `pcr_ratio` | PCR 비율 | Float8 | 당일 풋콜 비율임 |
| `pcr_ma5` | PCR MA5 | Float8 | PCR 5일 이동평균임 |
| `fear_greed_idx` | 공포-탐욕 지수 | Varchar | 공포-탐욕 판정 레이블임 |
| `pcr_warning_flag` | PCR 하방 경보 | Boolean | PCR 기반 하방 경보 시그널임 (`is_downside_warning` 별칭) |
| `pcr_bullish_flag` | PCR 상승 돌파 | Boolean | 콜옵션 과매집 시그널임 |

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