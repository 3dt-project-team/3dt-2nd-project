from flask import Blueprint

# static_url_path를 추가하여 메인 앱의 static과 충돌을 막습니다.
web_bp = Blueprint(
    "web",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/web_static",
)

from . import routes as routes  # noqa: E402, F401
