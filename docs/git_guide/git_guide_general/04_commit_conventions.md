# 04. 커밋 메시지 컨벤션 (Commit Conventions)

## Conventional Commits

팀 전체가 동일한 커밋 메시지 형식을 사용하면 히스토리가 깔끔해지고,
자동 CHANGELOG 생성과 CI 자동화가 가능해집니다.

### 형식

```
type(scope): short description
```

- **소문자**로 시작
- description은 **50자 이내** 권장
- 마침표(`.`) 없이 끝냄

### 예시

```
feat(function): add eventhub trigger
fix(pipeline): resolve partition key error
docs(guide): add git branch strategy
chore(ci): update github actions workflow
refactor(auth): split vault module into sub-functions
```

---

## Type 목록

| type | 의미 | 예시 |
|---|---|---|
| `feat` | 기능 추가 | 새 API 엔드포인트, 새 파이프라인 |
| `fix` | 버그 수정 | 데이터 누락 해결, 에러 핸들링 |
| `hotfix` | 긴급 수정 | 프로덕션 장애 대응 |
| `chore` | 설정·의존성·환경 변경 | pyproject.toml 업데이트, Dockerfile 수정 |
| `refactor` | 구조 개선 (기능 변화 없음) | 함수 분리, 중복 제거 |
| `docs` | 문서 수정 | README 업데이트, 가이드 추가 |

---

## Scope 목록

scope는 **변경하는 범위**를 나타냅니다.

| scope | 의미 |
|---|---|
| `api` | API / Endpoint / Controller |
| `function` | Azure Function |
| `pipeline` | ETL / 배치 / 데이터 처리 로직 |
| `db` | DB 스키마 / 쿼리 / 인덱스 |
| `infra` | Azure 리소스 / IaC / 설정 |
| `ci` | GitHub Actions / 배포 |
| `auth` | 인증 / 권한 |
| `config` | 환경변수 / 설정 파일 |
| `guide` | 문서 / 가이드 |

### scope 사용 예시

```bash
feat(api): add user endpoint
fix(db): correct index on events table
chore(infra): upgrade terraform provider
docs(guide): add commit convention guide
```

---

## PR 제목 규칙

PR 제목은 커밋 메시지와 동일한 형식을 따르되, 대괄호 형식도 허용합니다.

```
# Conventional Commits 형식
feat(pipeline): add eventhub trigger pipeline

# 대괄호 형식
[Feat] EventHub 트리거 파이프라인 추가
```

---

## Issue 제목 규칙

Issue 템플릿에서 자동으로 prefix가 붙습니다.

### Feature Issue

```yaml
name: "Feature"
description: 기능 개발
title: "feat(scope): "
labels: ["feature"]
```

### Bug Issue

```yaml
name: "Bug"
description: 버그 수정
title: "fix(scope): "
labels: ["bug"]
```

### Issue 본문 필수 항목

| 필드 | Feature | Bug |
|---|---|---|
| Description | ✅ 무엇을 변경하는지 | — |
| What happened? | — | ✅ 어떤 문제 발생 |
| Expected behavior | — | ✅ 정상 동작은 무엇 |

---

## commitlint (자동 검증)

커밋 메시지가 규칙에 맞는지 자동으로 검증하는 도구입니다.
`pre-commit` hook과 함께 사용하면 잘못된 커밋 메시지를 방지할 수 있습니다.

```yaml
# .pre-commit-config.yaml 에서 설정 (06_automation.md 참고)
- repo: https://github.com/alessandrojcm/commitlint-pre-commit-hook
  hooks:
    - id: commitlint
      stages: [commit-msg]
```

---

## 다음 단계

커밋 규칙을 익혔다면 → [05_cicd_fundamentals.md](05_cicd_fundamentals.md) 에서 CI/CD 자동화를 학습하세요.
