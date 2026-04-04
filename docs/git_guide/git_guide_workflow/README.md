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
