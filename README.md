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
│   ├── ensemble_strategy.py      # Databricks: Soft Switching 동적 가중치 앙상블 (v0414)
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
