# 빌드 컨텍스트: 저장소 루트에서 실행해야 합니다.
#   docker build -f adf/custom_activity/Dockerfile -t 3dt-custom-activity .
# ACR 푸시:
#   az acr build --registry <acr-name> --image 3dt-custom-activity:latest \
#     --file adf/custom_activity/Dockerfile .

FROM python:3.11-slim

# ── uv 설치 ─────────────────────────────────────────────────────────────────
# ghcr.io 공식 이미지에서 uv/uvx 바이너리를 직접 복사.
# curl·pip 없이 uv를 사용할 수 있는 가장 빠르고 가벼운 방법.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# ── 1단계: 의존성 설치 (Docker 레이어 캐시 활용) ─────────────────────────────
# pyproject.toml과 lockfile만 먼저 복사.
# 소스 코드가 변경되어도 이 파일들이 바뀌지 않으면 이 레이어는 재실행되지 않음.
COPY pyproject.toml uv.lock* ./

# uv sync로 pyproject.toml의 전체 의존성(dev 포함) 설치.
# CI/CD 및 테스트 일관성을 위해 개발 도구도 이미지에 포함.
# --no-install-project: 소스 없이 의존성만 먼저 설치해 레이어 캐시 활용.
RUN uv sync --no-install-project

# ── 2단계: 소스 코드 복사 ──────────────────────────────────────────────────
# 소스 변경 시 이 레이어부터 재빌드됨 (의존성 레이어는 캐시 유지).
COPY src/ ./src/
COPY adf/custom_activity/main.py .

# uv sync가 생성한 .venv의 Python으로 실행
CMD [".venv/bin/python", "main.py"]
