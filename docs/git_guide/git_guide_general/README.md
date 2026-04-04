# Git Guide — General

팀원 전체가 참고하는 **범용 Git 가이드**입니다.
프로젝트에 특화된 워크플로우는 [git_guide_workflow/](../git_guide_workflow/README.md)를 참고하세요.

> 📌 `notion_archive/` 에는 이전 Notion에서 export한 원본 파일이 보관되어 있습니다.
> 아래 가이드는 해당 내용을 100 % 포함하면서 체계적으로 재구성한 버전입니다.

---

## 학습 로드맵

| 순서 | 문서 | 핵심 키워드 |
|:---:|---|---|
| 1 | [01_git_fundamentals.md](01_git_fundamentals.md) | init, clone, add, commit, push, pull, 3-area 모델 |
| 2 | [02_branch_strategy.md](02_branch_strategy.md) | GitHub Flow, Git Flow, feature/hotfix 패턴 |
| 3 | [03_collaboration.md](03_collaboration.md) | PR, Code Review, 충돌 해결, CODEOWNERS |
| 4 | [04_commit_conventions.md](04_commit_conventions.md) | Conventional Commits, scope 표, commitlint |
| 5 | [05_cicd_fundamentals.md](05_cicd_fundamentals.md) | GitHub Actions, ACR + Docker, AKS + Terraform |
| 6 | [06_automation.md](06_automation.md) | pre-commit, Git Hooks, AI 자동화 |
| 7 | [07_advanced.md](07_advanced.md) | rebase, cherry-pick, stash, reflog, submodule |

---

## 권장 학습 순서

```
01 기초 ─── 02 브랜치 ─── 03 협업 ─── 04 커밋 규칙
                                          │
                              05 CI/CD ◄──┘
                                │
                          06 자동화 ─── 07 고급
```

Git을 처음 접한다면 01 → 02 → 03 → 04 순서로 읽고,
CI/CD와 자동화는 프로젝트 세팅 후에 필요할 때 참고하세요.
