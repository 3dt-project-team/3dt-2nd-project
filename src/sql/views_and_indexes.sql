-- =============================================================================
-- SENSE — Views & Indexes
-- 목적: Power BI / Web App 서빙 최적화
--
-- 실행 순서: gold_layer_ddl.sql → seed_data.sql → (데이터 적재) → 이 파일
-- 재실행 안전: CREATE OR REPLACE VIEW, CREATE INDEX IF NOT EXISTS
-- =============================================================================


-- =============================================================================
-- § 1. 인덱스 (Indexes)
-- =============================================================================

-- ─── 벡터 인덱스 

-- HNSW (pgvector) — RAG 코사인 유사도 검색
CREATE INDEX IF NOT EXISTS idx_feature_vec_hnsw
    ON gold_news.fact_feature_vector_store
    USING hnsw (summary_vec vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);


-- ─── 시계열 인덱스

-- BRIN — 대규모 시계열 (삽입 순서≈날짜 순 보장 시 효율적)
CREATE INDEX IF NOT EXISTS idx_fact_macro_all_date
    ON gold_macro.fact_macro_all USING brin (trade_date);

CREATE INDEX IF NOT EXISTS idx_yf_fx_fred_date
    ON gold_macro.fact_yf_fx_fred_1y USING brin (trade_date);

CREATE INDEX IF NOT EXISTS idx_equity_ohlcv_date
    ON gold_equity.fact_equity_ohlcv USING brin (trade_date);

CREATE INDEX IF NOT EXISTS idx_ensemble_forecast_date
    ON public.fact_ensemble_forecast USING brin (date);

CREATE INDEX IF NOT EXISTS idx_stat_forecast_base_date
    ON public.fact_stat_forecast USING brin (base_date);


-- ─── 뉴스 필터 인덱스

CREATE INDEX IF NOT EXISTS idx_news_display_pub_date
    ON gold_news.dim_news_display (pub_date DESC);

CREATE INDEX IF NOT EXISTS idx_news_display_keyword
    ON gold_news.dim_news_display (stock_keyword, pub_date DESC);

CREATE INDEX IF NOT EXISTS idx_sentiment_daily_pk
    ON gold_news.agg_market_sentiment_daily (base_date DESC, stock_code);


-- ─── JSONB 인덱스 (Power BI 키 검색)

CREATE INDEX IF NOT EXISTS idx_sentiment_keywords_gin
    ON gold_news.agg_market_sentiment_daily USING gin (daily_keywords);

CREATE INDEX IF NOT EXISTS idx_feature_keyword_momentum_gin
    ON gold_news.fact_feature_vector_store USING gin (keyword_momentum);


-- ─── ML / 앙상블 예측 조회

CREATE INDEX IF NOT EXISTS idx_ensemble_ticker_base
    ON public.fact_ensemble_forecast (ticker, base_date DESC);

CREATE INDEX IF NOT EXISTS idx_stat_forecast_ticker_base
    ON public.fact_stat_forecast (ticker, base_date DESC);


-- =============================================================================
-- § 2. 뷰 (Views)
-- =============================================================================

-- ─── V1: 최신 앙상블 예측 (Web App 메인 대시보드)
-- 티커별 가장 최신 base_date 기준 30일 예측 조회
CREATE OR REPLACE VIEW public.v_forecast_latest AS
SELECT DISTINCT ON (ticker, horizon_day)
    ticker,
    base_date::DATE         AS base_date,
    date::DATE              AS forecast_date,
    horizon_day,
    final_pred,
    pi_lower,
    pi_upper,
    confidence_score,
    regime_label,
    run_timestamp
FROM public.fact_ensemble_forecast
ORDER BY ticker, horizon_day, base_date DESC;

COMMENT ON VIEW public.v_forecast_latest IS
    'Web App 메인: 티커별 최신 base_date 기준 앙상블 예측';


-- ─── V2: 일간 리포트 통합 (Power BI 1-pager)
-- samsung·skhynix 뉴스 감성 + 매크로 + 예측을 하나의 행으로
CREATE OR REPLACE VIEW public.v_daily_report_summary AS
WITH latest_forecast AS (
    SELECT ticker, base_date::DATE AS base_date,
           final_pred, confidence_score, regime_label
    FROM public.v_forecast_latest
    WHERE horizon_day = 5
),
sentiment AS (
    SELECT base_date, stock_code,
           avg_sentiment, news_vol
    FROM gold_news.agg_market_sentiment_daily
),
macro_latest AS (
    SELECT trade_date,
           usd_krw_rate, fred_dgs10, fred_t10y2y,
           fred_bamlh0a0hym2, stagnation_pressure
    FROM gold_macro.fact_yf_fx_fred_1y
)
SELECT
    lf.base_date,
    lf.ticker,
    lf.final_pred,
    lf.confidence_score,
    lf.regime_label,
    s.avg_sentiment,
    s.news_vol,
    m.usd_krw_rate,
    m.fred_dgs10,
    m.fred_t10y2y,
    m.fred_bamlh0a0hym2,
    m.stagnation_pressure
FROM latest_forecast lf
LEFT JOIN sentiment       s ON lf.base_date = s.base_date
    AND (
        (lf.ticker = '005930.KS' AND s.stock_code = 'SAMSUNG') OR
        (lf.ticker = '000660.KS' AND s.stock_code = 'SKHYNIX')
    )
LEFT JOIN macro_latest    m ON lf.base_date = m.trade_date;

COMMENT ON VIEW public.v_daily_report_summary IS
    'Power BI 일간 리포트: 예측 + 감성 + 매크로 통합';


-- ─── V3: 뉴스 감성 추이 (Power BI 라인 차트)
CREATE OR REPLACE VIEW gold_news.v_news_sentiment_trend AS
SELECT
    base_date,
    stock_code,
    avg_sentiment,
    news_vol,
    main_aspect,
    AVG(avg_sentiment) OVER (
        PARTITION BY stock_code
        ORDER BY base_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                               AS sentiment_ma7
FROM gold_news.agg_market_sentiment_daily
ORDER BY base_date DESC, stock_code;

COMMENT ON VIEW gold_news.v_news_sentiment_trend IS
    'Power BI: 일별 감성 + 7일 이동평균';


-- ─── V4: 매크로 최신 스냅샷 (Power BI 게이지/카드)
CREATE OR REPLACE VIEW gold_macro.v_macro_latest AS
SELECT
    trade_date,
    usd_krw_rate,
    fred_dgs10,
    fred_dgs2,
    fred_t10y2y,
    fred_dff,
    fred_bamlh0a0hym2,
    stagnation_pressure,
    risk_off_flag
FROM gold_macro.fact_yf_fx_fred_1y
ORDER BY trade_date DESC
LIMIT 1;

COMMENT ON VIEW gold_macro.v_macro_latest IS
    'Power BI 카드: 최신 매크로 스냅샷 (1행)';


-- ─── V5: 퀀트 통합 신호 (Power BI 신호등 패널)
CREATE OR REPLACE VIEW gold_ml.v_quant_daily_signals AS
SELECT
    sox.us_trade_date               AS signal_date,
    sox.sox_return_1d,
    sox.spillover_flag              AS sox_downside_flag,
    sox.upside_surge_flag           AS sox_upside_flag,
    mem.memory_sentiment_index,
    mem.memory_trend_flag,
    pcr.pcr_ratio,
    pcr.pcr_ma5,
    pcr.fear_greed_idx,
    pcr.is_downside_warning         AS pcr_warning_flag,
    pcr.pcr_bullish_flag
FROM gold_ml.fact_quant_sox_sync  sox
LEFT JOIN gold_ml.fact_quant_memory_proxy  mem
       ON sox.kr_effective_date = mem.trade_date
LEFT JOIN gold_ml.gold_quant_pcr_signals   pcr
       ON sox.kr_effective_date = pcr.trade_date
ORDER BY sox.us_trade_date DESC;

COMMENT ON VIEW gold_ml.v_quant_daily_signals IS
    'Power BI 신호등: SOX 동조 + 메모리 감성 + PCR 퀀트 신호 통합';


-- ─── V6: 최신 예측 비교 (Web App — 통계 vs 앙상블)
CREATE OR REPLACE VIEW public.v_model_comparison_latest AS
WITH ens AS (
    SELECT ticker, horizon_day AS horizon, final_pred AS ensemble_pred,
           confidence_score, regime_label, base_date::DATE AS base_date
    FROM public.v_forecast_latest
),
stat AS (
    SELECT ticker, horizon, model,
           prediction AS stat_pred,
           change_pct,
           base_date::DATE AS base_date
    FROM public.fact_stat_forecast sf1
    WHERE run_timestamp = (
        SELECT MAX(run_timestamp) FROM public.fact_stat_forecast sf2
        WHERE sf1.ticker = sf2.ticker
    )
)
SELECT
    e.ticker,
    e.base_date,
    e.horizon,
    e.ensemble_pred,
    e.confidence_score,
    e.regime_label,
    s.model,
    s.stat_pred,
    s.change_pct,
    e.ensemble_pred - s.stat_pred   AS model_gap
FROM ens e
LEFT JOIN stat s ON e.ticker = s.ticker
    AND e.horizon = s.horizon
    AND e.base_date = s.base_date;

COMMENT ON VIEW public.v_model_comparison_latest IS
    'Web App: 앙상블 vs 통계 기준선 예측 비교 (horizon별)';
