from src.service.app.router import classify_query, extract_filters
from src.service.app.schemas import QueryRoute


def test_classify_query_as_hybrid_for_risk_with_news_evidence():
    route = classify_query("SK하이닉스 하락 리스크 근거 기사 보여줘")
    assert route == QueryRoute.HYBRID


def test_classify_query_as_metric_for_macro_only_question():
    route = classify_query("반도체 업황을 SOX, 환율, PCR 기준으로 설명해줘")
    assert route == QueryRoute.METRIC


def test_extract_filters_infers_stock_and_sentiment():
    filters = extract_filters("삼성전자 호재 뉴스 요약해줘")

    assert filters.stock_keyword == "SAMSUNG"
    assert filters.stock_code == "SAMSUNG"
    assert filters.ticker == "005930.KS"
    assert filters.sentiment_class == "호재"
