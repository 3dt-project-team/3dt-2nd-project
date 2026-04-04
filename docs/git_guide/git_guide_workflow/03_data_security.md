# 03. 데이터 보안 (Data Security)

## 원칙

1. **시크릿은 코드에 절대 포함하지 않는다**
2. **데이터 파일은 Git에 커밋하지 않는다**
3. **모든 자격 증명은 Azure Key Vault로 중앙 관리한다**

---

## .gitignore 전략

프로젝트 `.gitignore`에 다음 패턴이 설정되어 있습니다:

```gitignore
# === 환경 변수 / 시크릿 ===
.env
.env.*
!.env.example          # 템플릿은 커밋 허용

# === 데이터 파일 ===
*.csv
*.parquet
*.xlsx
*.json.gz
data/
raw/

# === Python ===
__pycache__/
*.py[cod]
.venv/

# === MLflow ===
mlruns/
mlartifacts/

# === IDE ===
.idea/
```

### 이미 커밋된 파일 제거

```bash
# 실수로 커밋한 파일을 추적에서 제거 (파일은 로컬에 유지)
git rm --cached .env
git rm --cached -r data/
git commit -m "fix(config): remove tracked secrets and data files"
```

---

## Azure Key Vault 시크릿 관리

### vault_manager 아키텍처

```
DefaultAzureCredential
       │
       ├─ 로컬    : az login
       └─ 클라우드 : Managed Identity
              │
              ▼
        Azure Key Vault ({your-kv-name})
         ├─ adls-account-name
         ├─ adls-client-id / adls-client-secret / adls-tenant-id
         └─ pg-connection-string
```

### 시크릿 목록

| 시크릿 이름 | 용도 | 사용 서비스 |
|---|---|---|
| `adls-account-name` | ADLS 스토리지 계정 이름 | 전체 |
| `adls-client-id` | Service Principal 클라이언트 ID | Databricks |
| `adls-client-secret` | Service Principal 시크릿 | Databricks |
| `adls-tenant-id` | Azure AD 테넌트 ID | Databricks |
| `pg-connection-string` | PostgreSQL 연결 문자열 | ADF, Databricks, ML Studio |

### 시크릿 접근 코드

```python
from utils.vault_manager import vault

# 개별 시크릿 조회
account = vault.get_secret("adls-account-name")

# 모든 시크릿 조회 (캐시됨)
all_secrets = vault.get_all_secrets()
```

---

## .env 파일 관리

### .env.example (Git에 포함 — 템플릿)

```bash
# .env.example — 이 파일은 Git에 포함됩니다
KEY_VAULT_URL=https://your-keyvault-name.vault.azure.net/
ADLS_ACCOUNT_NAME=
PG_CONNECT_TIMEOUT_SECONDS=5
```

### .env (Git에 절대 포함 않음 — 실제 값)

```bash
# .env — .gitignore에 의해 제외됩니다
KEY_VAULT_URL=https://{your-kv-name}.vault.azure.net/
ADLS_ACCOUNT_NAME={your-adls-account-name}
PG_CONNECT_TIMEOUT_SECONDS=5
```

### 새 팀원 온보딩

```bash
cp .env.example .env
# .env 파일에 실제 Key Vault URL 입력
az login
uv run python src/utils/vault_manager.py  # 연결 테스트
```

---

## detect-secrets (시크릿 감지)

`detect-secrets`는 코드에 하드코딩된 시크릿을 **자동으로 감지**합니다.

### 초기 설정

```bash
# baseline 파일 생성 (최초 1회)
uv run detect-secrets scan > .secrets.baseline

# 이미 알려진 시크릿을 baseline에서 감사
uv run detect-secrets audit .secrets.baseline
```

### pre-commit 연동

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/Yelp/detect-secrets
  rev: v1.5.0
  hooks:
    - id: detect-secrets
      args: ['--baseline', '.secrets.baseline']
```

### 동작 방식

```
git commit 시 → detect-secrets hook 실행
  │
  ├─ 새로 추가된 시크릿 패턴 감지 → ❌ 커밋 차단
  └─ baseline에 있는 항목 → ✅ 통과 (이미 감사 완료)
```

---

## 체크리스트

- [ ] `.gitignore`에 `.env`, `data/`, `*.csv`, `*.parquet` 포함
- [ ] `.env.example`에 키 이름만 기재 (값은 비워둠)
- [ ] 모든 시크릿은 Key Vault에 저장
- [ ] `detect-secrets` baseline 생성
- [ ] pre-commit에 detect-secrets hook 등록
- [ ] PR 리뷰 시 하드코딩된 시크릿 확인
