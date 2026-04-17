# SENSE 프로젝트 회고록

> **SENSE** — Semiconductor Economic News & Sentiment Engine  
> **기간**: 2025년 4월 3일 ~ 4월 17일 (약 10 영업일)  
> **팀**: 6인 팀 (3dt-2nd-team1)  
> **발표일**: 2026년 4월 17일

---

## 1. 프로젝트 개요

반도체 경제 뉴스 및 감성 데이터를 활용하여 삼성전자·SK하이닉스 주가를 T+20일 앙상블 예측하고, 결과를 웹 대시보드로 서빙하는 End-to-End Azure 데이터 파이프라인 프로젝트.

### 핵심 성과

| 항목 | 내용 |
|---|---|
| 예측 대상 | 삼성전자(005930.KS), SK하이닉스(000660.KS) |
| 예측 horizon | T+20 거래일 |
| 최종 앙상블 | TimesFM 2.5 (0.45) + AutoML UC BestTrial (0.55) |
| 최종 R² | 삼성전자 **0.9266** / SK하이닉스 **0.7097** |
| 피처 수 | **47개** (기술적 지표 + 감성 + 키워드 교호작용) |
| 웹 대시보드 | https://sense-web.azurewebsites.net (v1.2) |
| GitHub | https://github.com/3dt-project-team/3dt-2nd-project |

---

## 2. Azure 리소스 목록 (삭제 전 기록)

> 리소스 그룹: **3dt-2nd-team1** (koreacentral)

### 2-1. 핵심 인프라

| 리소스 | 이름 | SKU / 티어 | 역할 |
|---|---|---|---|
| Resource Group | `3dt-2nd-team1` | — | 모든 리소스 컨테이너 |
| Azure Key Vault | `kv-3dt-team1` | Standard | 비밀 중앙 관리 |
| ADLS Gen2 | `3dtteam1adls` | Standard LRS, HNS 활성화 | 데이터 레이크 (raw/curated/feature) |
| Azure Databricks | `sense-adb` | Standard SKU | 전처리·피처 엔지니어링·앙상블 실행 |
| Azure Database for PostgreSQL | `sense-pg-server` | PG 16, B1ms | 예측 결과 서빙 |
| Azure Container Registry | `sense3dtacr` | Standard, Admin 활성화 | 컨테이너 이미지 저장 |
| Azure App Service Plan | `ASP-sense-web` | Standard S1, Linux | 웹앱 호스팅 플랜 |
| Azure App Service | `sense-web` | — | Flask 웹 대시보드 (Production + Staging Slot) |
| Azure Data Factory | `sense-adf` | — | 파이프라인 오케스트레이션 |
| Azure OpenAI | — | gpt-4.1-mini / gpt-5.4-mini | RAG 챗봇·AI 분석 |

### 2-2. Key Vault 시크릿 목록

| 시크릿 이름 | 값 (예시) | 용도 |
|---|---|---|
| `adls-account-name` | `3dtteam1adls` | ADLS Gen2 계정명 |
| `adls-client-id` | sense-databricks-sp Client ID | ADLS 인증 SP |
| `adls-client-secret` | sense-databricks-sp Secret | ADLS 인증 SP |
| `adls-tenant-id` | `5fb256f0-…` | Azure 테넌트 |
| `pg-connection-string` | `postgres @ sense-pg-server` | PostgreSQL 연결 문자열 |
| `azure-openai-endpoint` | Azure OpenAI endpoint URL | GPT API |
| `azure-openai-key` | Azure OpenAI API Key | GPT API |
| `KEY_VAULT_URL` | `https://kv-3dt-team1.vault.azure.net/` | vault_manager 초기화 |

### 2-3. ADLS Gen2 컨테이너 구조

```
3dtteam1adls
 ├── raw/
 │   ├── news/google/         # Google News RSS + Playwright 크롤링
 │   ├── news/naver/          # 네이버 뉴스 API + 본문 크롤링
 │   ├── macro/               # Yahoo Finance 매크로 (OHLCV, FRED 금리)
 │   └── trade/               # 관세청 수출입 통계 (HS Code 8542)
 ├── curated/                 # Databricks 전처리 결과 (시계열 보간, TF-IDF)
 └── feature/
     ├── gold_macro_1y/       # 1년 매크로 피처 마트
     ├── macro_semiconductor/ # 반도체 수출입 파생 변수
     ├── timesfm_forecast/    # TimesFM 2.5 XReg 예측 결과
     └── …
```

### 2-4. PostgreSQL 테이블/뷰 목록

| 스키마.테이블 | 용도 |
|---|---|
| `public.fact_ensemble_forecast` | 앙상블 T+20 예측 결과 (40행: 2종목 × 20일) |
| `gold_news.agg_market_sentiment_daily` | ABSA 일별 감성 집계 |
| `gold_news.v_news_sentiment_trend` | 감성 트렌드 뷰 (avg_sentiment, news_vol, daily_keywords) |
| `sense_databricks.models.automl_삼성전자_t20` | UC 등록 AutoML 모델 v1 (R²=0.817) |
| `sense_databricks.models.automl_SK하이닉스_t20` | UC 등록 AutoML 모델 v1 (R²=0.770) |

### 2-5. ACR 이미지 목록

| 이미지 | 태그 | 내용 |
|---|---|---|
| `sense3dtacr.azurecr.io/sense-web` | `v1.0` | Flask + RAG 챗봇 초기 버전 |
| `sense3dtacr.azurecr.io/sense-web` | `v1.1` | Bold 렌더링·고지문 수정 |
| `sense3dtacr.azurecr.io/sense-web` | `v1.2` | 한/영 병기 레이블 + Plain Language 챗봇 |
| `sense3dtacr.azurecr.io/google-news-crawler` | `latest` | ACI 기반 Google News 크롤러 |

---

## 3. 데이터 파이프라인 아키텍처

```
외부 소스
  ├── 야후 파이낸스   → OHLCV (삼성/SK/NVDA/SOX/환율/금리)
  ├── 네이버 뉴스     → 반도체 뉴스 본문
  ├── Google News    → 글로벌 반도체 뉴스
  ├── FRED           → 금리 6종 (DGS10, DGS2, T10Y2Y, BAMLH0A0HYM2, DFF, DFII10)
  └── 관세청         → 수출입 통계 (HS Code 8542)
         │
         ▼
  ADF (오케스트레이션) ── 매일 16:30 KST 스케줄 트리거
   ├── ACI Activity      → Google News 크롤러 (Playwright one-shot)
   ├── Functions Activity → 네이버 뉴스·환율 수집
   └── Custom Activity   → Yahoo Finance·FRED·관세청
         │
         ▼
  ADLS Gen2 (raw/)
         │  Databricks AutoLoader
         ▼
  ADLS Gen2 (curated/)  ── 01_raw_to_curated.py
   - 결측치 보간 (Forward Fill, 휴장일 통일)
   - ABSA 감성 분석 (Azure OpenAI)
   - TF-IDF 키워드 추출
         │
         ▼
  ADLS Gen2 (feature/)  ── 02_curated_to_feature.py
   - gold_macro_1y: NVDA/SOX 로그수익률, yield_spread, FX, risk_off_flag
   - sense_macro: 23개 파생 리스크 시그널 (macro_stress_score, fear_composite 등)
   - macro_semiconductor: semi_expDlr, semi_impDlr (월별 Forward Fill)
   - 피처 마트: 47개 파생변수 (기술적 지표 + 감성 + 키워드 교호작용)
         │
         ▼
  Databricks (앙상블 실행)  ── ensemble_strategy.py (v0419)
   ├── TimesFM 2.5 XReg 예측  (w=0.45)
   └── AutoML UC BestTrial    (w=0.55)
         │  동적 가중치 조정 (5개 신호: RSI·vol_ratio·이격도·감성·뉴스량)
         ▼
  PostgreSQL (fact_ensemble_forecast)
         │
         ▼
  sense-web (Flask + RAG 챗봇)  ── https://sense-web.azurewebsites.net
```

---

## 4. ML 모델 성능 기록

### 4-1. 모델 비교 (삼성전자)

| 모델 | R² | 비고 |
|---|---|---|
| ElasticNetCV (Silver Layer) | 0.05 | 정규화 과잉, 단순 회귀 한계 |
| AutoML Random Forest (Silver) | 0.72 | v0417 AutoML 하이퍼파라미터: max_depth=8, n_estimators=400 |
| AutoML UC BestTrial (Gold Layer 재학습) | **0.9266** | v0419 피처 통일 후 R² 0.817 → 0.9266 |

### 4-2. 모델 비교 (SK하이닉스)

| 모델 | R² | 비고 |
|---|---|---|
| ElasticNetCV (Silver Layer) | **-1.19** | 완전 실패 — 예측력 없음 |
| AutoML Random Forest (Silver) | 0.86 | v0417 AutoML 결과 |
| AutoML UC BestTrial (Gold Layer 재학습) | **0.7097** | v0419 피처 통일 후 |

### 4-3. 앙상블 가중치 설계

| 단계 | 버전 | TimesFM | UC | 설명 |
|---|---|---|---|---|
| 초기 | v0413 | 0.50 | 0.50 | 동등 기여도 시작 |
| Soft Switching 도입 | v0414 | 동적 | 동적 | RSI·이격도·변동성 연속 조정 |
| 최종 최적화 | v0419 | **0.45** | **0.55** | UC R² 우위 반영, clip [0.25, 0.75] |

#### 동적 가중치 조정 신호 (5개)

| 신호 | 조정 범위 | 방향 |
|---|---|---|
| RSI(14) 과매수(>70) | ±0.20 | UC 강화 |
| RSI(14) 과매도(<30) | ±0.20 | TimesFM 강화 |
| 실현 변동성 비율 (5d/20d) | ±0.15 | 급증 → UC 강화 |
| 120일 이격도 | ±0.15 | 과열 → UC 강화 (1.5제곱 가속) |
| 뉴스 ABSA 감성 + 급증 비율 | ±0.10 | 호재 → TimesFM, 악재/급증 → UC |

#### 레짐 분류

| 레짐 | 조건 | 의미 |
|---|---|---|
| `TREND` | w_trend ≥ 0.55 | 추세 지속 장세 |
| `MEAN_REV` | w_meanrev ≥ 0.55 | 과열·평균 회귀 장세 |
| `NEUTRAL` | 둘 다 < 0.55 | 중립 |

---

## 5. 피처 엔지니어링 요약 (47개)

### 그룹별 구성

| 그룹 | 주요 피처 | 개수 |
|---|---|---|
| 매크로 (Gold Layer) | NVDA/SOX 로그수익률, yield_spread, usd_krw_*, risk_off_flag | ~8 |
| 리스크 시그널 (sense_macro) | macro_stress_score, fear_composite, semi_risk_signal 등 | 23 |
| 기술적 지표 | log_return, rsi_14, atr_14, atr_pct, disparity_120d, realized_vol_5d/20d, vol_ratio | 8 |
| 뉴스 감성 | sentiment_momentum, news_vol_surge, sentiment_vol_7d, sent_price_decouple, avg_sentiment | 5 |
| 키워드 파생 | keyword_diversity_ma7, keyword_delta_momentum, concentration_change, keyword_surge_count | ~4 |
| 교호작용 (Interaction) | keyword_surge_x_rsi, keyword_div_x_vol, sentiment_x_surge, kw_positive_x_disparity | 4 |

---

## 6. 웹 서비스 배포 이력

### SENSE 웹 대시보드 (sense-web)

| 버전 | 날짜 | 주요 내용 |
|---|---|---|
| v1.0 | 4/15 | Flask + RAG 챗봇 초기 배포. Blue-Green Slot 구조 구성 |
| v1.1 | 4/16 | Bold 렌더링 수정, 하단 고지문 추가 (PR #99) |
| v1.2 | 4/16 | 한/영 병기 레이블 (Forecast·Sentiment·Regime·Confidence), Plain Language 챗봇, Dockerfile 추가 (PR #100) |

### 인프라 구성

```
ACR: sense3dtacr.azurecr.io/sense-web:v1.2
  └── python:3.11-slim
  └── gunicorn gthread (JSON CMD 형식)
  └── libpq-dev, gcc 빌드 레이어

App Service: sense-web (ASP-sense-web, Standard S1, Linux, koreacentral)
  ├── Production Slot  → https://sense-web.azurewebsites.net        ✅ v1.2
  └── Staging Slot    → https://sense-web-staging.azurewebsites.net  (swap 후 v1.1)

인증:
  - Managed Identity → ACR Pull (acrUseManagedIdentityCreds=true)
  - Managed Identity → Key Vault Secrets User → pg-connection-string, azure-openai-*

앱 설정:
  - KEY_VAULT_URL = https://kv-3dt-team1.vault.azure.net/
  - WEBSITES_PORT = 8000
```

### Blue-Green 배포 절차

```
1. az acr build  → 새 이미지 빌드 (ACR 내에서 실행, 로컬 Docker 불필요)
2. az webapp config container set  → Staging 슬롯 이미지 교체
3. 앱 설정 확인 (KEY_VAULT_URL, WEBSITES_PORT, acrUseManagedIdentityCreds)
4. Staging 헬스체크 (HTTP 200 확인)
5. az webapp deployment slot swap  → Production ↔ Staging 무중단 전환
```

---

## 7. 주요 기술 결정 및 이유

| 결정 | 이유 |
|---|---|
| **TimesFM 2.5 선택** | Google 사전학습 Foundation Model — 파인튜닝 없이 추세 추종 장세 특화, XReg(외부 공변량) 지원으로 퀀트 지표 직접 주입 가능 |
| **AutoML UC BestTrial 선택** | Databricks AutoML이 하이퍼파라미터 자동 최적화 + Unity Catalog 등록 → sklearn 1.8.0 네이티브 직렬화로 호환성 패치 불필요 |
| **ElasticNet 제거 (v0419)** | 삼성 R²=0.05 / SK R²=-1.19 — 예측력 부족. AutoML UC로 대체 후 삼성 R²=0.93 달성 |
| **Soft Switching 도입** | Hard Threshold 방식은 RSI 69→71 미세 변화에도 가중치 급변(Spike) 발생. 연속 선형·비선형 보간으로 안정화 |
| **5개 감성 신호 추가** | 반도체 AI 슈퍼사이클 국면에서 뉴스 감성이 펀더멘탈보다 빠르게 시장 심리를 반영. 감성 피처 추가 후 예측 안정성 향상 |
| **T+20 예측 horizon** | 기관 투자자 월간 포트폴리오 리뷰 주기와 일치. T+1~5는 노이즈 과다, T+60+는 불확실성 급증 |
| **uv 패키지 관리** | Poetry 대비 10× 빠른 의존성 해결. Python 3.11 버전 고정. `uv sync --extra ml/databricks` 로 선택적 설치 |
| **Azure Key Vault 중앙화** | 모든 시크릿을 코드·Git에서 완전 분리. DefaultAzureCredential 패턴으로 로컬(az login)↔클라우드(Managed Identity) 동일 코드 |

---

## 8. 트러블슈팅 주요 기록

| 이슈 | 원인 | 해결 |
|---|---|---|
| SK하이닉스 R²=-1.19 | Silver Layer 피처 스케일 불일치, ElasticNet 과잉 정규화 | Gold Layer 재학습 + AutoML UC로 교체 → R²=0.71 |
| sklearn 1.4.2→1.8.0 역직렬화 오류 | `__sklearn_is_fitted__` 미구현, `SimpleImputer._fill_dtype` 누락 | `_deep_mark_fitted()` 재귀 패치 함수 직접 개발 |
| Staging 503 오류 | Slot swap 이전 Staging에 `KEY_VAULT_URL`, `WEBSITES_PORT`, `acrUseManagedIdentityCreds` 미설정 | 앱 설정 3개 추가 → HTTP 200 |
| Confidence Score 5.5/4.5 (초기) | TimesFM 시뮬레이션↔ElasticNet 예측값 격차 과대 | TimesFM 실제 XReg 결과 ADLS 연동 후 점수 개선 |
| Hard Threshold Spike | RSI 경계값에서 예측값 불연속 급변 | Soft Switching 연속 보간 함수로 대체 |
| Date 인덱스 충돌 | `reset_index(drop=True)` 호출 시 인덱스·컬럼 동시 존재 충돌 | 조건 분기 처리 (v0418) |
| Silver vs Gold 피처 불일치 | 학습/추론 피처 마트 데이터 소스 차이 → TimesFM context 변화 | 3개 노트북 Gold Layer 소스 통일 (v0419) |

---

## 9. Git/협업 운영 기록

- **기본 브랜치**: `dev` (main이 아닌 dev)
- **워크플로우**: GitHub Flow — feature 브랜치 → PR → Squash merge → dev
- **PR 수**: 100+ (PR #100: v1.2 최종 배포)
- **커밋 컨벤션**: `type(scope): description` (소문자, 50자 이내)
- **pre-commit 훅**: ruff (lint+format+import sort) + detect-secrets
- **브랜치 네이밍**: `feat/`, `fix/`, `hotfix/`, `chore/`, `refactor/`, `docs/`, `set/`

---

## 10. 최종 파이프라인 흐름 (End-to-End)

```
ADF 스케줄 트리거 (16:30 KST)
  → 수집기 실행 (ACI/Functions/Custom Activity)
  → ADLS raw/ 적재
  → Databricks: raw → curated (01_raw_to_curated.py)
  → Databricks: curated → feature (02_curated_to_feature.py)
  → Databricks: feature → ML 피처셋 (03_ml_feature_build.py)
  → Databricks: 앙상블 실행 (ensemble_strategy.py)
      ├── TimesFM 2.5 XReg 예측 (timesfm_forecast/)
      └── AutoML UC BestTrial 추론 (automl_best_trial.py)
  → PostgreSQL: fact_ensemble_forecast 적재
  → sense-web: Flask 대시보드 → 사용자 조회
```

ADF 파이프라인 JSON: `adf/pipeline/Pipeline_Daily_SENSE_Predict.json`  
ADF 트리거: `adf/trigger/tr_daily_sense_predict.json` (매일 16:30 KST)

---

## 11. 리소스 삭제 시 체크리스트

> 리소스 그룹 삭제 전 확인 사항

- [ ] PostgreSQL 데이터 백업 (`pg_dump`) — fact_ensemble_forecast, gold_news.*
- [ ] ADLS feature/ 레이어 주요 파셋 로컬 백업 (timesfm_forecast, gold_macro_1y)
- [ ] ACR 이미지 로컬 Pull 또는 tar 저장 — `sense3dtacr.azurecr.io/sense-web:v1.2`
- [ ] Key Vault 시크릿 목록 기록 (위 2-2 섹션 완료)
- [ ] ADF 파이프라인 JSON Git 커밋 확인 (`adf/` 폴더)
- [ ] Databricks 노트북 Git 동기화 확인 (`notebooks/` 폴더)
- [ ] GitHub Secrets 삭제 (Azure SP 자격증명 등)
- [ ] 리소스 그룹 삭제:
  ```bash
  az group delete --name 3dt-2nd-team1 --yes --no-wait
  ```

---

## 12. 프로젝트 파일 구조 (최종)

```
10_Second_Team_Project/
├── app.py                          # Flask 웹 앱 진입점
├── pyproject.toml                  # 의존성 (uv 관리, Python 3.11)
├── Dockerfile                      # python:3.11-slim, gunicorn gthread
├── .dockerignore
├── adf/
│   ├── pipeline/
│   │   └── Pipeline_Daily_SENSE_Predict.json  # 7단계 순차 파이프라인
│   ├── trigger/
│   │   └── tr_daily_sense_predict.json        # 매일 16:30 KST
│   ├── dataset/, linkedService/, dataflow/
│   └── custom_activity/            # ADF Custom Activity Docker
├── notebooks/
│   ├── ensemble_strategy.py        # 핵심: TimesFM+UC 동적 앙상블 (v0419)
│   ├── automl_best_trial.py        # AutoML UC 추론·SHAP 분석
│   ├── timesfm_inference.py        # TimesFM 2.5 Full Feature
│   ├── 01_raw_to_curated.py        # Databricks 전처리
│   ├── 02_curated_to_feature.py    # 피처 엔지니어링
│   └── 03_ml_feature_build.py      # ML 피처셋 빌드
├── src/
│   ├── utils/vault_manager.py      # Key Vault / ADLS / PostgreSQL 인증
│   ├── ingestion/                  # 수집기 (네이버/야후/관세청)
│   ├── models/                     # ML Studio 학습 스크립트
│   └── service/                    # RAG 서비스 (Flask 라우터, 리트리버)
├── docs/
│   ├── architecture.md
│   ├── implementation_plan.md
│   ├── ensemble_model_guide.md
│   ├── TimesFM_앙상블_튜닝_트러블슈팅.md
│   ├── analysis_results.md
│   └── project_retrospective.md   # ← 이 파일
└── tests/
```

---

*문서 작성일: 2026-04-17 · 발표 완료 후 리소스 삭제 전 기록*
