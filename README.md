# SENSE — Semiconductor Economic News & Sentiment Engine

반도체 경제 뉴스 및 감성 분석 엔진 · 6인 팀 Azure 데이터 파이프라인 (ADF → Databricks → ML Studio).

## 폴더 구조

```
├── adf/
│   ├── pipeline/           # ADF 파이프라인 JSON
│   ├── dataset/            # 데이터셋 정의
│   ├── linkedService/      # Linked Service 정의
│   ├── trigger/            # 트리거 정의
│   └── custom_activity/    # ADF Custom Activity Docker 컨테이너
├── src/
│   ├── utils/
│   │   └── vault_manager.py  # Key Vault / ADLS Gen2 / PostgreSQL 인증 모듈
│   └── models/
│       ├── train.py          # SENSE 감성 분석 모델 학습 스크립트
│       └── aml_train_example.py  # ML Studio CommandJob 제출 예시
├── notebooks/
│   ├── 01_raw_to_curated.py      # Databricks: 뉴스 원문 클렌징
│   ├── 02_curated_to_feature.py  # Databricks: 피처 엔지니어링
│   ├── ensemble_strategy.py      # Databricks: TimesFM(0.45)+UC BestTrial(0.55) 동적 앙상블 + 감성 가중치 (v0419)
│   ├── automl_best_trial.py      # Databricks: AutoML UC 추론·평가·SHAP + Gold Layer (v0419)
│   ├── timesfm_inference.py      # Databricks: TimesFM 2.5 Zero-shot 시계열 예측 + Gold Layer (v0419)
│   ├── databricks_uv_example.py  # uv + vault_manager 연동 예시
│   └── init_script_install_uv.sh # 클러스터 Init Script
├── tests/
│   ├── conftest.py         # pytest 픽스처
│   └── test_vault_manager.py
├── docs/                   # 아키텍처, 가이드 문서
│   └── git_guide/          # Git 가이드 (general + workflow)
├── pyproject.toml          # 패키지 의존성 (uv 관리)
└── .env.example            # 로컬 환경 변수 템플릿
```

## SENSE 웹 대시보드

**https://sense-web.azurewebsites.net**

반도체 주가 예측 및 뉴스 감성 분석 결과를 실시간으로 제공하는 Flask 웹 대시보드.

| 섹션 | 내용 |
|------|------|
| 예측 (Forecast) | 삼성전자·SK하이닉스 20일 앙상블 예측 + Confidence Score |
| 감성 (Sentiment) | 뉴스 감성 트렌드 + 커뮤니티 반응 |
| 시장 국면 (Regime) | RSI/ATR 기반 레짐 (Trend-Up/Neutral/Caution) |
| AI 챗봇 (Ask AI) | RAG 기반 질의응답 + `[한마디로 / Plain Language]` 요약 섹션 |

**현재 버전**: v1.2 — 한/영 병기 레이블 + Plain Language 챗봇 적용

### 로컬 실행

```bash
cp .env.example .env   # KEY_VAULT_URL 입력
uv run python app.py
```

### 배포 (ACR + Azure App Service)

```bash
# 이미지 빌드 및 푸시
az acr build --registry sense3dtacr --image sense-web:vX.Y .

# Staging 컨테이너 이미지 업데이트
az webapp config container set --name sense-web --resource-group 3dt-2nd-team1 \
  --slot staging --container-image-name sense3dtacr.azurecr.io/sense-web:vX.Y

# Production Slot Swap
az webapp deployment slot swap --name sense-web --resource-group 3dt-2nd-team1 \
  --slot staging --target-slot production
```

## 빠른 시작

```bash
git clone https://github.com/3dt-project-team/3dt-2nd-project.git
cd 3dt-2nd-project
git checkout dev

# uv 설치 (최초 1회, PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

uv sync

cp .env.example .env   # KEY_VAULT_URL 입력 후 az login 실행
uv run python src/utils/vault_manager.py

# pre-commit hook 등록 (최초 1회)
uv run pre-commit install
```

## 핵심 문서

| 문서 | 내용 |
|---|---|
| [docs/git_guide/](docs/git_guide/) | Git 가이드 (범용 + 프로젝트 워크플로우) |
| [docs/architecture.md](docs/architecture.md) | 전체 데이터 흐름 및 서비스 역할 |
| [docs/uv_integration_guide.md](docs/uv_integration_guide.md) | Azure 서비스별 uv 통합 방법 |
| [docs/implementation_plan.md](docs/implementation_plan.md) | 프로젝트 마일스톤 및 구현 계획 |
| [docs/ensemble_model_guide.md](docs/ensemble_model_guide.md) | 앙상블 모델 가이드 (가중치 규칙, 튜닝 이력) |
| [docs/analysis_results.md](docs/analysis_results.md) | TimesFM vs 전통 모델 출력 분석 보고서 |
| [docs/TimesFM_앙상블_튜닝_트러블슈팅.md](docs/TimesFM_앙상블_튜닝_트러블슈팅.md) | TimesFM & 통계 기준선 앙상블 모델 전 개발 히스토리 (분석→튜닝→트러블슈팅) |
| [ref/모델_평가_GPT_비교.md](ref/모델_평가_GPT_비교.md) | Azure OpenAI 모델(4.1-mini/5.4-mini/5.4/5.4-pro) 성능·비용 비교 |
