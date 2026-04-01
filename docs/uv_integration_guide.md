# Azure 서비스별 uv 통합 가이드

uv는 Rust로 작성된 Python 패키지 관리자로, pip 대비 10–100배 빠른 설치 속도를 제공합니다.
이 프로젝트에서는 **pyproject.toml** 기반으로 의존성을 관리하고, 각 Azure 서비스 환경에서 uv를 활용해 환경 구성 시간을 단축합니다.

## 로컬 개발 — 기본 워크플로

```bash
# uv 설치 (최초 1회)
pip install uv

# 의존성 설치 (pyproject.toml 기준)
uv sync                    # 기본 의존성
uv sync --extra ml         # ML 관련 (azure-ai-ml, mlflow)
uv sync --extra databricks # Databricks SDK

# 패키지 추가
uv add requests            # pyproject.toml에 자동 반영
uv add --dev pytest        # dev 그룹에 추가

# 잠금 파일 재생성 (의존성 변경 후)
uv lock
```

---

## 1. Azure Data Factory — Custom Activity

ADF 자체는 Python을 실행하지 않습니다.
ADF가 호출하는 **Custom Activity 컨테이너** 안에서 uv를 사용합니다.

**핵심 파일:** [`adf/custom_activity/Dockerfile`](../adf/custom_activity/Dockerfile)

```dockerfile
# uv 바이너리를 ghcr.io 공식 이미지에서 복사 (별도 설치 없음)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# --system: 컨테이너 시스템 Python에 직접 설치 (가상 환경 불필요)
RUN uv pip install --system -r requirements.txt
```

**설정 흐름:**
1. 이 저장소를 Azure Container Registry(ACR)에 빌드·푸시
2. ADF > Custom Activity > Docker Image 설정에 ACR 이미지 경로 입력
3. Key Vault Linked Service 연결 → Managed Identity 자동 인증

**참고:** ADF Linked Service(ADLS, SQL)는 UI에서 Key Vault 비밀을 직접 참조하도록 설정할 수 있습니다. Python 코드 없이 연결 가능합니다.

---

## 2. Azure Databricks — Init Script + 노트북

클러스터 시작 시 Init Script를 실행해 uv를 준비합니다.

**핵심 파일:** [`notebooks/init_script_install_uv.sh`](../notebooks/init_script_install_uv.sh)

**Init Script 등록:**
```bash
# DBFS에 업로드
databricks fs cp notebooks/init_script_install_uv.sh \
    dbfs:/FileStore/scripts/install_uv.sh

# 클러스터 > Edit > Advanced Options > Init Scripts 에 경로 등록
```

**Init Script 없이 노트북 셀에서 즉석 설치:**
```python
# %sh
# pip install uv -q
# uv pip install --system azure-identity azure-keyvault-secrets \
#   azure-storage-file-datalake python-dotenv -q
```

**vault_manager + ADLS 연동 전체 예시:** [`notebooks/databricks_uv_example.py`](../notebooks/databricks_uv_example.py)

**Databricks Secret Scope 활용 (권장):**
Key Vault 연동 Secret Scope를 사용하면 `KEY_VAULT_URL` 자체도 코드에서 제거할 수 있습니다.
```python
KEY_VAULT_URL = dbutils.secrets.get(scope="kv-scope", key="KEY-VAULT-URL")
os.environ["KEY_VAULT_URL"] = KEY_VAULT_URL
```

---

## 3. Azure ML Studio — CommandJob (v2 SDK)

학습 잡(Job)이 실행될 때 uv로 패키지를 설치하면 pip 대비 환경 구성 시간을 단축할 수 있습니다.
반복 실험이 많을수록 효과가 큽니다.

**핵심 파일:** [`src/models/aml_train_example.py`](../src/models/aml_train_example.py)

```python
job = command(
    command=(
        "uv pip install --system "
        "azure-identity azure-keyvault-secrets azure-storage-file-datalake "
        "python-dotenv sqlalchemy && "
        "python models/train.py"
    ),
    environment_variables={
        "KEY_VAULT_URL": "https://{your-kv}.vault.azure.net/",
    },
    ...
)
```

**커스텀 Docker 이미지 (반복 실험 시 더 효율적):**
uv로 패키지가 미리 설치된 이미지를 ACR에 빌드·등록하면, 잡마다 설치 시간이 0에 가까워집니다.

---

## vault_manager.py 의존성 관리

세 환경 모두에서 `vault_manager.py`가 정상 동작하려면 아래 패키지가 필요합니다.
`pyproject.toml` 기본 의존성에 이미 포함되어 있으므로 `uv sync` 한 번으로 해결됩니다.

```toml
# pyproject.toml 기본 의존성 (발췌)
"azure-identity>=1.19.0",
"azure-keyvault-secrets>=4.9.0",
"azure-storage-file-datalake>=12.19.0",
"python-dotenv>=1.0.0",
"pyodbc>=5.2.0",
"sqlalchemy>=2.0.0",
```

| 환경 | vault_manager 인증 방식 |
|---|---|
| 로컬 개발 | `az login` → DefaultAzureCredential |
| ADF Custom Activity | Managed Identity → DefaultAzureCredential |
| Databricks | Service Principal (adls-client-id/secret/tenant-id) |
| ML Studio Compute | Managed Identity → DefaultAzureCredential |

**Key Vault에 등록해야 할 시크릿 목록:**

| 시크릿 이름 | 설명 | 필요 환경 |
|---|---|---|
| `adls-account-name` | ADLS Gen2 스토리지 계정 이름 | 전체 |
| `adls-client-id` | Service Principal 클라이언트 ID | Databricks |
| `adls-client-secret` | Service Principal 클라이언트 시크릿 | Databricks |
| `adls-tenant-id` | Azure AD 테넌트 ID | Databricks |
| `sql-connection-string` | Azure SQL ODBC 연결 문자열 | Azure SQL 사용 시 |

**`sql-connection-string` 예시 (Managed Identity, 비밀번호 없음):**
```
Driver={ODBC Driver 18 for SQL Server};Server=tcp:{server}.database.windows.net,1433;Database={db};Authentication=ActiveDirectoryMsi;
```
