# 06. AI 자동화

## Copilot Instructions

`.github/copilot-instructions.md`는 GitHub Copilot에게 프로젝트의 규칙과 컨텍스트를 알려주는 파일입니다.

### 설정 위치

```
.github/
└── copilot-instructions.md   ← Copilot이 자동으로 읽음
```

### 우리 프로젝트의 Instructions

현재 설정된 주요 내용:

```markdown
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
```

### Copilot이 자동으로 따르는 것들

| 항목 | 효과 |
|---|---|
| 브랜치 전략 | `dev` 기반 작업, PR 생성 |
| 커밋 메시지 | `type(scope): description` 형식 |
| 보안 규칙 | 시크릿·데이터 파일 커밋 방지 |
| 프로젝트 구조 | 올바른 디렉토리에 파일 생성 |

---

## CODEOWNERS

`.github/CODEOWNERS` 파일로 PR 생성 시 자동으로 Reviewer를 할당합니다.

### 설정 방법

1. **GitHub Organization에서 팀 생성**
2. **`.github/CODEOWNERS` 작성:**

```
# 모든 파일 — 팀 전체가 reviewer
* @3dt-project-team/team

# 경로별 특화 reviewer (선택)
adf/**          @3dt-project-team/data-engineers
src/models/**   @3dt-project-team/ml-engineers
docs/**         @3dt-project-team/team
```

3. **Branch Rules에서 활성화:**
   - Settings → Branches → Rules
   - **Require review from Code Owners** 체크

### 동작 흐름

```
PR 생성 → CODEOWNERS 자동 매칭 → Reviewer 자동 할당 → 알림 발송
```

---

## Codex / Agentic Coding Instruction

AI 코딩 에이전트(Codex, Copilot Agent)에게 Git 규칙을 명시적으로 전달하는 instruction입니다.

### Codex용 Instruction

```
You are an agentic coding assistant for this repository.
You MUST follow our Git conventions exactly.

Branch rules:
  - Default branch is dev. NEVER push directly to dev. Always use PRs.
  - Create a working branch per task/issue using: type/short-description
  - Allowed types: feat, fix, hotfix, chore, refactor, docs

Commit rules:
  - Format: type(scope): short description
  - Allowed scopes: api, function, pipeline, db, infra, ci, auth, config, guide
  - Allowed types: feat, fix, hotfix, chore, refactor, docs
  - Keep description under 50 chars, lowercase, no period

PR rules:
  - Title: [Type] 한국어 설명
  - Body must include: Summary, Changes, Test, Related sections
  - Reference the related issue: Closes #번호

Security:
  - NEVER hardcode secrets, API keys, or connection strings
  - Use vault_manager.get_secret() for all credentials
  - NEVER commit .env, data files, or credentials
```

### Copilot Workspace 활용

GitHub Copilot Workspace는 Issue → 코드 변경을 자동화합니다:

```
1. Issue 작성 (요구사항 명확히 기술)
2. Copilot Workspace가 변경 계획 생성
3. 개발자가 계획 리뷰 및 수정
4. Copilot이 코드 변경 실행
5. PR 자동 생성
```

---

## 자동화 조합 요약

```
개발자 코드 작성
       │
       ▼
  [git commit]
       │
       ├── pre-commit ──── ruff lint + format
       ├── pre-commit ──── detect-secrets
       └── commit-msg ──── commitlint
       │
       ▼
  [git push]
       │
       ▼
  [PR 생성]
       │
       ├── CODEOWNERS ──── Reviewer 자동 할당
       ├── GitHub Actions ── CI (lint + test + build)
       └── Branch Protection ── CI 통과 + 승인 필수
       │
       ▼
  [Merge]
       │
       └── GitHub Actions ── CD (Docker build + ACR push + 배포)
```

---

## 설정 파일 체크리스트

| 파일 | 역할 | 상태 |
|---|---|---|
| `.github/copilot-instructions.md` | Copilot 프로젝트 규칙 | ✅ 설정됨 |
| `.github/CODEOWNERS` | Reviewer 자동 할당 | ⬜ 설정 필요 |
| `.pre-commit-config.yaml` | pre-commit hooks | ✅ 설정됨 |
| `commitlint.config.js` | 커밋 메시지 규칙 | ⬜ 설정 필요 |
| `.github/workflows/ci.yml` | CI 파이프라인 | ⬜ 설정 필요 |
| `.github/workflows/cd.yml` | CD 파이프라인 | ⬜ 설정 필요 |
