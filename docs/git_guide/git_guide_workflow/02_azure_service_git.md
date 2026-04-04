# 02. Azure 서비스별 Git 연동

각 Azure 서비스마다 Git 연동 방식이 다릅니다.
서비스별 주의사항과 Best Practice를 정리합니다.

---

## Azure Data Factory (ADF)

### Git 연동 방식

ADF는 **파이프라인 JSON 코드**를 Git으로 관리합니다.

```
adf/
├── pipeline/          ← 파이프라인 JSON
├── dataset/           ← 데이터셋 정의
├── linkedService/     ← 연결 정보 (Key Vault 참조)
└── trigger/           ← 트리거 정의
```

### 주의사항

| 규칙 | 이유 |
|---|---|
| **feature 브랜치에서 편집** | JSON 충돌 방지 |
| **같은 파이프라인 동시 편집 금지** | JSON merge가 거의 불가능 |
| **merge 전 팀 채팅으로 조율** | 덮어쓰기 사고 방지 |
| **dev 브랜치에서 Publish** | Publish = ARM 템플릿 생성 → 배포 |

### ADF Git 워크플로우

```
1. ADF Studio 접속
2. 좌측 상단에서 feature 브랜치 선택 (또는 생성)
3. 파이프라인 편집
4. Save (= Git commit)
5. GitHub에서 PR 생성
6. 리뷰 후 dev에 merge
7. ADF Studio에서 dev 브랜치로 전환 → Publish
```

### Custom Activity Docker 이미지

프로젝트의 `adf/custom_activity/` 폴더에 Dockerfile과 진입점이 있습니다.

```bash
# 로컬 빌드 테스트
cd adf/custom_activity
docker build -t adf-custom:dev .

# ACR에 push (CI에서 자동화)
docker tag adf-custom:dev <ACR>.azurecr.io/adf-custom:latest
docker push <ACR>.azurecr.io/adf-custom:latest
```

---

## Azure Databricks

### Git 연동 방식: Databricks Repos

Databricks는 **Repos** 기능으로 GitHub 저장소를 직접 동기화합니다.

```
Databricks Workspace
└── Repos/
    └── 3dt-2nd-project/     ← GitHub 저장소 클론
        ├── src/
        ├── notebooks/
        └── pyproject.toml
```

### 워크플로우

```bash
# 1. Databricks Workspace → Repos 탭
# 2. Add Repo → GitHub 저장소 URL 입력
# 3. feature 브랜치로 체크아웃

# Repos UI에서:
#   - Pull: 원격 최신화
#   - 브랜치 전환
#   - Commit & Push (간단한 변경)

# 복잡한 작업은 로컬 VS Code에서 하고 Push → Databricks에서 Pull
```

### Init Script (uv 설치)

클러스터 시작 시 uv와 공통 패키지를 자동 설치합니다.

```bash
# dbfs:/FileStore/scripts/install_uv.sh
#!/bin/bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv pip install --system azure-identity azure-keyvault-secrets azure-storage-file-datalake
```

### Databricks에서 vault_manager 사용

```python
import sys
sys.path.insert(0, "/Workspace/Repos/3dt-2nd-project/src")

from utils.vault_manager import vault
client = vault.get_storage_client("your-adls-account")
# Databricks에서는 자동으로 Spark conf OAuth 설정
```

### Databricks Secret Scope (대안)

vault_manager 대신 Databricks 자체 Secret Scope도 사용 가능합니다:

```python
# Databricks Secret Scope으로 Key Vault 연결
secret = dbutils.secrets.get(scope="keyvault-scope", key="pg-connection-string")
```

---

## Azure ML Studio

### Git 연동 방식

ML Studio는 **터미널에서 직접 Git** 명령어를 사용합니다.

```bash
# ML Studio Compute Instance에서:
cd /home/azureuser/cloudfiles/code
git clone https://github.com/3dt-project-team/3dt-2nd-project.git
cd 3dt-2nd-project
git checkout dev
uv sync --extra ml
```

### MLflow + Git 커밋 해시

실험 추적 시 Git 커밋 해시를 태깅하면 재현성이 보장됩니다:

```python
import subprocess
import mlflow

commit_hash = subprocess.check_output(
    ["git", "rev-parse", "HEAD"]
).decode().strip()

mlflow.set_tag("git_commit", commit_hash)
mlflow.set_tag("git_branch", "dev")
```

### CommandJob에서 uv 사용

```python
from azure.ai.ml import command

job = command(
    code="./src",
    command="pip install uv && uv pip install --system azure-identity mlflow && python models/train.py",
    environment="AzureML-sklearn-1.5@latest",
    compute="gpu-cluster",
)
```

---

## ADLS Gen2 (Azure Data Lake Storage)

### Git과의 관계

ADLS Gen2의 **데이터 파일은 Git에 포함하지 않습니다**.

```gitignore
# .gitignore
*.csv
*.parquet
*.xlsx
data/
raw/
```

### 데이터 레이크 구조

```
ADLS Gen2
├── raw/       ← ADF가 적재 (원본 데이터)
├── curated/   ← Databricks가 생성 (전처리 완료)
└── feature/   ← Databricks가 생성 (ML용 피처)
```

### vault_manager로 접근

```python
from utils.vault_manager import vault

# 일반 환경 (ADF, ML Studio)
client = vault.get_storage_client()
file_system = client.get_file_system_client("raw")

# Databricks 환경
vault.get_storage_client()  # 자동으로 Spark conf 설정
df = spark.read.parquet("abfss://curated@account.dfs.core.windows.net/data/")
```

---

## Azure Database for PostgreSQL

### Git과의 관계

PostgreSQL의 스키마 변경은 **마이그레이션 스크립트**로 관리합니다.

```
src/
└── migrations/           ← SQL 마이그레이션 스크립트
    ├── 001_init.sql
    ├── 002_add_index.sql
    └── ...
```

### vault_manager로 접근

```python
from utils.vault_manager import vault

# psycopg (직접 연결)
conn = vault.get_pg_connection()

# SQLAlchemy (ORM / pandas)
engine = vault.get_pg_connection(engine="sqlalchemy")
df = pd.read_sql("SELECT * FROM results LIMIT 10", engine)
```

### Key Vault 시크릿

| 시크릿 이름 | 용도 |
|---|---|
| `pg-connection-string` | PostgreSQL 연결 문자열 |

연결 문자열 형식:
```
host=<server>.postgres.database.azure.com dbname=<db> user=<user> password=<pass> sslmode=require
```

---

## 서비스별 연동 요약

| 서비스 | Git 연동 | ADLS | PostgreSQL | Key Vault |
|---|---|---|---|---|
| **ADF** | ADF Studio UI | Linked Service | Linked Service | UI 직접 연결 |
| **Databricks** | Repos (Pull/Push) | Spark conf OAuth | JDBC Connector | vault_manager / Secret Scope |
| **ML Studio** | 터미널 Git CLI | vault_manager | vault_manager | DefaultAzureCredential |
| **로컬 개발** | VS Code Git | vault_manager | vault_manager | az login |
