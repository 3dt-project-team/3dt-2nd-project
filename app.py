import os

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from src.service.web import web_bp

load_dotenv()


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app():
    app = Flask(__name__)
    is_app_service = bool(os.getenv("WEBSITE_SITE_NAME"))

    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-key")
    app.config["SESSION_COOKIE_SECURE"] = _get_bool_env("SESSION_COOKIE_SECURE", is_app_service)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["PREFERRED_URL_SCHEME"] = os.getenv(
        "PREFERRED_URL_SCHEME",
        "https" if is_app_service else "http",
    )

    # App Service forwards the original protocol and host via proxy headers.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.register_blueprint(web_bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=_get_bool_env("FLASK_DEBUG", False),
    )
