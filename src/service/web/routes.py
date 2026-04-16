import os
import re
import uuid

from flask import jsonify, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.models.models import (
    CommunityPost,
    CommunityReaction,
    EnsembleForecast,
    MarketSentiment,
    NewsDisplay,
)
from src.service.rag import handle_chat_request_payload
from src.utils.database import SessionLocal

from . import web_bp

TARGET_STOCKS = [
    {
        "ticker": "005930.KS",
        "name": "삼성전자",
        "news_keyword": "samsung",
        "aliases": ["005930.KS", "005930", "삼성전자", "samsung"],
        "price_unit": "원",
    },
    {
        "ticker": "000660.KS",
        "name": "SK하이닉스",
        "news_keyword": "skhynix",
        "aliases": ["000660.KS", "000660", "SK하이닉스", "하이닉스", "sk hynix", "skhynix"],
        "price_unit": "원",
    },
    {
        "ticker": "NVDA",
        "name": "엔비디아",
        "news_keyword": "nvda",
        "aliases": ["NVDA", "엔비디아", "nvidia"],
        "price_unit": "달러",
    },
    {
        "ticker": "AMD",
        "name": "AMD",
        "news_keyword": "amd",
        "aliases": ["AMD", "amd", "advanced micro devices"],
        "price_unit": "달러",
    },
    {
        "ticker": "TSM",
        "name": "TSMC",
        "news_keyword": "tsm",
        "aliases": ["TSM", "tsm", "tsmc"],
        "price_unit": "달러",
    },
    {
        "ticker": "ASML",
        "name": "ASML",
        "news_keyword": "asml",
        "aliases": ["ASML", "asml"],
        "price_unit": "달러",
    },
    {
        "ticker": "MU",
        "name": "마이크론",
        "news_keyword": "mu",
        "aliases": ["MU", "mu", "micron"],
        "price_unit": "달러",
    },
    {
        "ticker": "INTC",
        "name": "인텔",
        "news_keyword": "intc",
        "aliases": ["INTC", "intc", "intel"],
        "price_unit": "달러",
    },
    {
        "ticker": "WDC",
        "name": "웨스턴디지털",
        "news_keyword": "wdc",
        "aliases": ["WDC", "wdc", "western digital"],
        "price_unit": "달러",
    },
    {
        "ticker": "^SOX",
        "name": "필라델피아 반도체 지수",
        "news_keyword": "sox",
        "aliases": ["^SOX", "SOX", "sox", "필라델피아 반도체 지수"],
        "price_unit": "pt",
    },
]

REGIME_LABEL_KR_MAP = {
    "trend": "상승",
    "mean_rev": "횡보",
    "mean reversion": "횡보",
    "neutral": "횡보",
    "bull": "상승",
    "bear": "하락",
    "pullback": "하락",
    "breakout": "상승",
    "risk_off": "하락",
    "risk_on": "상승",
    "risk": "하락",
    "opportunity": "상승",
    "mid": "횡보",
    "high_vol": "횡보",
    "high volatility": "횡보",
    "high-vol": "횡보",
}

REGIME_RATE_FIELDS = [
    ("risk_rate", "하락"),
    ("opportunity_rate", "상승"),
    ("neutral_rate", "횡보"),
]


def _to_korean_regime_text(value: str | None) -> str:
    if not value:
        return ""

    translated = value
    for src, dest in sorted(
        REGIME_LABEL_KR_MAP.items(), key=lambda item: len(item[0]), reverse=True
    ):
        escaped = re.escape(src).replace(r"\ ", r"[\\s_\-]+")
        translated = re.sub(escaped, dest, translated, flags=re.IGNORECASE)
    return translated


def _collect_regime_rates(forecast: EnsembleForecast | None) -> list[dict]:
    if not forecast:
        return []

    rates = []
    for field_name, label_kr in REGIME_RATE_FIELDS:
        raw_value = getattr(forecast, field_name, None)
        if raw_value is None:
            continue

        rate_value = float(raw_value)
        if rate_value <= 1:
            rate_value *= 100

        rates.append({"label": label_kr, "value": rate_value})
    return rates


def find_stock_option(ticker: str) -> dict:
    for stock in TARGET_STOCKS:
        if stock["ticker"] == ticker:
            return stock
    return TARGET_STOCKS[0]


def post_matches_stock(post: CommunityPost, aliases: list[str]) -> bool:
    haystacks = [post.content or ""]
    haystacks.extend(reply.content or "" for reply in post.replies)
    combined_text = " ".join(haystacks).lower()
    return any(alias.lower() in combined_text for alias in aliases)


@web_bp.before_request
def ensure_session_id():
    """Assign a stable anonymous session id for community and chatbot usage."""
    if "user_sid" not in session:
        session["user_sid"] = str(uuid.uuid4())


@web_bp.route("/admin/login", methods=["POST"])
def admin_login():
    """Enable admin mode when the submitted password matches the configured value."""
    password = request.form.get("password")
    admin_pw = os.getenv("ADMIN_PASSWORD")

    if not admin_pw:
        return "<script>alert('ADMIN_PASSWORD가 설정되지 않았습니다.'); history.back();</script>"

    if password == admin_pw:
        session["is_admin"] = True
        return redirect(url_for("web.index"))

    return "<script>alert('비밀번호가 올바르지 않습니다.'); history.back();</script>"


@web_bp.route("/admin/logout")
def admin_logout():
    """Clear the admin session."""
    session.pop("is_admin", None)
    return redirect(url_for("web.index"))


@web_bp.route("/api/chat", methods=["POST"])
def api_chat():
    """Bridge the web chatbot UI to the existing RAG chat service."""
    body, status = handle_chat_request_payload(request.get_json(silent=True))
    return jsonify(body), status


@web_bp.route("/")
def index():
    db = SessionLocal()
    try:
        selected_ticker = request.args.get("ticker", TARGET_STOCKS[0]["ticker"])
        if selected_ticker not in {item["ticker"] for item in TARGET_STOCKS}:
            selected_ticker = TARGET_STOCKS[0]["ticker"]
        selected_stock = find_stock_option(selected_ticker)

        latest_news = db.query(NewsDisplay).order_by(NewsDisplay.pub_date.desc()).limit(5).all()
        forecast = (
            db.query(EnsembleForecast)
            .filter(EnsembleForecast.ticker == selected_ticker)
            .order_by(EnsembleForecast.date.desc())
            .first()
        )
        sentiment = db.query(MarketSentiment).order_by(MarketSentiment.base_date.desc()).first()
        root_posts = (
            db.query(CommunityPost)
            .options(selectinload(CommunityPost.replies), selectinload(CommunityPost.reactions))
            .filter(CommunityPost.parent_id.is_(None))
            .order_by(CommunityPost.created_at.desc())
            .all()
        )
        posts = [post for post in root_posts if post_matches_stock(post, selected_stock["aliases"])]
        regime_label_ko = _to_korean_regime_text(forecast.regime_label if forecast else "")
        regime_rates = _collect_regime_rates(forecast)

        return render_template(
            "index.html",
            news_list=latest_news,
            fc=forecast,
            st=sentiment,
            posts=posts,
            selected_ticker=selected_ticker,
            selected_stock=selected_stock,
            stock_options=TARGET_STOCKS,
            regime_label_ko=regime_label_ko,
            regime_rates=regime_rates,
            current_user_sid=session.get("user_sid"),
            is_admin=session.get("is_admin", False),
        )
    finally:
        db.close()


@web_bp.route("/post/new", methods=["POST"])
def create_post():
    db = SessionLocal()
    try:
        content = request.form.get("content")
        parent_id = request.form.get("parent_id")

        if content and content.strip():
            new_post = CommunityPost(
                session_id=session["user_sid"],
                content=content.strip(),
                parent_id=parent_id if parent_id else None,
            )
            db.add(new_post)
            db.commit()
        return redirect(url_for("web.index"))
    except SQLAlchemyError as exc:
        print(f"게시글 작성 중 오류 발생: {exc}")
        db.rollback()
        return redirect(url_for("web.index"))
    finally:
        db.close()


@web_bp.route("/post/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    db = SessionLocal()
    try:
        post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()

        is_owner = post and post.session_id == session.get("user_sid")
        is_admin = session.get("is_admin", False)

        if post and (is_owner or is_admin):
            db.delete(post)
            db.commit()
            return jsonify({"success": True})

        return jsonify({"success": False, "message": "삭제 권한이 없습니다."}), 403
    except SQLAlchemyError as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500
    finally:
        db.close()


@web_bp.route("/post/<int:post_id>/<action>", methods=["POST"])
def react_post(post_id, action):
    if action not in ["like", "dislike"]:
        return jsonify({"error": "잘못된 요청입니다."}), 400

    db = SessionLocal()
    user_sid = session["user_sid"]

    try:
        existing_reaction = (
            db.query(CommunityReaction)
            .filter(CommunityReaction.post_id == post_id, CommunityReaction.session_id == user_sid)
            .first()
        )

        if existing_reaction:
            if existing_reaction.reaction_type == action:
                db.delete(existing_reaction)
            else:
                existing_reaction.reaction_type = action
        else:
            new_reaction = CommunityReaction(
                post_id=post_id,
                session_id=user_sid,
                reaction_type=action,
            )
            db.add(new_reaction)

        db.commit()

        likes_count = (
            db.query(CommunityReaction)
            .filter(CommunityReaction.post_id == post_id, CommunityReaction.reaction_type == "like")
            .count()
        )
        dislikes_count = (
            db.query(CommunityReaction)
            .filter(
                CommunityReaction.post_id == post_id,
                CommunityReaction.reaction_type == "dislike",
            )
            .count()
        )

        return jsonify({"success": True, "likes": likes_count, "dislikes": dislikes_count})

    except SQLAlchemyError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        db.close()


@web_bp.route("/debug")
def debug_tables():
    db = SessionLocal()
    try:
        query = (
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_schema IN ('gold_news', 'community');"
        )
        result = db.execute(query)
        tables = [f"{row[0]}.{row[1]}" for row in result]
        return f"현재 조회 가능한 테이블 목록: {tables}"
    except SQLAlchemyError as exc:
        return f"에러 발생: {str(exc)}"
    finally:
        db.close()
