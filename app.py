import os

from dotenv import load_dotenv
from flask import Flask

from src.service.web import web_bp

# .env 파일의 환경 변수를 불러옵니다.
load_dotenv()


def create_app():
    app = Flask(__name__)

    # 세션이나 보안을 위한 시크릿 키 설정 (키볼트에서 가져오도록 수정 가능)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-key")

    # 설계한 web 서비스를 Flask 앱에 등록합니다.
    app.register_blueprint(web_bp)

    return app


# _name_ (X) -> __name__ (O) 언더바가 앞뒤로 2개입니다!
if __name__ == "__main__":
    app = create_app()
    print("서버를 시작합니다...")  # 확인을 위한 출력문 추가
    app.run(host="0.0.0.0", port=5000, debug=True)
