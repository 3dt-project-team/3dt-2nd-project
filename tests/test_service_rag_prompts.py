from src.service.rag.prompts import build_user_prompt, render_context_snapshot
from src.service.rag.schemas import QueryFilters, QueryRoute, RetrievalBundle


def make_bundle() -> RetrievalBundle:
    return RetrievalBundle(
        question="SK하이닉스 하락 리스크 근거 기사와 매크로 신호를 요약해줘",
        route=QueryRoute.HYBRID,
        filters=QueryFilters(
            stock_keyword="skhynix",
            stock_code="SKHYNIX",
            ticker="000660.KS",
        ),
        news_docs=[
            {
                "display_title": "메모리 가격 둔화 우려",
                "core_summary": "AI 수요는 강하지만 메모리 가격은 단기 변동성이 커졌다.",
                "sentiment_class": "악재",
                "category": "company",
                "press": "Reuters",
                "stock_keyword": "skhynix",
                "pub_date": "2026-04-15",
                "aspect_tag": "memory",
                "feature_score": 0.88,
                "hybrid_score": 0.91,
                "search_context": "메모리 현물가와 수요 둔화 우려를 함께 언급했다.",
                "original_url": "https://example.com/article",
            }
        ],
        sentiment_snapshot=[
            {
                "base_date": "2026-04-15",
                "stock_code": "SKHYNIX",
                "avg_sentiment": -0.22,
                "news_vol": 18,
            }
        ],
        sentiment_trend=[
            {
                "base_date": "2026-04-15",
                "stock_code": "SKHYNIX",
                "avg_sentiment": -0.22,
                "news_vol": 18,
            }
        ],
        macro_snapshot=[
            {
                "trade_date": "2026-04-15",
                "usd_krw_rate": 1398.2,
                "fred_dgs10": 4.31,
                "risk_off_flag": 1,
            }
        ],
        macro_trend=[
            {
                "trade_date": "2026-04-15",
                "usd_krw_rate": 1398.2,
                "fred_dgs10": 4.31,
                "risk_off_flag": 1,
            }
        ],
        ml_feature_snapshot=[
            {
                "trade_date": "2026-04-15",
                "sox_return_1d": -2.3,
                "avg_absa_score": -0.22,
                "downside_flag": True,
            }
        ],
        forecast_rows=[
            {
                "ticker": "000660.KS",
                "horizon_day": 5,
                "confidence_score": 0.82,
            }
        ],
        quant_signal_rows=[
            {
                "sox_return_1d": -2.3,
                "pcr_ratio": 1.21,
                "memory_trend_flag": "bearish",
            }
        ],
        model_comparison_rows=[
            {
                "model": "ridge",
                "stat_pred": -1.2,
                "ensemble_pred": -1.8,
            }
        ],
    )


def test_build_user_prompt_contains_required_sections():
    prompt = build_user_prompt(make_bundle())

    assert "질문:" in prompt
    assert "최신 예측:" in prompt
    assert "최신 매크로 스냅샷:" in prompt
    assert "최신 ML 피처 스냅샷:" in prompt
    assert "근거 기사 후보:" in prompt
    assert "메모리 가격 둔화 우려" in prompt


def test_render_context_snapshot_surfaces_key_signals():
    snapshot = render_context_snapshot(make_bundle())

    assert "[LLM 응답 없이도 확인 가능한 컨텍스트 요약]" in snapshot
    assert "최근 예측" in snapshot
    assert "최근 매크로" in snapshot
    assert "최근 ML 피처" in snapshot
    assert "근거 기사" in snapshot
