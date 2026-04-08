# SENSE 프로젝트 아키텍처

> **SENSE** — Semiconductor Economic News & Sentiment Engine

## 전체 데이터 흐름

```
외부 데이터 소스
       │
       ▼
Azure Data Factory (ADF) ── 타이머 트리거 기반 오케스트레이션
 ├─ ACI Activity        → Google News 크롤러 (Playwright one-shot)
 ├─ Functions Activity  → 네이버 뉴스, 환율(FX) 수집
 ├─ Custom Activity     → Yahoo Finance 매크로·퀀트, 관세청 수출통계
 └─ 파이프라인 JSON, parquet     → adf/ 폴더

       │  수집 결과
       ▼
ADLS Gen2 (Azure Data Lake Storage Gen2) — 3dtteam1adls
 ├─ raw/       원본 데이터 (수집기가 적재)
 ├─ curated/   전처리 완료 데이터 (Databricks가 생성)
 └─ feature/   ML용 피처 데이터 (Databricks가 생성)

Azure Databricks (sense-adb)
 ├─ raw → curated : 데이터 클렌징·변환 (시계열 보간, TF-IDF)
 ├─ curated → feature : 피처 엔지니어링 (ABSA, 벡터 임베딩)
 └─ 공통 모듈 사용 : src/utils/vault_manager.py

Azure ML Studio
 ├─ feature → 모델 학습 (CommandJob, XGBoost/LightGBM)
 ├─ MLflow 실험 트래킹 (Git commit hash 태깅)
 └─ 결과 저장 → PostgreSQL

Azure Database for PostgreSQL
 ├─ 최종 예측·분석 결과 서빙
 └─ pgvector 확장 → RAG 하이브리드 검색

Power BI / Web App / AI Agent
 └─ PostgreSQL ↔ 대시보드·리포트·RAG 서빙
```

## 서비스별 역할

| 서비스 | 역할 | Git 경로 |
|---|---|---|
| Azure Data Factory | **파이프라인 오케스트레이션** (타이머 트리거, Activity 호출) | `adf/` |
| Azure Container Registry (`sense3dtacr`) | 컨테이너 이미지 저장소 (ACR Build) | _인프라, Git 외부_ |
| Azure Container Instances | One-shot 크롤링 실행 (Google News) | `src/ingestion/google_news_crawler/Dockerfile` |
| Azure Functions | 이벤트/배치 수집 (네이버 뉴스, 환율 FX) | `src/ingestion/naver_collectors/`, `apps/fx-collector/` |
| ADLS Gen2 (`3dtteam1adls`) | 데이터 레이크 (raw·curated·feature) | _데이터는 Git에 없음_ |
| Databricks (`sense-adb`) | 대용량 전처리·피처 엔지니어링 | `src/`, `notebooks/` |
| ML Studio | 모델 학습·실험 관리 | `src/models/` |
| Azure Database for PostgreSQL | 결과 데이터 저장·서빙 (`sense_db`, `pgvector`) | _인프라, Git 외부_ |
| Azure Key Vault (`kv-3dt-team1`) | 모든 자격 증명 중앙 관리 | `src/utils/vault_manager.py` |

## 인증 구조

모든 서비스는 **Azure Key Vault**를 통해 자격 증명을 관리합니다.

```
DefaultAzureCredential
       │
       ├─ 로컬 개발  : az login
       └─ 클라우드  : Managed Identity (비밀번호 코드 노출 없음)
              │
              ▼
        Azure Key Vault (kv-3dt-team1)
         ├─ adls-account-name        → 3dtteam1adls ✅
         ├─ adls-client-id           → sense-databricks-sp clientId ✅
         ├─ adls-client-secret       → sense-databricks-sp secret ✅
         ├─ adls-tenant-id           → 5fb256f0-… ✅
         └─ pg-connection-string     → sense_db @ sense-pg-server ✅
```

`src/utils/vault_manager.py` 가 이 인증 흐름을 추상화합니다.
- `vault.get_storage_client()` → ADLS Gen2 DataLakeServiceClient (또는 Databricks Spark conf 설정)
- `vault.get_pg_connection()` → psycopg.Connection 또는 SQLAlchemy Engine

## 서비스별 연동 방식 요약

| 서비스 | ADLS Gen2 | PostgreSQL | Key Vault |
|---|---|---|---|
| Databricks | Spark conf OAuth (Service Principal) | psycopg / JDBC | vault_manager 또는 dbutils.secrets |
| Data Factory | Linked Service (Managed Identity) | Linked Service (KV 비밀 참조) | UI에서 Key Vault 직접 연결 |
| ML Studio | vault_manager + DataLakeServiceClient | vault_manager + psycopg/SQLAlchemy | DefaultAzureCredential (Managed Identity) |
| ACI (Google News) | vault_manager + DataLakeServiceClient | — | System-Assigned MI → Key Vault Secrets User |
| Azure Functions | vault_manager / Binding | — | Managed Identity → Key Vault Secrets User |

## 로컬 개발 환경 설정

```bash
git clone https://github.com/3dt-project-team/3dt-2nd-project.git
cd 3dt-2nd-project
git checkout dev

# uv 설치 (최초 1회, Windows PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

uv sync              # 기본 의존성
uv sync --extra ml   # ML 관련 추가 의존성

cp .env.example .env
# .env 에 KEY_VAULT_URL 입력 후:
az login

uv run python src/utils/vault_manager.py   # 연결 테스트
```
