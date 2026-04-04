# 05. pre-commit 설정 가이드

## 개요

**pre-commit**은 `git commit` 시 자동으로 린트, 포맷, 시크릿 감지 등을 실행하는 도구입니다.
팀 전체가 동일한 코드 품질 기준을 유지할 수 있습니다.

---

## 설치

```bash
# 이미 pyproject.toml dev 의존성에 포함
uv sync

# Git Hook 등록 (최초 1회, 반드시 실행)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

> ⚠️ `pre-commit install`을 실행해야 `.git/hooks/`에 Hook이 등록됩니다.
> 새 팀원은 `uv sync` 후 반드시 이 명령을 실행해야 합니다.

---

## 설정 파일

프로젝트 루트의 `.pre-commit-config.yaml`:

```yaml
repos:
  # ──────────────────────────────────────────────
  # ruff: 린트 + import 정렬 + 포맷 (Rust 기반, 빠름)
  # ──────────────────────────────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]           # 자동 수정 가능한 항목은 fix
      - id: ruff-format         # black 호환 포맷팅

  # ──────────────────────────────────────────────
  # detect-secrets: 하드코딩된 시크릿 감지
  # ──────────────────────────────────────────────
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

  # ──────────────────────────────────────────────
  # commitlint: 커밋 메시지 규칙 검증
  # ──────────────────────────────────────────────
  - repo: https://github.com/alessandrojcm/commitlint-pre-commit-hook
    rev: v9.18.0
    hooks:
      - id: commitlint
        stages: [commit-msg]
        additional_dependencies: ['@commitlint/config-conventional']
```

---

## Hook별 설명

### 1. ruff (린트 + import 정렬)

```bash
# 수동 실행
uv run ruff check src/ --fix
uv run ruff format src/
```

| 규칙 | 설명 |
|---|---|
| `E` | PEP 8 스타일 오류 |
| `F` | Pyflakes (미사용 변수, import 등) |
| `I` | isort (import 정렬) |

### 2. ruff-format (포맷팅)

black과 호환되는 코드 포맷팅을 수행합니다.
`pyproject.toml`의 `[tool.ruff]` 설정을 따릅니다:

```toml
[tool.ruff]
line-length = 100
```

### 3. detect-secrets (시크릿 감지)

```bash
# baseline 초기 생성 (최초 1회)
uv run detect-secrets scan > .secrets.baseline

# baseline 감사 (false positive 제거)
uv run detect-secrets audit .secrets.baseline
```

감지되는 패턴:
- API 키, 토큰, 비밀번호
- Base64 인코딩된 시크릿
- Azure 연결 문자열

### 4. commitlint (커밋 메시지 검증)

커밋 메시지가 Conventional Commits 형식인지 확인합니다.

```bash
# ✅ 통과
feat(api): add user endpoint
fix(db): correct index

# ❌ 차단
Add user endpoint         # type 없음
FEAT: add user endpoint   # 대문자
feat: add.                # 마침표
```

commitlint 설정 파일 (`commitlint.config.js`):

```javascript
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'scope-enum': [2, 'always', [
      'api', 'function', 'pipeline', 'db', 'infra',
      'ci', 'auth', 'config', 'guide'
    ]],
  },
};
```

---

## 실행 흐름

### 자동 실행 (commit 시)

```
git add .
git commit -m "feat(api): add endpoint"
      │
      ▼
  [pre-commit stage]
      ├── ruff ──────── ✅ Passed (auto-fixed 2 files)
      ├── ruff-format ── ✅ Passed
      └── detect-secrets ── ✅ Passed
      │
      ▼
  [commit-msg stage]
      └── commitlint ── ✅ "feat(api): add endpoint" 규칙 통과
      │
      ▼
  커밋 완료 ✅
```

### 수동 실행 (전체 파일)

```bash
# 모든 파일에 대해 실행
uv run pre-commit run --all-files

# 특정 hook만 실행
uv run pre-commit run ruff --all-files
uv run pre-commit run detect-secrets --all-files
```

---

## 새 팀원 온보딩 체크리스트

```bash
# 1. 의존성 설치
uv sync

# 2. pre-commit hook 등록
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

# 3. 전체 파일 검사 (첫 실행 시 캐시 생성)
uv run pre-commit run --all-files
```

---

## 트러블슈팅

| 문제 | 해결 |
|---|---|
| Hook이 실행되지 않음 | `uv run pre-commit install` 재실행 |
| commitlint가 node 관련 에러 | Node.js 16+ 설치 확인 |
| detect-secrets false positive | `.secrets.baseline` 에서 해당 항목을 audit → mark false |
| ruff가 파일을 수정했지만 커밋 실패 | 수정된 파일을 `git add` 후 재커밋 |
