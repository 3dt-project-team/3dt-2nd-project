# SENSE 프로젝트 2부: 데이터 파이프라인 — ADF 오케스트레이션과 Medallion 아키텍처

> **시리즈**: Azure + Databricks + TimesFM으로 반도체 주가 예측 파이프라인 구축하기  
> **분류**: Data Engineering, ADF, Databricks, ADLS Gen2, Medallion Architecture  
> **작성일**: 2026년 4월 17일  

---

## 들어가며 — 파이프라인 품질이 모델 품질을 결정한다

ML 엔지니어들이 모델 튜닝에 집착하는 동안, 실제 프로젝트에서 예측 품질을 가장 크게 떨어뜨리는 것은 대부분 데이터 파이프라인입니다. 결측치가 0으로 채워지거나, 거래일 기준이 맞지 않거나, 뉴스 날짜가 공시 전날로 잘못 적재되는 순간 — 아무리 정교한 모델도 쓰레기를 예측합니다.

SENSE 파이프라인 설계에서 우리가 세운 원칙은 세 가지였습니다.

1. **신뢰성**: 수집 실패가 전체 파이프라인을 멈추어서는 안 된다.
2. **재현성**: 같은 날짜 범위로 재처리하면 항상 같은 결과가 나와야 한다.
3. **투명성**: 각 레이어에 무엇이 들어 있는지, 어디서 왔는지 추적 가능해야 한다.

이 원칙들을 어떻게 구현했는지 이번 편에서 상세히 다룹니다.

---

## 1. ADF 파이프라인 구조 — 7단계 순차 체인

ADF 파이프라인 `Pipeline_Daily_SENSE_Predict`는 매일 16:30 KST에 트리거되어 7개 Activity를 순서대로 실행합니다. 장 마감(15:30) 후 1시간의 여유를 두어 당일 종가 데이터가 확정된 상태에서 수집하는 것이 16:30 트리거 선택의 이유입니다.

```
[파이프라인 의존성 체인]

① collect_yahoo_fred (Custom Activity)
   └─ Yahoo Finance OHLCV 10종 + FRED 금리 6종
   └─ ADLS raw/macro/, raw/fred/ 적재
           │ 성공 시
           ▼
② collect_naver_news (Functions Activity)
   └─ 네이버 뉴스 API 검색 + 본문 크롤링
   └─ ADLS raw/news/naver/ 적재
           │ 성공 시
           ▼
③ collect_google_news (ACI Activity)
   └─ Google News RSS + Playwright 브라우저 자동화
   └─ ADLS raw/news/google/ 적재
           │ 성공 시 (③와 ②는 병렬 가능)
           ▼
④ collect_customs (Custom Activity)
   └─ 관세청 API — HS Code 8542 월별 수출입
   └─ ADLS raw/trade/ 적재
           │ 성공 시
           ▼
⑤ databricks_raw_to_curated (Databricks Activity)
   └─ 01_raw_to_curated.py 실행
   └─ ADLS raw/ → curated/ 변환
           │ 성공 시
           ▼
⑥ databricks_curated_to_feature (Databricks Activity)
   └─ 02_curated_to_feature.py 실행
   └─ ADLS curated/ → feature/ 변환
           │ 성공 시
           ▼
⑦ databricks_ensemble (Databricks Activity)
   └─ ensemble_strategy.py 실행
   └─ fact_ensemble_forecast → PostgreSQL 적재
```

각 Activity에는 재시도 정책이 설정되어 있습니다: 네트워크 오류나 일시적 API 장애는 5분 간격으로 최대 3회 재시도합니다. 관세청 API는 월말에 업데이트 지연이 잦아 재시도를 5회로 늘렸습니다.

---

## 2. 수집기 구현 — 세 가지 실행 환경

### 2.1 Custom Activity — Docker로 Python 환경 격리

Custom Activity는 ADF가 사용자 정의 Docker 컨테이너를 실행하는 방식입니다. Yahoo Finance와 FRED 수집에 이 방식을 택한 이유는 **yfinance 라이브러리의 의존성 충돌** 때문이었습니다. `yfinance`는 `numpy`, `pandas`, `requests` 특정 버전을 요구하는데, 이것이 다른 수집기 의존성과 충돌했습니다. 컨테이너 격리로 이 문제를 원천 차단했습니다.

```python
# adf/custom_activity/main.py (핵심 부분)

import yfinance as yf
from azure.storage.filedatalake import DataLakeServiceClient
from src.utils.vault_manager import vault

TICKERS = [
    "005930.KS",  # 삼성전자
    "000660.KS",  # SK하이닉스
    "NVDA", "TSM", "MU", "ASML", "^SOX",
    "KRW=X", "GC=F",  # 환율, 금
]

FRED_SERIES = ["DGS10", "DGS2", "T10Y2Y", "BAMLH0A0HYM2", "DFF", "DFII10"]

def collect_and_upload(run_date: str):
    client = vault.get_storage_client()
    
    # Yahoo Finance 수집
    for ticker in TICKERS:
        df = yf.download(ticker, start="2020-01-01", end=run_date, auto_adjust=True)
        parquet_path = f"raw/macro/yfinance/{ticker.replace('^', '').replace('=', '_')}.parquet"
        _upload_parquet(client, df, parquet_path)
    
    # FRED 수집
    from fredapi import Fred
    fred = Fred(api_key=vault.get_secret("fred-api-key"))
    for series_id in FRED_SERIES:
        series = fred.get_series(series_id, observation_start="2020-01-01")
        _upload_parquet(client, series.to_frame(series_id), f"raw/fred/{series_id}.parquet")
```

Dockerfile은 `python:3.11-slim` 베이스 이미지에 필요한 패키지만 설치합니다. ACR Build(`az acr build`)를 통해 로컬 Docker 없이 클라우드에서 직접 이미지를 빌드합니다.

### 2.2 Azure Functions — 서버리스로 네이버 뉴스 수집

네이버 뉴스는 왜 Functions로 구현했을까요? 수집 로직이 **API 호출 → 결과 저장**이라는 단순한 구조이고, 이 작업은 하루 한 번만 실행됩니다. 상시 구동 서버를 두는 것은 낭비입니다. Functions의 소비 요금제(Consumption Plan)에서는 실행한 만큼만 비용이 발생합니다.

```python
# src/ingestion/naver_collectors/__init__.py (핵심 부분)

import azure.functions as func
from bs4 import BeautifulSoup
import aiohttp

KEYWORDS = ["삼성전자 반도체", "SK하이닉스 HBM", "반도체 수출", "메모리 수율"]

async def fetch_news_articles(session, keyword: str, display: int = 50):
    """네이버 뉴스 API 호출 + 본문 크롤링"""
    # 1단계: 검색 API로 URL 목록 수집
    headers = {
        "X-Naver-Client-Id": vault.get_secret("naver-client-id"),
        "X-Naver-Client-Secret": vault.get_secret("naver-client-secret"),
    }
    async with session.get(NAVER_SEARCH_URL, headers=headers,
                           params={"query": keyword, "display": display}) as resp:
        items = (await resp.json())["items"]
    
    # 2단계: 각 URL의 본문을 비동기 크롤링
    tasks = [_scrape_article_body(session, item["link"]) for item in items]
    bodies = await asyncio.gather(*tasks, return_exceptions=True)
    
    return [
        {**item, "body": body}
        for item, body in zip(items, bodies)
        if not isinstance(body, Exception)
    ]

app = func.FunctionApp()

@app.timer_trigger(schedule="0 30 16 * * *")  # 매일 16:30 (but ADF가 호출)
async def collect_naver_news(timer: func.TimerRequest):
    async with aiohttp.ClientSession() as session:
        all_articles = []
        for keyword in KEYWORDS:
            articles = await fetch_news_articles(session, keyword)
            all_articles.extend(articles)
    
    # ADLS Gen2 적재
    client = vault.get_storage_client()
    today = datetime.date.today().isoformat()
    _upload_json(client, all_articles, f"raw/news/naver/{today}.json")
```

### 2.3 ACI One-Shot — Playwright 브라우저 자동화

Google News는 공식 API가 없습니다. RSS 피드를 파싱하면 기사 제목과 URL은 가져올 수 있지만, 실제 본문을 읽으려면 브라우저가 JavaScript를 실행해야 하는 경우가 많습니다. `Playwright`는 Headless 브라우저를 Python으로 제어하는 라이브러리입니다.

이 수집기는 하루 한 번만 실행되고, 실행 시간이 길 수 있습니다. **Azure Container Instances(ACI)**는 이런 "무거운 one-shot 작업"에 최적화되어 있습니다. 컨테이너를 실행하고, 작업이 끝나면 자동으로 종료됩니다. 유휴 상태로 요금이 발생하지 않습니다.

```dockerfile
# src/ingestion/google_news_crawler/Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .
CMD ["python", "crawler.py"]
```

---

## 3. ADLS Gen2 — Medallion 레이어 설계

### 3.1 raw/ — 원본 그대로

raw 레이어의 원칙은 단순합니다: **수집기가 가져온 것을 그대로 보존한다**. 변환, 정제, 필터링 없이 원본 형태로 저장합니다. 왜냐하면 나중에 전처리 로직이 바뀌었을 때, 이 raw 데이터에서 재처리할 수 있어야 하기 때문입니다.

```
raw/
├── macro/
│   ├── yfinance/
│   │   ├── 005930KS.parquet          # 삼성전자 OHLCV
│   │   ├── 000660KS.parquet          # SK하이닉스 OHLCV
│   │   ├── NVDA.parquet
│   │   └── SOX.parquet
│   └── kfinance/                     # 한국 옵션·KFinance 데이터
├── fred/
│   ├── DGS10.parquet
│   ├── DGS2.parquet
│   └── T10Y2Y.parquet
├── news/
│   ├── naver/
│   │   └── 2026-04-17.json
│   └── google/
│       └── 2026-04-17.json
└── trade/
    └── HS8542_monthly.parquet         # 관세청 반도체 수출입
```

### 3.2 curated/ — 신뢰할 수 있는 정제 데이터

`01_raw_to_curated.py`가 생성하는 curated 레이어는 세 가지 작업을 수행합니다.

**① 거래일 통일과 결측치 보간**

삼성전자는 한국거래소(KRX) 거래일 기준, NVIDIA는 NYSE 거래일 기준입니다. 이 두 캘린더는 공휴일이 다릅니다. NVIDIA가 거래한 날 삼성전자가 휴장이었다면, 한국 주식 데이터에는 그날 레코드가 없습니다. 이 불일치를 그대로 두면 조인 시 NaN이 발생합니다.

우리는 **KRX 거래일 캘린더**를 기준으로 전체 시계열을 정렬하고, NYSE 공휴일에 해당하는 날의 미국 주식 데이터는 Forward Fill(전일 종가로 대체)을 적용했습니다. 주식 시장의 특성상 직전 거래일 종가가 가장 합리적인 대체값입니다.

```python
# notebooks/01_raw_to_curated.py (핵심 부분)

from pandas.tseries.offsets import CustomBusinessDay
from pandas_market_calendars import get_calendar

# KRX 거래일 캘린더
krx_cal = get_calendar("XKRX")
krx_bd = krx_cal.schedule(start_date="2020-01-01", end_date=run_date)
trading_days = krx_bd.index.normalize()  # 거래일 DatetimeIndex

# 전체 데이터를 KRX 거래일 기준으로 리인덱싱
df_unified = df.reindex(trading_days)

# NYSE 공휴일 → Forward Fill
df_unified[us_columns] = df_unified[us_columns].ffill()

# 한국 데이터 결측 → 선형 보간 (장기 휴장 대응)
df_unified[kr_columns] = df_unified[kr_columns].interpolate(method="time")
```

**② ABSA 뉴스 감성 분석**

raw 레이어의 뉴스 JSON을 읽어 Azure OpenAI(gpt-4.1-mini)로 ABSA 분석을 수행합니다. 이 결과가 curated 레이어에 저장됩니다. 모델 학습 시 매번 OpenAI API를 호출하는 것은 비용과 지연 시간 면에서 비효율적이므로, 전처리 단계에서 한 번만 실행하고 결과를 저장합니다.

**③ TF-IDF 키워드 추출**

뉴스 텍스트에서 당일 핵심 키워드를 TF-IDF로 추출합니다. TF-IDF는 문서 집합 전체에서 특정 단어의 상대적 중요도를 계산합니다. "반도체"처럼 매일 등장하는 단어는 낮은 점수를 받고, "관세 폭탄"처럼 특정 날 갑자기 많이 등장한 단어는 높은 점수를 받습니다.

### 3.3 feature/ — ML 준비 완료 피처 마트

`02_curated_to_feature.py`가 생성하는 feature 레이어는 ML 모델이 바로 소비할 수 있는 형태의 피처 마트입니다. 다음 편에서 이 레이어의 핵심인 47개 피처 엔지니어링을 상세히 다룹니다.

```
feature/
├── gold_macro_1y/            # 1년치 매크로·주가 통합 데이터셋
├── macro_semiconductor/      # 관세청 기반 수출입 파생변수
├── sense_macro/              # 23개 리스크 시그널 파생변수
└── timesfm_forecast/         # TimesFM 2.5 XReg 예측 결과
    ├── samsung_t20.parquet
    └── skhynix_t20.parquet
```

---

## 4. Databricks 전처리 — AutoLoader와 Delta Lake

### 4.1 AutoLoader로 증분 수집

Databricks의 AutoLoader(`cloudFiles` 소스)는 ADLS의 새 파일 도착을 자동으로 감지합니다. 매일 ADF 파이프라인이 새 파일을 raw에 적재하면, AutoLoader가 변경된 파일만 읽어 처리합니다. 전체 히스토리를 매번 다시 읽지 않습니다.

```python
# Databricks 노트북 내 AutoLoader 패턴
df_stream = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "parquet")
    .option("cloudFiles.schemaLocation", schema_location)
    .load(f"abfss://raw@3dtteam1adls.dfs.core.windows.net/macro/yfinance/")
)
```

### 4.2 Key Vault Secret Scope

Databricks에서 ADLS에 접근하는 방식은 두 가지입니다: SAS 토큰(만료 관리 번거로움)과 Service Principal OAuth(영구적, 자동 갱신). 우리는 후자를 선택하고, Service Principal 자격증명을 Key Vault에 보관합니다.

Databricks의 Key Vault-backed Secret Scope를 사용하면 `dbutils.secrets.get()`으로 Key Vault 시크릿에 접근합니다. 노트북 코드에 자격증명이 노출되지 않습니다.

```python
# Databricks 노트북 내 ADLS 인증

spark.conf.set(
    "fs.azure.account.auth.type.3dtteam1adls.dfs.core.windows.net",
    "OAuth"
)
spark.conf.set(
    "fs.azure.account.oauth.provider.type.3dtteam1adls.dfs.core.windows.net",
    "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider"
)
spark.conf.set(
    "fs.azure.account.oauth2.client.id.3dtteam1adls.dfs.core.windows.net",
    dbutils.secrets.get(scope="sense-kv-scope", key="adls-client-id")
)
spark.conf.set(
    "fs.azure.account.oauth2.client.secret.3dtteam1adls.dfs.core.windows.net",
    dbutils.secrets.get(scope="sense-kv-scope", key="adls-client-secret")
)
```

---

## 5. PostgreSQL 스키마 설계 — 서빙을 위한 구조

앙상블 예측 결과는 최종적으로 PostgreSQL에 적재됩니다. 웹 대시보드가 이 데이터를 읽어 시각화합니다.

### 5.1 fact_ensemble_forecast — 예측 결과 팩트 테이블

```sql
CREATE TABLE fact_ensemble_forecast (
    id              SERIAL PRIMARY KEY,
    run_date        DATE NOT NULL,           -- 예측 실행일
    stock_code      VARCHAR(20) NOT NULL,    -- 005930.KS / 000660.KS
    forecast_date   DATE NOT NULL,           -- 예측 대상일 (T+1 ~ T+20)
    horizon         INTEGER NOT NULL,        -- 몇 거래일 후인지 (1~20)
    
    -- 예측값
    price_forecast  DOUBLE PRECISION,        -- 앙상블 예측 주가
    pi_lower        DOUBLE PRECISION,        -- 90% 신뢰구간 하단
    pi_upper        DOUBLE PRECISION,        -- 90% 신뢰구간 상단
    
    -- 앙상블 메타데이터
    weight_timesfm  DOUBLE PRECISION,        -- TimesFM에 부여된 가중치
    weight_ucmodel  DOUBLE PRECISION,        -- UC BestTrial에 부여된 가중치
    regime          VARCHAR(20),             -- TREND / MEAN_REV / NEUTRAL
    confidence_score DOUBLE PRECISION,       -- 0~10 신뢰도 점수
    
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 웹 대시보드 조회 성능을 위한 복합 인덱스
CREATE INDEX idx_forecast_stock_date ON fact_ensemble_forecast(stock_code, run_date DESC);
```

매일 앙상블이 실행되면 40개 레코드(2종목 × 20거래일)가 이 테이블에 삽입됩니다. 웹 대시보드는 `WHERE run_date = CURRENT_DATE`로 당일 예측을 조회합니다.

### 5.2 뉴스 감성 뷰 — RAG 챗봇의 컨텍스트 소스

```sql
-- 챗봇이 참조하는 일별 감성 집계 뷰
CREATE VIEW gold_news.v_news_sentiment_trend AS
SELECT
    base_date,
    stock_code,
    avg_sentiment,
    news_vol,
    ROUND(
        CAST(news_vol AS NUMERIC) /
        NULLIF(LAG(news_vol, 1) OVER (PARTITION BY stock_code ORDER BY base_date), 0) - 1,
        4
    ) AS news_vol_surge,   -- 뉴스 언급량 급증률 (전일 대비)
    daily_keywords
FROM gold_news.agg_market_sentiment_daily
ORDER BY base_date DESC;
```

---

## 6. 팀 협업 — ADF JSON 충돌 예방

ADF 파이프라인 JSON은 UI에서 수정하면 `adf/pipeline/` 폴더에 저장됩니다. 팀원 2명이 동시에 ADF UI를 수정하면 Git merge conflict가 발생합니다. 이 JSON은 중첩 구조가 깊어 conflict 해결이 어렵습니다.

우리가 정한 규칙은 단순했습니다: **ADF 파이프라인 수정은 팀 채팅에서 먼저 공지한다**. 그리고 수정을 마치면 반드시 ADF UI의 "Publish" 버튼을 눌러 `adf_publish` 브랜치에 반영하고, 관련 JSON을 `adf/` 폴더에 커밋합니다.

낮은 기술 비용의 협업 프로토콜이 수십 번의 merge conflict를 예방했습니다.

---

## 마치며 — 다음 편 예고

이번 편에서는 ADF 파이프라인 7단계 체인, 세 가지 수집기 구현 방식, Medallion 레이어 설계, PostgreSQL 스키마를 살펴봤습니다.

다음 편에서는 feature 레이어를 채우는 핵심 작업 — 47개 피처 엔지니어링과 Azure OpenAI 기반 ABSA 뉴스 감성 분석을 상세히 다룹니다.
