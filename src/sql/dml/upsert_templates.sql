-- =============================================================================
-- SENSE — DML Upsert Templates
-- 목적: Databricks 파이프라인에서 PostgreSQL 적재 시 사용하는 UPSERT 패턴
--
-- 실행 방식: psycopg3 execute_many / SQLAlchemy Core executemany
-- 재실행 안전: ON CONFLICT DO UPDATE
-- =============================================================================

-- =============================================================================
-- § 1. public.fact_ensemble_forecast — TimesFM 앙상블 예측
--      notebooks/timesfm_inference.py 출력
-- =============================================================================
INSERT INTO public.fact_ensemble_forecast (
    date, ticker, base_date, horizon_day,
    trend_score, mean_rev_score,
    trend_pred, meanrev_pred, final_pred,
    pi_lower, pi_upper,
    confidence_score, regime_flag, regime_label,
    run_timestamp
)
VALUES (
    %(date)s, %(ticker)s, %(base_date)s, %(horizon_day)s,
    %(trend_score)s, %(mean_rev_score)s,
    %(trend_pred)s, %(meanrev_pred)s, %(final_pred)s,
    %(pi_lower)s, %(pi_upper)s,
    %(confidence_score)s, %(regime_flag)s, %(regime_label)s,
    %(run_timestamp)s
)
ON CONFLICT (ticker, base_date, horizon_day)
DO UPDATE SET
    trend_score      = EXCLUDED.trend_score,
    mean_rev_score   = EXCLUDED.mean_rev_score,
    trend_pred       = EXCLUDED.trend_pred,
    meanrev_pred     = EXCLUDED.meanrev_pred,
    final_pred       = EXCLUDED.final_pred,
    pi_lower         = EXCLUDED.pi_lower,
    pi_upper         = EXCLUDED.pi_upper,
    confidence_score = EXCLUDED.confidence_score,
    regime_flag      = EXCLUDED.regime_flag,
    regime_label     = EXCLUDED.regime_label,
    run_timestamp    = EXCLUDED.run_timestamp;


-- =============================================================================
-- § 2. public.fact_stat_forecast — Ridge/ElasticNet 통계 기준선 예측
--      notebooks/statistical_baseline_analysis.py 출력
-- =============================================================================
INSERT INTO public.fact_stat_forecast (
    ticker, base_date, horizon,
    model, model_type, prediction,
    change_pct, scenario, run_timestamp
)
VALUES (
    %(ticker)s, %(base_date)s, %(horizon)s,
    %(model)s, %(model_type)s, %(prediction)s,
    %(change_pct)s, %(scenario)s, %(run_timestamp)s
)
ON CONFLICT (ticker, base_date, horizon, model, scenario)
DO UPDATE SET
    prediction    = EXCLUDED.prediction,
    change_pct    = EXCLUDED.change_pct,
    model_type    = EXCLUDED.model_type,
    run_timestamp = EXCLUDED.run_timestamp;


-- =============================================================================
-- § 3. gold_ml.gold_ml_feature_set — ML 통합 피처셋
--      Databricks 02_curated_to_feature.py 출력
-- =============================================================================
INSERT INTO gold_ml.gold_ml_feature_set (
    base_date,
    samsung_close, skhynix_close,
    usd_krw_rate, fred_dgs10, fred_dgs2, fred_t10y2y, fred_dff, fred_bamlh0a0hym2,
    sox_return_1d, memory_sentiment_index, semi_export_yoy, avg_iv,
    avg_absa_score, news_vol,
    target_return_5d, downside_flag, upside_flag, regime_label
)
VALUES (
    %(base_date)s,
    %(samsung_close)s, %(skhynix_close)s,
    %(usd_krw_rate)s, %(fred_dgs10)s, %(fred_dgs2)s,
    %(fred_t10y2y)s, %(fred_dff)s, %(fred_bamlh0a0hym2)s,
    %(sox_return_1d)s, %(memory_sentiment_index)s,
    %(semi_export_yoy)s, %(avg_iv)s,
    %(avg_absa_score)s, %(news_vol)s,
    %(target_return_5d)s, %(downside_flag)s, %(upside_flag)s, %(regime_label)s
)
ON CONFLICT (base_date)
DO UPDATE SET
    samsung_close           = EXCLUDED.samsung_close,
    skhynix_close           = EXCLUDED.skhynix_close,
    usd_krw_rate            = EXCLUDED.usd_krw_rate,
    fred_dgs10              = EXCLUDED.fred_dgs10,
    fred_dgs2               = EXCLUDED.fred_dgs2,
    fred_t10y2y             = EXCLUDED.fred_t10y2y,
    fred_dff                = EXCLUDED.fred_dff,
    fred_bamlh0a0hym2       = EXCLUDED.fred_bamlh0a0hym2,
    sox_return_1d           = EXCLUDED.sox_return_1d,
    memory_sentiment_index  = EXCLUDED.memory_sentiment_index,
    semi_export_yoy         = EXCLUDED.semi_export_yoy,
    avg_iv                  = EXCLUDED.avg_iv,
    avg_absa_score          = EXCLUDED.avg_absa_score,
    news_vol                = EXCLUDED.news_vol,
    target_return_5d        = EXCLUDED.target_return_5d,
    downside_flag           = EXCLUDED.downside_flag,
    upside_flag             = EXCLUDED.upside_flag,
    regime_label            = EXCLUDED.regime_label;


-- =============================================================================
-- § 4. gold_news.dim_news_display + agg_market_sentiment_daily
-- =============================================================================

-- dim_news_display: news_id(UUID) 중복 시 무시
INSERT INTO gold_news.dim_news_display (
    news_id, display_title, core_summary,
    sentiment_class, category, press, original_url,
    stock_keyword, pub_date, is_surge
)
VALUES (
    %(news_id)s, %(display_title)s, %(core_summary)s,
    %(sentiment_class)s, %(category)s, %(press)s, %(original_url)s,
    %(stock_keyword)s, %(pub_date)s, %(is_surge)s
)
ON CONFLICT (news_id) DO NOTHING;


-- agg_market_sentiment_daily: 동일 날짜·종목 재집계 시 갱신
INSERT INTO gold_news.agg_market_sentiment_daily (
    base_date, stock_code,
    avg_sentiment, news_vol,
    main_aspect, daily_keywords
)
VALUES (
    %(base_date)s, %(stock_code)s,
    %(avg_sentiment)s, %(news_vol)s,
    %(main_aspect)s, %(daily_keywords)s
)
ON CONFLICT (base_date, stock_code)
DO UPDATE SET
    avg_sentiment  = EXCLUDED.avg_sentiment,
    news_vol       = EXCLUDED.news_vol,
    main_aspect    = EXCLUDED.main_aspect,
    daily_keywords = EXCLUDED.daily_keywords;


-- =============================================================================
-- § 5. gold_macro.fact_yf_fx_fred_1y — 매크로 통합 와이드 테이블
-- =============================================================================
INSERT INTO gold_macro.fact_yf_fx_fred_1y (
    trade_date,
    yfinance_samsung_close, yfinance_skhynix_close,
    yfinance_nvda_close, yfinance_amd_close, yfinance_mu_close,
    yfinance_tsm_close, yfinance_asml_close, yfinance_sox_close,
    usd_krw_rate, usd_krw_change, usd_krw_pct, risk_off_flag,
    fred_dgs10, fred_dgs2, fred_t10y2y, fred_dff, fred_dfii10,
    fred_bamlh0a0hym2, yield_spread, yield_spread_change,
    stagnation_pressure, "주말여부", "한국_휴장일_여부"
)
VALUES (
    %(trade_date)s,
    %(yfinance_samsung_close)s, %(yfinance_skhynix_close)s,
    %(yfinance_nvda_close)s, %(yfinance_amd_close)s, %(yfinance_mu_close)s,
    %(yfinance_tsm_close)s, %(yfinance_asml_close)s, %(yfinance_sox_close)s,
    %(usd_krw_rate)s, %(usd_krw_change)s, %(usd_krw_pct)s, %(risk_off_flag)s,
    %(fred_dgs10)s, %(fred_dgs2)s, %(fred_t10y2y)s, %(fred_dff)s, %(fred_dfii10)s,
    %(fred_bamlh0a0hym2)s, %(yield_spread)s, %(yield_spread_change)s,
    %(stagnation_pressure)s, %(주말여부)s, %(한국_휴장일_여부)s
)
ON CONFLICT (trade_date)
DO UPDATE SET
    yfinance_samsung_close  = EXCLUDED.yfinance_samsung_close,
    yfinance_skhynix_close  = EXCLUDED.yfinance_skhynix_close,
    yfinance_nvda_close     = EXCLUDED.yfinance_nvda_close,
    yfinance_amd_close      = EXCLUDED.yfinance_amd_close,
    yfinance_mu_close       = EXCLUDED.yfinance_mu_close,
    yfinance_tsm_close      = EXCLUDED.yfinance_tsm_close,
    yfinance_asml_close     = EXCLUDED.yfinance_asml_close,
    yfinance_sox_close      = EXCLUDED.yfinance_sox_close,
    usd_krw_rate            = EXCLUDED.usd_krw_rate,
    usd_krw_change          = EXCLUDED.usd_krw_change,
    usd_krw_pct             = EXCLUDED.usd_krw_pct,
    risk_off_flag           = EXCLUDED.risk_off_flag,
    fred_dgs10              = EXCLUDED.fred_dgs10,
    fred_dgs2               = EXCLUDED.fred_dgs2,
    fred_t10y2y             = EXCLUDED.fred_t10y2y,
    fred_dff                = EXCLUDED.fred_dff,
    fred_dfii10             = EXCLUDED.fred_dfii10,
    fred_bamlh0a0hym2       = EXCLUDED.fred_bamlh0a0hym2,
    yield_spread            = EXCLUDED.yield_spread,
    yield_spread_change     = EXCLUDED.yield_spread_change,
    stagnation_pressure     = EXCLUDED.stagnation_pressure,
    "주말여부"              = EXCLUDED."주말여부",
    "한국_휴장일_여부"      = EXCLUDED."한국_휴장일_여부";
