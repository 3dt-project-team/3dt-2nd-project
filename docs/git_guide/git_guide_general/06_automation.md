# 06. 자동화 (Automation)

## Git Hooks

Git Hook은 특정 Git 이벤트(commit, push 등) 발생 시 자동으로 실행되는 스크립트입니다.

### 주요 Hook

| Hook | 실행 시점 | 용도 |
|---|---|---|
| `pre-commit` | `git commit` 직전 | 린트, 포맷, 시크릿 감지 |
| `commit-msg` | 커밋 메시지 작성 후 | 메시지 규칙 검증 (commitlint) |
| `pre-push` | `git push` 직전 | 테스트 실행 |

---

## pre-commit 프레임워크

**pre-commit**은 Python 기반의 Git Hook 관리 도구입니다.
`.pre-commit-config.yaml` 파일 하나로 팀 전체의 Hook을 통일할 수 있습니다.

### 왜 pre-commit인가?

| 도구 | 언어 | 특징 |
|---|---|---|
| **pre-commit** ✅ | Python | 언어 무관, 거대 생태계, 선언적 YAML |
| Husky | Node.js | npm 프로젝트에서 인기, JavaScript 생태계 |
| lefthook | Go | 빠른 실행, Go 바이너리 |

우리 팀은 **Python 프로젝트**이므로 pre-commit이 가장 자연스럽습니다.

### 설치 및 활성화

```bash
# uv로 설치 (이미 dev 의존성에 포함)
uv sync

# Git Hook 등록 (최초 1회)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

# 전체 파일에 대해 수동 실행
uv run pre-commit run --all-files
```

### 설정 파일 예시

```yaml
# .pre-commit-config.yaml
repos:
  # ruff — 린트 + import 정렬
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # detect-secrets — 하드코딩된 시크릿 감지
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

  # commitlint — 커밋 메시지 규칙 검증
  - repo: https://github.com/alessandrojcm/commitlint-pre-commit-hook
    rev: v9.18.0
    hooks:
      - id: commitlint
        stages: [commit-msg]
        additional_dependencies: ['@commitlint/config-conventional']
```

### 동작 흐름

```
git commit -m "feat(api): add endpoint"
      │
      ▼
  pre-commit hook 실행
      │
      ├── ruff ──────── 린트 + 자동 수정
      ├── ruff-format ── 포맷팅
      └── detect-secrets ── 시크릿 감지
      │
      ▼
  commit-msg hook 실행
      │
      └── commitlint ── "feat(api): add endpoint" ✅ 규칙 통과
      │
      ▼
  커밋 완료 ✅
```

---

## AI 자동화

### Copilot Instructions

`.github/copilot-instructions.md` 파일로 Copilot에게 프로젝트 규칙을 알려줄 수 있습니다.

```markdown
# Project Guidelines

## Repository Workflow
- Use GitHub Flow only.
- Never commit directly to dev.
- Open a PR for all merges to dev.

## Commit Conventions
- Use Conventional Commit prefixes: feat, fix, docs, refactor.
- PR title format: [Feat] OOO 기능 추가.
```

### Codex / Agentic Coding용 Instruction

AI 코딩 에이전트에게 Git 규칙을 명시하면 자동으로 컨벤션을 따릅니다:

```
You are an agentic coding assistant for this repository.
You MUST follow our Git conventions exactly.

Branch rules:
  - Default branch is dev. NEVER push directly to dev. Always use PRs.
  - Create a working branch per task using: type/short-description
  - Allowed types: feat, fix, hotfix, chore, refactor, docs

Commit rules:
  - Format: type(scope): short description
  - Allowed scopes: api, function, pipeline, db, infra, ci, auth, config

PR rules:
  - Title: [Type] 한국어 설명
  - Include Summary, Changes, Test, Related sections
  - Reference the related issue: Closes #번호
```

---

## 다음 단계

자동화를 익혔다면 → [07_advanced.md](07_advanced.md) 에서 고급 Git 기법을 학습하세요.
