from types import SimpleNamespace

from src.service.rag.retriever import (
    QueryFilters,
    get_latest_forecast,
    get_sentiment_snapshot,
    search_hybrid_news,
)


def test_search_hybrid_news_casts_optional_filters_for_psycopg3(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_query(query, params):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr("src.service.rag.retriever.run_query", fake_run_query)
    monkeypatch.setattr(
        "src.service.rag.retriever.get_settings",
        lambda: SimpleNamespace(rerank_pool_multiplier=4),
    )

    filters = QueryFilters(
        stock_keyword=None,
        sentiment_class=None,
        category=None,
        news_limit=3,
    )

    search_hybrid_news([0.1, 0.2], filters)

    query = captured["query"]
    params = captured["params"]

    assert "%s::text IS NULL OR UPPER(d.stock_keyword) LIKE" in query
    assert "UPPER(%s::text)" in query
    assert "%s::text IS NULL OR d.sentiment_class = %s::text" in query
    assert "%s::text IS NULL OR d.category LIKE '%%' || %s::text || '%%'" in query
    assert params[0] == "[0.10000000,0.20000000]"
    assert params[-2] == 12
    assert params[-1] == 3


def test_get_sentiment_snapshot_casts_optional_stock_code(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_query(query, params):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr("src.service.rag.retriever.run_query", fake_run_query)

    get_sentiment_snapshot(None)

    assert "%s::text IS NULL OR UPPER(stock_code) LIKE" in captured["query"]
    assert "UPPER(%s::text)" in captured["query"]
    assert captured["params"] == (None, None)


def test_get_latest_forecast_casts_optional_ticker(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_query(query, params):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr("src.service.rag.retriever.run_query", fake_run_query)

    get_latest_forecast(None, 5)

    assert "WHERE (%s::text IS NULL OR ticker = %s::text)" in captured["query"]
    assert captured["params"] == (None, None, 5)
