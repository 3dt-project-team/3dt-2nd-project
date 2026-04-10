#!/bin/bash
set -e

echo "[Init] uv 설치 시작..."
# curl -LsSf https://astral.sh/uv/install.sh | sh
# source "$HOME/.cargo/env"

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
# source "$HOME/.cargo/env"
# uv pip install --system azure-identity azure-keyvault-secrets azure-storage-file-datalake

pip install --upgrade pip -q
pip install uv -q

echo "[Init] uv 설치 완료: $(uv --version)"


echo "[Init] 공통 라이브러리 설치 중..."
uv pip install --system --break-system-packages azure-identity azure-keyvault-secrets azure-storage-file-datalake python-dotenv sqlalchemy
# uv pip install --system \
#   azure-identity \
#   azure-keyvault-secrets \
#   azure-storage-file-datalake \
#   python-dotenv \
#   sqlalchemy

echo "[Init] 설치 완료"