# 구현 계획

## 프로젝트 목표
Azure Data Factory, Databricks, ML Studio를 활용한 데이터 파이프라인 구축 및 ML 모델 운영.
데이터 저장소: ADLS Gen2 (레이크) + Azure Database for PostgreSQL (서빙).

---

## M0: GitHub 리포지토리 세팅 (gh CLI)

> `gh` CLI로 자동화 가능한 항목들. 아래 순서대로 실행하면 됨.

### 현재 상태 (업데이트됨)

| 항목 | 상태 | 비고 |
|---|---|---|
| 기본 브랜치 | ✅ `dev` | 완료 |
| dev branch protection | ✅ PR 필수, 1명 Approve, CODEOWNERS, dismiss stale | M0-C 완료 |
| force push 금지 | ✅ 금지 | M0-C 완료 |
| conversation 해결 필수 | ✅ 활성 | M0-C 완료 |
| Squash merge만 허용 | ✅ squash only | M0-B 완료 |
| merge 후 브랜치 자동 삭제 | ✅ 활성 | M0-B 완료 |
| `feature`/`refactor`/`chore` 레이블 | ✅ 추가됨 | M0-A 완료 |
| Issue 템플릿 (Feature/Bug) | ✅ PR #3 pending merge | M0-E — set/github-templates |
| PR 템플릿 | ✅ PR #3 pending merge | M0-E — set/github-templates |
| CODEOWNERS | ✅ PR #3 pending merge | M0-E — set/github-templates |
| main branch protection | ⬜ main 브랜치 없음 | M0-D — 생성 후 적용 필요 |

### M0-A: 레이블 추가/수정

```bash
# feature 레이블 추가 (enhancement는 기본 GitHub 레이블, 팀 컨벤션은 feature)
gh label create "feature" --description "기능 개발" --color "0075ca" \
  --repo 3dt-project-team/3dt-2nd-project

# refactor 레이블 추가
gh label create "refactor" --description "구조 개선 (기능 변화 없음)" --color "e4e669" \
  --repo 3dt-project-team/3dt-2nd-project

# chore 레이블 추가
gh label create "chore" --description "설정·의존성·환경 변경" --color "cfd3d7" \
  --repo 3dt-project-team/3dt-2nd-project
```

### M0-B: Repo 설정 (Squash only + 브랜치 자동 삭제)

```bash
# Squash merge만 허용 + PR merge 후 브랜치 자동 삭제
gh api repos/3dt-project-team/3dt-2nd-project \
  --method PATCH \
  --field allow_squash_merge=true \
  --field allow_merge_commit=false \
  --field allow_rebase_merge=false \
  --field delete_branch_on_merge=true \
  --field squash_merge_commit_title="PR_TITLE" \
  --field squash_merge_commit_message="PR_BODY"
```

### M0-C: Branch Protection 강화 (dev)

```bash
# dev: force push 금지 + conversation 해결 필수 추가
gh api repos/3dt-project-team/3dt-2nd-project/branches/dev/protection \
  --method PUT \
  --field required_status_checks=null \
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"require_code_owner_reviews":true,"dismiss_stale_reviews":true}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false \
  --field required_conversation_resolution=true
```

### M0-D: main Branch Protection 생성

```bash
# main: 더 엄격한 보호 (2명 Approve + CI 필수)
gh api repos/3dt-project-team/3dt-2nd-project/branches/main/protection \
  --method PUT \
  --field required_status_checks=null \
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":2,"require_code_owner_reviews":true,"dismiss_stale_reviews":true}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

### M0-E: Issue 템플릿 + PR 템플릿 + CODEOWNERS 파일 생성

파일 위치: `.github/`

```
.github/
├── ISSUE_TEMPLATE/
│   ├── feature.yml    # [feat] 기능 개발 템플릿
│   └── bug.yml        # [fix] 버그 수정 템플릿
├── PULL_REQUEST_TEMPLATE.md
└── CODEOWNERS
```

> **다음 구현 단계**: PR #3 merge → main 브랜치 생성 후 M0-D 적용

---

## 마일스톤

### M1: 인프라 설정
- [ ] Azure Key Vault 생성 및 시크릿 등록 (`adls-account-name`, `pg-connection-string` 등)
- [ ] ADLS Gen2 컨테이너 구성 (`raw` / `curated` / `feature`)
- [ ] Azure Database for PostgreSQL 스키마 정의
- [ ] Managed Identity 권한 설정 (ADLS, PostgreSQL, Key Vault)

### M2: 데이터 수집 (ADF)
- [ ] Linked Service 연결 구성 (ADLS, PostgreSQL, Key Vault)
- [ ] 원본 데이터 수집 파이프라인 구현 → `adf/` 폴더에 JSON 저장
- [ ] 트리거 설정 (스케줄 또는 이벤트 기반)

### M3: 전처리 (Databricks)
- [ ] 클러스터 Init Script 등록 (`notebooks/init_script_install_uv.sh`)
- [ ] vault_manager 연동 및 ADLS Spark conf 설정
- [ ] 데이터 클렌징·변환 → `curated/` 저장
- [ ] 피처 엔지니어링 → `feature/` 저장

### M4: 모델링 (ML Studio)
- [ ] 컴퓨팅 클러스터 구성
- [ ] Feature 데이터 Datastore 등록
- [ ] 학습 잡 제출 (`src/models/aml_train_example.py` 참고)
- [ ] MLflow 실험 트래킹 + Git commit hash 태깅

### M5: 서빙
- [ ] 예측 결과 Azure Database for PostgreSQL 적재
- [ ] 최종 파이프라인 End-to-End 검증

## 관련 문서
- 아키텍처 개요: [architecture.md](architecture.md)
- uv 통합 가이드: [uv_integration_guide.md](uv_integration_guide.md)
- 협업 규칙: [../docs/git_guide/](git_guide/)
