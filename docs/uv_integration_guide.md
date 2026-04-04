# Azure 서비스별 uv 통합 가이드

uv는 Rust로 작성된 Python 패키지 관리자로, pip 대비 10–100배 빠른 설치 속도를 제공합니다.
이 프로젝트에서는 **pyproject.toml** 기반으로 의존성을 관리하고, 각 Azure 서비스 환경에서 uv를 활용해 환경 구성 시간을 단축합니다.

## 로컬 개발 — 기본 워크플로

```bash
# uv 설치 (최초 1회)
# Windows PowerShell (권장):
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# 의존성 설치 (pyproject.toml 기준)
# .python-version 파일 덕분에 항상 Python 3.11 가상환경이 생성됨
uv sync                    # 기본 의존성
uv sync --extra ml         # ML 관련 (azure-ai-ml, mlflow)
uv sync --extra databricks # Databricks SDK

# Python 스크립트 실행 — uv run 사용 (venv 자동 적용)
# 'python src/...' 대신 반드시 'uv run python src/...' 를 사용할 것
# 이유: uv는 .venv를 만들지만 자동 활성화하지 않으므로 bare 'python'은 시스템 Python을 가리킴
uv run python src/utils/vault_manager.py

# 또는 venv를 직접 활성화 후 실행
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

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
FROM python:3.11-slim

# ghcr.io 공식 이미지에서 uv/uvx 바이너리 복사
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# pyproject.toml을 먼저 복사해 Docker 레이어 캐시 활용
COPY pyproject.toml uv.lock* ./

# pyproject.toml 기본 의존성 설치
# --no-dev: 개발 도구 제외  --no-install-project: 소스 없이 의존성만 설치
RUN uv sync --no-dev --no-install-project

COPY src/ ./src/
CMD [".venv/bin/python", "main.py"]
```

**핵심 옵션 설명:**

| 옵션 | 설명 |
|---|---|
| `--no-dev` | `[dependency-groups.dev]`(pytest, ruff 등) 제외 |
| `--no-install-project` | 소스를 복사하기 전에 의존성만 먼저 설치해 레이어 캐시 활용 |
| `uv.lock*` COPY | lockfile이 있으면 정확한 버전 고정, 없으면 최신 해상도로 설치 |

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
        "python-dotenv psycopg sqlalchemy && "
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
"psycopg[binary]>=3.2.0",
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
| `pg-connection-string` | PostgreSQL 연결 문자열 | PostgreSQL 사용 시 |

**`pg-connection-string` 예시:**
```
host={server}.postgres.database.azure.com dbname={db} user={user} password={pass} sslmode=require
```

---

## 개발 도구 실행 방법

`pyproject.toml [dependency-groups.dev]`에 등록된 도구는 모두 `uv run`으로 실행합니다.
가상 환경을 직접 활성화하지 않아도 됩니다.

### pytest — 테스트 실행

```bash
# 전체 테스트
uv run pytest

# 특정 파일만
uv run pytest src/utils/test_vault_manager.py

# 상세 출력
uv run pytest -v

# 커버리지 포함 (pytest-cov 설치 시)
uv run pytest --cov=src --cov-report=term-missing
```

### ruff — 린터 + import 정렬

```bash
# 린트 검사 (수정 없이 결과만 출력)
uv run ruff check src/

# 자동 수정 가능한 문제 일괄 수정
uv run ruff check src/ --fix

# import 정렬 확인
uv run ruff check src/ --select I

# 포맷 확인 (black 호환 모드)
uv run ruff format src/ --check
```

### black — 코드 포매터

```bash
# src/ 전체 포맷
uv run black src/

# 변경 없이 diff 확인만
uv run black src/ --check --diff
```

### ty — 타입 체커 (Astral, 신표준)

`ty`는 Astral이 Rust로 개발 중인 타입 체커로, mypy 대비 수십 배 빠릅니다.
아직 alpha 단계이므로 CI에서 빌드 실패 기준으로 사용하되, `--error-on-warning`은 제외합니다.

```bash
# src/ 전체 타입 검사
uv run ty check src/

# 특정 파일만
uv run ty check src/utils/vault_manager.py

# 상세 출력
uv run ty check src/ --verbose
```

> **참고:** `pyproject.toml`의 `[tool.ty]` 섹션에서 검사 대상 경로와 Python 버전을 설정합니다.

### 한 번에 전체 검사 (CI 흉내)

```bash
uv run ruff check src/ && \
uv run black src/ --check && \
uv run ty check src/ && \
uv run pytest
```

---

## VS Code 자동화 설정

`.vscode/` 폴더의 설정 파일이 Git에 포함되어 있으므로, **저장소를 clone하면 팀 전체가 동일한 개발 환경을 자동으로 공유**합니다.

### 1단계: 권장 확장 설치

```
Cmd+Shift+P (Windows: Ctrl+Shift+P)
→ "Extensions: Show Recommended Extensions"
→ 목록의 확장을 모두 설치
```

또는 터미널에서 한 번에 설치:
```bash
# 확장 ID 목록은 .vscode/extensions.json 참고
code --install-extension ms-python.python
code --install-extension ms-python.pylance
code --install-extension ms-python.black-formatter
code --install-extension charliermarsh.ruff
code --install-extension tamasfe.even-better-toml
```

### 2단계: Python 인터프리터 선택

`uv sync` 실행 후 VS Code가 `.venv`를 자동 감지합니다.
감지되지 않으면:

```
Cmd+Shift+P → "Python: Select Interpreter"
→ ./.venv/bin/python (또는 Windows: .venv\Scripts\python.exe) 선택
```

### 3단계: 자동화 확인

`.vscode/settings.json`에 아래 동작이 이미 설정되어 있습니다.

| 이벤트 | 자동 동작 |
|---|---|
| 파일 저장 | black으로 자동 포맷 |
| 파일 저장 | ruff로 lint 자동 수정 |
| 파일 저장 | ruff로 import 자동 정렬 |
| 파일 편집 | Pylance IntelliSense (자동완성, 정의 이동) |

### ty — VS Code 연동 (예정)

ty의 공식 VS Code 확장은 아직 출시 전입니다 (2026 상반기 예정).
현재는 터미널에서 실행하거나, VS Code Tasks로 등록해 사용합니다:

```
Cmd+Shift+P → "Tasks: Run Task" → "ty: type check"
```

Tasks 설정 예시 (`.vscode/tasks.json` 직접 추가):
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "ty: type check",
      "type": "shell",
      "command": "uv run ty check src/",
      "group": "test",
      "presentation": { "panel": "shared" },
      "problemMatcher": []
    }
  ]
}
```

> ty 공식 확장 출시 후 `.vscode/settings.json`의 `python.analysis.typeCheckingMode` 주석 처리된 부분을 활성화하고 이 섹션을 업데이트하세요.

---

## pre-commit — Git Hook 자동화

[`.pre-commit-config.yaml`](../.pre-commit-config.yaml) 파일이 프로젝트 루트에 구성되어 있습니다.
`git commit` 실행 시 아래 검사가 자동으로 수행됩니다.

| Hook | 역할 |
|---|---|
| `ruff` | 린트 검사 + 자동 수정 (`--fix`) |
| `ruff-format` | 코드 포맷 (black 호환) |
| `detect-secrets` | 시크릿 유출 방지 |

### 설치 및 활성화

```bash
# dev 의존성에 포함되어 있으므로 uv sync만으로 설치됨
uv sync

# Git hook 등록 (최초 1회)
uv run pre-commit install

# 전체 파일 대상 수동 실행 (CI 테스트용)
uv run pre-commit run --all-files
```

### secrets baseline 생성

detect-secrets hook은 `.secrets.baseline` 파일을 참조합니다.
최초 실행 전에 baseline을 생성해야 합니다.

```bash
uv run detect-secrets scan > .secrets.baseline
```

> **상세 설정:** [docs/git_guide/git_guide_workflow/05_precommit_setup.md](git_guide/git_guide_workflow/05_precommit_setup.md)
