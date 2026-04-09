# Google News Crawler — ACI 배포 가이드

> **대상**: `3dtteam1adls`의 `raw/news/google/` 경로에 구글 뉴스 Parquet를 수집·저장하는  
> One-shot Azure Container Instance 크롤러

---

## 1. 사전 준비

### 1-1. 필수 도구

```bash
# 설치 확인
az --version        # Azure CLI 2.60+
docker --version    # Docker Desktop (로컬 빌드 시에만 필요)
```

> **Azure CLI 미설치 시** → [설치 가이드](https://learn.microsoft.com/cli/azure/install-azure-cli)

### 1-2. Azure 로그인

```bash
az login
az account set --subscription 27db5ec6-d206-4028-b5e1-6004dca5eeef
```

### 1-3. 리소스 정보 확인

| 항목 | 값 |
|------|-----|
| 리소스 그룹 | `3dt-2nd-team1` |
| ACR | `sense3dtacr` (koreacentral) |
| Key Vault | `kv-3dt-team1` |
| ADLS 계정 | `3dtteam1adls` |
| ADLS 컨테이너 | `raw` |

---

## 2. 이미지 빌드 & ACR 푸시

> **리포지토리 루트**에서 실행합니다.  
> ACR 빌드는 Docker Desktop 없이도 가능합니다 (클라우드 빌드).

```bash
az acr build \
  --registry sense3dtacr \
  --image google-news-crawler:latest \
  --file src/ingestion/google_news_crawler/Dockerfile \
  .
```

### 이미지 확인

```bash
az acr repository show-tags \
  --name sense3dtacr \
  --repository google-news-crawler \
  --output table
```

---

## 3. ACR Admin 자격증명 확인

ACI는 ACR에 접근하기 위해 admin 계정이 필요합니다.

```bash
az acr credential show --name sense3dtacr --query "{username:username, password:passwords[0].value}" -o json
```

출력 예시:
```json
{
  "username": "sense3dtacr",
  "password": "xxxxxxxxxxxxxxxxxxxx"
}
```

`username`과 `password`를 메모해 두세요. 다음 단계의 `<acr-admin-user>` / `<acr-admin-password>` 자리에 사용합니다.

---

## 4. ACI 생성 및 실행

### 4-1. 기본 실행 (오늘까지 기본 키워드)

```bash
az container create \
  --resource-group 3dt-2nd-team1 \
  --name sense-news-crawler \
  --image sense3dtacr.azurecr.io/google-news-crawler:latest \
  --registry-login-server sense3dtacr.azurecr.io \
  --registry-username <acr-admin-user> \
  --registry-password <acr-admin-password> \
  --assign-identity \
  --environment-variables \
    KEY_VAULT_URL=https://kv-3dt-team1.vault.azure.net/ \
    KEYWORDS="SK Hynix,Samsung Electronics" \
    DATE_START=2025-04-01 \
  --restart-policy Never \
  --os-type Linux \
  --cpu 2 \
  --memory 4 \
  --location koreacentral
```

### 4-2. 날짜 범위·키워드 지정

```bash
az container create \
  --resource-group 3dt-2nd-team1 \
  --name sense-news-crawler \
  --image sense3dtacr.azurecr.io/google-news-crawler:latest \
  --registry-login-server sense3dtacr.azurecr.io \
  --registry-username <acr-admin-user> \
  --registry-password <acr-admin-password> \
  --assign-identity \
  --environment-variables \
    KEY_VAULT_URL=https://kv-3dt-team1.vault.azure.net/ \
    KEYWORDS="SK Hynix,Samsung Electronics,TSMC" \
    DATE_START=2025-01-01 \
    DATE_END=2025-12-31 \
  --restart-policy Never \
  --os-type Linux \
  --cpu 2 \
  --memory 4 \
  --location koreacentral
```

### 환경변수 설명

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `KEY_VAULT_URL` | ✅ | — | `https://kv-3dt-team1.vault.azure.net/` |
| `KEYWORDS` | ❌ | `SK Hynix,Samsung Electronics` | 콤마로 구분된 검색 키워드 |
| `DATE_START` | ❌ | `2025-04-01` | 수집 시작일 `YYYY-MM-DD` |
| `DATE_END` | ❌ | 실행 당일 | 수집 종료일 `YYYY-MM-DD` |

---

## 5. ACI Managed Identity에 권한 부여

> ACI 생성 후 한 번만 수행하면 됩니다.

### 5-1. ACI의 Principal ID 확인

```bash
az container show \
  --resource-group 3dt-2nd-team1 \
  --name sense-news-crawler \
  --query "identity.principalId" -o tsv
```

`<PRINCIPAL_ID>`로 메모합니다.

### 5-2. Key Vault — Secrets User 권한 부여

```bash
az role assignment create \
  --assignee <PRINCIPAL_ID> \
  --role "Key Vault Secrets User" \
  --scope $(az keyvault show --name kv-3dt-team1 --query id -o tsv)
```

### 5-3. ADLS — Storage Blob Data Contributor 권한 부여

```bash
az role assignment create \
  --assignee <PRINCIPAL_ID> \
  --role "Storage Blob Data Contributor" \
  --scope $(az storage account show --name 3dtteam1adls --resource-group 3dt-2nd-team1 --query id -o tsv)
```

> 권한 전파에 최대 2~3분이 소요될 수 있습니다.

---

## 6. 실행 상태 확인 및 로그

### 상태 확인

```bash
az container show \
  --resource-group 3dt-2nd-team1 \
  --name sense-news-crawler \
  --query "{status:instanceView.state, exitCode:instanceView.currentState.exitCode}" \
  -o table
```

| `status` | 의미 |
|----------|------|
| `Running` | 크롤링 중 |
| `Succeeded` | 정상 완료 |
| `Failed` | 오류 발생 → 로그 확인 |

### 실시간 로그

```bash
az container logs \
  --resource-group 3dt-2nd-team1 \
  --name sense-news-crawler \
  --follow
```

---

## 7. 결과 데이터 확인

크롤링 완료 후 ADLS에 다음 경로로 Parquet 파일이 저장됩니다.

```
raw/news/google/keyword={safe_keyword}/year={YYYY}/month={MM}/articles.parquet
```

예시 (SK Hynix, 2025년 4월):
```
raw/news/google/keyword=SK_Hynix/year=2025/month=04/articles.parquet
```

체크포인트(재시작 시 이어하기):
```
raw/news/google/checkpoints/{safe_keyword}_{YYYY-MM}.json
```

---

## 8. 재실행 (코드 변경 없이 날짜만 다시)

기존 ACI 컨테이너는 `--restart-policy Never`이므로 재실행하려면 삭제 후 재생성합니다.

```bash
# 기존 컨테이너 삭제
az container delete \
  --resource-group 3dt-2nd-team1 \
  --name sense-news-crawler \
  --yes

# 재생성 (4-1 또는 4-2 명령 반복)
az container create ...
```

> ⚡ **체크포인트 덕분에** 동일 키워드·월 조합은 이미 수집된 데이터를 건너뜁니다.

---

## 9. 코드 수정 후 재배포

소스 코드를 수정한 경우 이미지를 다시 빌드·푸시한 뒤 ACI를 재생성합니다.

```bash
# 1. 이미지 재빌드
az acr build \
  --registry sense3dtacr \
  --image google-news-crawler:latest \
  --file src/ingestion/google_news_crawler/Dockerfile \
  .

# 2. 기존 ACI 삭제
az container delete --resource-group 3dt-2nd-team1 --name sense-news-crawler --yes

# 3. ACI 재생성 (4-1 명령 참고)
az container create ...
```

---

## 10. 관련 파일

```
src/ingestion/google_news_crawler/
├── Dockerfile          # 컨테이너 이미지 정의
├── requirements.txt    # Python 의존성
├── .dockerignore
├── main.py             # 엔트리포인트
├── config.py           # 환경변수 기반 설정
├── utils.py            # ADLS 저장 유틸리티
└── crawling_google_news.py  # RSS + Playwright 크롤링 로직
```
