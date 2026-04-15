from flask import Blueprint

# Blueprint 생성
web_bp = Blueprint("web", __name__, template_folder="templates", static_folder="static")

# noqa 뒤에 : 를 붙여야 ruff가 인식합니다.
from . import routes as routes  # noqa: E402, F401
