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
 ├─ Custom Activity     → Yahoo Finance 매크로·퀀트, 관세청 수출통계, FRED 금리 6종
 └─ 파이프라인 JSON, parquet     → adf/ 폴더

       │  수집 결과
       ▼
ADLS Gen2 (Azure Data Lake Storage Gen2) — 3dtteam1adls
 ├─ raw/       원본 데이터 (수집기가 적재)
 ├─ curated/   전처리 완료 데이터 (Databricks가 생성)
 └─ feature/   ML용 피처 데이터 (Databricks가 생성)

Azure Databricks (sense-databricks, Premium)
 ├─ raw → curated : 데이터 클렌징·변환 (시계열 보간, TF-IDF)
 ├─ curated → feature : 피처 엔지니어링 (ABSA, 벡터 임베딩)
 ├─ 공통 모듈 사용 : src/utils/vault_manager.py
 └─ Key Vault-backed Secret Scope (sense-kv-scope) 로 비밀 관리

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
| Custom Activity (ADF) | FRED 금리 6종 일별 수집 (DGS10, DGS2, T10Y2Y, BAMLH0A0HYM2, DFF, DFII10) | `src/ingestion/` (구현 예정) |
| ADLS Gen2 (`3dtteam1adls`) | 데이터 레이크 (raw·curated·feature) | _데이터는 Git에 없음_ |
| Databricks (`sense-databricks`, Premium) | 대용량 전처리·피처 엔지니어링, Key Vault Secret Scope | `src/`, `notebooks/` |
| ML Studio | 모델 학습·실험 관리 | `src/models/` |
| Azure Database for PostgreSQL | 결과 데이터 저장·서빙 (`postgres`, `pgvector`) | _인프라, Git 외부_ |
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
         └─ pg-connection-string     → postgres @ sense-pg-server ✅
```

`src/utils/vault_manager.py` 가 이 인증 흐름을 추상화합니다.
- `vault.get_storage_client()` → ADLS Gen2 DataLakeServiceClient (또는 Databricks Spark conf 설정)
- `vault.get_pg_connection()` → psycopg.Connection 또는 SQLAlchemy Engine

### Databricks Key Vault Secret Scope 설정 (완료)

`sense-databricks` (Premium)에서 Key Vault-backed Secret Scope를 사용합니다.

**구성 완료 내역 (2026-01-09)**
- `AzureDatabricks` 앱(`2ff814a6-3304-4ab8-85cb-cd0e6f879c1d`)에 **Key Vault Secrets User** RBAC 역할 부여
- Scope: `/subscriptions/.../resourceGroups/3dt-2nd-team1/providers/Microsoft.KeyVault/vaults/kv-3dt-team1`

**Secret Scope 등록 (Databricks에서 1회 수동 실행)**
```
https://<sense-databricks-url>#secrets/createScope

- Scope Name : sense-kv-scope
- DNS Name   : https://kv-3dt-team1.vault.azure.net/
- Resource ID: /subscriptions/27db5ec6-d206-4028-b5e1-6004dca5eeef/resourceGroups/3dt-2nd-team1/providers/Microsoft.KeyVault/vaults/kv-3dt-team1
```

**노트북에서 사용**
```python
adls_secret = dbutils.secrets.get(scope="sense-kv-scope", key="adls-client-secret")
```

## 서비스별 연동 방식 요약

| 서비스 | ADLS Gen2 | PostgreSQL | Key Vault |
|---|---|---|---|
| Databricks | Spark conf OAuth (Service Principal) | psycopg / JDBC | Key Vault-backed Secret Scope (dbutils.secrets) |
| Data Factory | Linked Service (Managed Identity) | Linked Service (KV 비밀 참조) | UI에서 Key Vault 직접 연결 |
| ML Studio | vault_manager + DataLakeServiceClient | vault_manager + psycopg/SQLAlchemy | DefaultAzureCredential (Managed Identity) |
| ACI (Google News) | vault_manager + DataLakeServiceClient | — | System-Assigned MI → Key Vault Secrets User |
| Azure Functions | vault_manager / Binding | — | Managed Identity → Key Vault Secrets User |

## MS 아키텍처 베스트 프랙티스 참조

SENSE 프로젝트는 Microsoft가 공식 권장하는 엔터프라이즈 클라우드 아키텍처 패턴을 기반으로 설계되었습니다.

| 참조 아키텍처 | 적용 영역 | 핵심 개념 |
|---|---|---|
| [Modern Analytics Architecture (Azure Databricks)](https://learn.microsoft.com/en-us/azure/architecture/solution-ideas/articles/azure-databricks-modern-analytics-architecture) | 전체 데이터 흐름 | Medallion(Bronze/Silver/Gold), ADF + Databricks + ADLS |
| [Ingest, ETL & Stream with ADB](https://learn.microsoft.com/en-us/azure/architecture/solution-ideas/articles/ingest-etl-stream-with-adb) | M3 전처리 | Auto Loader(`cloudFiles`) 증분 수집, Delta Lake MERGE INTO |
| [Next Order Forecasting](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/next-order-forecasting) | M4 모델링 | ADF → ML parallel jobs → Batch Scoring |
| [Orchestrate ML with Databricks](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/orchestrate-machine-learning-azure-databricks) | M4 MLOps | MLflow 실험 트래킹, Dev → Staging → Prod 워크플로우 |
| [Many Models (Azure ML)](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/many-models-machine-learning-azure-machine-learning) | M4 모델 확장 | 종목별 개별 모델 병렬 학습 (`parallel` component) |
| [ADF CI/CD Manual Promotion](https://learn.microsoft.com/en-us/azure/data-factory/continuous-integration-delivery-manual-promotion) | 협업·배포 | ADF Git 연동, ARM 템플릿 기반 환경 프로모션 |

> 상세 실행 가이드: `ref/실행 아이디어.md`

### Auto Loader 증분 수집

Databricks `cloudFiles` Auto Loader를 활용하여 ADLS Gen2 raw 레이어에 신규 적재된 파일만 자동 감지하고 Silver 레이어로 증분 처리합니다.

```python
# Auto Loader 증분 수집 예시
spark.readStream.format("cloudFiles") \
    .option("cloudFiles.format", "parquet") \
    .option("cloudFiles.schemaLocation", "/checkpoints/schema/") \
    .load("abfss://raw@3dtteam1adls.dfs.core.windows.net/news/google/") \
    .writeStream.format("delta") \
    .option("checkpointLocation", "/checkpoints/news_google/") \
    .trigger(availableNow=True) \
    .toTable("silver.news_google")
```

### MLOps 배치 추론 파이프라인 (ADF 오케스트레이션)

```
ADF Timer Trigger (매일 장 마감 후)
    │
    ├─ Step 1: Copy Data Activity — 매크로/뉴스/FRED 금리 수집
    ├─ Step 2: Databricks Notebook Activity — 피처 엔지니어링 (TF-IDF, ABSA)
    ├─ Step 3: AML Batch Endpoint 호출 — 리스크 스코어 추론
    └─ Step 4: Copy Data Activity — 결과 + 원문 → PostgreSQL 적재
```

### Many Models 패턴

종목별 개별 모델을 병렬 학습하여 단일 모델의 한계를 극복합니다.

| 모델 | 역할 | 타겟 변수 |
|---|---|---|
| 삼성전자 (`005930.KS`) | 하방 리스크 예측 | 주가 변동률 |
| SK하이닉스 (`000660.KS`) | 하방 리스크 예측 | 주가 변동률 |
| NVDA | 글로벌 피어 리스크 모니터링 | 주가 변동률 (선행 Proxy) |
| MU | 메모리 수급 선행 지표 | 주가 변동률 (선행 Proxy) |

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
