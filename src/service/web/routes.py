from flask import render_template

from src.models.models import EnsembleForecast, MarketSentiment, NewsDisplay
from src.utils.database import SessionLocal

from . import web_bp

# src/service/web/routes.py


@web_bp.route("/")
def index():
    db = SessionLocal()
    try:
        # 데이터 쿼리
        latest_news = db.query(NewsDisplay).order_by(NewsDisplay.pub_date.desc()).limit(5).all()
        forecast = db.query(EnsembleForecast).order_by(EnsembleForecast.date.desc()).first()
        sentiment = db.query(MarketSentiment).order_by(MarketSentiment.base_date.desc()).first()

        # render_template의 인자값 이름을 확인하세요.
        # 'fc'라는 이름으로 'forecast' 데이터를 보낸다고 설정해야 합니다.
        return render_template(
            "index.html",
            news_list=latest_news,
            fc=forecast,  # 이 이름(fc)이 HTML의 {{ fc }}와 일치해야 합니다.
            st=sentiment,
        )
    finally:
        db.close()


@web_bp.route("/debug")
def debug_tables():
    db = SessionLocal()
    try:
        # 문자열을 여러 줄로 나누어 100자를 넘지 않게 합니다.
        query = (
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_schema LIKE 'gold%';"
        )
        result = db.execute(query)
        tables = [f"{row[0]}.{row[1]}" for row in result]
        return f"현재 접속된 DB의 골드 레이어 테이블 목록: {tables}"
    except Exception as e:
        return f"에러 발생: {str(e)}"
    finally:
        db.close()
