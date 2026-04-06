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
| main branch protection | N/A | dev가 메인 브랜치 — M0-D 불필요 |

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

### M0-D: main Branch Protection — N/A

> `dev`가 기본(메인) 브랜치이므로 별도 `main` 브랜치 보호 설정 불필요.

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

> **다음 구현 단계**: PR #3 merge → M0 완료

---

## M0-F: `gh` CLI로 불가능한 항목 — 수동 설정 필요

아래 항목들은 `gh` CLI가 아닌 **UI 또는 다른 CLI**로 설정해야 합니다.

### 1. GitHub Actions 워크플로우 파일 생성

> `gh` CLI는 파일 생성 불가. git으로 직접 추가.

```bash
# 브랜치 생성 후 워크플로우 파일 작성 → PR
git checkout -b set/github-actions
# .github/workflows/ci.yml 작성 (04_cicd_project.md 참고)
git add .github/workflows/
git commit -m "set(ci): add CI workflow"
git push origin set/github-actions
gh pr create --base dev --title "[Set] GitHub Actions CI 워크플로우 추가"
```

### 2. GitHub Secrets 등록

> `gh secret set`으로 등록 가능하지만, **Secret 값(Service Principal 등)은 Azure에서 먼저 생성** 필요.

```bash
# ① Azure Service Principal 생성 (az CLI)
az ad sp create-for-rbac \
  --name "github-actions-sp" \
  --role contributor \
  --scopes /subscriptions/<subscription-id>/resourceGroups/3dt-2nd-team1 \
  --sdk-auth
# 출력된 JSON을 복사

# ② gh CLI로 Secret 등록
gh secret set AZURE_CREDENTIALS  # 붙여넣기 후 Enter
gh secret set ACR_LOGIN_SERVER    # 예: yourname.azurecr.io
gh secret set ACR_USERNAME
gh secret set ACR_PASSWORD
gh secret set ACR_NAME
```

> 참고: `04_cicd_project.md` → GitHub Secrets 설정 표

### 3. commitlint (Node.js 필요)

> `.pre-commit-config.yaml`에 commitlint 추가 시 **Node.js(npm)가 있어야** 동작.
> 팀 전체 노트북에 Node.js 설치 후 활성화 권장.

```bash
# Node.js 설치 (PowerShell)
winget install OpenJS.NodeJS.LTS

# 설치 확인
node --version    # v20.x.x
npm --version

# pre-commit 재설치 (Node 훅 등록)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

> `.pre-commit-config.yaml`의 commitlint 섹션은 현재 주석 처리 상태 — Node 설치 후 활성화

### 4. ADF Studio Git 연동

> ADF Studio UI에서만 설정 가능 (`gh` CLI 해당 없음).

```
1. ADF Studio (portal.azure.com) → Manage → Git Configuration
2. Repository type: GitHub
3. Org: 3dt-project-team / Repo: 3dt-2nd-project
4. Collaboration branch: dev
5. Root folder: /adf
6. Import existing resources: Yes
```

> 이후 ADF UI에서 저장(Save)하면 자동으로 Git commit. 브랜치 전환도 ADF UI 내에서.

### 5. Databricks Repos 연동

> Databricks Workspace UI에서만 설정 가능.

```
1. Databricks Workspace → Repos 탭
2. Add Repo → GitHub URL 입력:
   https://github.com/3dt-project-team/3dt-2nd-project.git
3. 브랜치: dev (기본값)
4. 작업 시작 전 feature 브랜치로 체크아웃
```

> 클러스터 Init Script도 UI에서: Compute → Edit Cluster → Advanced Options → Init Scripts

### 6. GitHub Projects (칸반 보드)

> `gh project create`로 프로젝트 생성은 가능하지만, **컬럼 자동화(To Do → In Progress 자동 이동 등)는 UI 필요**.

```bash
# CLI로 프로젝트 생성만 가능
gh project create --owner 3dt-project-team --title "3dt-2nd-project 칸반"
```

> 자동화 설정: GitHub → Projects → 해당 프로젝트 → Workflows 탭 → Item added to project 등 활성화

---

## 마일스톤

### M1: 인프라 설정
- [x] Azure Key Vault 생성 (`kv-3dt-team1`, koreacentral)
- [x] Key Vault 시크릿 등록 — `adls-account-name` = `3dtteam1adls` ✅
- [x] ADLS Gen2 생성 (`3dtteam1adls`, koreacentral, HNS 활성화)
- [x] ADLS Gen2 컨테이너 구성 (`raw` / `curated` / `feature`) ✅
- [x] Key Vault 시크릿 등록 — `pg-connection-string` (`sense_db` @ `sense-pg-server`) ✅
- [x] Key Vault 시크릿 등록 — `adls-client-id` / `adls-client-secret` / `adls-tenant-id` (sense-databricks-sp) ✅
- [x] Azure Database for PostgreSQL 생성 — `sense-pg-server` (PG16, B1ms, koreacentral) ✅
  - `sense_db` 데이터베이스 생성 ✅
  - `AllowAzureServices` 방화벽 규칙 ✅
- [x] Databricks SP ADLS 권한 — `sense-databricks-sp` → Storage Blob Data Contributor ✅
- [x] fx-collector (Azure Functions) Managed Identity → Key Vault Secrets User ✅
- [ ] ADF Managed Identity → Key Vault Secrets User (ADF 생성 후, issue #11)
- [ ] ML Studio Managed Identity → Key Vault Secrets User (ML Studio 생성 후, issue #11)

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
