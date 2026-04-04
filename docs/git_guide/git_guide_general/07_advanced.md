# 07. 고급 Git (Advanced)

## rebase vs merge

두 브랜치를 합치는 두 가지 방법입니다.

### merge

```bash
git checkout dev
git merge feat/my-feature
```

```
dev:     A ── B ── C ─────── M (merge commit)
                  \         /
feature:           D ── E ─┘
```

- **장점**: 히스토리 보존 (누가 언제 어떤 브랜치에서 작업했는지)
- **단점**: merge commit이 쌓여 히스토리가 복잡해질 수 있음

### rebase

```bash
git checkout feat/my-feature
git rebase dev
```

```
dev:     A ── B ── C
                    \
feature:             D' ── E' (리베이스된 커밋)
```

- **장점**: 선형 히스토리 (깔끔한 커밋 로그)
- **단점**: 커밋 해시가 변경됨 → 공유 브랜치에서는 위험

### 언제 무엇을 쓸까?

| 상황 | 권장 |
|---|---|
| feature → dev PR merge | **Squash merge** (GitHub PR 설정) |
| 로컬에서 최신 dev 반영 | `git rebase dev` |
| 공유 브랜치 (이미 push됨) | `git merge` (절대 rebase 금지) |

> ⚠️ **Golden Rule**: 이미 push한 커밋은 rebase하지 마세요.
> 다른 사람의 히스토리가 꼬입니다.

---

## cherry-pick

특정 커밋 하나만 다른 브랜치에 가져옵니다.

```bash
# 가져올 커밋의 해시 확인
git log --oneline

# 현재 브랜치에 특정 커밋 적용
git cherry-pick <commit-hash>
```

### 사용 사례

- hotfix 브랜치의 수정을 dev에도 적용
- 다른 feature 브랜치의 유틸 함수 하나만 가져오기

---

## stash

작업 중인 변경을 임시 저장하고 다른 브랜치로 이동할 때 사용합니다.

```bash
# 현재 변경 임시 저장
git stash
git stash -m "WIP: 작업 설명"       # 메시지 포함
git stash -u                        # untracked 파일 포함

# stash 목록 확인
git stash list

# 가장 최근 stash 복원
git stash pop                       # 복원 + 삭제
git stash apply                     # 복원 (삭제 안 함)

# 특정 stash 복원
git stash apply stash@{1}

# stash 삭제
git stash drop stash@{0}
git stash clear                     # 전체 삭제
```

---

## reflog

Git의 모든 HEAD 이동 기록을 보여줍니다. 실수로 삭제한 커밋도 복구할 수 있습니다.

```bash
# HEAD 이동 기록 확인
git reflog

# 출력 예시
# abc1234 HEAD@{0}: commit: feat(api): add endpoint
# def5678 HEAD@{1}: checkout: moving from dev to feat/api
# ghi9012 HEAD@{2}: commit: docs: update readme

# 특정 시점으로 복구
git reset --hard HEAD@{2}
```

> 💡 `git reflog`는 **30일간** 기록을 보관합니다.
> "다 날렸다!" 해도, 30일 이내라면 reflog로 복구할 수 있습니다.

---

## submodule

다른 Git 저장소를 하위 디렉토리로 포함시킬 때 사용합니다.

```bash
# 서브모듈 추가
git submodule add <repo-url> <path>

# 서브모듈 포함해서 클론
git clone --recurse-submodules <repo-url>

# 서브모듈 업데이트
git submodule update --remote
```

### 주의사항

- 서브모듈은 **특정 커밋에 고정**됩니다
- 업데이트하려면 명시적으로 `--remote` 필요
- 팀원 모두가 `--recurse-submodules` 으로 클론해야 함

---

## .gitattributes

파일별로 Git의 동작을 제어합니다.

```gitattributes
# 텍스트 파일 줄바꿈 자동 변환
* text=auto

# 특정 파일은 항상 LF 유지
*.py text eol=lf
*.sh text eol=lf
*.yml text eol=lf

# 바이너리 파일은 diff 하지 않음
*.png binary
*.parquet binary
```

### 왜 필요한가?

- Windows(CRLF)와 macOS/Linux(LF)의 줄바꿈 차이로 인한 불필요한 diff 방지
- 바이너리 파일의 무의미한 diff 방지

---

## 유용한 명령어 모음

```bash
# 특정 파일의 변경 이력
git log --follow <파일명>

# 코드 작성자 확인 (blame)
git blame <파일명>

# 커밋 간 차이
git diff <commit1>..<commit2>

# 마지막 커밋 수정 (아직 push 안 했을 때)
git commit --amend -m "새 메시지"

# 특정 커밋까지 되돌리기 (커밋 히스토리 유지)
git revert <commit-hash>

# 커밋 히스토리 그래프로 보기
git log --oneline --graph --all
```

---

## 가이드 완료

모든 범용 Git 가이드를 학습했습니다!
프로젝트에 특화된 워크플로우는 [git_guide_workflow](../git_guide_workflow/README.md)를 참고하세요.
