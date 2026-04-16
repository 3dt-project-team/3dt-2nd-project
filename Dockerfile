FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 레이어를 먼저 복사해 캐시 최적화
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# src/ 패키지를 모듈로 인식하기 위해 PYTHONPATH 설정
ENV PYTHONPATH=/app

EXPOSE 8000

# JSON 배열 = shell 미경유 → app:create_app() 괄호 파싱 문제 없음
# Azure App Service 'Startup Command' 필드는 반드시 비워 두어야 한다.
# 값이 있으면 이 CMD가 무시되고 ModuleNotFoundError가 발생한다.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "--worker-tmp-dir", "/tmp", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info", "app:create_app()"]
