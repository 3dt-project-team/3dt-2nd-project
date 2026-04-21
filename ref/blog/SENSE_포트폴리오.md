# SENSE 포트폴리오

> **프로젝트명**: SENSE — Semiconductor Economic News & Sentiment Engine  
> **기간**: 2025년 4월 (2주)  
> **팀 규모**: 6인  
> **역할**: 클라우드 인프라·아키텍처 설계 + ML 모델·앙상블 전략 (페어 담당 2개 파트)

---

## Key Point

> **Azure Medallion 파이프라인 설계 + 동적 가중치 앙상블 모델 개발** — ADF 7단계 자동화 파이프라인과 Databricks Medallion 아키텍처를 직접 설계하고, TimesFM 2.5 XReg + AutoML Random Forest를 결합한 Soft Switching 앙상블로 T+20 예측 R² 초기 −1.19 → 0.82/0.77 달성. sklearn 1.4→1.8 역직렬화 호환성 패치를 직접 개발하여 무중단 배포 유지.

**Tech Stack**: Python 3.11 · Azure Data Factory · ADLS Gen2 · Azure Databricks · Azure ML Studio · Azure Key Vault · PostgreSQL · TimesFM 2.5 · scikit-learn · MLflow · Docker · Flask · uv

---

## Description

반도체 주가(삼성전자·SK하이닉스)에 영향을 미치는 **뉴스 감성**, **거시경제 지표**, **수급·파생 데이터** 세 가지 축을 통합하여 T+20일 예측과 근거를 함께 제공하는 AI 시스템. 6인 팀, 페어 단위로 파트 분담.

**팀 내 역할 (김건동 — 인프라·아키텍처 + ML·데이터 분석)**
- **[아키텍처]** Azure 클라우드 전체 설계: ADF → ADLS Gen2(Medallion) → Databricks → ML Studio → PostgreSQL
- **[아키텍처]** ADF 7단계 순차 파이프라인 구성, 타이머 트리거 완전 자동화
- **[아키텍처]** Azure Key Vault 기반 `DefaultAzureCredential` 자격증명 중앙화
- **[ML]** 47개 피처 엔지니어링 설계 (기술적 지표·거시경제 리스크·ABSA 뉴스 감성)
- **[ML]** TimesFM 2.5 XReg + AutoML UC BestTrial 기반 Soft Switching 동적 앙상블 개발
- **[ML]** Confidence Score 시스템 및 레짐 분류(TREND/MEAN_REV/NEUTRAL) 설계

---

## Key Experience & Retrospective

---

### [경험 1] ADF vs Databricks 전처리 이원화 — 기술 선택의 근거

**Problem**  
데이터 전처리를 ADF Data Flow 단일화로 설계했으나, 10만 건 이상의 뉴스 JSON 처리와 Python 기반 복잡한 피처 엔지니어링을 ADF에서 수행하기에 성능·유연성 한계 발생.

**Solution**  
세 가지 기준(데이터 크기, 변환 복잡도, ML 연동 필요성)으로 역할 이원화:
- **ADF Data Flow**: 환율·금리 등 소규모 정형 데이터 변환 (GUI 기반, 운영 접근성 우수)
- **Databricks**: 대용량 뉴스 JSON·Parquet 처리 + Unity Catalog 기반 ML 모델 연동 필수

**Result**  
- 하이브리드 아키텍처로 파이프라인 안정성 확보
- 심사위원 "ADF vs Databricks 비교 분석이 우수하다" 평가 — 기술 선택의 근거를 명확히 설명하는 것이 면접·발표에서 강력한 어필 포인트임을 확인

---

### [경험 2] 7단계 ADF 파이프라인 — 트리거 충돌과 중복 적재 해결

**Problem**  
멀티 파이프라인 동시 실행 시 트리거 타이밍 충돌로 동일 날짜 데이터 중복 적재 발생. 팀 간 ADF JSON 편집 시 Git 병합 충돌로 파이프라인 덮어쓰기 위험 상존.

**Solution**  
- Activity 간 명시적 의존성(Success/Failure) 체인으로 **7단계 순차 실행** 보장
- 타이머 트리거를 장 마감 후 1시간(16:30 KST) 단일 시점으로 통일
- 팀 내 파이프라인 JSON 편집 협의 프로토콜 수립 (편집 전 팀 채팅 알림 의무화)

**Result**  
- 2주 운영 중 중복 적재 0건
- 매일 16:30 ADF 타이머 트리거 기반 **완전 무인 자동화** 달성 (수집→전처리→예측→PostgreSQL 적재)

---

### [경험 3] 초기 R² = −1.19 → 0.82 달성 — 피처 설계가 모델보다 중요하다

**Problem**  
초기 모델(ElasticNet + OHLCV 단순 피처)에서 삼성전자 R²=0.05, SK하이닉스 R²=−1.19 기록. 음수 R²은 모델이 단순 평균 예측보다 못하다는 의미.

**Cause 분석**
- 변수 간 스케일 불일치 (삼성전자 주가 ~60,000원 vs FRED 금리 ~4.5%)
- 타겟 변수를 절대 주가로 설정 → 비정상(Non-stationary) 시계열 학습 오류
- 선형 모델의 비선형 관계 포착 불가

**Solution**  
세 가지 근본적 재설계:

1. **타겟 재정의**: 절대 주가 → `log(P_{t+20} / P_t)` T+20 누적 로그수익률 (정상성 확보)
2. **피처 47개 설계**: RSI·ATR·120일 이격도·`vol_ratio` 등 기술 지표 + `macro_stress_score`·`fear_composite` 거시 리스크 + ABSA 뉴스 감성 점수
3. **모델 교체**: ElasticNet → Databricks AutoML BestTrial (Random Forest, 비선형 관계 자동 학습)

```python
# RSI 기반 Soft Switching 가중치 — 시장 국면별 동적 배합
def compute_dynamic_weights(rsi, vol_ratio, disparity_120d, avg_sentiment, news_vol_surge):
    adj = 0.0
    if rsi > 70:   # 과매수 → AutoML(평균회귀) 강화
        adj -= 0.20 * ((rsi - 70) / 30) ** 1.5
    elif rsi < 30: # 과매도 → TimesFM(추세) 강화
        adj += 0.20 * ((30 - rsi) / 30) ** 1.5
    # vol_ratio, 이격도, 감성, 뉴스 급증 신호 추가 반영
    ...
    return np.clip(0.45 + adj, 0.25, 0.75), ...  # 클리핑으로 극단 편향 방지
```

**Result**  
- 삼성전자 R² 0.05 → **0.82**, SK하이닉스 R² −1.19 → **0.77**
- Hard Threshold 가중치(불연속 Spike) → Soft Switching 연속 보간으로 일별 예측값 안정화

---

### [경험 4] sklearn 역직렬화 오류 — 무중단 배포를 위한 호환성 패치

**Problem**  
Databricks Runtime 업그레이드 후 AutoML UC 등록 모델 추론 시 `AttributeError: 'SimpleImputer' object has no attribute '_fill_dtype'` 발생. 직렬화 환경(sklearn 1.4.2) ↔ 추론 환경(sklearn 1.8.0) 버전 불일치가 원인.

**Solution**  
공유 클러스터 환경을 제어할 수 없는 상황 → AutoML 재실행(60분+) 대신 **재귀적 호환성 패치 함수** 직접 개발:

```python
def _deep_mark_fitted(estimator):
    """sklearn 1.4.x → 1.8.x 역직렬화 호환성 패치 (Pipeline/ColumnTransformer 재귀 처리)"""
    if not hasattr(estimator, "__sklearn_is_fitted__"):
        object.__setattr__(estimator, "__sklearn_is_fitted__", lambda: True)
    if (estimator.__class__.__name__ == "SimpleImputer"
            and hasattr(estimator, "statistics_")
            and not hasattr(estimator, "_fill_dtype")):
        estimator._fill_dtype = estimator.statistics_.dtype
    for attr in ["steps", "estimators_", "transformers_"]:
        for item in (getattr(estimator, attr, None) or []):
            _deep_mark_fitted(item[1] if isinstance(item, tuple) else item)
```

**Result**  
- AutoML 재학습 없이 기존 모델 즉시 복구 — 다운타임 0
- 클러스터 환경이 바뀌어도 코드 한 줄로 대응 가능한 범용 패치로 발전

---

## Tech Stack 선택 근거

| 기술 | 선택 이유 | 비교 대상 |
|---|---|---|
| **Azure** | Key Vault 중앙 인증 + ADF-Databricks 네이티브 연동 + 관리형 ML Studio | AWS (연동 복잡도, 팀 학습 곡선 불리) |
| **PostgreSQL** | 오픈소스 활용도 + 동시 다중 조회 성능 | ADLS Gen2 단독 (분산 조회 한계), Azure SQL (오픈소스 생태계 열세) |
| **TimesFM 2.5** | Foundation Model XReg 공변량 주입 → 매크로 컨텍스트 반영 추세 예측 | LSTM (학습 데이터 부족 시 과적합), Prophet (외부 변수 주입 한계) |
| **AutoML UC BestTrial** | 비선형 관계 자동 탐색 + Unity Catalog 모델 버전 관리 자동화 | 수동 하이퍼파라미터 튜닝 (시간·인력 비용) |
| **Soft Switching** | 연속 보간으로 예측값 Spike 제거, 클리핑으로 극단 편향 방지 | Hard Threshold (불연속 가중치 점프 문제) |

---

## 결과 및 성과

- 6개 외부 소스 완전 자동 수집 파이프라인 — **매일 16:30 ADF 타이머 트리거 무인 운영**
- T+20 예측 성능: 삼성전자 R² **0.82**, SK하이닉스 R² **0.77** (초기 −1.19 대비)
- Confidence Score + 레짐 분류(TREND/MEAN_REV/NEUTRAL) 기반 **사용자 투자 판단 보조 시스템** 완성
- 심사위원 총평: "공연을 본 것 같다" — 기술 깊이·비즈니스 가치·Responsible AI 전방위 호평

---

## Links

- **GitHub**: [3dt-project-team/3dt-2nd-project](https://github.com/3dt-project-team/3dt-2nd-project)
- **기술 블로그**: `ref/blog/sense_01~05` (아키텍처·파이프라인·피처·앙상블·트러블슈팅 5편)
- **아키텍처 문서**: `docs/architecture.md`
- **배포 가이드**: `docs/cicd/webapp_container_deployment.md`
