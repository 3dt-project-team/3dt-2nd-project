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
- [x] Key Vault 시크릿 등록 — `pg-connection-string` (`postgres` @ `sense-pg-server`) ✅
- [x] Key Vault 시크릿 등록 — `adls-client-id` / `adls-client-secret` / `adls-tenant-id` (sense-databricks-sp) ✅
- [x] Azure Database for PostgreSQL 생성 — `sense-pg-server` (PG16, B1ms, koreacentral) ✅
  - `postgres` 데이터베이스 (기본 DB 사용) ✅
  - `AllowAzureServices` 방화벽 규칙 ✅
- [x] Databricks SP ADLS 권한 — `sense-databricks-sp` → Storage Blob Data Contributor ✅
- [x] fx-collector (Azure Functions) Managed Identity → Key Vault Secrets User ✅
- [x] Azure Databricks workspace 생성 — `sense-adb` (koreacentral, Standard SKU) ✅
- [x] Azure Container Registry 생성 — `sense3dtacr` (koreacentral, Standard, admin 활성화) ✅
- [x] Google News 크롤러 ACI 컨테이너 이미지 빌드 & 푸시 — `sense3dtacr.azurecr.io/google-news-crawler:latest` ✅
- [ ] ADF Managed Identity → Key Vault Secrets User (ADF 생성 후, issue #11)
- [ ] ML Studio Managed Identity → Key Vault Secrets User (ML Studio 생성 후, issue #11)

### M2: 데이터 수집

> ADF = 오케스트레이션 레이어 (타이머 트리거). 수집 실행은 ACI / Azure Functions / Python 스크립트.

#### ✅ 완료
- [x] Google News 크롤러 (ACI) — RSS + Playwright 2단계 크롤링, ADLS `raw/news/google/` 적재
- [x] 네이버 뉴스 크롤러 (Azure Functions) — 검색 API + Playwright 본문 크롤링
- [x] Yahoo Finance 매크로·주가 수집 스크립트 — `src/ingestion/yahoo_finance_crawler.py`
- [x] 환율(FX) 수집 (Azure Functions) — `apps/fx-collector/`, Open Exchange Rates API
- [x] 관세청 수출입 통계 수집 — `src/utils/kr_public_data_customs.py`, HS Code 8542 기반

#### 🚧 진행 중
- [ ] FRED 금리 6종 수집 스크립트 — `src/ingestion/` 하위, FRED API (`DGS10`, `DGS2`, `T10Y2Y`, `BAMLH0A0HYM2`, `DFF`, `DFII10`)

#### ❌ 미완료
- [ ] ADF Linked Service 연결 구성 (ADLS, PostgreSQL, Key Vault)
- [ ] ADF 수집 파이프라인 — ACI Activity (Google News), Functions Activity (Naver/FX), Custom Activity (Yahoo/관세청)
- [ ] ADF 타이머 트리거 설정 (일 1회 또는 장 마감 후)
- [ ] 수집 파이프라인 JSON 저장 → `adf/` 폴더

### M3: 전처리 (Databricks)
- [ ] 클러스터 Init Script 등록 (`notebooks/init_script_install_uv.sh`)
- [ ] vault_manager 연동 및 ADLS Spark conf 설정
- [ ] Databricks Auto Loader (`cloudFiles`) 증분 수집 설정 — raw → curated 자동 파이프라인 (MS [Ingest ETL Stream](https://learn.microsoft.com/en-us/azure/architecture/solution-ideas/articles/ingest-etl-stream-with-adb) 참조)
- [ ] 시계열 결측치 Forward Fill 보간 (국가별 휴장일 통일)
- [ ] FRED 금리 결측값(`"."`) NULL 변환 + Forward Fill → `curated/fred/` 적재
- [ ] Spark TF-IDF 기반 동적 키워드 모멘텀
- [ ] Azure OpenAI 연동 (뉴스 요약, ABSA 감성 분석)
- [ ] Summary-based Indexing 벡터 임베딩
- [ ] 데이터 클렌징·변환 → `curated/` 저장
- [ ] 피처 엔지니어링 → `feature/` 저장

### M4: 모델링 (ML Studio + TimesFM)

#### TimesFM 2.5 시계열 예측 (Databricks)
- [x] TimesFM 2.5 환경 구성 — `pip install timesfm[torch,xreg]`, GPU 클러스터 설정
- [x] Step 1: Zero-shot Baseline 추론 — 삼성전자/SK하이닉스 종가 시계열 → 20일 예측 + Quantile PI
- [x] Step 2: XReg 공변량 추론 — 매크로/퀀트/감성 지표를 외부 회귀 변수로 입력
- [x] 교차 검증 파생 변수 생성 — 47개 피처 (return, MA, vol, cross-signal 포함)
- [x] 시나리오 분석 (What-If) — 5개 그룹, 12개 시나리오 + 일관성 검증 (v0411)
- [x] Rolling Window Backtest — 멀티호라이즌(5d/10d/20d), Conformal PI 보정 (v0411)
- [x] XReg Attribution (공변량 기여도) — 종목별 Leave-One-Out + 시각화 (v0411)
- [x] 피처 상관관계 분석 — Pearson/Spearman 이중 히트맵 (v0411)
- [x] VaR/CVaR 리스크 지표 — Quantile 기반 T+5/10/20 VaR 산출 (v0411)

#### 전통 모델 비교 파이프라인 (Databricks)
- [x] statistical_baseline_analysis.py — VAR + Ridge 기반 동일 프레임워크 분석 (Full Feature)
- [x] Granger Causality 검정 — 주요 피처→close 인과 관계 검증
- [x] TimesFM vs 전통 모델 교차 비교 리포트 — Ridge MAPE 4.69~5.71% vs TimesFM 5.08~9.37%, Ridge 방향 정확도 70~87.5%
- [x] VaR/CVaR 리스크 지표 — Ridge 잔차 기반 T+5/10/20 VaR/CVaR 산출 (v0412)
- [x] 백테스트 개선 — AutoReg 다단계 예측 (AR(1) proxy 교체), Bootstrap PI (±2σ 교체), Step-wise 방향 정확도 (v0412)
- [x] 피처 파리티 — 전통 모델 파생 변수 40→47개 통일 (TimesFM 동일) (v0412)
- [x] 한글 폰트 수정 — glob+addfont 직접 등록 방식으로 교체 (v0412)
- [x] 분석 결과 보고서 — `docs/analysis_results.md` 생성 (v0412)
- [x] apt-get update 추가 — Databricks 패키지 저장소 갱신 후 fonts-nanum 설치 (v0413)
- [x] 동적 가중치 앙상블 — `ensemble_strategy.py` 신규 (TimesFM×ElasticNet 후처리 파이프라인) (v0413)
- [x] Feature Engineering 고도화 — RSI(14), ATR(14), 120d 이격도, 로그수익률 추가 (v0413)
- [x] ElasticNetCV + Time-Decay — Ridge→ElasticNet 전환, 60d half-life 지수감쇠 가중치 (v0413)
- [x] 레짐 기반 동적 가중치 — RSI/ATR/이격도 조건부 가중치 조정 + Confidence Score (v0413)
- [x] 앙상블 시각화 — Dynamic Weighting Strategy 차트 (ref/image.png 재현) (v0413)
- [x] fact_ensemble_forecast — PostgreSQL 적재용 DataFrame 포맷 정의 (v0413)
- [x] ADLS 경로 수정 — curated/ 하위 경로 및 TICKER_COL_MAP 직접 매핑으로 수정 (v0413)
- [x] fact_ensemble_forecast PostgreSQL 적재 완료 — 40행 (2종목 × 20일) (v0413)
- [x] Soft Switching 동적 가중치 보간 — Hard Threshold→선형/비선형 연속 함수 전환 (v0414)
- [x] 로그수익률 타겟 전환 — 절대가(원)→log(P_{t+20}/P_t) 스케일 불변 (v0414)
- [x] Alpha 범위 축소 — 자동(40~189)→0.001~1.0 (과잉 정규화 방지) (v0414)
- [x] Time-Decay 강화 — half_life 60→30 거래일 (최근 랠리 가중치 강화) (v0414)
- [x] Interaction Term — RSI×vol_ratio 복합 신호 중첩 3가지 규칙 (v0414)
- [x] 뉴스 감성 통합 — PostgreSQL Gold Layer (`v_news_sentiment_trend`) 연동 (v0415)
- [x] 감성 파생 피처 — sentiment_momentum, news_vol_surge, sent_price_decouple 등 5개 (v0415)
- [x] Soft Switching 감성 가중치 — `_sentiment_weight_adjustment()` ±0.15 클리핑 (v0415)
- [x] Interaction Term 감성 규칙 — 호재×RSI과매수, 악재×RSI과매도 2개 규칙 추가 (v0415)
- [x] GPT 프롬프트 감성 주입 — AI 슈퍼사이클 스토리라인 + 뉴스 감성 섹션 (v0415)
- [x] 키워드 파생변수 — `daily_keywords` JSONB → diversity, delta, concentration 등 6종 + 교호작용 4종 (v0416)
- [x] 상관관계 분석 — Spearman/Pearson 교차검증 키워드 파생변수 상관 셀 (v0416)
- [x] AI 중간 해석 셀 — 키워드 상관, ElasticNet 결과, 앙상블 레짐 3개 셀 (v0416)
- [x] 멀티모델 비교 — GPT-5.4 계열 Responses API 4개 모델 비교 (v0416)
- [x] `plt.show()` → `display(fig)` — 3개 노트북 전체 Databricks 호환 전환 (v0416)
- [x] AutoML RandomForest 통합 — Databricks AutoML 검증 (삼성 R²=0.72, SK R²=0.86) 기반 RF 모델 추가 (v0417)
- [x] 회귀 컴포넌트 블렌딩 — `regression_pred = 0.7*RF + 0.3*EN` AutoML 하이퍼파라미터 적용 (v0417)
- [x] SQLAlchemy 2.x 호환성 — `engine.connect()` + `conn.commit()` 패턴 (3개 파일) (v0417)
- [x] AI 최종 모델 전환 — Section 8 gpt-4.1-mini → **gpt-5.4-mini** (Responses API) (v0418)
- [x] ElasticNet 시나리오 분석 — `use_elasticnet` 플래그 + RF+EN vs RF-only 비교 셀 (v0418)
- [x] Date 인덱스 충돌 수정 — `reset_index(drop=True)` 조건 분기 적용 (v0418)
- [x] AutoML BestTrial 노트북 — `automl_best_trial.py` Databricks 노트북 신규 (v0418)
- [x] GPT 모델 비교 평가 — `ref/모델_평가_GPT_비교.md` 성능/가격/품질 분석 문서 (v0418)

> ⚠️ **v0413 실행 결과 발견 이슈 → v0414 대응:**
> - SK하이닉스 ElasticNet R²=−0.33 → **v0414: 로그수익률 타겟으로 스케일 차이 해소**
> - Confidence Score 5.5/4.5 → TimesFM 시뮬레이션과 ElasticNet 간 격차 과대 (실제 TFM 연동 시 개선 예상)
> - alpha=40~189 (과잉 정규화) → **v0414: 0.001~1.0 범위로 축소**
> - Hard Threshold 불연속 → **v0414: Soft Switching 연속 함수 전환**
> - KFinance(28행, 1컬럼), 반도체 수출입(24행, 4컬럼) → Silver 데이터 품질 점검 필요

> **파일 구조 변경 (v0411→Full Feature, v0413→Ensemble):**
> - `timesfm_inference.py` — TimesFM 메인 (Full Feature)
> - `timesfm_inference_lite.py` — TimesFM 간소화 아카이브
> - `statistical_baseline_analysis.py` — 전통 모델 메인 (Full Feature)
> - `statistical_baseline_analysis_lite.py` — 전통 모델 간소화 아카이브
> - `ensemble_strategy.py` — 동적 가중치 앙상블 (v0413 신규, v0415 감성, v0416 키워드, v0417 AutoML RF, v0418 gpt-5.4-mini)
> - `automl_best_trial.py` — AutoML BestTrial RF 추론/평가/SHAP 분석 (v0418 신규)
> - `correlation_analysis.py` — 원본 상관분석 (복원)

#### XGBoost/LightGBM 분류 (ML Studio)
- [ ] 컴퓨팅 클러스터 구성
- [ ] Feature 데이터 Datastore 등록
- [ ] XGBoost/LightGBM 하방 리스크 예측 모델 학습
- [ ] 학습 잡 제출 (`src/models/aml_train_example.py` 참고)
- [ ] MLflow 실험 트래킹 + Git commit hash 태깅
- [ ] Many Models 패턴 적용 — 삼성전자/SK하이닉스/NVDA/MU 종목별 개별 모델 병렬 학습 (AML `parallel` component, MS [Many Models](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/many-models-machine-learning-azure-machine-learning) 참조)
- [ ] AML Batch Endpoint 등록 및 ADF 연동 (MS [Orchestrate ML](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/orchestrate-machine-learning-azure-databricks) 참조)

#### 앙상블 합의 판정
- [x] 동적 가중치 앙상블 (`ensemble_strategy.py`) — TimesFM(추세) × ElasticNet(회귀) 후처리 결합 (v0413)
- [x] AutoML RandomForest 통합 — RF+EN 블렌딩 회귀 컴포넌트 (v0417, Issue #88)
- [ ] XGBoost 확률 통합 — 하방 리스크 확률을 앙상블 가중치에 반영
- [ ] RAG 연동 — XReg Attribution 기반 예측 근거 자동 생성

### M5: 서빙
- [ ] 예측 결과 Azure Database for PostgreSQL 적재
- [ ] PostgreSQL `pgvector` 확장 + 하이브리드 검색 구현
- [ ] Power BI 시각화 대시보드 (XAI 피처 중요도 포함)
- [ ] Web App + AI Agent RAG 서빙
- [ ] 최종 파이프라인 End-to-End 검증

---

## 일정 (9 영업일 — 4/3 ~ 4/15)

| Day | 날짜 | 마일스톤 | 상태 |
|-----|------|---------|------|
| 1–2 | 4/3–4/4 | M0 GitHub 세팅 + M1 인프라 프로비저닝 | ✅ 완료 |
| 3–4 | 4/7–4/8 | M1 추가 인프라 (ACR, Databricks) + M2 수집기 구현 | ✅ 완료 |
| 5 | 4/9 | M2 ADF 오케스트레이션 파이프라인 구성 | 🔜 |
| 6 | 4/10 | M3 Databricks 전처리 (Bronze → Silver → Gold) | 🔜 |
| 7 | 4/11 | M4 TimesFM Full Feature + 전통 모델 비교 파이프라인 + 파일 재구조화 | ✅ 완료 |
| 8 | 4/14 | M4 ML 학습 (XGBoost/LightGBM) + M5 PostgreSQL 적재 | 🔜 |
| 9 | 4/15 | M5 서빙 (Power BI + Web App + AI Agent) | 🔜 |

## 관련 문서
- 아키텍처 개요: [architecture.md](architecture.md)
- uv 통합 가이드: [uv_integration_guide.md](uv_integration_guide.md)
- 협업 규칙: [../docs/git_guide/](git_guide/)
- MS 아키텍처 베스트 프랙티스: [architecture.md #MS 아키텍처 베스트 프랙티스 참조](architecture.md#ms-아키텍처-베스트-프랙티스-참조)
- **TimesFM 앙상블 모델 분석 기록**: [TimesFM_앙상블_튜닝_트러블슈팅.md](TimesFM_앙상블_튜닝_트러블슈팅.md) — v0412~v0414 개발 히스토리, 6가지 이슈 트러블슈팅, 파라미터 튜닝
- **v0415 뉴스 감성 통합**: Gold Layer `v_news_sentiment_trend` 뷰 활용, 5개 감성 파생 피처, Soft Switching 감성 가중치, Interaction 규칙 확장, GPT 프롬프트 AI 슈퍼사이클 스토리라인
- **v0416 키워드 파생변수 + 멀티모델**: `daily_keywords` JSONB 6종 파생변수, 교호작용 4종, Spearman/Pearson 교차검증 상관분석, AI 중간 해석 3셀, GPT-5.4 계열 Responses API 멀티모델 비교, `display(fig)` 전환
- **v0418 AI 최종 모델 + BestTrial**: Section 8 gpt-5.4-mini 전환 (속도 2.87s, Input $0.25/1M), ElasticNet 시나리오 분석 플래그, Date 인덱스 충돌 수정, `automl_best_trial.py` UC 모델 추론/SHAP 노트북, `ref/모델_평가_GPT_비교.md` 문서