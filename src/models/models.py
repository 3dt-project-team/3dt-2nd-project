from sqlalchemy import Column, Date, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


# 1. 뉴스 서빙용 (gold_news.dim_news_display)
class NewsDisplay(Base):
    __tablename__ = "dim_news_display"
    __table_args__ = {"schema": "gold_news"}
    news_id = Column(UUID(as_uuid=True), primary_key=True)
    display_title = Column(Text)
    core_summary = Column(Text)
    sentiment_class = Column(String(10))
    pub_date = Column(Date)
    original_url = Column(Text)


# 2. 시장 감성 집계 (gold_news.agg_market_sentiment_daily)
class MarketSentiment(Base):
    __tablename__ = "agg_market_sentiment_daily"
    __table_args__ = {"schema": "gold_news"}
    base_date = Column(Date, primary_key=True)
    stock_code = Column(Text, primary_key=True)
    avg_sentiment = Column(Float)
    daily_keywords = Column(JSONB)  # TOP 10 키워드 포함


# 3. 앙상블 예측 결과 (public.fact_ensemble_forecast)
class EnsembleForecast(Base):
    __tablename__ = "fact_ensemble_forecast"
    date = Column(DateTime, primary_key=True)
    ticker = Column(Text, primary_key=True)
    final_pred = Column(Float)
    confidence_score = Column(Float)
    regime_label = Column(Text)
