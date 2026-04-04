# 3DT 2nd Project — Azure 데이터 플랫폼

6인 팀 Azure 데이터 파이프라인 프로젝트 (ADF → Databricks → ML Studio).

## 폴더 구조

```
├── adf/
│   └── custom_activity/    # ADF Custom Activity Docker 컨테이너
├── src/
│   ├── utils/
│   │   └── vault_manager.py  # Key Vault / ADLS Gen2 / PostgreSQL 인증 모듈
│   └── models/             # ML 모델링 스크립트
├── notebooks/              # Databricks 노트북 및 Init Script
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
