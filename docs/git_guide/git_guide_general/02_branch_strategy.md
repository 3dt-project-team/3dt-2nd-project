# 02. 브랜치 전략 (Branch Strategy)

## 브랜치란?

브랜치는 독립적인 작업 라인입니다.
`dev`(또는 `main`) 브랜치에서 새 브랜치를 만들어 작업하고,
작업이 끝나면 PR(Pull Request)을 통해 다시 합칩니다.

---

## GitHub Flow (우리 팀 채택)

가장 단순하고 효과적인 전략입니다.

```
dev (기본 브랜치)
 │
 ├── feat/add-eventhub-trigger   ← 기능 개발
 ├── fix/partition-key-error     ← 버그 수정
 └── hotfix/prod-timeout         ← 긴급 수정
```

### 규칙

1. `dev` 브랜치에 **직접 push 금지** — 반드시 PR 사용
2. 모든 작업은 **Issue 생성 후** 브랜치 생성
3. 브랜치 이름은 `type/short-description` 형식
4. 작업 완료 후 PR merge → **브랜치 자동 삭제**

### GitHub Flow 전체 흐름

```
1. dev 최신화        git pull origin dev
2. 브랜치 생성       git checkout -b feat/my-feature
3. 작업 + 커밋       git add . && git commit
4. 원격에 push       git push origin feat/my-feature
5. PR 생성          GitHub에서 PR 작성
6. 리뷰 + 승인      최소 1명 승인
7. dev에 merge      Squash merge 또는 Merge commit
8. 브랜치 삭제       자동 또는 수동
```

---

## 브랜치 네이밍 컨벤션

### 형식

```
type/short-description
```

- **소문자만** 사용
- 공백 대신 **하이픈(`-`)** 사용
- 짧고 의미 있게 작성

### 허용 type

| type | 의미 | 예시 |
|---|---|---|
| `feat` | 기능 추가 | `feat/add-eventhub-trigger` |
| `fix` | 버그 수정 | `fix/partition-key-error` |
| `hotfix` | 긴급 수정 | `hotfix/prod-timeout` |
| `chore` | 설정·의존성·환경 | `chore/update-ci-workflow` |
| `refactor` | 구조 개선 | `refactor/split-vault-module` |
| `docs` | 문서 수정 | `docs/git-guide-restructure` |
| `set` | 초기 설정 | `set/issue_template` |

---

## Git Flow (참고)

더 복잡한 릴리스 사이클이 필요한 대규모 프로젝트에서 사용합니다.

```
main ──────────────────────────────────────────
  │                                          ▲
  └── develop ──────────────────────────────┐│
        │                                   ││
        ├── feature/xxx ──► develop merge   ││
        │                                   ││
        └── release/1.0 ──► main + develop ─┘│
                                             │
        hotfix/yyy ──────► main + develop ───┘
```

| 브랜치 | 역할 |
|---|---|
| `main` | 프로덕션 릴리스 (태그 관리) |
| `develop` | 개발 통합 브랜치 |
| `feature/*` | 기능 개발 → develop에 merge |
| `release/*` | 릴리스 준비 (QA) → main + develop에 merge |
| `hotfix/*` | 프로덕션 긴급 수정 → main + develop에 merge |

### GitHub Flow vs Git Flow 비교

| 항목 | GitHub Flow | Git Flow |
|---|---|---|
| 복잡도 | 낮음 | 높음 |
| 브랜치 수 | 2~3개 | 5개 이상 |
| 릴리스 관리 | PR merge = 배포 | release 브랜치 별도 |
| 적합 대상 | 소규모 팀, CI/CD 자동화 | 릴리스 주기가 긴 대규모 프로젝트 |
| **우리 팀 선택** | ✅ | — |

---

## 일상 브랜치 명령어

```bash
# 브랜치 목록 확인
git branch              # 로컬
git branch -r           # 원격
git branch -a           # 전체

# 브랜치 생성 + 전환
git checkout -b feat/my-feature

# 브랜치 전환
git checkout dev
git switch dev          # Git 2.23+ 동일

# 브랜치 삭제 (로컬)
git branch -d feat/my-feature       # merge된 브랜치만
git branch -D feat/my-feature       # 강제 삭제

# 원격 브랜치 삭제
git push origin --delete feat/my-feature
```

---

## 다음 단계

브랜치 전략을 이해했다면 → [03_collaboration.md](03_collaboration.md) 에서 PR과 협업 방법을 학습하세요.
