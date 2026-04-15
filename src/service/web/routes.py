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
from src.utils.database import SessionLocal

from . import web_bp


# ----------------------------------------------------------------
# [공통] 비로그인 사용자 식별을 위한 세션 ID 발급
# ----------------------------------------------------------------
@web_bp.before_request
def ensure_session_id():
    """사용자가 접속할 때 세션 ID가 없으면 고유한 UUID를 발급하여 세션에 저장합니다."""
    if "user_sid" not in session:
        session["user_sid"] = str(uuid.uuid4())


# ----------------------------------------------------------------
# [관리자] 로그인 및 로그아웃 로직
# ----------------------------------------------------------------
@web_bp.route("/admin/login", methods=["POST"])
def admin_login():
    """비밀번호를 확인하여 관리자 세션을 부여합니다."""
    password = request.form.get("password")
    # .env 파일에 ADMIN_PASSWORD를 설정하세요. 없으면 기본값 admin1234를 사용합니다.
    admin_pw = os.getenv("ADMIN_PASSWORD", "admin1234")

    if password == admin_pw:
        session["is_admin"] = True
        return redirect(url_for("web.index"))

    return "<script>alert('비밀번호가 틀렸습니다.'); history.back();</script>"


@web_bp.route("/admin/logout")
def admin_logout():
    """관리자 세션을 제거합니다."""
    session.pop("is_admin", None)
    return redirect(url_for("web.index"))


# ----------------------------------------------------------------
# [조회] 메인 페이지 (분석 결과 + 게시글 목록)
# ----------------------------------------------------------------
@web_bp.route("/")
def index():
    db = SessionLocal()
    try:
        # 1. 반도체 분석 데이터 조회 (기존 데이터)
        latest_news = db.query(NewsDisplay).order_by(NewsDisplay.pub_date.desc()).limit(5).all()
        forecast = db.query(EnsembleForecast).order_by(EnsembleForecast.date.desc()).first()
        sentiment = db.query(MarketSentiment).order_by(MarketSentiment.base_date.desc()).first()

        # 2. 커뮤니티 게시글 최신순 조회
        posts = db.query(CommunityPost).order_by(CommunityPost.created_at.desc()).all()

        # 3. HTML 템플릿 렌더링
        # is_admin 정보를 넘겨줘야 HTML에서 관리자 전용 UI를 표시할 수 있습니다.
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


# ----------------------------------------------------------------
# [작성] 새로운 커뮤니티 게시글 등록
# ----------------------------------------------------------------
@web_bp.route("/post/new", methods=["POST"])
def create_post():
    db = SessionLocal()
    try:
        content = request.form.get("content")
        if content and content.strip():
            new_post = CommunityPost(session_id=session["user_sid"], content=content.strip())
            db.add(new_post)
            db.commit()
        return redirect(url_for("web.index"))
    except Exception as e:
        print(f"게시글 작성 중 오류 발생: {e}")
        db.rollback()
        return redirect(url_for("web.index"))
    finally:
        db.close()


# ----------------------------------------------------------------
# [삭제] 게시글 삭제 (본인 확인 및 관리자 우회 로직 포함)
# ----------------------------------------------------------------
@web_bp.route("/post/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    db = SessionLocal()
    try:
        post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()

        # 권한 체크: (작성자 본인 세션과 일치) OR (관리자 로그인 상태)
        is_owner = post and post.session_id == session.get("user_sid")
        is_admin = session.get("is_admin", False)

        if post and (is_owner or is_admin):
            db.delete(post)
            db.commit()
            return jsonify({"success": True})

        return jsonify({"success": False, "message": "삭제 권한이 없습니다."}), 403
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# ----------------------------------------------------------------
# [반응] 좋아요/싫어요 처리 (비동기 API)
# ----------------------------------------------------------------
@web_bp.route("/post/<int:post_id>/<action>", methods=["POST"])
def react_post(post_id, action):
    if action not in ["like", "dislike"]:
        return jsonify({"error": "잘못된 접근입니다."}), 400

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
                post_id=post_id, session_id=user_sid, reaction_type=action
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
                CommunityReaction.post_id == post_id, CommunityReaction.reaction_type == "dislike"
            )
            .count()
        )

        return jsonify({"success": True, "likes": likes_count, "dislikes": dislikes_count})

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ----------------------------------------------------------------
# [디버그] DB 테이블 상태 확인
# ----------------------------------------------------------------
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
    except Exception as e:
        return f"에러 발생: {str(e)}"
    finally:
        db.close()
