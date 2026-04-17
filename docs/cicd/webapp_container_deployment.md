# SENSE 웹앱 컨테이너 배포 전략

> **대상**: `app.py` 기반 Flask 웹앱을 Azure App Service (Web App for Containers)로 배포
>
> **참고 레퍼런스**: `ref/lala-container-deployment-handoff-2026-03-06.md`

---

## 1. 배포 구조 개요

```
로컬 / CI
    │  docker build & push
    ▼
ACR (Azure Container Registry)
    │  App Service pulls on restart / slot swap
    ▼
App Service — staging 슬롯   ──swap──►  App Service — production 슬롯
    │  Managed Identity → Key Vault
    ▼
PostgreSQL (pg-connection-string)
Azure OpenAI (azure-openai-api-key / endpoint)
```

**핵심 원칙**: `appCommandLine`(Portal 시작 명령)은 **항상 비워 둔다**.
Dockerfile CMD JSON 배열이 진입점이며, Portal에서 값을 입력하면 CMD가 무시된다.
(레퍼런스 문서 §2 참조)

---

## 2. wsgi.py가 필요 없는 이유

레퍼런스 프로젝트(lala)에서 `wsgi.py`가 필요했던 이유는 **`appCommandLine`(Portal 시작 명령)** 방식을 사용했기 때문이다.  
Portal에서 입력한 문자열은 Linux 컨테이너 shell을 경유하므로, `create_app()`의 괄호가 shell에 의해 파싱되어 깨진다.

```
# shell 방식 — 괄호가 shell 메타문자로 해석됨 (문제 발생)
appCommandLine = gunicorn "app:create_app()"
```

**Dockerfile CMD를 JSON 배열로 쓰면 shell을 거치지 않으므로 괄호를 그대로 전달할 수 있다.**

```dockerfile
# JSON 배열 방식 — shell 미경유, 괄호 문제 없음 (권장)
CMD ["gunicorn", "app:create_app()"]
```

따라서 SENSE 프로젝트는 `app.py`의 `create_app()`을 Dockerfile CMD에서 직접 참조하며, `wsgi.py`는 추가하지 않는다.

---

## 3. 필요 파일

### 3-1. `Dockerfile` (프로젝트 루트)

```dockerfile
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
# appCommandLine(Portal 시작 명령)은 반드시 비워 두어야 한다.
CMD ["gunicorn",
     "--bind", "0.0.0.0:8000",
     "--workers", "1",
     "--threads", "4",
     "--worker-class", "gthread",
     "--timeout", "120",
     "--worker-tmp-dir", "/tmp",
     "--access-logfile", "-",
     "--error-logfile", "-",
     "--log-level", "info",
     "app:create_app()"]
```

### 3-2. `.dockerignore` (프로젝트 루트)

```
.env
.env.*
*.pyc
__pycache__/
.git/
.venv/
notebooks/
adf/
docs/
tests/
*.csv
*.parquet
```

### 3-3. `requirements.txt` — 컨테이너 이미지용 의존성

> `pyproject.toml`이 진실 공급원(source of truth)이지만, Dockerfile은 `requirements.txt`를 사용한다.
> uv를 쓰지 않는 배포 환경에서도 재현 가능하도록 유지한다.

```
flask
gunicorn
python-dotenv
azure-identity>=1.16
azure-keyvault-secrets>=4.8
psycopg2-binary
sqlalchemy
openai
```

> `gunicorn`이 빠지면 컨테이너가 기동되지 않는다.

---

## 4. Azure 인프라 설정

### 4-1. 필요 리소스

| 리소스 | 용도 |
|---|---|
| Azure Container Registry (ACR) | 이미지 저장소 |
| App Service (Web App for Containers) | Flask 앱 실행 — production |
| App Service 배포 슬롯 (staging) | 무중단 배포용 스테이징 환경 |
| Managed Identity (System-assigned) | ACR pull + Key Vault 접근 |
| Azure Key Vault | DB 연결문자열·OpenAI API 키 관리 |

### 4-2. Managed Identity 역할 할당

```bash
# App Service의 principal ID 확인
PRINCIPAL_ID=$(az webapp identity show \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --query principalId -o tsv)

# ACR에 AcrPull 권한 부여
ACR_ID=$(az acr show --name <acr-name> --query id -o tsv)
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role AcrPull \
  --scope $ACR_ID

# Key Vault에 Secrets User 권한 부여
KV_ID=$(az keyvault show --name <keyvault-name> --query id -o tsv)
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Key Vault Secrets User" \
  --scope $KV_ID
```

> 슬롯(staging)도 별도 Managed Identity를 가지므로 동일한 역할 할당이 필요하다.

### 4-3. App Service 환경 변수

App Service → 구성 → 애플리케이션 설정에서 설정. 슬롯별로 독립적으로 관리된다.

| 키 | 값 | 슬롯 고정 여부 |
|---|---|---|
| `KEY_VAULT_URL` | `https://<keyvault-name>.vault.azure.net/` | 아니오 (swap 시 이동) |
| `FLASK_SECRET_KEY` | Key Vault 참조 또는 직접 입력 | 아니오 |
| `ADMIN_PASSWORD` | Key Vault 참조 | 아니오 |
| `SENSE_KV_PG_CONNECTION_SECRET_NAME` | `pg-connection-string` | 아니오 |
| `SENSE_KV_AOAI_API_KEY_SECRET_NAME` | `azure-openai-api-key` | 아니오 |
| `SENSE_KV_AOAI_ENDPOINT_SECRET_NAME` | `azure-openai-endpoint` | 아니오 |
| `SLOT_NAME` | `staging` / `production` | **예 (슬롯 고정)** |

> **슬롯 고정(Slot Setting)**: `SLOT_NAME`처럼 슬롯 식별용 변수는 슬롯 고정으로 설정해야 swap 후에도 각 슬롯 값이 유지된다.
> 절대 입력하지 않을 것: **시작 명령(Startup Command)** 필드.

---

## 5. 배포 슬롯 (Staging → Production Swap)

### 개념

App Service 배포 슬롯을 이용하면 **무중단 배포**가 가능하다.

```
새 이미지
   │ push
   ▼
staging 슬롯 (예열 + 검증)
   │ az webapp deployment slot swap
   ▼
production 슬롯 (트래픽 수신)

기존 production 내용 → staging 슬롯으로 이동 (롤백 가능)
```

### 슬롯 생성

```bash
az webapp deployment slot create \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --slot staging \
  --configuration-source <app-service-name>
```

### 배포 절차 (전체 플로우)

```bash
# 1) 이미지 빌드 & push (버전 태그 필수)
az acr login --name <acr-name>
docker build -t <acr-name>.azurecr.io/sense-web:v<N> .
docker push <acr-name>.azurecr.io/sense-web:v<N>

# 2) staging 슬롯에 새 이미지 배포
az webapp config container set \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --slot staging \
  --docker-custom-image-name <acr-name>.azurecr.io/sense-web:v<N>

# 3) staging 슬롯 재시작 후 검증
az webapp restart \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --slot staging

curl https://<app-service-name>-staging.azurewebsites.net/

# 4) 정상 확인 후 production으로 swap
az webapp deployment slot swap \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --slot staging \
  --target-slot production
```

### 롤백

swap은 양방향이므로, 문제 발생 시 동일 명령으로 즉시 되돌릴 수 있다.

```bash
# 이전 버전으로 즉시 롤백
az webapp deployment slot swap \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --slot staging \
  --target-slot production
```

---

## 6. 헬스 체크 확인

```bash
# production
curl https://<app-service-name>.azurewebsites.net/

# staging (swap 전 검증)
curl https://<app-service-name>-staging.azurewebsites.net/

# 로그 스트림
az webapp log tail \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --slot staging
```

정상 기동 시 Gunicorn 로그:
```
[INFO] Starting gunicorn 23.x.x
[INFO] Listening at: http://0.0.0.0:8000
[INFO] Booting worker with pid: ...
```

---

## 7. 트러블슈팅

### 증상: `ModuleNotFoundError: No module named '"app` 또는 `'"src`

**원인**: Portal의 "시작 명령(Startup Command)"에 값이 입력되어 Dockerfile CMD가 무시됨.

```bash
# 시작 명령 강제 초기화
az resource update \
  --resource-group <resource-group> \
  --name <app-service-name> \
  --resource-type "Microsoft.Web/sites" \
  --set properties.siteConfig.appCommandLine=""

az webapp restart --name <app-service-name> --resource-group <resource-group>
```

### 증상: Key Vault 접근 오류 (`CredentialUnavailableError`)

**원인**: Managed Identity 미설정 또는 Key Vault Secrets User 역할 미할당.

```bash
az webapp identity show --name <app-service-name> --resource-group <resource-group>
az role assignment list --assignee <principal-id> --all
```

### 증상: PostgreSQL 연결 실패

1. Key Vault에 `pg-connection-string` 시크릿 존재 여부 확인
2. App Service 아웃바운드 IP → PostgreSQL 방화벽 허용 목록 추가
3. 연결 문자열에 `sslmode=require` 포함 여부 확인

---

## 8. 보안 주의사항

- **Portal "시작 명령(Startup Command)"은 항상 비워 둔다.** — 입력 시 `ModuleNotFoundError` 재현
- `FLASK_SECRET_KEY`를 기본값(`dev-key`)으로 운영하지 않는다.
- `.env` 파일은 `.dockerignore`에 추가해 이미지에 포함되지 않도록 한다.
- Managed Identity 단독 운영 권장 — `DOCKER_REGISTRY_SERVER_PASSWORD` 방식은 사용하지 않는다.
- `ADMIN_PASSWORD`는 Key Vault에서 참조하거나 App Service 환경 변수로만 설정한다.

---

*최초 작성: 2026-04-17 | 참고: `ref/lala-container-deployment-handoff-2026-03-06.md`*


---

## 1. 배포 구조 개요

```
로컬 / CI
    │  docker build
    ▼
ACR (Azure Container Registry)
    │  App Service pulls on restart
    ▼
Azure App Service (Web App for Containers)
    │  Managed Identity → Key Vault
    ▼
PostgreSQL (pg-connection-string)
Azure OpenAI (azure-openai-api-key / endpoint)
```

**핵심 원칙**: `appCommandLine`(Portal 시작 명령)은 **항상 비워 둔다**.
Dockerfile CMD가 진입점이며, Portal에서 값을 입력하면 CMD가 무시되어 `ModuleNotFoundError`가 재현된다.
(레퍼런스 문서 §2 참조)

---

## 2. 필요 파일

### 2-1. `wsgi.py` (프로젝트 루트)

`create_app()` callable을 모듈 레벨 객체로 분리해 Gunicorn이 따옴표 없이 참조하도록 한다.

```python
"""
Gunicorn entrypoint for Azure App Service.
wsgi.py 로 분리하면 Dockerfile CMD 에서 따옴표 파싱 문제를 피할 수 있다.
"""
from app import create_app

application = create_app()
```

> **주의**: `app.py`가 프로젝트 루트에 있으므로 `from app import create_app` 사용.
> `PYTHONPATH=/app`이 설정되어 있어야 한다 (Dockerfile ENV 참조).

---

### 2-2. `Dockerfile` (프로젝트 루트)

```dockerfile
FROM python:3.11-slim

# 시스템 의존성 (psycopg2-binary 빌드 불필요하지만 혹시 모를 네이티브 빌드 대비)
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

# appCommandLine(Portal 시작 명령)은 반드시 비워 두어야 한다.
# 값이 있으면 이 CMD가 무시되고 ModuleNotFoundError가 발생한다.
CMD ["gunicorn",
     "--bind", "0.0.0.0:8000",
     "--workers", "1",
     "--threads", "4",
     "--worker-class", "gthread",
     "--timeout", "120",
     "--worker-tmp-dir", "/tmp",
     "--access-logfile", "-",
     "--error-logfile", "-",
     "--log-level", "info",
     "wsgi:application"]
```

---

### 2-3. `requirements.txt` 필수 패키지 확인

배포 이미지에 아래 패키지가 포함되어야 한다.

```
flask
gunicorn
python-dotenv
azure-identity>=1.16
azure-keyvault-secrets>=4.8
psycopg2-binary
sqlalchemy
openai
```

> `gunicorn`이 빠지면 컨테이너가 기동되지 않는다. 로컬 개발 환경에서 누락되기 쉬우므로 반드시 확인.

---

## 3. Azure 인프라 설정

### 3-1. 필요 리소스

| 리소스 | 용도 |
|---|---|
| Azure Container Registry (ACR) | 이미지 저장소 |
| App Service (Web App for Containers) | Flask 앱 실행 |
| Managed Identity (System-assigned) | ACR pull + Key Vault 접근 |
| Azure Key Vault | DB 연결문자열·OpenAI API 키 관리 |

### 3-2. Managed Identity 역할 할당

```bash
# App Service의 principal ID 확인
PRINCIPAL_ID=$(az webapp identity show \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --query principalId -o tsv)

# ACR에 AcrPull 권한 부여
ACR_ID=$(az acr show --name <acr-name> --query id -o tsv)
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role AcrPull \
  --scope $ACR_ID

# Key Vault에 Secrets User 권한 부여
KV_ID=$(az keyvault show --name <keyvault-name> --query id -o tsv)
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Key Vault Secrets User" \
  --scope $KV_ID
```

### 3-3. 앱 환경 변수 설정

App Service → 구성 → 애플리케이션 설정에서 다음을 설정한다.
실제 값은 Key Vault에서 로드되므로 Key Vault URL만 필수이며, 나머지는 시크릿 이름 오버라이드용이다.

| 키 | 값 |
|---|---|
| `KEY_VAULT_URL` | `https://<keyvault-name>.vault.azure.net/` |
| `FLASK_SECRET_KEY` | Key Vault 시크릿 참조 또는 직접 입력 |
| `SENSE_KV_PG_CONNECTION_SECRET_NAME` | `pg-connection-string` |
| `SENSE_KV_AOAI_API_KEY_SECRET_NAME` | `azure-openai-api-key` |
| `SENSE_KV_AOAI_ENDPOINT_SECRET_NAME` | `azure-openai-endpoint` |

> **절대 입력하지 않을 것**: `Startup Command` (시작 명령) 필드.
> 비어 있어야 Dockerfile CMD가 정상 실행된다.

---

## 4. 이미지 빌드 및 배포 절차

### 최초 배포

```bash
# 1) ACR 로그인
az acr login --name <acr-name>

# 2) 이미지 빌드 (버전 태그 필수 — latest는 캐시 문제 있음)
docker build -t <acr-name>.azurecr.io/sense-web:v1 .

# 3) 이미지 push
docker push <acr-name>.azurecr.io/sense-web:v1

# 4) App Service에 컨테이너 이미지 설정
az webapp config container set \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --docker-custom-image-name <acr-name>.azurecr.io/sense-web:v1 \
  --docker-registry-server-url https://<acr-name>.azurecr.io

# 5) Managed Identity 기반 ACR pull 활성화
az webapp config set \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --generic-configurations '{"acrUseManagedIdentityCreds": true}'

# 6) 재시작
az webapp restart --name <app-service-name> --resource-group <resource-group>
```

### 코드 변경 후 재배포

```bash
# 버전 번호를 올려서 빌드·push·업데이트
docker build -t <acr-name>.azurecr.io/sense-web:v<N> .
docker push <acr-name>.azurecr.io/sense-web:v<N>

az webapp config container set \
  --name <app-service-name> \
  --resource-group <resource-group> \
  --docker-custom-image-name <acr-name>.azurecr.io/sense-web:v<N>

az webapp restart --name <app-service-name> --resource-group <resource-group>
```

> `latest` 태그는 App Service가 캐시를 재사용할 수 있으므로 항상 `:v<N>` 식으로 올린다.

---

## 5. 헬스 체크 확인

배포 완료 후 `/` 또는 별도 `/health` 엔드포인트로 정상 기동 확인.

```bash
curl https://<app-service-name>.azurewebsites.net/
```

App Service 로그 스트림:

```bash
az webapp log tail --name <app-service-name> --resource-group <resource-group>
```

정상 기동 시 Gunicorn 로그 예시:
```
[INFO] Starting gunicorn
[INFO] Listening at: http://0.0.0.0:8000
[INFO] Booting worker with pid: ...
```

---

## 6. 트러블슈팅

### 증상: `ModuleNotFoundError: No module named '"src`

**원인**: App Service Portal의 "시작 명령(Startup Command)"에 값이 입력되어 있어 Dockerfile CMD가 무시됨.

**해결**:
```bash
az resource update \
  --resource-group <resource-group> \
  --name <app-service-name> \
  --resource-type "Microsoft.Web/sites" \
  --set properties.siteConfig.appCommandLine=""
```

그 후 재시작:
```bash
az webapp restart --name <app-service-name> --resource-group <resource-group>
```

### 증상: Key Vault 접근 오류 (`CredentialUnavailableError`)

**원인**: Managed Identity 미설정 또는 Key Vault Secrets User 역할 미할당.

**확인**:
```bash
az webapp identity show --name <app-service-name> --resource-group <resource-group>
az role assignment list --assignee <principal-id> --all
```

### 증상: PostgreSQL 연결 실패

**확인 순서**:
1. Key Vault에 `pg-connection-string` 시크릿이 존재하는지 확인
2. App Service의 아웃바운드 IP가 PostgreSQL 방화벽 허용 목록에 있는지 확인
3. `ssl=require` 파라미터 포함 여부 확인

---

## 7. 보안 주의사항

- `appCommandLine`(시작 명령)은 **항상 비어 있어야 한다**.
- `.env` 파일은 이미지에 포함되지 않도록 `.dockerignore`에 추가한다.
- `DOCKER_REGISTRY_SERVER_PASSWORD` 방식 대신 Managed Identity 단독으로 운영하는 것을 권장한다.
- `FLASK_SECRET_KEY`를 기본값(`dev-key`)으로 운영하지 않는다 — Key Vault 또는 App Service 환경 변수로 반드시 재설정한다.

---

## 8. `.dockerignore` 권장 설정

```
.env
.env.*
*.pyc
__pycache__/
.git/
.venv/
notebooks/
adf/
docs/
tests/
*.csv
*.parquet
```

---

*최초 작성: 2026-04-17 