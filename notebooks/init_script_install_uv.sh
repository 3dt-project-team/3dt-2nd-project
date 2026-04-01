#!/bin/bash
# Databricks 클러스터 Init Script — uv 설치 및 공통 라이브러리 세팅
#
# 등록 방법:
#   1. 이 파일을 DBFS에 업로드:
#      databricks fs cp notebooks/init_script_install_uv.sh dbfs:/FileStore/scripts/install_uv.sh
#   2. 클러스터 > Edit > Advanced Options > Init Scripts
#      > dbfs:/FileStore/scripts/install_uv.sh 등록

set -e

echo "[Init] uv 설치 시작..."
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.cargo/env"
echo "[Init] uv 설치 완료: $(uv --version)"

echo "[Init] 공통 라이브러리 설치 중..."
uv pip install --system \
  azure-identity \
  azure-keyvault-secrets \
  azure-storage-file-datalake \
  python-dotenv \
  sqlalchemy

echo "[Init] 설치 완료"
