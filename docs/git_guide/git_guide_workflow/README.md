# Git Guide — Project Workflow

**3DT 2nd Project**에 특화된 Git 워크플로우 가이드입니다.
범용 Git 지식은 [git_guide_general/](../git_guide_general/README.md)를 먼저 참고하세요.

---

## 가이드 인덱스

| 순서 | 문서 | 핵심 키워드 |
|:---:|---|---|
| 1 | [01_project_github_flow.md](01_project_github_flow.md) | 브랜치 네이밍, dev→main 머지 전략, Issue-first |
| 2 | [02_azure_service_git.md](02_azure_service_git.md) | ADF, Databricks Repos, ML Studio, ADLS, PostgreSQL |
| 3 | [03_data_security.md](03_data_security.md) | .gitignore, KV 시크릿, detect-secrets, .env |
| 4 | [04_cicd_project.md](04_cicd_project.md) | Azure Container Apps, GitHub Actions, ACR |
| 5 | [05_precommit_setup.md](05_precommit_setup.md) | ruff, black, detect-secrets, commitlint |
| 6 | [06_ai_automation.md](06_ai_automation.md) | Copilot Instructions, CODEOWNERS, Copilot Workspace |

---

## 프로젝트 기술 스택

| 카테고리 | 기술 |
|---|---|
| **언어** | Python 3.11 |
| **패키지 매니저** | uv (Rust 기반) |
| **데이터 수집** | Azure Data Factory |
| **데이터 처리** | Azure Databricks |
| **ML 학습** | Azure ML Studio v2 |
| **데이터 레이크** | ADLS Gen2 |
| **데이터베이스** | Azure Database for PostgreSQL |
| **시크릿 관리** | Azure Key Vault |
| **CI/CD** | GitHub Actions + ACR |
| **Linter / Formatter** | ruff + black |
| **Type Checker** | ty (Astral, alpha) |
| **Git Hooks** | pre-commit |

---

## 리소스별 작업 흐름

### 공통 루틴 (매일 작업 시작)

```bash
git checkout dev
git pull origin dev
# Issue 생성 → 브랜치 생성 → 작업 → 커밋 → push → PR
git checkout -b feat/내-작업-내용
```

---

### 로컬 (VS Code)

```
dev 최신화 → 브랜치 생성 → 코드 작업
→ git add / commit (pre-commit 자동 실행)
→ git push origin feat/...
→ GitHub PR → 1명 Approve → Squash merge → 브랜치 자동 삭제
```

- 커밋 전 `uv run pre-commit run --all-files`로 수동 확인 가능
- 커밋 메시지: `type(scope): 설명` (예: `feat(pipeline): add eventhub trigger`)

---

### ADF (Azure Data Factory)

```
ADF Studio 접속 → 좌측 상단 브랜치 선택 (feature 브랜치)
→ 파이프라인 편집 → Save (= Git commit 자동)
→ GitHub PR → dev merge
→ ADF Studio에서 dev 브랜치로 전환 → Publish
```

- **같은 파이프라인 동시 편집 금지** — 작업 전 팀 채팅으로 조율
- Publish는 반드시 **dev 브랜치**에서

---

### Databricks

```
Repos 탭 → feature 브랜치로 체크아웃 → Pull (최신화)
→ Notebook 작업 → Commit & Push (Repos UI)
→ GitHub PR → dev merge → Databricks에서 Pull
```

- 복잡한 변경은 로컬 VS Code에서 push → Databricks에서 Pull
- `sys.path.insert(0, "/Workspace/Repos/3dt-2nd-project/src")` 후 `from utils.vault_manager import vault` 사용

---

### ML Studio

```
Compute Instance 터미널:
git checkout dev → git pull → git checkout -b feat/...
→ 학습 스크립트 작업 → uv sync --extra ml
→ git commit (커밋 해시 MLflow 태깅) → git push → GitHub PR
```

- 실험 트래킹 시 Git 커밋 해시를 MLflow에 태깅해 재현성 확보
  ```python
  mlflow.set_tag("git_commit", subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip())
  ```
