# 01. 프로젝트 GitHub Flow

## 우리 팀의 브랜치 전략

```
main ─────────────────────────────── 프로덕션 (안정)
  │
  └── dev ────────────────────────── 개발 통합 (기본 브랜치)
        │
        ├── feat/add-eventhub       ← 기능 개발
        ├── fix/partition-key       ← 버그 수정
        ├── docs/git-guide          ← 문서 작업
        ├── set/issue_template      ← 초기 설정
        └── chore/update-deps       ← 의존성·설정
```

### 핵심 규칙

1. **기본 브랜치 = `dev`** (main이 아님)
2. **dev 직접 push 금지** — 반드시 PR 사용
3. **Issue 먼저 생성 → 브랜치 생성** (Issue-first 원칙)
4. **PR merge 후 브랜치 자동 삭제**
5. **main은 안정 버전 릴리스 시에만 merge**

---

## 일일 작업 루틴

### 1. 매일 작업 시작

```bash
# 현재 브랜치 확인
git branch

# dev로 이동 후 최신화
git checkout dev
git pull origin dev
```

### 2. Issue 생성 → 브랜치 생성

```bash
# GitHub에서 Issue 생성 (Feature 또는 Bug 템플릿)
# Issue 번호 확인 (예: #42)

# 브랜치 생성
git checkout -b feat/add-eventhub-trigger
```

### 3. 작업 + 커밋

```bash
# 의미 단위로 커밋 (작은 단위 권장)
git add .
git commit -m "feat(function): add eventhub trigger handler"

# 추가 작업 후 또 커밋
git add .
git commit -m "feat(function): add retry logic for eventhub"
```

### 4. Push + PR

```bash
# 원격에 push
git push origin feat/add-eventhub-trigger

# GitHub에서 PR 생성
#   제목: [Feat] EventHub 트리거 핸들러 추가
#   본문: Summary, Changes, Test, Related (Closes #42)
```

### 5. 리뷰 + Merge

- 최소 1명 Approve 후 merge
- **Squash merge** 권장 (커밋 히스토리 정리)
- merge 후 브랜치 자동 삭제

---

## 브랜치 네이밍 규칙

### 형식

```
type/short-description
```

### 팀 허용 type

| type | 의미 | 예시 |
|---|---|---|
| `feat` | 기능 추가 | `feat/add-eventhub-trigger` |
| `fix` | 버그 수정 | `fix/partition-key-error` |
| `hotfix` | 긴급 수정 | `hotfix/prod-timeout` |
| `chore` | 설정·의존성 | `chore/update-ci-workflow` |
| `refactor` | 구조 개선 | `refactor/split-vault-module` |
| `docs` | 문서 수정 | `docs/git-guide-restructure` |
| `set` | 초기 설정 | `set/issue_template` |

### 규칙

- **소문자**만 사용
- 공백 대신 **하이픈(`-`)** 사용
- **짧고 의미 있게** (3~5단어)

---

## Issue 템플릿

### Feature

```yaml
name: "Feature"
description: 기능 개발
title: "feat(scope): "
labels: ["feature"]
body:
  - type: textarea
    id: description
    attributes:
      label: Description
      placeholder: 무엇을 변경하는지 간단히 작성
    validations:
      required: true
```

### Bug

```yaml
name: "Bug"
description: 버그 수정
title: "fix(scope): "
labels: ["bug"]
body:
  - type: textarea
    id: problem
    attributes:
      label: What happened?
      placeholder: 어떤 문제가 발생했는가?
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
      placeholder: 정상 동작은 무엇인가?
```

---

## PR 규칙

### 제목 형식

```
[Type] 한국어 설명
```

예시: `[Feat] EventHub 트리거 파이프라인 추가`

### 본문 템플릿

```markdown
## Summary
- EventHub 트리거 핸들러를 추가하여 실시간 이벤트 처리

## Changes
- src/functions/eventhub.py: 트리거 핸들러 구현
- pyproject.toml: azure-functions 의존성 추가

## Test
- 로컬에서 func start로 트리거 동작 확인

## Related
- Closes #42
```

### PR 체크리스트

- [ ] 커밋 메시지가 `type(scope): description` 형식인가?
- [ ] PR 제목이 `[Type] 설명` 형식인가?
- [ ] 관련 Issue가 연결되어 있는가?
- [ ] 린트/포맷 검사를 통과했는가?

---

## dev → main 머지 전략

`main`은 안정된 프로덕션 코드만 포함합니다.

### 머지 조건

1. dev에서 충분한 테스트 완료
2. 팀 전체 합의 (회의 또는 Slack)
3. Release PR 생성 → 최소 2명 Approve
4. `main`에 merge 후 태그 생성

```bash
# Release 태그
git tag -a v1.0.0 -m "Release: 데이터 파이프라인 v1"
git push origin v1.0.0
```
