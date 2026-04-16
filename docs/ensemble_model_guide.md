# SENSE 앙상블 모델 가이드

> **문서 버전**: v0419 (2025-04-19)
> **대상 코드**: `notebooks/ensemble_strategy.py`
> **실행 환경**: Databricks (Azure), Python 3.11, scikit-learn 1.8, numpy, pandas, mlflow

---

## 목차

1. [모델 개요](#1-모델-개요)
2. [파이프라인 구조](#2-파이프라인-구조)
3. [피처 엔지니어링 (Step 1)](#3-피처-엔지니어링-step-1)
4. [AutoML UC BestTrial 모델 (Step 2)](#4-automl-uc-besttrial-모델-step-2)
5. [동적 가중치 규칙 — 설계 의도 (Step 3)](#5-동적-가중치-규칙--설계-의도-step-3)
6. [Confidence Score](#6-confidence-score)
7. [모델 튜닝 이력](#7-모델-튜닝-이력)
8. [알려진 한계 및 개선 방향](#8-알려진-한계-및-개선-방향)

---

## 1. 모델 개요

### 1-1. 앙상블 전략 요약

SENSE 앙상블은 **두 가지 상반된 시장 관점**을 결합합니다.

| 모델 | 역할 | 관점 |
|---|---|---|
| **TimesFM 2.5-200M** | Trend Model (추세) | "현재 모멘텀이 지속된다" |
| **Databricks AutoML UC BestTrial** | Mean-Reversion Model (평균회귀) | "극단은 평균으로 돌아온다" |

> **v0419 변경**: ElasticNetCV(R²≈0.05/−1.19)를 제거하고, Databricks AutoML이 자동 선택한
> Unity Catalog(UC) BestTrial 모델(삼성 R²=0.9266, SK R²=0.7097)로 교체.
> 수동 RandomForest 학습도 제거 — AutoML 파이프라인이 최적 모델을 선택합니다.

두 모델의 예측값을 **시장 레짐(RSI, 변동성, 이격도, 뉴스 감성)에 따라 가중치를 동적으로 조절**하여 결합합니다. 이는 단일 모델의 편향을 보완하고, 시장 상태에 적응하는 예측을 생성합니다.

### 1-2. 입출력 명세

```
[입력]
├── ADLS feature/gold_macro_1y/          (매크로·주가·환율·금리)
├── ADLS feature/macro_semiconductor/     (반도체 수출입 월별)
├── ADLS feature/sense_macro/             (리스크 시그널 23개 파생변수)
├── ADLS feature/timesfm_forecast/        (TimesFM 2.5 XReg 결과, 3-tier 로드)
├── PostgreSQL gold_news.v_news_sentiment_trend  (일별 뉴스 감성)
└── Unity Catalog AutoML BestTrial 모델 (mlflow.sklearn.load_model)

[출력]
├── fact_ensemble_forecast DataFrame → PostgreSQL 적재
├── Dynamic Weighting Strategy 시각화 차트
└── AI(GPT gpt-5.4-mini / Responses API) 해석 텍스트
```

### 1-3. 대상 종목

| 종목코드 | 종목명 | close 컬럼 |
|---|---|---|
| `005930.KS` | 삼성전자 | `yfinance_samsung_close` |
| `000660.KS` | SK하이닉스 | `yfinance_skhynix_close` |

---

## 2. 파이프라인 구조

```
Step 1: Feature Engineering
├── 기술적 보조지표 생성 (RSI, ATR, 이격도, 로그수익률)
├── 피처 마트 구성 (47+ 컬럼)
└── 반도체/KFinance 데이터 병합

Step 2: ElasticNetCV + Time-Decay
├── 타겟: 로그수익률 log(P_{t+20} / P_t) ← v0414
├── Time-Decay 가중치 (half_life=30)
├── ElasticNetCV (L1+L2, alpha 0.001~1.0)
└── 피처 중요도 출력

Step 3: 동적 가중치 앙상블
├── TimesFM 예측 로드 (또는 시뮬레이션)
├── Soft Switching 가중치 계산 ← v0414
│   ├── RSI 보간 함수
│   ├── 변동성 보간 함수
│   ├── 이격도 보간 함수
│   └── 복합 지표 Interaction Term
├── 앙상블 점 예측 + PI 밴드
└── Confidence Score 산출

Step 4: 출력
├── 시각화 (Dynamic Weighting Strategy 차트)
├── fact_ensemble_forecast DataFrame
├── PostgreSQL 적재
└── Azure OpenAI GPT 해석
```

---

## 3. 피처 엔지니어링 (Step 1)

### 3-1. 기술적 보조지표

| 지표 | 함수 | 산식 | 용도 |
|---|---|---|---|
| **RSI(14)** | `compute_rsi()` | 100 − 100/(1+RS), RS = EMA(gain)/EMA(loss) | 과매수/과매도 판단 → 가중치 조정 |
| **ATR(14)** | `compute_atr()` / `compute_atr_from_close()` | EMA(True Range, 14) | 변동성 레짐 판단 |
| **120일 이격도** | `create_enhanced_features()` 내부 | (close − MA120) / MA120 × 100 | 장기 추세 대비 괴리율 |
| **로그수익률** | `create_enhanced_features()` 내부 | log(P_t / P_{t−1}) | 스케일 불변 수익률 |
| **Realized Vol (5d/20d)** | `create_enhanced_features()` 내부 | std(log_return, window) × √252 | 단기/장기 변동성 |
| **vol_ratio** | `create_enhanced_features()` 내부 | realized_vol_5d / realized_vol_20d | 변동성 가속/감속 |
| **ATR%** | `create_enhanced_features()` 내부 | ATR / close × 100 | 종목 간 비교 가능한 정규화 변동성 |

### 3-2. 피처 마트 구조

- **기본 컬럼 33개**: close, kfin_*, semi_*, yfinance_*, fred_*, usd_krw_rate 등
- **매크로 파생 14개**: 교호 작용(5), 시차(5), 변동성(4)
- **sense_macro 파생변수 22개**: NVDA/SOX 변동성, 금리 스프레드, 리스크 시그널 등
- **Step 1 추가 7개**: log_return, rsi_14, atr_14, atr_pct, disparity_120d, realized_vol_5d, realized_vol_20d, vol_ratio
- **뉴스 감성 파생 6개**: sentiment_momentum, news_vol_surge, sentiment_vol_7d, keyword_diversity, keyword_delta, keyword_concentration
- **총 69+ 컬럼** (Gold Layer 통합)

---

## 4. AutoML UC BestTrial 모델 (Step 2)

### 4-1. 모델 변경 이력 및 선택 이유

| 버전 | 회귀 모델 | R² (삼성/SK) | 비고 |
|---|---|---|---|
| v0413~v0414 | ElasticNetCV | 0.697 / −0.329 | 스케일 문제, 과잉 정규화 |
| v0414 | ElasticNetCV (로그수익률 타겟) | 0.05 / −1.19 | 개선 실패 |
| v0417 | RF+EN 블렌딩 (0.7\*RF + 0.3\*EN) | RF 0.72/0.86 | 수동 학습 |
| **v0419** | **Databricks AutoML UC BestTrial** | **0.9266 / 0.7097** | **최종 채택** |

> **결론**: ElasticNet은 피처 47개에서 유의미한 패턴을 추출하지 못했고(R²≈0.05),
> Databricks AutoML이 자동 탐색한 BestTrial 파이프라인(SimpleImputer + RandomForest 등)이
> Gold Layer 69개 피처에서 압도적 성능을 달성.

### 4-2. Unity Catalog 모델 정보

| 항목 | 삼성전자 | SK하이닉스 |
|---|---|---|
| UC 모델명 | `sense_databricks.models.automl_삼성전자_t20` | `sense_databricks.models.automl_SK하이닉스_t20` |
| 버전 | v1 | v1 |
| R² (train/test) | 0.8165 / 0.9266 | 0.7703 / 0.7097 |
| 방향 정확도 | 95.0% | 81.7% |
| 타겟 | `log(close_{t+20} / close_t)` 로그수익률 | 동일 |
| 학습 데이터 | Gold Layer `feature/` 컨테이너 | 동일 |

### 4-3. 모델 로딩 및 호환성 패치

```python
import mlflow
from mlflow import MlflowClient

mlflow.set_registry_uri("databricks-uc")
client = MlflowClient(registry_uri="databricks-uc")

UC_MODELS = {
    "005930.KS": "sense_databricks.models.automl_삼성전자_t20",
    "000660.KS": "sense_databricks.models.automl_SK하이닉스_t20",
}

# 최신 버전 조회 → 모델 로드
versions = client.search_model_versions(f"name='{model_name}'")
latest_ver = max(int(v.version) for v in versions)
model = mlflow.sklearn.load_model(f"models:/{model_name}/{latest_ver}")
```

**sklearn 1.4 → 1.8 호환성 패치** (`_deep_mark_fitted`):

Databricks AutoML이 sklearn 1.4.2로 학습한 모델을 1.8.0 런타임에서 로드할 때
`__sklearn_is_fitted__` 메서드 누락으로 `NotFittedError` 발생. 재귀적 패치로 해결:

```python
def _deep_mark_fitted(obj, _visited=None):
    """역직렬화된 sklearn 파이프라인의 모든 하위 estimator를 fitted로 마킹."""
    # SimpleImputer._fill_dtype 누락 복원 (1.4.2 → 1.8.0)
    if isinstance(obj, SimpleImputer) and not hasattr(obj, "_fill_dtype"):
        obj._fill_dtype = obj.statistics_.dtype if hasattr(obj, "statistics_") else np.float64
    # 모든 속성 재귀 순회하며 fitted 마킹
    ...
```

### 4-4. 예측 및 역변환

```python
# 피처 준비 (학습 시와 동일한 피처 정렬)
X_latest = mart.drop(columns=["date", "target", ...]).iloc[[-1]]

# 로그수익률 예측
log_return_pred = model.predict(X_latest)[0]

# 가격 역변환
last_price = mart["close"].iloc[-1]
price_pred = last_price * np.exp(log_return_pred)
```

---

## 5. 동적 가중치 규칙 — 설계 의도 (Step 3)

### 5-1. 설계 철학

> **"Dynamic Weight Interpolation"** — 시장은 이진(Binary)이 아니라 연속(Continuous)입니다.
> RSI 69와 71에서 가중치가 급변하는 것은 비현실적입니다.
> 모든 지표 구간에서 가중치가 부드럽게 전이되도록 설계합니다.

**기본 원칙:**
- Base weight: TimesFM 0.45 / UC BestTrial 0.55 (UC R² 우위 반영)
- 5개 조정 함수가 독립적으로 가중치를 ±조정 (v0416: 감성 추가)
- 최종 클리핑: [0.25, 0.75] — 양쪽 모델 모두 검증되어 극단 편중 방지

### 5-2. RSI 가중치 조정 (`_rsi_weight_adjustment`)

**목적**: 과매수/과매도 상태에서 적절한 모델로 가중치를 기울임

**퀀트적 근거**: Wilder(1978)의 RSI는 70 이상에서 과매수, 30 이하에서 과매도를 나타냅니다. 그러나 Hard Threshold(if/else)는 RSI 69.9→70.1에서 가중치가 불연속적으로 점프하는 문제가 있습니다.

**구간별 설계 의도:**

| 구간 | 조정값 | 의도 |
|---|---|---|
| RSI < 30 (극단 과매도) | +0.13 + 가속 보정(최대 +0.07) | 반등 모멘텀이 강할 가능성 → TimesFM(추세) 강화. 극단으로 갈수록 반등 확률 상승 → 가속 |
| RSI 30~50 (약세~중립) | +0.13 × (50 − RSI)/20, 최대 +0.13 | 중립에서 점진적으로 추세 모델 신뢰도 증가. RSI 30에서 +0.13까지 선형 증가 |
| RSI 50 (완전 중립) | 0.00 | 조정 없음 — 두 모델 동등 |
| RSI 50~70 (강세~과매수) | −0.0065 × (RSI − 50), 최대 −0.13 | 과매수 접근 시 점진적으로 UC(회귀) 강화. 과열 조정에 대비 |
| RSI > 70 (극단 과매수) | −0.13 − 가속 보정(최대 −0.07) | 과열 상태에서 평균회귀 압력 극대화. 가속은 완만 → 급격한 전환 방지 |

> **v0416 변경**: UC BestTrial(R²=0.93)이 검증된 모델이므로 극단적 전환 불필요.
> 조정 범위 ±0.30 → **±0.20**으로 축소.

**수식:**
- 정상 구간(30~50): $\text{adj} = +0.13 \times (50 - \text{RSI}) / 20$
- 정상 구간(50~70): $\text{adj} = -0.0065 \times (\text{RSI} - 50)$
- 극단 과매도(<30): $\text{adj} = +0.13 + 0.07 \times \min\left(\frac{30 - \text{RSI}}{30}, 1\right)$
- 극단 과매수(>70): $\text{adj} = -0.13 - 0.07 \times \min\left(\frac{\text{RSI} - 70}{30}, 1\right)$

**대칭 가속 설계 이유 (v0416):**
- 양쪽 모델이 모두 검증된 실제 모델이므로 과매도(+0.07)와 과매수(−0.07) 가속을 대칭으로 설계

### 5-3. 변동성 가중치 조정 (`_vol_weight_adjustment`)

**목적**: 변동성 레짐 변화를 감지하여 모델 선택에 반영

**퀀트적 근거**: `vol_ratio = realized_vol_5d / realized_vol_20d`는 단기 변동성이 장기 대비 얼마나 높은지를 측정합니다. 급등은 레짐 전환 신호이고, 안정은 추세 지속 환경입니다.

| 구간 | 조정값 | 의도 |
|---|---|---|
| vol_ratio ≤ 0.8 (저변동) | +0.12 × (0.8 − vol)/0.8 | 안정적 환경 → 추세 지속 가능 → TimesFM 강화 |
| 0.8 < vol_ratio < 1.2 (데드존) | 0.00 | 정상 변동성 → 조정 불필요. **노이즈 필터링** |
| vol_ratio ≥ 1.2 (고변동) | −0.15 × min((vol−1.2)/0.8, 1) | 변동성 급증 → 레짐 전환 가능 → UC(보수적) 강화 |

**데드존(0.8~1.2) 설계 의도:**
- 변동성 비율의 정상 범위. 이 구간에서는 변동성이 의미 있는 신호를 주지 않으므로 묵시적으로 무시
- 불필요한 가중치 변동(whipsaw)을 방지

> **v0416 변경**: ±0.20 → **±0.15** 스케일 조정 (UC 모델 신뢰도 향상에 따른 보수적 운영)

### 5-4. 이격도 가중치 조정 (`_disparity_weight_adjustment`)

**목적**: 장기 평균(MA120) 대비 괴리가 클수록 평균회귀 압력을 비선형으로 강화

**퀀트적 근거**: 120일 이동평균 이격도가 극단에 도달하면 평균회귀(Mean Reversion) 확률이 비선형적으로 증가합니다. 이격도 10%와 20%의 차이는 단순 2배가 아니라 회귀 압력이 가속됩니다.

| 구간 | 조정값 | 의도 |
|---|---|---|
| disparity > 0 (양의 이격) | $-0.15 \times \min(d/20, 1)^{1.5}$ | 장기 평균 위에 위치 → 하방 회귀 압력. **1.5제곱 가속**: 이격도가 클수록 회귀 압력 급증 |
| disparity < 0 (음의 이격) | $+0.15 \times \min(|d|/10, 1)^{1.5}$ | 장기 평균 아래 → 반등 기대 → 추세 모델 강화 |

**1.5제곱 가속의 의미:**

| 이격도 | 선형 조정 | 1.5제곱 조정 | 차이 |
|---|---|---|---|
| 5% | −0.0375 | −0.0264 | 완만 (일반 영역) |
| 10% | −0.075 | −0.053 | 여전히 완만 |
| 15% | −0.1125 | −0.092 | 가속 시작 |
| 20% | −0.15 | −0.15 | 최대치 도달 |

→ 작은 이격도에서는 조정이 약하고, 극단으로 갈수록 급격히 강해지는 비선형 구조

**양/음 비대칭(d/20 vs |d|/10) 설계 이유:**
- 양의 이격(고평가) 20%까지 최대 조정 → 상승장에서 과도한 보수성을 방지
- 음의 이격(저평가) 10%에서 최대 조정 → 급락 후 반등 기대를 빠르게 반영

### 5-5. 복합 지표 Interaction Term (`_interaction_weight`)

**목적**: 단일 지표만으로 포착하기 어려운 **복합 신호**를 반영

**퀀트적 근거**: RSI 과매수 단독보다 RSI 과매수 + 변동성 급증이 동시에 발생하면 급락 확률이 훨씬 높습니다. 단일 지표의 합보다 복합 효과가 크므로 별도의 Interaction Term이 필요합니다.

| 규칙 | 조건 | 조정값 | 의도 |
|---|---|---|---|
| **과매수 + 고변동** | RSI > 60 AND vol_ratio > 1.2 | −0.08 × strength | 과열 + 불안정 = 급락 위험 ↑ → UC 긴급 강화 |
| **과매도 + 고변동** | RSI < 40 AND vol_ratio > 1.2 | +0.08 × strength | 공포 매도 + 변동성 = V자 반등 가능 → TimesFM 강화 |
| **이격도 + 과매수** | disparity > 15% AND RSI > 65 | −0.08 × strength | 장기 고평가 + 단기 과열 = 이중 회귀 압력 → UC 강화 |
| **호재 + 과매수** | sentiment > 0.3 AND RSI > 60 | −0.08 × strength | 모멘텀 과열 경고 → UC 강화 (v0416) |
| **악재 + 과매도** | sentiment < −0.3 AND RSI < 40 | +0.08 × strength | 패닉 → 역발상 반등 기대 → TimesFM 강화 (v0416) |

**strength 계산**: 각 조건의 초과 정도를 곱하여 신호 강도를 산출

$$\text{strength} = \text{rsi\_strength} \times \text{vol\_strength}$$

- `rsi_strength = min((RSI − 60) / 40, 1)` — RSI가 60을 넘을수록 강도 증가, 100에서 최대
- `vol_strength = min((vol − 1.2) / 0.8, 1)` — vol이 1.2를 넘을수록 강도 증가, 2.0에서 최대

### 5-6. 감성 가중치 조정 (`_sentiment_weight_adjustment`) — v0416 추가

**목적**: 뉴스 감성 극단값과 뉴스량 급증을 레짐 전환 전조 신호로 활용

| 조건 | 조정값 | 의도 |
|---|---|---|
| avg_sentiment > 0.3 (강한 호재) | +0.07 × strength | 모멘텀 지속 기대 → TimesFM 강화 |
| avg_sentiment < −0.3 (강한 악재) | −0.07 × strength | 과도한 비관 → 평균회귀 기대 → UC 강화 |
| news_vol_surge > 2.0 (뉴스 폭증) | −0.03 × strength | 변곡점 전조 → 보수적 UC 강화 |

- 최종 클리핑: ±0.10 이내 (UC BestTrial이 이미 감성 피처를 내재하므로 조정분 축소)

### 5-7. 가중치 합산 및 클리핑

```
w_trend = 0.45 + rsi_adj + vol_adj + disp_adj + interaction_adj + sent_adj
w_trend = clip(w_trend, 0.25, 0.75)
w_meanrev = 1.0 − w_trend
```

**클리핑 범위 [0.25, 0.75] 설계 이유 (v0416):**
- 양쪽 모델이 모두 검증된 실제 모델 (TimesFM Zero-shot + UC R²=0.93)
- 극단 편중 불필요 → v0414의 [0.15, 0.85]에서 좁혀 보수적 운영
- 최소 25%의 가중치는 "반대 의견"으로 리스크 헤지 역할

**레짐 라벨 결정:**
| 조건 | 레짐 | regime_flag |
|---|---|---|
| w_trend ≥ 0.55 | TREND | 1 |
| w_meanrev ≥ 0.55 | MEAN_REV | −1 |
| 나머지 | NEUTRAL | 0 |

### 5-8. 가중치 규칙 종합 예시

**시나리오 A:** RSI=75, vol_ratio=1.4, disparity=+18%, 감성=−0.1
```
rsi_adj     = -0.13 - 0.07 × min((75-70)/30, 1)  = -0.142
vol_adj     = -0.15 × min((1.4-1.2)/0.8, 1)       = -0.038
disp_adj    = -0.15 × min(18/20, 1)^1.5            = -0.117
interaction = -0.08 × (15/40 × 0.25)               = -0.008
sent_adj    = 0.00 (±0.3 이내 → 무조정)
────────
w_trend     = 0.45 - 0.142 - 0.038 - 0.117 - 0.008 = 0.145
→ clip(0.145, 0.25, 0.75) = 0.25 (최소값 적용)
→ UC 75%, TimesFM 25% — 강한 회귀 레짐
```

**시나리오 B:** RSI=25, vol_ratio=0.6, disparity=−12%, 감성=+0.5
```
rsi_adj     = +0.13 + 0.07 × min((30-25)/30, 1)   = +0.142
vol_adj     = +0.12 × (0.8-0.6)/0.8                = +0.030
disp_adj    = +0.15 × min(12/10, 1)^1.5            = +0.150
interaction = +0.08 × (15/40 × 0.75)               = +0.023 (Rule 2)
sent_adj    = +0.07 × min((0.5-0.3)/0.4, 1)        = +0.035
────────
w_trend     = 0.45 + 0.142 + 0.030 + 0.150 + 0.023 + 0.035 = 0.830
→ clip(0.830, 0.25, 0.75) = 0.75 (최대값 적용)
→ TimesFM 75%, UC 25% — 강한 추세 레짐
```

---

## 6. Confidence Score

### 6-1. 산출 로직

신뢰도 점수는 **PI(Prediction Interval) 너비**와 **모델 간 합의도** 두 축으로 구성됩니다.

$$\text{Confidence} = \text{PI Score} + \text{Consensus Score}$$

| 구성 요소 | 배점 | 산식 | 의미 |
|---|---|---|---|
| PI Score | 0~50 | $\min(50, \; 250 / \max(\text{PI\_width\%}, 1))$ | PI 밴드가 좁을수록 예측 정밀도 높음 |
| Consensus | 0~50 | $\max(0, \; 50 \times (1 - \frac{\text{divergence\%}}{20}))$ | 두 모델 예측이 일치할수록 높은 점수 |

### 6-2. 해석 기준

| 점수 구간 | 해석 |
|---|---|
| 80~100 | 높은 신뢰도 — 두 모델 합의 + 좁은 PI |
| 50~80 | 중간 신뢰도 — 부분 합의 또는 중간 PI |
| 20~50 | 낮은 신뢰도 — 모델 간 괴리 또는 넓은 PI |
| 0~20 | 매우 낮음 — 불확실성 높음, 투자 판단 유보 권고 |

---

## 7. 모델 튜닝 이력

### 7-1. 버전별 변경 사항

| 항목 | v0413 (초기) | v0414 (Soft Switching) |
|---|---|---|
| **ElasticNet 타겟** | 절대가(원) | 로그수익률 log(P_{t+20}/P_t) |
| **alpha 범위** | None (자동: 40~189) | np.logspace(-3, 0, 50) → 0.001~1.0 |
| **half_life** | 60 거래일 | 30 거래일 |
| **가중치 방식** | Hard Threshold (if/else) | Soft Switching (연속 보간 함수) |
| **RSI 규칙** | RSI>70: −0.20 / RSI<30: +0.20 | 선형 보간 + 극단 가속 |
| **변동성 규칙** | vol>1.5: −0.20 / vol<0.8: +0.20 | 데드존(0.8~1.2) + 양 극단 선형 |
| **이격도 규칙** | disparity>20: −0.10 / <−10: +0.20 | 1.5제곱 비선형 가속 |
| **Interaction Term** | 없음 | 3가지 복합 규칙 |
| **가중치 클리핑** | [0.20, 0.80] | [0.15, 0.85] |

### 7-2. v0415~v0419 변경 이력

| 버전 | 주요 변경 |
|---|---|
| **v0415** | 뉴스 감성 통합: `_sentiment_weight_adjustment()` 추가, gold_news 연동, 감성 파생 피처 3종 |
| **v0416** | 키워드 파생변수 6종 추가, 멀티모델 GPT 비교, 가중치 스케일 조정 (RSI ±0.20, vol ±0.15, 감성 ±0.10), 기본 가중치 0.45/0.55, 클리핑 [0.25, 0.75] |
| **v0417** | AutoML RandomForest 통합 (RF+EN 블렌딩 0.7:0.3), SQLAlchemy 2.x 호환 |
| **v0418** | AI 모델 gpt-5.4-mini 전환 (Responses API), ElasticNet 시나리오 플래그 추가 |
| **v0419** | **UC 모델 재학습** (Gold Layer 69 피처), ElasticNet 완전 제거, RF 수동 학습 제거, 3-tier TimesFM 로드, sklearn 1.4→1.8 호환성 패치 |

### 7-3. v0413 실행 결과 (참고)

| 항목 | 삼성전자 | SK하이닉스 |
|---|---|---|
| ElasticNet R² | 0.697 | **−0.329** ⚠️ |
| alpha | 40.85 | 189.31 |
| 활성 피처 | ~15/47 | ~3/47 |
| T+20 예측 | −16.13% | −16.59% |
| 앙상블 T+20 | +3.6% | +25.7% |
| Confidence | 5.5/100 | 4.5/100 |

### 7-4. v0419 실행 결과 (UC BestTrial 기반)

| 항목 | 삼성전자 | SK하이닉스 |
|---|---|---|
| UC BestTrial R² (test) | **0.9266** | **0.7097** |
| 방향 정확도 | 95.0% | 81.7% |
| 데이터 소스 | Gold Layer (feature/) | Gold Layer (feature/) |
| TimesFM 로드 | ADLS 실제 결과 | ADLS 실제 결과 |

### 7-5. v0413 문제 진단 → v0414~v0419 해결 매핑

| 문제 | 원인 | 해결책 |
|---|---|---|
| SK하이닉스 R²=−0.33 | 스케일 차이 → 수렴 실패 | v0414: 로그수익률 타겟 |
| alpha=189 (과잉 정규화) | alpha 범위 너무 넓음 | v0414: alpha 0.001~1.0 |
| ElasticNet R²≈0.05 | 선형 모델의 한계 | v0419: AutoML UC BestTrial로 교체 (R²=0.93) |
| RSI 가중치 급변 | Hard Threshold | v0414: Soft Switching 보간 |
| 감성 신호 미반영 | 뉴스 데이터 미활용 | v0415: 감성 가중치 함수 추가 |
| TimesFM 시뮬레이션 의존 | 독립 실행 시 Random Walk | v0419: ADLS 3-tier 로드 (실제 결과 우선) |

---

## 8. 알려진 한계 및 개선 방향

### 8-1. 현재 한계

| 한계 | 설명 | 영향도 |
|---|---|---|
| **TimesFM 3-tier fallback** | ADLS 실제 결과 미존재 시 시뮬레이션 사용 가능 → 운영 안정성 확보 필요 | 중간 |
| **sklearn 버전 호환성** | UC 모델 로드 시 1.4→1.8 패치 필요 → Databricks 런타임 업그레이드 시 재검증 | 중간 |
| **종목 2개 한정** | 삼성전자, SK하이닉스만 — SOX, NVDA 등 해외 종목 미포함 | 낮음 |
| **뉴스 감성 지연** | 당일 뉴스 기반 → T+0 감성만 반영, T-1~T-3 감성 모멘텀 활용 중 | 낮음 |

### 8-2. v0414 대비 해결된 항목

| 기존 한계 | 해결 버전 | 해결 방법 |
|---|---|---|
| TimesFM 시뮬레이션 의존 | v0419 | ADLS 3-tier 로드 (실제 결과 우선) |
| Silver 데이터 품질 | v0419 | Gold Layer 통합 (feature/ 컨테이너) |
| Confidence Score 낮음 | v0419 | UC R²=0.93으로 모델 합의도 개선 |
| 앙상블 모델 확장 필요 | v0419 | AutoML이 최적 모델 자동 선택 (ElasticNet→BestTrial) |

### 8-3. 향후 개선 방향

1. **종목별 특화 피처**: SK하이닉스 → HBM 가격, NVIDIA 상관계수 추가
2. **Bayesian Optimization**: Soft Switching 파라미터 (기울기, 데드존 폭 등) 자동 최적화
3. **Walk-Forward Validation**: 시계열 교차 검증으로 과적합 검증
4. **Confidence Score 고도화**: 모델 간 예측 분산, 과거 예측 정확도 반영
5. **Multi-horizon 학습**: T+5, T+10, T+20 개별 모델 → 기간별 특성 반영
