import os
import uuid

from flask import jsonify, redirect, render_template, request, session, url_for

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
        latest_news = db.query(NewsDisplay).order_by(NewsDisplay.pub_date.desc()).limit(5).all()
        forecast = db.query(EnsembleForecast).order_by(EnsembleForecast.date.desc()).first()
        sentiment = db.query(MarketSentiment).order_by(MarketSentiment.base_date.desc()).first()
        posts = (
            db.query(CommunityPost)
            .filter(CommunityPost.parent_id.is_(None))
            .order_by(CommunityPost.created_at.desc())
            .all()
        )

        return render_template(
            "index.html",
            news_list=latest_news,
            fc=forecast,
            st=sentiment,
            posts=posts,
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
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
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

    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
        return f"에러 발생: {str(exc)}"
    finally:
        db.close()
