# Naver News Crawler — Azure Container Instance 배포용
#
# 빌드 (리포지토리 루트에서 실행):
#   az acr build --registry sense3dtacr \
#     --image naver-news-crawler:latest \
#     --file src/ingestion/naver_collectors/Dockerfile .
#
# ACI one-shot 실행 예시:
#   az container create \
#     --resource-group 3dt-2nd-team1 \
#     --name naver-news-crawler \
#     --image sense3dtacr.azurecr.io/naver-news-crawler:latest \
#     --registry-login-server sense3dtacr.azurecr.io \
#     --registry-username <acr-admin-user> \
#     --registry-password <acr-admin-password> \
#     --assign-identity \
#     --environment-variables \
#         KEY_VAULT_URL=https://kv-3dt-team1.vault.azure.net/ \
#         KEYWORDS="삼성전자,SK하이닉스" \
#         DATE_START=2025-04-01 \
#     --restart-policy Never \
#     --location koreacentral
#
# 필수 환경변수:
#   KEY_VAULT_URL  : https://<vault-name>.vault.azure.net/
#   KEYWORDS       : 콤마 구분 키워드 (기본: "삼성전자,SK하이닉스")
#   DATE_START     : YYYY-MM-DD (기본: 2025-04-01)
#   DATE_END       : YYYY-MM-DD (기본: 오늘)
#   ADLS_ACCOUNT   : ADLS 계정명 (기본: 3dtteam1adls)
#   ADLS_CONTAINER : ADLS 컨테이너명 (기본: raw)

FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

COPY src/ingestion/naver_collectors/naver_crawler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY src/ingestion/naver_collectors/naver_crawler/ /app/

CMD ["python", "naver_news_crawler.py"]