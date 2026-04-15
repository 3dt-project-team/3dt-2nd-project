from __future__ import annotations

from .config import get_settings
from .schemas import QueryFilters, QueryRoute

STOCK_ALIASES = {
    "samsung": ("SAMSUNG", "SAMSUNG", "005930.KS"),
    "삼성전자": ("SAMSUNG", "SAMSUNG", "005930.KS"),
    "005930": ("SAMSUNG", "SAMSUNG", "005930.KS"),
    "005930.ks": ("SAMSUNG", "SAMSUNG", "005930.KS"),
    "sk하이닉스": ("SK HYNIX", "SK HYNIX", "000660.KS"),
    "하이닉스": ("SK HYNIX", "SK HYNIX", "000660.KS"),
    "sk hynix": ("SK HYNIX", "SK HYNIX", "000660.KS"),
    "skhynix": ("SK HYNIX", "SK HYNIX", "000660.KS"),
    "000660": ("SK HYNIX", "SK HYNIX", "000660.KS"),
    "000660.ks": ("SK HYNIX", "SK HYNIX", "000660.KS"),
}

NEWS_KEYWORDS = {
    "뉴스",
    "기사",
    "보도",
    "헤드라인",
    "이슈",
    "속보",
    "근거 기사",
    "관련 기사",
}

METRIC_KEYWORDS = {
    "매크로",
    "환율",
    "금리",
    "유가",
    "구리",
    "달러",
    "dxy",
    "sox",
    "pcr",
    "수출",
    "메모리",
    "지표",
    "신호",
}

FORECAST_KEYWORDS = {
    "예측",
    "전망",
    "리스크",
    "위험",
    "확률",
    "하락",
    "상승",
    "급락",
    "변동성",
    "시나리오",
}


def classify_query(question: str) -> QueryRoute:
    q = question.lower()
    news_hit = any(keyword in q for keyword in NEWS_KEYWORDS)
    metric_hit = any(keyword in q for keyword in METRIC_KEYWORDS)
    forecast_hit = any(keyword in q for keyword in FORECAST_KEYWORDS)

    if (forecast_hit and news_hit) or (news_hit and metric_hit) or (forecast_hit and metric_hit):
        return QueryRoute.HYBRID
    if forecast_hit:
        return QueryRoute.FORECAST
    if metric_hit:
        return QueryRoute.METRIC
    if news_hit:
        return QueryRoute.NEWS
    return QueryRoute.HYBRID


def infer_stock(question: str) -> tuple[str, str, str]:
    q = question.lower()
    for alias, target in STOCK_ALIASES.items():
        if alias in q:
            return target

    settings = get_settings()
    return (
        settings.default_stock_keyword,
        settings.default_stock_code,
        settings.default_ticker,
    )


def infer_sentiment(question: str) -> str | None:
    q = question.lower()

    positive_markers = ("호재 기사", "호재 뉴스", "긍정 기사", "긍정 뉴스", "bullish")
    negative_markers = ("악재 기사", "악재 뉴스", "부정 기사", "부정 뉴스", "bearish")
    neutral_markers = ("중립 기사", "중립 뉴스", "neutral")

    if any(marker in q for marker in positive_markers):
        return "호재"
    if any(marker in q for marker in negative_markers):
        return "악재"
    if any(marker in q for marker in neutral_markers):
        return "중립"
    return None


def infer_category(question: str) -> str | None:
    q = question.lower()

    if any(keyword in q for keyword in ("policy", "정책", "관세", "보조금", "규제")):
        return "정책"
    if any(keyword in q for keyword in ("macro", "거시", "환율", "금리")):
        return "거시경제"
    if any(keyword in q for keyword in ("실적", "earnings")):
        return "실적"
    if any(keyword in q for keyword in ("수급", "flow")):
        return "수급"
    return None


def extract_filters(question: str) -> QueryFilters:
    settings = get_settings()
    stock_keyword, stock_code, ticker = infer_stock(question)

    return QueryFilters(
        stock_keyword=stock_keyword,
        stock_code=stock_code,
        ticker=ticker,
        sentiment_class=infer_sentiment(question),
        category=infer_category(question),
        news_limit=settings.default_news_limit,
        history_days=settings.default_history_days,
    )
