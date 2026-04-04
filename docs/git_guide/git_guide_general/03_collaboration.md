# 03. 협업 (Collaboration)

## Pull Request (PR)

PR은 "내 브랜치의 변경을 `dev`에 합쳐달라"는 요청입니다.
코드 리뷰, 자동 테스트, 토론이 모두 PR 안에서 이루어집니다.

### PR 작성 템플릿

```markdown
<!--
PR 제목 규칙: type(scope): description
예) feat(function): add eventhub trigger
-->

## Summary
<!-- 한 줄: 무엇을 왜 변경했는지 -->
- 

## Changes
<!-- 핵심 변경 2~5개 -->
- 
- 

## Test
<!-- 실행한 테스트/확인 (없으면 N/A) -->
- N/A

## Related
<!-- 이슈 자동 종료: Closes #번호 -->
- Closes #
```

### PR 규칙

| 규칙 | 설명 |
|---|---|
| 제목 형식 | `[Feat] OOO 기능 추가` 또는 `type(scope): description` |
| 리뷰어 | 최소 **1명** 승인 필수 |
| CI 통과 | GitHub Actions 체크가 통과해야 merge 가능 |
| 문제 기술 | PR 설명에 "어떤 문제를 해결했는지" 반드시 포함 |
| 테스트 방법 | "어떻게 테스트했는지" 기술 |

---

## Code Review

### Reviewer가 해야 할 일

1. **GitHub 앱에서 알림 켜기** — Reviewer로 지정되면 빠르게 확인
2. PR의 **Files changed** 탭에서 코드 diff 확인
3. 인라인 코멘트로 피드백 남기기
4. 최종 판단: **Approve** / **Request changes** / **Comment**

### 좋은 리뷰 체크리스트

- [ ] 로직에 버그가 없는가?
- [ ] 네이밍이 명확한가? (변수, 함수, 클래스)
- [ ] 불필요한 코드(데드 코드)가 없는가?
- [ ] 보안 이슈는 없는가? (하드코딩된 시크릿 등)
- [ ] 기존 코드와 스타일이 일관적인가?

> 참고 자료: [GitHub PR Review 가이드](https://nashs789.tistory.com/157)

---

## CODEOWNERS

`CODEOWNERS` 파일을 설정하면 PR 생성 시 **자동으로 Reviewer가 할당**됩니다.

### 설정 방법

1. GitHub Organization에서 팀 생성
2. `.github/CODEOWNERS` 파일 작성

```
# 모든 파일에 대해 팀 전체를 reviewer로 지정
* @3dt-project-team/team
```

3. Branch Rules에서 **Require review from Code Owners** 체크

### 특정 경로별 오너 설정

```
# Azure 관련 코드
adf/**          @3dt-project-team/data-engineers
src/models/**   @3dt-project-team/ml-engineers

# 문서
docs/**         @3dt-project-team/team
```

---

## 충돌 해결 (Merge Conflict)

두 브랜치가 같은 파일의 같은 부분을 수정하면 충돌이 발생합니다.

### 충돌 해결 순서

```bash
# 1. dev 최신화
git checkout dev
git pull origin dev

# 2. 작업 브랜치로 돌아가서 dev merge
git checkout feat/my-feature
git merge dev

# 3. 충돌 표시된 파일 수정
#    <<<<<<< HEAD (내 변경)
#    =======
#    >>>>>>> dev  (dev의 변경)

# 4. 수정 완료 후 add + commit
git add .
git commit -m "fix: resolve merge conflict with dev"

# 5. push
git push origin feat/my-feature
```

### VS Code에서 충돌 해결

VS Code는 충돌 발생 시 시각적 인터페이스를 제공합니다:
- **Accept Current Change** — 내 변경 유지
- **Accept Incoming Change** — dev의 변경 수용
- **Accept Both Changes** — 둘 다 포함
- **Compare Changes** — 나란히 비교

---

## Branch Protection 설정

`dev` 브랜치를 보호하려면 GitHub에서 Branch Rules를 설정합니다.

### 설정 순서

1. **Settings → Branches → Rules** 선택
2. RuleSet 이름 지정 (예: `Protect dev branch`)
3. **Enforcement status** → Active
4. **Target Branches** → Include default branch
5. **Branch Rules** 체크:

| 규칙 | 설명 |
|---|---|
| Require a pull request before merging | dev 직접 push 금지 |
| Require approvals (1+) | 최소 1명 승인 |
| Require status checks to pass | CI 통과 필수 |
| Do not allow force pushes | force push 금지 |
| Do not allow deletions | 브랜치 삭제 금지 |

> 이 설정들은 **dev 직접 push ❌**, **PR 없이 merge ❌**, **CI 실패하면 merge ❌**, **force push ❌** 를 강제합니다.

---

## GitHub Projects (칸반 보드)

Issue와 PR을 칸반 보드로 시각화하여 프로젝트를 관리합니다.

### 보드 생성

1. GitHub → Projects → New project → **Board** 선택

### 칸반 컬럼

| Column | 의미 | 전환 방식 |
|---|---|---|
| **Backlog** | 해야 할 일 | 자동 (Issue 생성 시) |
| **In Progress** | 작업 중 | 수동 |
| **In Review** | PR 올라간 상태 | 수동 |
| **Done** | merge + 배포 완료 | 자동 (PR merge 시) |

### 자동화 설정

- Issue가 생성되면 → Backlog에 자동 추가
- PR이 merge되면 → Done으로 자동 이동

---

## 다음 단계

협업 방법을 익혔다면 → [04_commit_conventions.md](04_commit_conventions.md) 에서 커밋 메시지 규칙을 학습하세요.
