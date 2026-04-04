# Project Guidelines

## Source Of Truth
- 아키텍처 및 서비스 구조: [docs/architecture.md](docs/architecture.md)
- uv 통합 가이드: [docs/uv_integration_guide.md](docs/uv_integration_guide.md)
- Git 가이드 (범용): [docs/git_guide/git_guide_general/](docs/git_guide/git_guide_general/)
- Git 가이드 (프로젝트 워크플로우): [docs/git_guide/git_guide_workflow/](docs/git_guide/git_guide_workflow/)
- 프로젝트 구성 및 실행: [README.md](README.md)
- Keep this file minimal; do not duplicate long process docs.

## Repository Workflow
- Use GitHub Flow only.
- Never commit directly to main.
- Create feature branches with pattern: type/name-task.
- Open a PR for all merges to main.

## Commit And PR Conventions
- Use Conventional Commit prefixes: feat, fix, docs, refactor.
- PR title format: [Feat] OOO 기능 추가.
- In PR description, include:
  - What problem is solved
  - How to test
  - Related issue (if any)

## Project Structure
- Monorepo structure:
  - adf for ADF pipeline JSON
  - src/utils and src/models for shared Python modules
  - notebooks for EDA and experiments
  - docs for architecture, schema, and meeting notes
  - See [docs/architecture.md](docs/architecture.md) for full data flow.

## Data And Security Rules
- Do not commit data files such as csv/parquet to Git.
- Do not commit secrets or env files.
- Ensure gitignore blocks local data and secret files.
- Database: Azure Database for PostgreSQL (psycopg + SQLAlchemy).
- pre-commit hooks must pass before commit (ruff, detect-secrets). See [docs/git_guide/git_guide_workflow/05_precommit_setup.md](docs/git_guide/git_guide_workflow/05_precommit_setup.md).

## Tool-Specific Collaboration Notes
- Azure Data Factory:
  - Switch to your feature branch before editing.
  - Coordinate in chat before touching the same pipeline to avoid JSON merge conflicts.
  - After merge to dev, publish from ADF dev branch.
- Databricks Repos:
  - Work on feature branches and sync frequently with Pull.
- ML Studio:
  - Use terminal Git workflow.
  - Track Git commit hash in MLflow tags for experiment traceability.

## Build And Test
- This repository is in bootstrap stage.
- If build/test commands are introduced later, add them to README and keep this file linked to README instead of duplicating command details.