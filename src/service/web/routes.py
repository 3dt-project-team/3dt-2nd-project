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
<<<<<<< HEAD
=======
from src.service.app import handle_chat_request_payload
>>>>>>> origin/dev
from src.utils.database import SessionLocal

from . import web_bp


<<<<<<< HEAD
# ----------------------------------------------------------------
# [공통] 비로그인 사용자 식별을 위한 세션 ID 발급
# ----------------------------------------------------------------
@web_bp.before_request
def ensure_session_id():
    """사용자가 접속할 때 세션 ID가 없으면 고유한 UUID를 발급하여 세션에 저장합니다."""
    if "user_sid" not in session:
        session["user_sid"] = str(uuid.uuid4())
=======
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
        return "<script>alert('ADMIN_PASSWORD is not configured.'); history.back();</script>"

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
>>>>>>> origin/dev


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
<<<<<<< HEAD
        # 1. 반도체 분석 데이터 조회 (기존 데이터)
=======
>>>>>>> origin/dev
        latest_news = db.query(NewsDisplay).order_by(NewsDisplay.pub_date.desc()).limit(5).all()
        forecast = db.query(EnsembleForecast).order_by(EnsembleForecast.date.desc()).first()
        sentiment = db.query(MarketSentiment).order_by(MarketSentiment.base_date.desc()).first()
        posts = db.query(CommunityPost).order_by(CommunityPost.created_at.desc()).all()

<<<<<<< HEAD
        # 2. 커뮤니티 게시글 최신순 조회
        # 대댓글이 메인 피드에 따로 뜨지 않도록 parent_id가 없는(None) 글들만 가져옵니다.
        # 각 글의 대댓글은 모델의 relationship을 통해 HTML 템플릿에서 post.replies로 접근합니다.
        posts = (
            db.query(CommunityPost)
            .filter(CommunityPost.parent_id.is_(None))
            .order_by(CommunityPost.created_at.desc())
            .all()
        )

        # 3. HTML 템플릿 렌더링
=======
>>>>>>> origin/dev
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


<<<<<<< HEAD
# ----------------------------------------------------------------
# [작성] 새로운 커뮤니티 게시글 및 대댓글 등록
# ----------------------------------------------------------------
=======
>>>>>>> origin/dev
@web_bp.route("/post/new", methods=["POST"])
def create_post():
    db = SessionLocal()
    try:
        content = request.form.get("content")
<<<<<<< HEAD
        parent_id = request.form.get("parent_id")  # HTML 폼에서 전달된 부모 ID

        if content and content.strip():
            new_post = CommunityPost(
                session_id=session["user_sid"],
                content=content.strip(),
                parent_id=parent_id if parent_id else None,  # 대댓글인 경우 부모 ID를 매핑
            )
            db.add(new_post)
            db.commit()
        return redirect(url_for("web.index"))
    except Exception as e:
        print(f"게시글 작성 중 오류 발생: {e}")
=======
        if content and content.strip():
            new_post = CommunityPost(session_id=session["user_sid"], content=content.strip())
            db.add(new_post)
            db.commit()
        return redirect(url_for("web.index"))
    except Exception as exc:  # noqa: BLE001
        print(f"게시글 작성 중 오류 발생: {exc}")
>>>>>>> origin/dev
        db.rollback()
        return redirect(url_for("web.index"))
    finally:
        db.close()


<<<<<<< HEAD
# ----------------------------------------------------------------
# [삭제] 게시글 삭제 (본인 확인 및 관리자 우회 로직 포함)
# ----------------------------------------------------------------
=======
>>>>>>> origin/dev
@web_bp.route("/post/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    db = SessionLocal()
    try:
        post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()

<<<<<<< HEAD
        # 권한 체크: (작성자 본인 세션과 일치) OR (관리자 로그인 상태)
=======
>>>>>>> origin/dev
        is_owner = post and post.session_id == session.get("user_sid")
        is_admin = session.get("is_admin", False)

        if post and (is_owner or is_admin):
            db.delete(post)
            db.commit()
            return jsonify({"success": True})

        return jsonify({"success": False, "message": "삭제 권한이 없습니다."}), 403
<<<<<<< HEAD
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
=======
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500
>>>>>>> origin/dev
    finally:
        db.close()


<<<<<<< HEAD
# ----------------------------------------------------------------
# [반응] 좋아요/싫어요 처리 (비동기 API)
# ----------------------------------------------------------------
@web_bp.route("/post/<int:post_id>/<action>", methods=["POST"])
def react_post(post_id, action):
    if action not in ["like", "dislike"]:
        return jsonify({"error": "잘못된 접근입니다."}), 400
=======
@web_bp.route("/post/<int:post_id>/<action>", methods=["POST"])
def react_post(post_id, action):
    if action not in ["like", "dislike"]:
        return jsonify({"error": "잘못된 요청입니다."}), 400
>>>>>>> origin/dev

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
<<<<<<< HEAD
                post_id=post_id, session_id=user_sid, reaction_type=action
=======
                post_id=post_id,
                session_id=user_sid,
                reaction_type=action,
>>>>>>> origin/dev
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
<<<<<<< HEAD
                CommunityReaction.post_id == post_id, CommunityReaction.reaction_type == "dislike"
=======
                CommunityReaction.post_id == post_id,
                CommunityReaction.reaction_type == "dislike",
>>>>>>> origin/dev
            )
            .count()
        )

        return jsonify({"success": True, "likes": likes_count, "dislikes": dislikes_count})

<<<<<<< HEAD
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
=======
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return jsonify({"error": str(exc)}), 500
>>>>>>> origin/dev
    finally:
        db.close()


<<<<<<< HEAD
# ----------------------------------------------------------------
# [디버그] DB 테이블 상태 확인
# ----------------------------------------------------------------
=======
>>>>>>> origin/dev
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
<<<<<<< HEAD
    except Exception as e:
        return f"에러 발생: {str(e)}"
=======
    except Exception as exc:  # noqa: BLE001
        return f"에러 발생: {str(exc)}"
>>>>>>> origin/dev
    finally:
        db.close()
