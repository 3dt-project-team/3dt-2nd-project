FROM python:3.10-slim

# uv 바이너리 복사 — pip 대신 초고속 패키지 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# 의존성 파일 먼저 복사 (Docker 레이어 캐시 최대한 활용)
COPY pyproject.toml .
RUN uv pip install --system \
    azure-identity \
    azure-keyvault-secrets \
    azure-storage-file-datalake \
    pyodbc \
    sqlalchemy \
    python-dotenv

# 소스 코드 복사
COPY src/ ./src/
COPY adf/custom_activity/main.py .

CMD ["python", "main.py"]
