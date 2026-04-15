from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

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


# 4. 커뮤니티 게시글 테이블
class CommunityPost(Base):
    __tablename__ = "posts"
    __table_args__ = {"schema": "community"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False)  # 글쓴이 식별
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 좋아요/싫어요 데이터와 연결
    reactions = relationship(
        "CommunityReaction", back_populates="post", cascade="all, delete-orphan"
    )


# 5. 반응(좋아요/싫어요) 테이블
class CommunityReaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("post_id", "session_id", name="_post_session_uc"),
        {"schema": "community"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("community.posts.id"), nullable=False)
    session_id = Column(String(100), nullable=False)  # 투표자 식별
    reaction_type = Column(String(10), nullable=False)  # 'like' or 'dislike'

    post = relationship("CommunityPost", back_populates="reactions")
