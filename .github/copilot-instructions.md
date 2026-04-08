# Project Guidelines

## Source Of Truth
- 아키텍처 및 서비스 구조: docs/architecture.md
- uv 통합 가이드: docs/uv_integration_guide.md
- Git 가이드: docs/git_guide/

## Repository Workflow
- Use GitHub Flow only.
- Never commit directly to dev.
- Create feature branches with pattern: type/name-task.
- Open a PR for all merges to dev.

## Commit And PR Conventions
- Use Conventional Commit prefixes: feat, fix, docs, refactor.
- PR title format: [Feat] OOO 기능 추가.

## Data And Security Rules
- Do not commit data files such as csv/parquet to Git.
- Do not commit secrets or env files.