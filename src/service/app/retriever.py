from __future__ import annotations

from typing import Any

from .config import get_settings
from .db import run_query, run_query_with_fallbacks
from .schemas import QueryFilters, QueryRoute, RetrievalBundle


def get_recent_news(filters: QueryFilters) -> list[dict[str, Any]]:
    query = """
    SELECT
        d.news_id,
        d.display_title,
        d.core_summary,
        d.sentiment_class,
        d.category,
        d.press,
        d.original_url,
        d.stock_keyword,
        d.pub_date,
        d.is_surge,
        f.search_context,
        f.feature_score,
        f.aspect_tag,
        f.keyword_momentum
    FROM gold_news.dim_news_display d
    LEFT JOIN gold_news.fact_feature_vector_store f
      ON d.news_id = f.news_id
    WHERE (%s IS NULL OR UPPER(d.stock_keyword) LIKE '%%' || UPPER(%s) || '%%')
      AND (%s IS NULL OR d.sentiment_class = %s)
      AND (%s IS NULL OR d.category LIKE '%%' || %s || '%%')
    ORDER BY d.pub_date DESC
    LIMIT %s;
    """
    return run_query(
        query,
        (
            filters.stock_keyword,
            filters.stock_keyword,
            filters.sentiment_class,
            filters.sentiment_class,
            filters.category,
            filters.category,
            filters.news_limit,
        ),
    )


def search_hybrid_news(
    question_embedding: list[float], filters: QueryFilters
) -> list[dict[str, Any]]:
    settings = get_settings()
    vector_str = "[" + ",".join(f"{value:.8f}" for value in question_embedding) + "]"
    candidate_limit = filters.news_limit * settings.rerank_pool_multiplier

    query = """
    WITH candidates AS (
        SELECT
            d.news_id,
            d.display_title,
            d.core_summary,
            d.sentiment_class,
            d.category,
            d.press,
            d.original_url,
            d.stock_keyword,
            d.pub_date,
            d.is_surge,
            f.search_context,
            f.feature_score,
            f.aspect_tag,
            f.keyword_momentum,
            f.summary_vec <=> %s::vector AS vector_distance,
            CASE
                WHEN d.pub_date >= CURRENT_DATE - INTERVAL '7 days' THEN 1.0
                WHEN d.pub_date >= CURRENT_DATE - INTERVAL '30 days' THEN 0.7
                ELSE 0.4
            END AS recency_score,
            CASE WHEN d.is_surge THEN 1.0 ELSE 0.0 END AS surge_score,
            CASE
                WHEN f.feature_score IS NULL THEN 0.0
                WHEN f.feature_score < 0 THEN 0.0
                WHEN f.feature_score > 1 THEN 1.0
                ELSE f.feature_score
            END AS feature_score_norm
        FROM gold_news.fact_feature_vector_store f
        JOIN gold_news.dim_news_display d
          ON d.news_id = f.news_id
        WHERE (%s IS NULL OR UPPER(d.stock_keyword) LIKE '%%' || UPPER(%s) || '%%')
          AND (%s IS NULL OR d.sentiment_class = %s)
          AND (%s IS NULL OR d.category LIKE '%%' || %s || '%%')
        ORDER BY f.summary_vec <=> %s::vector
        LIMIT %s
    )
    SELECT
        *,
        GREATEST(0.0, 1 - vector_distance) AS vector_score,
        ROUND(
            (
                GREATEST(0.0, 1 - vector_distance) * 0.60
                + feature_score_norm * 0.25
                + recency_score * 0.10
                + surge_score * 0.05
            )::numeric,
            4
        ) AS hybrid_score
    FROM candidates
    ORDER BY hybrid_score DESC, pub_date DESC
    LIMIT %s;
    """

    return run_query(
        query,
        (
            vector_str,
            filters.stock_keyword,
            filters.stock_keyword,
            filters.sentiment_class,
            filters.sentiment_class,
            filters.category,
            filters.category,
            vector_str,
            candidate_limit,
            filters.news_limit,
        ),
    )


def get_sentiment_snapshot(stock_code: str | None) -> list[dict[str, Any]]:
    query = """
    SELECT
        base_date,
        stock_code,
        avg_sentiment,
        news_vol,
        main_aspect,
        daily_keywords
    FROM gold_news.agg_market_sentiment_daily
    WHERE (%s IS NULL OR UPPER(stock_code) LIKE '%%' || UPPER(%s) || '%%')
    ORDER BY base_date DESC
    LIMIT 1;
    """
    return run_query(query, (stock_code, stock_code))


def get_sentiment_trend(stock_code: str | None, limit_days: int) -> list[dict[str, Any]]:
    query = """
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
        ) AS sentiment_ma7,
        daily_keywords
    FROM gold_news.agg_market_sentiment_daily
    WHERE (%s IS NULL OR UPPER(stock_code) LIKE '%%' || UPPER(%s) || '%%')
    ORDER BY base_date DESC
    LIMIT %s;
    """
    return run_query(query, (stock_code, stock_code, limit_days))


def get_macro_snapshot() -> list[dict[str, Any]]:
    query = """
    SELECT
        standard_date AS trade_date,
        usd_krw_rate,
        fred_dgs10,
        fred_dgs2,
        fred_t10y2y,
        fred_dff,
        fred_bamlh0a0hym2,
        NULL::FLOAT AS stagnation_pressure,
        NULL::INTEGER AS risk_off_flag,
        yfinance_sox_close,
        yfinance_nvda_close,
        yfinance_mu_close
    FROM gold_macro.fact_yf_fx_fred_1y
    ORDER BY standard_date DESC
    LIMIT 1;
    """
    return run_query(query)


def get_macro_trend(limit_days: int) -> list[dict[str, Any]]:
    query = """
    SELECT
        standard_date AS trade_date,
        usd_krw_rate,
        fred_dgs10,
        fred_t10y2y,
        fred_bamlh0a0hym2,
        NULL::FLOAT AS usd_krw_pct,
        NULL::FLOAT AS stagnation_pressure,
        NULL::INTEGER AS risk_off_flag
    FROM gold_macro.fact_yf_fx_fred_1y
    ORDER BY standard_date DESC
    LIMIT %s;
    """
    return run_query(query, (limit_days,))


def get_ml_feature_snapshot() -> list[dict[str, Any]]:
    return run_query_with_fallbacks(
        [
            (
                """
                SELECT
                    base_date AS trade_date,
                    NULL::FLOAT AS samsung_close,
                    NULL::FLOAT AS skhynix_close,
                    usd_krw_rate,
                    us_10y_yield AS fred_dgs10,
                    NULL::FLOAT AS fred_t10y2y,
                    NULL::FLOAT AS sox_return_1d,
                    NULL::FLOAT AS memory_sentiment_index,
                    semi_export_yoy,
                    pcr_val,
                    avg_absa_score,
                    target_return_5d,
                    CASE WHEN target_return_5d < 0 THEN TRUE ELSE FALSE END AS downside_flag,
                    CASE WHEN target_return_5d > 0 THEN TRUE ELSE FALSE END AS upside_flag,
                    regime_label
                FROM gold_ml.gold_ml_feature_set
                ORDER BY base_date DESC
                LIMIT 1;
                """,
                (),
            ),
        ]
    )


def get_latest_forecast(ticker: str | None, horizon_day: int) -> list[dict[str, Any]]:
    query = """
    SELECT DISTINCT ON (ticker, horizon_day)
        ticker,
        base_date::DATE AS base_date,
        date::DATE AS forecast_date,
        horizon_day,
        final_pred,
        pi_lower,
        pi_upper,
        confidence_score,
        regime_label,
        run_timestamp
    FROM public.fact_ensemble_forecast
    WHERE (%s IS NULL OR ticker = %s)
      AND horizon_day = %s
    ORDER BY ticker, horizon_day, base_date DESC
    LIMIT 3;
    """
    return run_query(query, (ticker, ticker, horizon_day))


def get_model_comparison(ticker: str | None) -> list[dict[str, Any]]:
    query = """
    WITH latest_ensemble AS (
        SELECT DISTINCT ON (ticker, horizon_day)
            ticker,
            base_date::DATE AS base_date,
            horizon_day AS horizon,
            final_pred AS ensemble_pred,
            confidence_score,
            regime_label
        FROM public.fact_ensemble_forecast
        WHERE (%s IS NULL OR ticker = %s)
        ORDER BY ticker, horizon_day, base_date DESC
    ),
    latest_stat AS (
        SELECT
            ticker,
            base_date::DATE AS base_date,
            horizon,
            model,
            prediction AS stat_pred,
            change_pct,
            ROW_NUMBER() OVER (
                PARTITION BY ticker, horizon, model, base_date::DATE
                ORDER BY run_timestamp DESC
            ) AS rn
        FROM public.fact_stat_forecast
        WHERE (%s IS NULL OR ticker = %s)
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
        e.ensemble_pred - s.stat_pred AS model_gap
    FROM latest_ensemble e
    LEFT JOIN latest_stat s
      ON e.ticker = s.ticker
     AND e.base_date = s.base_date
     AND e.horizon = s.horizon
     AND s.rn = 1
    ORDER BY e.base_date DESC, e.horizon ASC
    LIMIT 6;
    """
    return run_query(query, (ticker, ticker, ticker, ticker))


def get_quant_signal_snapshot() -> list[dict[str, Any]]:
    query = """
    SELECT
        sox.us_trade_date AS signal_date,
        sox.kr_effective_date,
        sox.sox_return_1d,
        sox.spillover_flag AS sox_downside_flag,
        sox.upside_surge_flag AS sox_upside_flag,
        mem.memory_sentiment_index,
        mem.memory_trend_flag,
        pcr.pcr_ratio,
        pcr.pcr_ma5,
        pcr.fear_greed_idx,
        pcr.is_downside_warning AS pcr_warning_flag,
        pcr.pcr_bullish_flag
    FROM gold_ml.fact_quant_sox_sync sox
    LEFT JOIN gold_ml.fact_quant_memory_proxy mem
      ON sox.kr_effective_date = mem.trade_date
    LEFT JOIN gold_ml.gold_quant_pcr_signals pcr
      ON sox.kr_effective_date = pcr.trade_date
    ORDER BY sox.us_trade_date DESC
    LIMIT 1;
    """
    return run_query(query)


def build_retrieval_bundle(
    question: str,
    route: QueryRoute,
    filters: QueryFilters,
    question_embedding: list[float] | None = None,
) -> RetrievalBundle:
    settings = get_settings()

    if question_embedding:
        news_docs = search_hybrid_news(question_embedding, filters)
        retrieval_mode = "hybrid-vector"
    else:
        news_docs = get_recent_news(filters)
        retrieval_mode = "recent-fallback"

    return RetrievalBundle(
        question=question,
        route=route,
        filters=filters,
        news_docs=news_docs,
        sentiment_snapshot=get_sentiment_snapshot(filters.stock_code),
        sentiment_trend=get_sentiment_trend(filters.stock_code, filters.history_days),
        macro_snapshot=get_macro_snapshot(),
        macro_trend=get_macro_trend(filters.history_days),
        ml_feature_snapshot=get_ml_feature_snapshot(),
        forecast_rows=get_latest_forecast(filters.ticker, settings.default_horizon_day),
        quant_signal_rows=get_quant_signal_snapshot(),
        model_comparison_rows=get_model_comparison(filters.ticker),
        debug={
            "retrieval_mode": retrieval_mode,
            "question_embedding_available": bool(question_embedding),
            "data_sources": {
                "news": [
                    "gold_news.dim_news_display",
                    "gold_news.fact_feature_vector_store",
                    "gold_news.agg_market_sentiment_daily",
                ],
                "macro": ["gold_macro.fact_yf_fx_fred_1y"],
                "ml": [
                    "gold_ml.fact_quant_sox_sync",
                    "gold_ml.fact_quant_memory_proxy",
                    "gold_ml.gold_quant_pcr_signals",
                    "gold_ml.gold_ml_feature_set",
                ],
                "forecast": [
                    "public.fact_ensemble_forecast",
                    "public.fact_stat_forecast",
                ],
            },
        },
    )
