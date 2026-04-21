# SENSE 포트폴리오

> **프로젝트명**: SENSE — Semiconductor Economic News & Sentiment Engine  
> **기간**: 2025년 4월 (2주)  
> **팀 규모**: 6인  
> **역할**: 클라우드 인프라·데이터 파이프라인 아키텍처 설계 및 구현

---

## Key Point

> **Azure 기반 엔터프라이즈급 MLOps 파이프라인 설계** — 6개 외부 데이터 소스를 하나의 자동화 파이프라인으로 통합하고, ADF·ADLS·Databricks·ML Studio를 연결한 Medallion 아키텍처 구축. 단일 실패점 없는 7단계 순차 체인 설계 및 클러스터 환경 변경에 대응하는 sklearn 역직렬화 호환성 패치 개발.

**Tech Stack**: Python 3.11 · Azure Data Factory · ADLS Gen2 · Azure Databricks · Azure ML Studio · Azure Functions · Azure Container Instances · Azure Key Vault · PostgreSQL · Docker · Flask · uv

---

## Description

반도체 주가(삼성전자·SK하이닉스)에 영향을 미치는 **뉴스 감성**, **거시경제 지표**, **수급·파생 데이터** 세 가지 축을 통합하여 T+20일 예측과 근거를 함께 제공하는 AI 시스템.

**팀 내 역할 (이은서 — 인프라·아키텍처 파트)**
- Azure 클라우드 전체 아키텍처 설계 및 기술 스택 선정
- ADF 파이프라인 오케스트레이션 구성 (7단계 의존성 체인, 타이머 트리거 자동화)
- ADLS Gen2 Medallion 아키텍처(Raw → Curated → Feature) 레이어 설계
- Azure Key Vault 기반 자격증명 중앙화 (`DefaultAzureCredential` 통합)
- Databricks 노트북 환경 관리 및 Custom Activity Docker 환경 구성

---

## Key Experience & Retrospective

---

### [경험 1] ADF vs Databricks 전처리 환경 이원화 설계

**Problem**  
데이터 전처리를 ADF Data Flow로 단일화하려 했으나, 10만 건 이상의 뉴스 JSON 처리와 ABSA 피처 엔지니어링 코드를 ADF에서 수행하기에 성능·유연성 한계 발생.

**Solution**  
세 가지 기준(데이터 크기, 변환 복잡도, ML 연동 필요성)으로 역할을 이원화:
- **ADF Data Flow**: 환율·금리 등 소규모 정형 데이터 변환 (GUI 기반, 운영 접근성 우수)
- **Databricks**: 대용량 뉴스 JSON, Parquet 피처 마트 생성, Unity Catalog 기반 ML 모델 연동

**Result**  
- 파이프라인 전체 처리 시간 단축. 툴 특성에 맞는 하이브리드 아키텍처로 운영 안정성 확보
- 심사위원 "ADF vs Databricks 비교 분석이 우수하다" 평가 → 근거 있는 기술 선택이 면접/발표 어필 포인트로 활용됨

---

### [경험 2] 7단계 ADF 파이프라인 — 트리거 충돌 및 중복 적재 해결

**Problem**  
ADF 멀티 파이프라인 동시 실행 시 트리거 타이밍 충돌로 동일 날짜 데이터 중복 적재 발생. 팀 내 파이프라인 JSON 편집 시 Git 병합 충돌로 덮어쓰기 위험도 상존.

**Solution**  
- Activity 간 명시적 의존성(Success/Failure) 설정으로 **7단계 순차 체인** 구성
- 타이머 트리거 시점을 장 마감 후 1시간(16:30 KST)으로 단일화하여 중복 실행 원천 차단
- 팀 내 파이프라인 편집 협의 프로토콜 수립 (ADF JSON 편집 전 팀 채팅 알림 의무화)

**Result**  
- 2주 운영 기간 중 중복 적재 0건
- 전체 파이프라인 완전 자동화 — 매일 16:30 ADF 타이머 트리거로 데이터 수집 → 전처리 → 예측 → PostgreSQL 적재 무인 운영

---

### [경험 3] sklearn 역직렬화 오류 — 클러스터 환경 변경 대응

**Problem**  
Databricks Runtime 업그레이드(13.3 LTS → 15.4 ML LTS) 후 AutoML 등록 모델 추론 시 `AttributeError: 'SimpleImputer' object has no attribute '_fill_dtype'` 발생. 모델 직렬화 환경(sklearn 1.4.2)과 추론 환경(sklearn 1.8.0) 버전 불일치가 원인.

**Solution**  
프로덕션 공유 클러스터 환경을 제어할 수 없는 상황에서, AutoML 재실행(60분+) 대신 **재귀적 패치 함수 `_deep_mark_fitted()`** 개발:

```python
def _deep_mark_fitted(estimator):
    """sklearn 1.4.x → 1.8.x 역직렬화 호환성 패치"""
    # 1) __sklearn_is_fitted__ 속성 사후 주입
    if not hasattr(estimator, "__sklearn_is_fitted__"):
        object.__setattr__(estimator, "__sklearn_is_fitted__", lambda: True)
    # 2) SimpleImputer._fill_dtype 복원
    if (estimator.__class__.__name__ == "SimpleImputer"
            and hasattr(estimator, "statistics_")
            and not hasattr(estimator, "_fill_dtype")):
        estimator._fill_dtype = estimator.statistics_.dtype
    # 3) Pipeline·ColumnTransformer 하위 추정기 재귀 처리
    for attr in ["steps", "estimators_", "transformers_"]:
        for item in (getattr(estimator, attr, None) or []):
            _deep_mark_fitted(item[1] if isinstance(item, tuple) else item)
```

**Result**  
- AutoML 재학습 없이 기존 모델 즉시 복구. 재처리 대기 시간 제로
- 환경 불변 조건(Immutable Infrastructure) 원칙의 한계와 호환성 패치의 실무 가치 체득

---

### [경험 4] Azure Key Vault 기반 자격증명 중앙화

**Problem**  
6인 팀이 각자 `.env` 파일로 자격증명을 관리 → 시크릿 노출 위험, 배포 환경(Databricks·Functions·App Service)마다 중복 설정 필요.

**Solution**  
`DefaultAzureCredential` 기반 `vault_manager.py` 모듈 설계:
- 로컬: `az login` → Managed Identity 없이 동일 코드 동작
- Databricks: 런타임 감지 후 Spark 세션 OAuth 자동 설정
- App Service: System-assigned Managed Identity → AcrPull + Key Vault Secrets User 권한

```python
vault.get_secret("pg-connection-string")   # PostgreSQL 접속 문자열
vault.get_storage_client()                  # ADLS Gen2 클라이언트
vault.get_pg_connection("sqlalchemy")       # SQLAlchemy Engine
```

**Result**  
- `.env` 파일 커밋 0건, 코드 내 하드코딩 시크릿 0건
- 단일 코드베이스로 로컬·Databricks·App Service 세 환경 동일 인증 처리

---

## Tech Stack 선택 근거

| 기술 | 선택 이유 | 비교 대상 |
|---|---|---|
| **Azure** | Key Vault 중앙 인증 + ADF-Databricks 네이티브 연동 + 관리형 ML Studio | AWS (연동 복잡도, 팀 학습 곡선 불리) |
| **PostgreSQL** | 오픈소스 활용도 + 동시 다중 조회 성능 | ADLS Gen2 단독 (분산 조회 한계), Azure SQL (오픈소스 생태계 열세) |
| **Databricks** | 대용량 Parquet·JSON 처리 + Unity Catalog ML 연동 | ADF Data Flow (소규모 정형 데이터에만 적합) |
| **Docker (Custom Activity)** | yfinance 의존성 충돌 격리, 재현 가능 환경 | Azure Functions (런타임 패키지 제약) |

---

## 결과 및 성과

- 6개 외부 소스(Yahoo Finance·FRED·네이버뉴스·Google News·관세청·KFinance) **완전 자동 수집 파이프라인** 구축
- ADF 타이머 트리거 기반 **매일 16:30 무인 실행** — 수동 개입 불필요
- 삼성전자·SK하이닉스 T+20 예측 R² 삼성 0.82 / SK하이닉스 0.77 달성 (초기 대비 대폭 개선)
- 심사위원 총평: "공연을 본 것 같다" — 발표 완성도·기술 깊이·비즈니스 가치 전방위 호평

---

## Links

- **GitHub**: [3dt-project-team/3dt-2nd-project](https://github.com/3dt-project-team/3dt-2nd-project)
- **기술 블로그**: `ref/blog/sense_01~05` (아키텍처·파이프라인·피처·앙상블·트러블슈팅 5편)
- **아키텍처 문서**: `docs/architecture.md`
- **배포 가이드**: `docs/cicd/webapp_container_deployment.md`
