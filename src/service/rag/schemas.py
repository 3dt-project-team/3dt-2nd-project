from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class QueryRoute(str, Enum):
    NEWS = "news"
    METRIC = "metric"
    FORECAST = "forecast"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class QueryFilters:
    stock_keyword: str | None = None
    stock_code: str | None = None
    ticker: str | None = None
    sentiment_class: str | None = None
    category: str | None = None
    news_limit: int = 6
    history_days: int = 7

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalBundle:
    question: str
    route: QueryRoute
    filters: QueryFilters
    news_docs: list[dict[str, Any]] = field(default_factory=list)
    sentiment_snapshot: list[dict[str, Any]] = field(default_factory=list)
    sentiment_trend: list[dict[str, Any]] = field(default_factory=list)
    macro_snapshot: list[dict[str, Any]] = field(default_factory=list)
    macro_trend: list[dict[str, Any]] = field(default_factory=list)
    ml_feature_snapshot: list[dict[str, Any]] = field(default_factory=list)
    forecast_rows: list[dict[str, Any]] = field(default_factory=list)
    quant_signal_rows: list[dict[str, Any]] = field(default_factory=list)
    model_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "route": self.route.value,
            "filters": self.filters.to_dict(),
            "news_docs": self.news_docs,
            "sentiment_snapshot": self.sentiment_snapshot,
            "sentiment_trend": self.sentiment_trend,
            "macro_snapshot": self.macro_snapshot,
            "macro_trend": self.macro_trend,
            "ml_feature_snapshot": self.ml_feature_snapshot,
            "forecast_rows": self.forecast_rows,
            "quant_signal_rows": self.quant_signal_rows,
            "model_comparison_rows": self.model_comparison_rows,
            "debug": self.debug,
        }
