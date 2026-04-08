# Google News Crawler — Azure Container Instance 배포용
#
# Base: Playwright 공식 이미지 (Chromium 내장)
# 빌드 (리포지토리 루트에서 실행):
#   az acr build --registry sense3dtacr \
#     --image google-news-crawler:latest \
#     --file apps/google-news-crawler/Dockerfile .
#
# ACI one-shot 실행 예시:
#   az container create \
#     --resource-group 3dt-2nd-team1 \
#     --name sense-news-crawler \
#     --image sense3dtacr.azurecr.io/google-news-crawler:latest \
#     --registry-login-server sense3dtacr.azurecr.io \
#     --registry-username <acr-admin-user> \
#     --registry-password <acr-admin-password> \
#     --assign-identity \
#     --environment-variables \
#         KEY_VAULT_URL=https://kv-3dt-team1.vault.azure.net/ \
#         KEYWORDS="SK Hynix,Samsung Electronics" \
#         DATE_START=2025-04-01 \
#     --restart-policy Never \
#     --location koreacentral
#
# ※ 실행 후 ACI MI에 아래 권한 부여 필요:
#   - Key Vault Secrets User  (kv-3dt-team1)
#   - Storage Blob Data Contributor  (3dtteam1adls)
#
# 필수 환경변수 (ACI 실행 시 --environment-variables 또는 --secure-environment-variables로 주입):
#   KEY_VAULT_URL   : https://<vault-name>.vault.azure.net/
#   KEYWORDS        : 콤마 구분 키워드  (기본: "SK Hynix,Samsung Electronics")
#   DATE_START      : YYYY-MM-DD          (기본: "2025-04-01")
#   DATE_END        : YYYY-MM-DD          (기본: 오늘)

FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# requirements 먼저 복사 → 코드 변경 시 레이어 캐시 재사용
COPY apps/google-news-crawler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 크롤러 소스 복사 (google_news_crawler/ 내 모든 파일)
COPY src/ingestion/google_news_crawler/ /app/

# vault_manager를 /app/ 에 flat 복사 → "from vault_manager import ..." 로 직접 import
COPY src/utils/vault_manager.py /app/vault_manager.py

CMD ["python", "main.py"]
