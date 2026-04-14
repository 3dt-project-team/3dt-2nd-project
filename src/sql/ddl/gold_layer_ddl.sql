-- =============================================================================
-- SENSE Gold Layer DDL
-- 데이터 사전: docs/data_dict/SENSE 데이터 사전.md
-- 실제 구조 확인: docs/SENSE_데이터_구조_전체.md §5-2 (2026-04-14)
--
-- 실행: psql -U <user> -d sense_db -f gold_layer_ddl.sql
-- 재실행 안전: CREATE TABLE / ADD COLUMN 모두 IF NOT EXISTS 사용
--
-- ─── 스키마별 현재 상태 ──────────────────────────────────────────────────────
-- gold_news   ✅ dim_news_display, agg_market_sentiment_daily,
--                fact_feature_vector_store
-- gold_macro  ✅ dim_macro_metadatas, fact_macro_all, fact_yf_fx_fred_1y,
--                fact_kfinance, fact_semiconductor_trade
-- gold_equity ⬜ 스키마만 존재, 테이블 신규 생성 필요
-- gold_ml     ✅ fact_quant_sox_sync, fact_quant_memory_proxy,
--                gold_customs_semiconductor, gold_ml_feature_set,
--                gold_quant_pcr_signals
-- public      ✅ fact_ensemble_forecast (160행), fact_stat_forecast
-- =============================================================================

-- § 0. 확장 & 스키마
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS gold_news;
CREATE SCHEMA IF NOT EXISTS gold_macro;
CREATE SCHEMA IF NOT EXISTS gold_equity;
CREATE SCHEMA IF NOT EXISTS gold_ml;


-- =============================================================================
-- § 1. gold_news (뉴스 Gold — 2026-04 재설계)
-- =============================================================================

-- ① Web App / Power BI 뉴스 리스트 서빙
CREATE TABLE IF NOT EXISTS gold_news.dim_news_display (
    news_id         UUID            PRIMARY KEY,
    display_title   TEXT            NOT NULL,
    core_summary    TEXT            NOT NULL,
    sentiment_class VARCHAR(10)     NOT NULL,   -- 호재|악재|중립
    category        VARCHAR(30)     NOT NULL,
    press           TEXT,
    original_url    TEXT,
    stock_keyword   TEXT            NOT NULL,   -- samsung|skhynix
    pub_date        DATE            NOT NULL
);
COMMENT ON COLUMN gold_news.dim_news_display.sentiment_class IS
    'absa_score >= 0.3 → 호재 | <= -0.3 → 악재 | 그 외 → 중립';


-- ② EDA / Power BI 리스크 차트 일별 집계
CREATE TABLE IF NOT EXISTS gold_news.agg_market_sentiment_daily (
    base_date       DATE            NOT NULL,
    stock_code      TEXT            NOT NULL,   -- SAMSUNG|SKHYNIX
    avg_sentiment   FLOAT           NOT NULL,
    news_vol        INTEGER         NOT NULL,
    main_aspect     TEXT,
    daily_keywords  JSONB           NOT NULL,
    PRIMARY KEY (base_date, stock_code)
);
COMMENT ON COLUMN gold_news.agg_market_sentiment_daily.daily_keywords IS
    '[{"rank":1,"keyword":"HBM","mention_count":18,"avg_sentiment":0.62,'
    '"sentiment_label":"positive","mention_delta":7,"mention_delta_pct":63.6,'
    '"sentiment_delta":0.14}]';


-- ③ ML 학습 + RAG 벡터 스토어
CREATE TABLE IF NOT EXISTS gold_news.fact_feature_vector_store (
    news_id         UUID            PRIMARY KEY,
    summary_vec     VECTOR(1536)    NOT NULL,
    search_context  TEXT            NOT NULL,
    feature_score   FLOAT           NOT NULL,
    aspect_tag      TEXT,
    keyword_momentum JSONB
);


-- =============================================================================
-- § 2. gold_macro (거시경제 Gold)
--
-- 실제 테이블명 vs 설계명:
--   dim_macro_metadatas  ← dim_macro_series
--   fact_macro_all       ← fact_macro_daily
--   fact_yf_fx_fred_1y   ← fact_macro_derived + fact_macro_fred 통합 와이드 테이블
--   fact_kfinance        ← 설계 미기재 신규
--   fact_semiconductor_trade ← fact_quant_customs
-- =============================================================================

CREATE TABLE IF NOT EXISTS gold_macro.dim_macro_metadatas (
    series_id       SMALLSERIAL     PRIMARY KEY,
    ticker          VARCHAR(20)     UNIQUE NOT NULL,
    display_name    VARCHAR(50)     NOT NULL,
    category        VARCHAR(20)     NOT NULL,   -- commodity|bond|currency|index
    unit            VARCHAR(20)     NOT NULL,
    data_source     VARCHAR(30)     NOT NULL    -- yahoo_finance|fred|open_exchange_rates
);


CREATE TABLE IF NOT EXISTS gold_macro.fact_macro_all (
    id              BIGSERIAL       PRIMARY KEY,
    series_id       SMALLINT        NOT NULL
                        REFERENCES gold_macro.dim_macro_metadatas(series_id),
    trade_date      DATE            NOT NULL,
    open            FLOAT,
    high            FLOAT,
    low             FLOAT,
    close           FLOAT           NOT NULL,
    volume          BIGINT,
    is_filled       BOOLEAN         NOT NULL DEFAULT FALSE,
    UNIQUE (series_id, trade_date)
);


-- yfinance + FX + FRED 통합 와이드 테이블 (노트북에서 gold_macro_1y.parquet 로 읽힘)
CREATE TABLE IF NOT EXISTS gold_macro.fact_yf_fx_fred_1y (
    trade_date              DATE        PRIMARY KEY,

    -- 주가
    yfinance_samsung_close  FLOAT,
    yfinance_skhynix_close  FLOAT,
    yfinance_nvda_close     FLOAT,
    yfinance_amd_close      FLOAT,
    yfinance_mu_close       FLOAT,
    yfinance_tsm_close      FLOAT,
    yfinance_asml_close     FLOAT,
    yfinance_sox_close      FLOAT,

    -- 환율
    usd_krw_rate            FLOAT,
    usd_krw_change          FLOAT,
    usd_krw_pct             FLOAT,
    risk_off_flag           INTEGER,

    -- FRED 금리
    fred_dgs10              FLOAT,
    fred_dgs2               FLOAT,
    fred_t10y2y             FLOAT,
    fred_dff                FLOAT,
    fred_dfii10             FLOAT,
    fred_bamlh0a0hym2       FLOAT,
    yield_spread            FLOAT,
    yield_spread_change     FLOAT,
    stagnation_pressure     FLOAT,

    -- 캘린더 (parquet 컬럼명 그대로 유지)
    "주말여부"              BOOLEAN,
    "한국_휴장일_여부"      BOOLEAN
);
COMMENT ON TABLE gold_macro.fact_yf_fx_fred_1y IS
    'yfinance + FX + FRED 1년 통합 와이드 테이블. Databricks feature/gold_macro_1y.parquet 경유 적재.';


-- kfinance 코스피200 옵션 파생 (월별·28행)
-- ⚠️ PCR 계산 불가 (2026-04): 코스피200 풋옵션 없음, 월별 스냅샷
CREATE TABLE IF NOT EXISTS gold_macro.fact_kfinance (
    trade_date      DATE        PRIMARY KEY,    -- 해당 월 마지막 영업일
    call_volume     FLOAT,
    call_oi         FLOAT,
    avg_iv          FLOAT,                      -- 내재변동성 (VIX 대용)
    iv_change       FLOAT,
    vol_change_pct  FLOAT,
    iv_surge_flag   INTEGER     NOT NULL DEFAULT 0  -- 전월비 +5 이상 시 1
);


-- 반도체 수출입 통계 (설계명: fact_quant_customs)
CREATE TABLE IF NOT EXISTS gold_macro.fact_semiconductor_trade (
    stat_year           SMALLINT        NOT NULL,
    stat_month          SMALLINT        NOT NULL,
    hs_code             VARCHAR(10)     NOT NULL,   -- 8542 = 반도체
    export_usd_amt      NUMERIC(20, 2)  NOT NULL,
    import_usd_amt      NUMERIC(20, 2),
    trade_balance       NUMERIC(20, 2),
    export_qty          FLOAT,
    yoy_change_pct      FLOAT,
    mom_change_pct      FLOAT,
    export_trend_flag   VARCHAR(10),                -- declining|stable|growing
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stat_year, stat_month, hs_code)
);


-- =============================================================================
-- § 3. gold_equity (주가 Gold — 신규 생성 필요)
-- ⚠️ 2026-04-14 기준 스키마만 존재. 골드레이어 적재 완료 후 이 DDL 실행.
-- =============================================================================

CREATE TABLE IF NOT EXISTS gold_equity.dim_equity (
    equity_id       SMALLSERIAL     PRIMARY KEY,
    ticker          VARCHAR(20)     UNIQUE NOT NULL,
    name_kr         VARCHAR(50),
    name_en         VARCHAR(50)     NOT NULL,
    market          VARCHAR(10)     NOT NULL,   -- KOSPI|NASDAQ|NYSE|CME
    asset_type      VARCHAR(15)     NOT NULL,   -- stock|futures|etf|index
    role            VARCHAR(20)     NOT NULL    -- target|leading
);


CREATE TABLE IF NOT EXISTS gold_equity.fact_equity_ohlcv (
    id          BIGSERIAL   PRIMARY KEY,
    equity_id   SMALLINT    NOT NULL
                    REFERENCES gold_equity.dim_equity(equity_id),
    trade_date  DATE        NOT NULL,
    open        FLOAT,
    high        FLOAT,
    low         FLOAT,
    close       FLOAT       NOT NULL,
    volume      BIGINT,
    is_filled   BOOLEAN     NOT NULL DEFAULT FALSE,
    UNIQUE (equity_id, trade_date)
);


-- ML 타겟 변수 (양방향: downside + upside)
CREATE TABLE IF NOT EXISTS gold_equity.fact_equity_target (
    id              BIGSERIAL   PRIMARY KEY,
    equity_id       SMALLINT    NOT NULL
                        REFERENCES gold_equity.dim_equity(equity_id),
    trade_date      DATE        NOT NULL,
    return_1d       FLOAT       NOT NULL,
    return_5d       FLOAT,
    realized_vol_5d FLOAT,
    max_drawdown_5d FLOAT,                      -- T+1~T+5 최대 낙폭 (%)
    max_gain_5d     FLOAT,                      -- T+1~T+5 최대 상승폭 (%)
    downside_flag   BOOLEAN     NOT NULL,       -- max_drawdown_5d < -3% → TRUE
    upside_flag     BOOLEAN     NOT NULL,       -- max_gain_5d > +3% → TRUE
    regime          VARCHAR(10) NOT NULL,       -- risk|opportunity|neutral|high_vol
    UNIQUE (equity_id, trade_date)
);
COMMENT ON COLUMN gold_equity.fact_equity_target.regime IS
    'risk | opportunity | neutral | high_vol. 보고서 자동 생성 색상 코딩에 사용.';


-- 파생 기술 지표 (Narrow 모델)
CREATE TABLE IF NOT EXISTS gold_equity.fact_equity_signals (
    id          BIGSERIAL   PRIMARY KEY,
    equity_id   SMALLINT    NOT NULL
                    REFERENCES gold_equity.dim_equity(equity_id),
    trade_date  DATE        NOT NULL,
    signal_name VARCHAR(30) NOT NULL,   -- ma_5|ma_20|rsi_14|bollinger_upper|
                                        -- bollinger_lower|volume_ma_20|volume_ratio
    signal_value FLOAT      NOT NULL,
    UNIQUE (equity_id, trade_date, signal_name)
);


-- =============================================================================
-- § 4. gold_ml (퀀트 선행지표 + ML 피처셋)
-- =============================================================================

-- SOX 글로벌 피어 동조화
CREATE TABLE IF NOT EXISTS gold_ml.fact_quant_sox_sync (
    id                  BIGSERIAL   PRIMARY KEY,
    us_trade_date       DATE        UNIQUE NOT NULL,
    kr_effective_date   DATE        NOT NULL,
    sox_close           FLOAT       NOT NULL,
    sox_return_1d       FLOAT       NOT NULL,
    nvda_return_1d      FLOAT,
    soxl_return_1d      FLOAT,
    correlation_30d     FLOAT,
    spillover_flag      BOOLEAN     NOT NULL DEFAULT FALSE,  -- SOX -2% 이하
    upside_surge_flag   BOOLEAN     NOT NULL DEFAULT FALSE   -- SOX +2% 이상
);

ALTER TABLE gold_ml.fact_quant_sox_sync
    ADD COLUMN IF NOT EXISTS soxl_return_1d     FLOAT,
    ADD COLUMN IF NOT EXISTS upside_surge_flag  BOOLEAN NOT NULL DEFAULT FALSE;


-- 메모리 기업 Proxy (MU/WDC)
CREATE TABLE IF NOT EXISTS gold_ml.fact_quant_memory_proxy (
    id                      BIGSERIAL   PRIMARY KEY,
    trade_date              DATE        UNIQUE NOT NULL,
    mu_close                FLOAT       NOT NULL,
    mu_return_1d            FLOAT       NOT NULL DEFAULT 0,
    wdc_close               FLOAT       NOT NULL,
    wdc_return_1d           FLOAT       NOT NULL DEFAULT 0,
    memory_sentiment_index  FLOAT       NOT NULL,   -- 0.6×MU + 0.4×WDC 시총 가중
    memory_ma5              FLOAT,
    memory_trend_flag       VARCHAR(10) NOT NULL DEFAULT 'neutral'  -- bearish|neutral|bullish
);

ALTER TABLE gold_ml.fact_quant_memory_proxy
    ADD COLUMN IF NOT EXISTS mu_return_1d  FLOAT,
    ADD COLUMN IF NOT EXISTS wdc_return_1d FLOAT,
    ADD COLUMN IF NOT EXISTS memory_ma5    FLOAT;


-- 관세청 반도체 수출 (gold_ml 버전 — gold_macro.fact_semiconductor_trade와 중복)
-- TODO: 두 테이블 중 하나로 통합 후 나머지 삭제 권장
CREATE TABLE IF NOT EXISTS gold_ml.gold_customs_semiconductor (
    stat_year       SMALLINT        NOT NULL,
    stat_month      SMALLINT        NOT NULL,
    hs_code         VARCHAR(10)     NOT NULL,
    export_usd_amt  NUMERIC(20, 2),
    import_usd_amt  NUMERIC(20, 2),
    trade_balance   NUMERIC(20, 2),
    yoy_change_pct  FLOAT,
    export_trend    VARCHAR(20),
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stat_year, stat_month, hs_code)
);


-- PCR 퀀트 시그널 (kfinance IV 대용 운영 중)
-- ⚠️ 코스피200 일별 풋/콜 데이터 미확보 → 정확한 PCR 산출 보류
CREATE TABLE IF NOT EXISTS gold_ml.gold_quant_pcr_signals (
    trade_date          DATE        PRIMARY KEY,
    put_volume          BIGINT      NOT NULL DEFAULT 0,
    call_volume         BIGINT      NOT NULL,
    pcr_ratio           FLOAT       NOT NULL,
    pcr_ma5             FLOAT,
    pcr_ma20            FLOAT,
    fear_greed_idx      VARCHAR(20),            -- Fear|Neutral|Greed
    pcr_breakout_flag   BOOLEAN     NOT NULL DEFAULT FALSE,  -- PCR MA5>MA20 하방 경고
    pcr_bullish_flag    BOOLEAN     NOT NULL DEFAULT FALSE,  -- PCR MA5<MA20 상승 모멘텀
    is_downside_warning BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE gold_ml.gold_quant_pcr_signals
    ADD COLUMN IF NOT EXISTS pcr_ma20           FLOAT,
    ADD COLUMN IF NOT EXISTS pcr_breakout_flag  BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS pcr_bullish_flag   BOOLEAN NOT NULL DEFAULT FALSE;


-- ML 통합 피처셋 (TimesFM XReg 공변량 + ElasticNet 피처)
CREATE TABLE IF NOT EXISTS gold_ml.gold_ml_feature_set (
    base_date               DATE        PRIMARY KEY,

    -- 주가 타겟
    samsung_close           FLOAT,
    skhynix_close           FLOAT,

    -- 매크로 피처
    usd_krw_rate            FLOAT,
    fred_dgs10              FLOAT,
    fred_dgs2               FLOAT,
    fred_t10y2y             FLOAT,
    fred_dff                FLOAT,
    fred_bamlh0a0hym2       FLOAT,

    -- 퀀트 선행 지표
    sox_return_1d           FLOAT,
    memory_sentiment_index  FLOAT,
    semi_export_yoy         FLOAT,
    avg_iv                  FLOAT,

    -- 뉴스 감성
    avg_absa_score          FLOAT,
    news_vol                INTEGER,

    -- 타겟 변수
    target_return_5d        FLOAT,
    downside_flag           BOOLEAN,
    upside_flag             BOOLEAN,
    regime_label            VARCHAR(20)
);


-- =============================================================================
-- § 5. public (ML 예측 출력)
-- =============================================================================

-- TimesFM 앙상블 예측 결과 (160행 기확인)
CREATE TABLE IF NOT EXISTS public.fact_ensemble_forecast (
    id              BIGSERIAL   PRIMARY KEY,
    date            TIMESTAMP   NOT NULL,       -- 예측 대상 일자
    ticker          TEXT        NOT NULL,
    base_date       TIMESTAMP   NOT NULL,       -- 예측 기준일
    horizon_day     BIGINT      NOT NULL,       -- 예측 기간 (일)
    trend_score     FLOAT,
    mean_rev_score  FLOAT,
    trend_pred      FLOAT,
    meanrev_pred    FLOAT,
    final_pred      FLOAT       NOT NULL,
    pi_lower        FLOAT,
    pi_upper        FLOAT,
    confidence_score FLOAT,
    regime_flag     BIGINT,
    regime_label    TEXT,
    run_timestamp   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ticker, base_date, horizon_day)
);
COMMENT ON TABLE public.fact_ensemble_forecast IS
    'notebooks/timesfm_inference.py 출력. 2026-04-14 기준 160행.';


-- Ridge 통계 기준선 예측 결과
CREATE TABLE IF NOT EXISTS public.fact_stat_forecast (
    id              BIGSERIAL   PRIMARY KEY,
    ticker          TEXT        NOT NULL,
    base_date       TIMESTAMP   NOT NULL,
    horizon         BIGINT      NOT NULL,
    model           TEXT        NOT NULL,
    model_type      TEXT        NOT NULL,
    prediction      FLOAT       NOT NULL,
    change_pct      FLOAT,
    scenario        TEXT,
    run_timestamp   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ticker, base_date, horizon, model, scenario)
);
COMMENT ON TABLE public.fact_stat_forecast IS
    'notebooks/statistical_baseline_analysis.py 출력.';
