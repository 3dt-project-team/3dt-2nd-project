-- 스키마 생성
CREATE SCHEMA IF NOT EXISTS gold_news;
CREATE SCHEMA IF NOT EXISTS gold_macro;
CREATE SCHEMA IF NOT EXISTS gold_equity;
CREATE SCHEMA IF NOT EXISTS gold_ml;

-- pgvector 확장팩 활성화 (벡터 검색용)
CREATE EXTENSION IF NOT EXISTS vector;

-- ==========================================
-- 1. gold_news 스키마 (뉴스 데이터 레이어)
-- ==========================================

-- [Dim] 뉴스 마스터: 원문 및 요약, 임베딩 벡터 저장
CREATE TABLE gold_news.dim_news_master (
    news_id         UUID PRIMARY KEY,
    published_date  DATE NOT NULL,
    published_time  TIMESTAMP,
    news_source     VARCHAR(50),
    title           VARCHAR(255) NOT NULL,
    full_text       TEXT NOT NULL,
    core_summary    TEXT NOT NULL,          -- AI 요약본
    category        VARCHAR(30) NOT NULL,   -- 실적, 공급망 등
    summary_vector  VECTOR(1536) NOT NULL,  -- OpenAI 임베딩 벡터
    original_url    VARCHAR(500)
);

-- [Fact] 뉴스 분석: 키워드 및 ABSA 감성 점수
CREATE TABLE gold_news.fact_news_analytics (
    analytics_id    BIGSERIAL PRIMARY KEY,
    news_id         UUID REFERENCES gold_news.dim_news_master(news_id),
    analyzed_date   DATE NOT NULL,
    dynamic_keywords JSONB NOT NULL,         -- ["HBM", "수율"] 등 GIN 인덱스 활용
    keyword_momentum JSONB NOT NULL,        -- 전일 대비 언급 급증률
    absa_aspect     VARCHAR(50),            -- 제조원가, 양산일정 등
    absa_score      FLOAT NOT NULL,         -- -1.0 ~ 1.0
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. gold_macro 스키마 (거시경제 지표 레이어)
-- ==========================================

-- [Dim] 거시지표 메타데이터
CREATE TABLE gold_macro.dim_macro_series (
    series_id       SMALLINT PRIMARY KEY,
    ticker          VARCHAR(20) UNIQUE NOT NULL,
    display_name    VARCHAR(50) NOT NULL,
    category        VARCHAR(20) NOT NULL,   -- commodity, bond 등
    unit            VARCHAR(20) NOT NULL,
    data_source     VARCHAR(30) NOT NULL
);

-- [Fact] 일별 거시 시계열 데이터
CREATE TABLE gold_macro.fact_macro_daily (
    id              BIGSERIAL PRIMARY KEY,
    series_id       SMALLINT REFERENCES gold_macro.dim_macro_series(series_id),
    trade_date      DATE NOT NULL,
    open            FLOAT,
    high            FLOAT,
    low             FLOAT,
    close           FLOAT NOT NULL,
    volume          BIGINT,
    is_filled       BOOLEAN DEFAULT FALSE,
    UNIQUE(series_id, trade_date)
);

-- [Fact] 파생 기술 지표 (이동평균, Z-Score 등)
CREATE TABLE gold_macro.fact_macro_derived (
    id              BIGSERIAL PRIMARY KEY,
    series_id       SMALLINT REFERENCES gold_macro.dim_macro_series(series_id),
    trade_date      DATE NOT NULL,
    indicator_name  VARCHAR(30) NOT NULL,   -- ma_20, rsi_14 등
    indicator_value FLOAT NOT NULL,
    UNIQUE(series_id, trade_date, indicator_name)
);

-- [Fact] FRED 금리 특화 테이블
CREATE TABLE gold_macro.fact_macro_fred (
    id              BIGSERIAL PRIMARY KEY,
    series_code     VARCHAR(20) NOT NULL,   -- DGS10, T10Y2Y 등
    observed_date   DATE NOT NULL,
    rate_value      FLOAT NOT NULL,
    is_filled       BOOLEAN DEFAULT FALSE,
    UNIQUE(series_code, observed_date)
);

-- ==========================================
-- 3. gold_equity 스키마 (주가 및 수급 레이어)
-- ==========================================

-- [Dim] 종목 메타데이터
CREATE TABLE gold_equity.dim_equity (
    equity_id       SMALLINT PRIMARY KEY,
    ticker          VARCHAR(20) UNIQUE NOT NULL,
    name_kr         VARCHAR(50),
    name_en         VARCHAR(50) NOT NULL,
    market          VARCHAR(10) NOT NULL,   -- KOSPI, NASDAQ 등
    asset_type      VARCHAR(15) NOT NULL,   -- stock, etf 등
    role            VARCHAR(20) NOT NULL    -- target(삼성/하이닉스), leading(엔비디아 등)
);

-- [Fact] 일별 OHLCV 주가 데이터
CREATE TABLE gold_equity.fact_equity_ohlcv (
    id              BIGSERIAL PRIMARY KEY,
    equity_id       SMALLINT REFERENCES gold_equity.dim_equity(equity_id),
    trade_date      DATE NOT NULL,
    open            FLOAT,
    high            FLOAT,
    low             FLOAT,
    close           FLOAT NOT NULL,
    volume          BIGINT,
    is_filled       BOOLEAN DEFAULT FALSE,
    UNIQUE(equity_id, trade_date)
);

-- [Fact] ML 타겟 변수 (예측 결과가 아닌 예측 '대상' 값)
CREATE TABLE gold_equity.fact_equity_target (
    id              BIGSERIAL PRIMARY KEY,
    equity_id       SMALLINT REFERENCES gold_equity.dim_equity(equity_id),
    trade_date      DATE NOT NULL,
    return_1d       FLOAT NOT NULL,         -- 내일 수익률
    return_5d       FLOAT,                  -- 5일 수익률
    realized_vol_5d FLOAT,
    downside_flag   BOOLEAN NOT NULL,       -- -3% 이하 하락 여부
    upside_flag     BOOLEAN NOT NULL,       -- +3% 이상 상승 여부
    regime          VARCHAR(10) NOT NULL,   -- risk, opportunity 등
    UNIQUE(equity_id, trade_date)
);

-- ==========================================
-- 4. gold_ml 스키마 (퀀트, 펀더멘털, 피처셋 통합)
-- ==========================================

-- [Fact] 글로벌 필라델피아 반도체(SOX) 동조화 지표
CREATE TABLE gold_ml.fact_quant_sox_sync (
    id              BIGSERIAL PRIMARY KEY,
    us_trade_date   DATE UNIQUE NOT NULL,
    kr_effective_date DATE NOT NULL,        -- 한국 시장 반영일 (T+1)
    sox_close       FLOAT NOT NULL,
    sox_return_1d   FLOAT NOT NULL,
    nvda_return_1d  FLOAT,
    correlation_30d FLOAT,                  -- 30일 상관계수
    spillover_flag  BOOLEAN DEFAULT FALSE   -- 하방 전이 경고
);

-- [Fact] 메모리 기업 Proxy (MU/WDC) 심리 지수
CREATE TABLE gold_ml.fact_quant_memory_proxy (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE UNIQUE NOT NULL,
    mu_close        FLOAT NOT NULL,
    wdc_close       FLOAT NOT NULL,
    memory_sentiment_index FLOAT NOT NULL,  -- 시총 가중 복합 지수
    memory_trend_flag VARCHAR(10)           -- bullish, bearish 등
);

-- 1. 반도체 수출입 통계 (Gold)
CREATE TABLE gold_ml.gold_customs_semiconductor ( 
    stat_year SMALLINT NOT NULL, -- 통계 연도 
    stat_month SMALLINT NOT NULL, -- 통계 월 
    hs_code VARCHAR(10) NOT NULL, -- 8542 (반도체) 
    export_usd_amt NUMERIC(20, 2), -- 수출 금액 (USD) 
    import_usd_amt NUMERIC(20, 2), -- 수입 금액 (USD) 
    trade_balance NUMERIC(20, 2), -- 무역 수지 
    yoy_change_pct FLOAT, -- 전년 동월 대비 증감률 
    export_trend VARCHAR(20), -- 'Growing', 'Stable', 'Declining' 
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (stat_year, stat_month, hs_code)
);

-- 2. 풋콜 비율 및 옵션 시그널 (Gold)
CREATE TABLE gold_ml.gold_quant_pcr_signals ( 
    trade_date DATE PRIMARY KEY, -- 거래일 
    put_volume BIGINT NOT NULL, -- 풋옵션 총 거래량 
    call_volume BIGINT NOT NULL, -- 콜옵션 총 거래량 
    pcr_ratio FLOAT NOT NULL, -- 풋/콜 비율 (위험 감지 지표) 
    pcr_ma5 FLOAT, -- PCR 5일 이동평균 (추세 파악) 
    fear_greed_idx VARCHAR(20), -- 'Fear', 'Neutral', 'Greed' 판정 
    is_downside_warning BOOLEAN DEFAULT FALSE, -- 하방 리스크 경고 플래그 
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 통합 ML 피처 및 리스크 지표 (Gold Master)
CREATE TABLE gold_ml.gold_ml_feature_set (
    base_date       DATE PRIMARY KEY,            -- 기준일 (T)
    
    -- [Customs Factor] 펀더멘털
    semi_export_yoy FLOAT,                       -- 반도체 수출 증감률 (최근 발표치)
    
    -- [Option Factor] 시장 심리
    pcr_val         FLOAT,                       -- 당일 풋콜 비율
    
    -- [Macro Factor] 외부 환경 (다른 팀원 데이터와 조인 예정)
    usd_krw_rate    FLOAT,                       -- 원달러 환율
    us_10y_yield    FLOAT,                       -- 미국 10년물 금리
    
    -- [Sentiment Factor] 뉴스 (다른 팀원 데이터와 조인 예정)
    avg_absa_score  FLOAT,                       -- 뉴스 감성 점수 평균
    
    -- [Target Variable] 예측 대상
    target_return_5d FLOAT,                      -- T+5일 수익률 (Labeling용)
    regime_label     VARCHAR(20)                 -- 'Risk', 'Opportunity', 'Neutral'
);

-- 퀀트 통합 시그널 뷰
CREATE VIEW gold_ml.v_quant_daily_signals AS
SELECT 
    s.kr_effective_date AS trade_date,
    s.spillover_flag,
    s.sox_return_1d,
    m.memory_trend_flag,
    c.yoy_change_pct AS customs_yoy
FROM gold_ml.fact_quant_sox_sync s
LEFT JOIN gold_ml.fact_quant_memory_proxy m ON s.us_trade_date = m.trade_date
LEFT JOIN gold_ml.gold_customs_semiconductor c ON TO_CHAR(s.kr_effective_date, 'YYYYMM') = (c.stat_year || LPAD(c.stat_month::text, 2, '0'));
