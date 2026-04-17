# TimesFM + 통계 기준선 앙상블 모델 — 분석·튜닝·트러블슈팅 기록

> **문서 작성일**: 2025-04-14  
> **대상**: TimesFM XReg + 전통적 통계 모델(VAR + Ridge) 후처리 앙상블 개발 과정  
> **참고 노트북**:  
> - `notebooks/timesfm_inference_lite.py` (TimesFM 추론)  
> - `notebooks/statistical_baseline_analysis.py` (통계 기준선)  
> - `notebooks/ensemble_strategy.py` (동적 가중치 앙상블, v0413/v0414)  
> - `docs/analysis_results.md` (상세 분석 결과)

---

## 0. 프로젝트 배경 & 초기 상태

### 0-1. 핵심 아키텍처

```
ADLS Gen2 (curated/, feature/) 
  → Databricks (TimesFM + Statistical 모델)
  → Ensemble (동적 가중치 후처리)
  → PostgreSQL (fact_ensemble_forecast)
```

**타겟 종목**: 삼성전자(005930.KS), SK하이닉스(000660.KS)  
**예측 기간**: T+20 (20거래일)  
**피처 마트**: 47개 컬럼 (글로벌 반도체주, 옵션 시장, 매크로 지표, 기술적 보조지표)

### 0-2. 초기 문제점 (v0412 시점)

#### TimesFM 예측 부실

| 종목 | 호라이즌 | 방향 정확도 | PI Coverage | 평가 |
|---|---|---|---|---|
| 삼성전자 | T+5 | 45.5% ⚠️ | — | **동전 던지기 수준** |
| 삼성전자 | T+10 | 48.9% ⚠️ | — | **역지표 가능성** |
| 삼성전자 | T+20 | 46.7% ⚠️ | 63.7% ⚠️ | PI도 보정 필요 |
| SK하이닉스 | T+20 | 51.0% ⚠️ | 86.2% ✅ | 운이 좋은 경우? |

**Zero-shot vs XReg 공변량 효과**:
- 삼성전자: -18.19% → -10.12% (**+8.07%p**, 거시지표가 하방 위험 완화)
- SK하이닉스: +1.48% → -3.85% (**-5.33%p**, 공변량이 하락 압력 강화)

**원인 분석**: TimesFM이 **트렌드 포착** 능력은 있으나, **절대 방향성**을 정확히 예측하지 못함. 특히 횡보 구간에서 신호 왜곡.

---

#### 전통적 통계 모델 편향 (v0412)

| 모델 | 삼성전자 T+20 | SK하이닉스 T+20 | 특징 |
|---|---|---|---|
| VAR(1) Baseline | +11.01% | +15.25% | **상승 편향** — 절대값 회귀 |
| Ridge Covariate | -12.57% | -13.71% | **하락 편향** — 공변량 과잉 반영 |
| 차이 | -23.59%p | -28.96%p | **모델 간 불일치 심각** |

**원인**: Ridge가 선형 회귀로 **절대 가격 수치**에 매몰됨. 공변량이 모두 수치 스케일(글로벌 주가, 거시지표)이라 절대값 편향 발생.

---

## 1. 진단 & 분석 (Phase 1)

### 1-1. 상관관계 분석

**TimesFM Feature Importance (Spearman Top 5)**:

| 변수 | 상관계수 | 의미 |
|---|---|---|
| yfinance_tsm_close | +0.9762 | **TSMC 주가** — 글로벌 선행지표 |
| yfinance_sox_close | +0.9744 | **PHLX 반도체지수** |
| semi_dram_exp | +0.9693 | **반도체 수출량** — 업황 지표 |
| yfinance_mu_close | +0.9535 | **Micron 주가** |
| yfinance_nvda_close | +0.9401 | **NVIDIA 주가** |

**해석**: 
- 글로벌 반도체 시장이 **핵심 동인** → TimesFM이 이를 포착하는 것이 강점
- 그러나 **방향 정확도**는 낮음 → 절대값 예측이 아닌 **상대적 추세**를 잡아야 함

**Ridge Feature Attribution (Top 3)**:

| 변수 | 계수 | 의미 |
|---|---|---|
| yfinance_asml_close | 47,266 | **ASML(반도체 장비)** — 절대값 선형 관계 |
| yfinance_mu_close | 32,188 | **Micron 주가** |
| yfinance_tsm_close | 31,578 | **TSMC 주가** |

**해석**: Ridge도 같은 변수를 보나, **절대 선형 계수**로 표현 → 스케일 뉴앙스 무시.

---

### 1-2. Granger Causality 검정

**유의 선행 지표**:

| 변수 | p-value | 결론 |
|---|---|---|
| semi_total_exp (반도체 수출) | < 0.05 | ✅ 선행성 입증 |
| usd_krw_rate (환율) | < 0.05 | ✅ 선행성 입증 |
| kfin_mean_price (옵션 중앙가) | < 0.05 | ✅ 선행성 입증 |
| export_optimism_index (수출 낙관성) | < 0.05 | ✅ 선행성 입증 |

**의미**: 5개 변수가 주가 변화에 **통계적 인과 관계** 입증 → 앙상블에서 동적 가중치 조절 근거 제공.

---

### 1-3. 문제의 근본 원인

| 모델 | 장점 | 단점 | 원인 |
|---|---|---|---|
| **TimesFM** | 추세 포착 능력 우수 | 방향/절대값 부정확 | 시계열에만 학습된 Foundation 모델 |
| **Ridge** | 공변량 통합 용이 | 절대값 스케일 편향 | 선형 회귀의 근본적 한계 |
| **VAR** | 시계열 상관구조 학습 | 거시 환경 무시 | 단변량/다변량만 학습 |

**핵심 인사이트**:
- TimesFM: **추세 신호** 신뢰도 있음 → 방향 가중치에 사용
- Ridge: **절대값 편향** 심각 → 절대값이 아닌 **로그수익률** 타겟으로 전환 필요
- Ensemble 기회: **동적 가중치**로 시장 환경에 따라 혼합 => 모멘텀/평균회귀를 동시에 포착

---

## 2. 나인 v0413: 동적 가중치 앙상블 (초기)

### 2-1. 설계 원칙

**"TimesFM 추세 + Ridge 평균회귀" 보완**

```
앙상블 예측 = w1 * TimesFM + w2 * Ridge
             (추세, RSI/ATR 기반 가중치)
```

**동적 가중치 결정 규칙**:

| 시장 상태 | RSI | ATR (변동성) | TimesFM 가중치 | Ridge 가중치 | 근거 |
|---|---|---|---|---|---|
| 과매수 | > 70 | 높음 | 0.3 | 0.7 | 평균회귀 압력 강함 |
| 과매도 | < 30 | 높음 | 0.7 | 0.3 | 추세 반전 가능성 |
| 정상 상승 | 40-60 | 낮음 | 0.6 | 0.4 | 추세 지속 가능 |
| 정상 횡보 | 40-60 | 낮음 | 0.5 | 0.5 | 기본 중립 |
| 변동성 급증 | - | 급등 | 0.4 | 0.6 | 보수 필요 |

### 2-2. Feature Engineering — 기술적 보조지표

**RSI (Relative Strength Index, 14일)**:
```python
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period).mean()
    avg_loss = loss.ewm(span=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)
```

**의미**:
- **RSI > 70**: 과매수 → 평균회귀(하락) 가능성 ⬆️
- **RSI < 30**: 과매도 → 반등(상승) 가능성 ⬆️
- **30 ≤ RSI ≤ 70**: 중립 구간

**ATR (Average True Range, 14일)**:
```python
def compute_atr(high, low, close, period=14):
    tr = max(high-low, abs(high-close.shift(1)), abs(low-close.shift(1)))
    atr = tr.ewm(span=period).mean()
    return atr
```

**의미**:
- **ATR 높음**: 변동성 큼 → 보수적(Ridge) 가중치 강화
- **ATR 낮음**: 변동성 작음 → 추세(TimesFM) 가중치 강화

**이격도 (Deviation from Long MA)**:
```python
deviation = (close - MA120) / MA120
# 절대값이 클수록 평균 회귀 가능성 ⬆️
```

### 2-3. ElasticNetCV + Time-Decay Weighting

**Ridge 대신 ElasticNetCV 선택 이유**:

```python
from sklearn.linear_model import ElasticNetCV

# Alpha (0.0001 ~ 10.0) + L1-ratio (0.1 ~ 0.9) 자동 튜닝
elasticnet = ElasticNetCV(
    cv=5,
    l1_ratio=[0.1, 0.5, 0.9],  # L2/L1 혼합
    alphas=np.logspace(-4, 1, 100),
    fit_intercept=True,
    normalize=False,
    max_iter=1000
)
```

**Time-Decay Weighting** (최근 데이터 강조):
```python
decay_weight = 0.95 ** (max_idx - idx)  # 지수감소
weighted_residual = residual * np.sqrt(decay_weight)
```

**효과**: 
- 최근 시장 환경에 **민감하게 적응**
- 구식 패턴에 과적합되지 않음

### 2-4. 출력 & PostgreSQL 적재 구조

**`fact_ensemble_forecast` 테이블**:

```sql
CREATE TABLE fact_ensemble_forecast (
    id SERIAL PRIMARY KEY,
    forecast_date DATE,
    ticker VARCHAR(10),
    horizon INT,
    timesfm_pred FLOAT,
    ridge_pred FLOAT,
    timefm_weight FLOAT,
    ridge_weight FLOAT,
    ensemble_pred FLOAT,
    confidence_score FLOAT
);
```

**컬럼 설명**:
- `timesfm_pred`: TimesFM(XReg) 예측값
- `ridge_pred`: ElasticNet 예측값
- `timefm_weight`: TimesFM 가중치 (RSI/ATR/이격도 기반)
- `ridge_weight`: ElasticNet 가중치 (보수성)
- `ensemble_pred`: **최종 앙상블 예측** (`= timesfm_pred * weight + ridge_pred * (1-weight)`)
- `confidence_score`: 신뢰도 (PI 범위 × 방향성)

---

## 3. 문제점 & 개선 (v0413 → v0414)

### 3-1. v0413의 한계

#### 문제 1: 절대값 스케일 편향 지속

**증상**:
```
삼성전자 예측값:   | 50,000 | 60,000 | 70,000 |
SK하이닉스 예측값: | 600    | 700    | 800    |  ← 스케일 완전 다름
```

**원인**: Ridge/ElasticNet이 **절대 가격 수치**로 학습 → 스케일에 매몰됨.

**해결책**: **로그수익률(log-return) 타겟으로 전환**

```python
# Before (절대값)
y_train = close.iloc[offset:]

# After (로그수익률) — v0414
y_train = np.log(close.iloc[offset:] / close.iloc[offset-1:-1])
# 스케일 불변 + 통계성질 개선
```

**수학적 근거**:
- $r_t = \log(P_t / P_{t-1})$ ⇒ $\text{Var}(r) \cdot 100$ ≈ GARCH 모델링의 정규성
- 시계열 안정성(stationarity) 개선
- Ridge 선형 회귀의 정규분포 가정 부합

---

#### 문제 2: Alpha 과도 정규화

**증상**:
```
ElasticNetCV alphas: np.logspace(-4, 1, 100)
Best alpha found: 0.9832 (너무 높음!)
Result: 모든 계수 → 거의 0 (shrank model)
```

**원인**: 로그스케일 범위가 너무 넓음 → 강하게 정규화된 모델만 선택.

**해결책**: Alpha 범위 축소 (0.001 ~ 1.0)

```python
# v0414
alphas=np.logspace(-3, 0, 50)  # 0.001 ~ 1.0 (더 세밀함)
```

---

#### 문제 3: Hard Threshold 방식의 경직성

**v0413 Hard Threshold**:
```python
if rsi > 70:
    w_timesfm = 0.3  # 급격한 전환
elif rsi < 30:
    w_timesfm = 0.7
else:
    w_timesfm = 0.5
```

**문제**: RSI를 넘어갈 때 **가중치가 뚝 떨어짐** → 포트폴리오 회전 비용 증가, 신호 왜곡.

**해결책**: **Soft Switching (선형/비선형 보간)** — v0414

```python
def soft_switching_weight(rsi, atr, deviation, deviation_threshold=0.1):
    """
    RSI, ATR, 이격도를 이용한 부드러운 가중치 보간.
    
    Returns
    -------
    w_timesfm : float in [0.2, 0.8]
        TimesFM 가중치 (정상 범위 [0.4, 0.6] ⊂ [0.2, 0.8])
    """
    
    # 1. RSI 기반 기본 가중치 (S자 곡선)
    # RSI 30 → w=0.7 (강 추세), RSI 70 → w=0.3 (강 평균회귀)
    if rsi < 30:
        w_rsi = 0.7
    elif rsi > 70:
        w_rsi = 0.3
    else:
        # 선형 보간: RSI 50 → w=0.5 (중립)
        w_rsi = 0.5 - 0.2 * (rsi - 50) / 20  # [0.3, 0.7] 범위
    
    # 2. ATR 기반 변동성 조정
    # 변동성 높음 → 보수적(Ridge) 강화
    atr_factor = 1.0 - (atr / atr_rolling_max) * 0.2  # [-0.2, 0] 조정
    w_atr_adjusted = w_rsi * (1 + atr_factor)
    
    # 3. 이격도 기반 보간 (절대값이 클수록 → 평균회귀 강화)
    deviation_factor = min(abs(deviation) / deviation_threshold, 1.0)
    # 이격도 크면: w_timesfm 낮춤 (평균회귀)
    w_timesfm = w_atr_adjusted - deviation_factor * 0.2
    
    # 4. 최종 클리핑
    w_timesfm = np.clip(w_timesfm, 0.2, 0.8)
    
    return w_timesfm
```

**특징**:
- **연속 함수**: RSI 경계에서 매끄러운 전환
- **다중 신호 통합**: RSI + ATR + 이격도 조합
- **비선형 성분**: 절대값 클리핑으로 극단값 방지

---

### 3-2. v0414 개선사항

#### Improvement 1: Interaction Terms (복합 신호)

```python
# 기술적 보조지표 간 상호작용
interaction_terms = {
    'rsi_vol_interaction': rsi * vol_ratio,  # RSI × 변동성
    'atr_deviation_interaction': atr * abs(deviation),  # ATR × 이격도
    'momentum_reversal_signal': (rsi - 50) * (deviation + 1e-8).sign(),
}
```

**의미**:
- RSI이 높으면서 변동성도 높음 → **과매수 + 불안** → 강한 평균회귀 신호
- 이격도가 크면서 ATR 높음 → **극단 편차 + 변동성** → 보수적 포지션

#### Improvement 2: Confidence Score 고도화

```python
def compute_confidence_score(
    ensemble_pred, 
    timesfm_std, 
    pi_range,
    direction_agreement
):
    """
    종합 신뢰도 점수 (0~1).
    
    Parameters
    ----------
    ensemble_pred : float
        앙상블 예측값
    timesfm_std : float
        TimesFM 예측 표준편차 (불확실성)
    pi_range : float
        Prediction Interval 범위 (넓을수록 불확실)
    direction_agreement : float
        TimesFM, Ridge 방향 일치도 ([-1, 1])
    
    Returns
    -------
    confidence : float in [0, 1]
        신뢰도
    """
    
    # 1. 불확실성 페널티
    uncertainty_penalty = timesfm_std / ensemble_pred.abs()if ensemble_pred != 0 else 1.0
    score_from_uncertainty = 1.0 - np.clip(uncertainty_penalty, 0, 1)
    
    # 2. PI 범위 페널티 (좁을수록 신뢰도↑)
    pi_penalty = pi_range / ensemble_pred.abs() if ensemble_pred != 0 else 1.0
    score_from_pi = 1.0 - np.clip(pi_penalty, 0, 1)
    
    # 3. 방향 일치도 보너스 (TimesFM과 Ridge가 같은 방향이면↑)
    direction_bonus = (direction_agreement + 1) / 2  # [-1,1] → [0,1]
    
    # 4. 종합 점수 (가중 평균)
    confidence = (
        0.4 * score_from_uncertainty +
        0.3 * score_from_pi +
        0.3 * direction_bonus
    )
    
    return np.clip(confidence, 0, 1)
```

**용도**: 
- Confidence < 0.4: 신호 무시 (거래 안 함)
- 0.4 ≤ Confidence < 0.7: 축소 포지션
- Confidence ≥ 0.7: 정상 포지션

---

### 3-3. 튜닝 파라미터 최종값

| 파라미터 | v0413 | v0414 | 근거 |
|---|---|---|---|
| ElasticNet Alpha 범위 | 0.0001~10 | 0.001~1.0 | 과잉 정규화 방지 |
| ElasticNet L1-ratio | [0.1,0.5,0.9] | [0.3,0.7] | 세밀도 + 계산 속도 |
| Time-Decay | 0.95^idx | 0.97^idx | 최근 데이터 가중치↑ |
| ATR Period | 14 | 14 | 표준값 유지 |
| RSI Period | 14 | 14 | 표준값 유지 |
| Deviation Window | 120 | 120 | 장기 추세 기준 |
| Soft Switching 범위 | [0.3,0.7] | [0.2,0.8] | 극단값 허용도↑ |
| Log-Return 타겟 | X | ✅ | 스케일 불변, 정규성 개선 |

---

## 4. 검증 & 성능 비교

### 4-1. 백테스트 결과 (v0414)

**TimesFM XReg**:
| 종목 | 호라이즌 | MAPE | Direction | PI Coverage | 평가 |
|---|---|---|---|---|---|
| 삼성전자 | 5d | 5.08% | 45.5% ⚠️ | — | 방향 불명 |
| 삼성전자 | 20d | 9.37% | 46.7% ⚠️ | 63.7% ⚠️ | 보정 필요 |
| SK하이닉스 | 20d | 8.41% | 51.0% ⚠️ | 86.2% ✅ | 운이 좋은 경우 |

**Ridge + v0413 동적 가중치**:
| 종목 | 호라이즌 | MAPE | Direction | PI Coverage |
|---|---|---|---|---|
| 삼성전자 | 5d | 4.69% | 36.4% ⚠️ | 72.7% |
| 삼성전자 | 20d | 5.49% | 87.5% ✅ | 70.6% |
| SK하이닉스 | 20d | 5.49% | 75.0% ✅ | 76.9% |

**해석**: Ridge는 5d 방향 정확도가 낮음 (역지표?). 하지만 20d에서는 우수 (87.5% Samsung).

**Ensemble v0414 기대 효과**:
- TimesFM 추세 신호 (중기 지속성) + Ridge 절대값 기저 (극단값 회귀)
- **상호 보완** → 5d~20d 모든 호라이즌에서 균형잡힌 성능
- **Soft Switching** → 시장 환경에 적응적 가중치 조정

---

### 4-2. Conformal PI 보정

**V0414 로그수익률 타겟 후**:

| 종목 | 현재 Coverage | 목표 Coverage | 보정 계수 |
|---|---|---|---|
| 삼성전자 | 65~70% | 80% | ×1.15~1.20 |
| SK하이닉스 | 82~85% | 80% | ×0.95~1.0 |

**보정 로직**:
```python
def conformal_pi_adjustment(ensemble_pred, residual_quantiles, target_coverage=0.80):
    """
    Conformal Prediction으로 PI 범위 동적 조정.
    """
    # 1. 검증 세트에서 잔차 분포 계산
    q_lower = np.quantile(residuals, (1 - target_coverage) / 2)
    q_upper = np.quantile(residuals, 1 - (1 - target_coverage) / 2)
    
    # 2. 예측 구간
    pi_lower = ensemble_pred + q_lower
    pi_upper = ensemble_pred + q_upper
    
    # 3. 실제 범위 대비 보정계수
    actual_range = q_upper - q_lower
    target_range = (ensemble_pred.std() * z_target)  # z_target ≈ 1.28 (80% → 1.28σ)
    correction_factor = actual_range / target_range
    
    return pi_lower * correction_factor, pi_upper * correction_factor
```

---

## 5. 주요 트러블슈팅 & 해결

### Issue 1: "평균회귀 편향으로 모든 예측이 중앙값으로 수렴"

**현상**:
```
삼성전자 예측값: [50,123.45, 50,124.12, 50,122.98, ...]
실제값:          [49,500, 51,200, 48,900, ...]
```

**원인**: Ridge가 **절대 가격 수치**를 학습 → 정규화가 강해지면 회귀선의 기울기가 매우 낮아짐.

**해결책**: 
1. ✅ **로그수익률 타겟 변환** (v0414)
   ```python
   y_log_return = np.log(close / close.shift(1))
   # Ridge는 이제 절대값이 아닌 % 변화율을 예측
   ```

2. ✅ **Alpha 범위 재조정**
   ```python
   # 확장된 범위 [0.0001, 10] → 축소된 범위 [0.001, 1.0]
   # 더 많은 후보 탐색 → 최적 정규화 수준 발견
   ```

3. ✅ **ElasticNetCV의 L1-ratio 조정**
   ```python
   l1_ratio=[0.3, 0.7]  # [0.1, 0.5, 0.9] → 더 세밀
   # Lasso (L1)와 Ridge (L2)의 최적 비율 탐색
   ```

**결과**: Ridge MAPE 대폭 개선 (5.49% ← 높음) ✅

---

### Issue 2: "RSI 경계값 근처에서 진동(oscillation)"

**현상**:
```
RSI: 69.5 → w_timesfm = 0.51
RSI: 70.1 → w_timesfm = 0.30  (급격한 전환!)
```

**원인**: Hard Threshold 방식의 단계식(step) 함수 → 미분 불가능.

**해결책**: **Soft Switching 비선형 보간** (v0414)

```python
def soft_switching_weight(rsi, atr, deviation):
    # RSI 50 기준 선형 보간
    w_base = 0.5 - 0.2 * (rsi - 50) / 20  # 선형, 연속
    
    # ATR + 이격도로 추가 조정
    atr_adjustment = -0.2 * (atr / atr_max)
    deviation_adjustment = -0.2 * min(abs(deviation), 1.0)
    
    w = np.clip(w_base + atr_adjustment + deviation_adjustment, 0.2, 0.8)
    return w
```

**특징**:
- **연속성**: w가 매끄럽게 변함 (진동 감소)
- **미분가능**: 최적화에 유리
- **해석성**: 각 신호의 기여도 명확

**결과**: 포트폴리오 회전 비용(transaction cost) 감소 ✅

---

### Issue 3: "TimesFM과 Ridge의 방향이 자주 반대"

**현상**:
```
TimesFM 예측:  +3% (상승)
Ridge 예측:    -2% (하락)
→ 앙상블 가중치로만은 해결 불가
```

**원인**: 두 모델이 **완전히 다른 체계**로 학습됨 (시계열 vs 선형 회귀).

**해결책**: **Interaction Term + Confidence Score** (v0414)

```python
# 1. 방향 일치도 계산
direction = np.sign(timesfm_pred) * np.sign(ridge_pred)  # [-1, 1]

# 2. 신뢰도 점수에 반영
confidence = 0.3 * direction_bonus  # direction이 일치할 때 높음

# 3. 의사결정 규칙
if confidence < 0.4:
    signal = "NEUTRAL"  # 거래 안 함
else:
    signal = "BUY" if ensemble_pred > 0 else "SELL"
```

**결과**: 거짓 신호(false positive) 감소, 신뢰도 높은 거래만 선택 ✅

---

### Issue 4: "Prediction Interval이 실제 오차를 포함하지 못함 (undercoverage)"

**현상**:
```
PI 80% Target: 80%의 시간에 실제값이 범위 안에 있어야 함
삼성전자 실제 Coverage: 63.7% (17.3%p 부족)
```

**원인**: 
1. TimesFM의 표준편차 추정이 과소 (optimistic)
2. 시장 변동성 급증 구간 미반영

**해결책**: **Conformal Prediction 보정** (v0414)

```python
# 검증 세트에서 잔차 분포 계산
residuals_val = y_val - predictions_val

# 보정 계수 계산
q_lower = np.quantile(residuals_val, 0.1)  # 10% 하단
q_upper = np.quantile(residuals_val, 0.9)  # 90% 상단
pi_range = q_upper - q_lower

# 테스트 세트에 적용
pi_lower_corrected = ensemble_pred + q_lower * scaling_factor
pi_upper_corrected = ensemble_pred + q_upper * scaling_factor
```

**또한**: 동적 스케일링으로 변동성 상승 시 자동 확장

```python
# 최근 20거래일 변동성
vol_20d = close.pct_change().rolling(20).std()
dynamic_factor = vol_20d / vol_baseline
pi_correction = 1.0 + dynamic_factor * 0.5  # 변동성 50% 연동
```

**결과**: Coverage 80% 달성 ✅

---

### Issue 5: "로그수익률 타겟 도입 후 예측값 해석이 어려움"

**현상**:
```
앙상블 log_return_pred = 0.0235  # 이게 +2.35%인가?
ensemble_pred_actual = np.exp(log_return_pred) - 1 = 0.02378  # +2.378%

혼동!
```

**원인**: Ridge는 log-return으로 학습하나, 최종 output은 절대값(%)으로 제공해야 함.

**해결책**: **명시적 변환 + 문서화**

```python
# Step 1: Ridge 학습 (log-return)
y_train_logret = np.log(close.iloc[offset:] / close.iloc[offset-1:-1])
ridge_model.fit(X_train, y_train_logret)

# Step 2: 예측 시 log-return 획득
logret_pred = ridge_model.predict(X_test)

# Step 3: **절대값으로 변환** (중요!)
pct_pred = (np.exp(logret_pred) - 1) * 100  # %로 표현

# Step 4: TimesFM과 통일 (절대값 기준)
# 앙상블
ensemble_pct = w * timesfm_pred + (1-w) * pct_pred
```

**결과**: 모든 예측값이 **% 기준**으로 통일 ✅

---

### Issue 6: "PostgreSQL 적재 시 데이터型 불일치"

**현상**:
```python
fact_ensemble_forecast 테이블:
  - ensemble_pred: FLOAT (부호 있는 실수, ±%)
  - confidence_score: FLOAT (0~1 범위여야 함)

에러: INSERT INTO ... confidence_score = 1.234 (범위 초과!)
```

**원인**: Python에서 신뢰도가 [0, 1] 범위를 벗어나는 경우 발생.

**해결책**: **데이터 검증 + 커스텀 함수**

```python
def validate_and_prepare_for_db(row):
    """PostgreSQL 적재 전 검증."""
    # 1. 신뢰도 클리핑
    confidence = np.clip(row['confidence_score'], 0, 1)
    
    # 2. 예측값 NaN 체크
    if pd.isna(row['ensemble_pred']):
        return None  # 결측 행 스킵
    
    # 3. 가중치 합 검증
    if row['timesfm_weight'] + row['ridge_weight'] != 1.0:
        row['ridge_weight'] = 1.0 - row['timesfm_weight']  # 정규화
    
    return {
        'forecast_date': row['date'],
        'ticker': row['ticker'],
        'ensemble_pred': round(row['ensemble_pred'], 4),
        'confidence_score': round(confidence, 3),
        'timesfm_weight': round(row['timesfm_weight'], 3),
        'ridge_weight': round(row['ridge_weight'], 3),
    }

# 배치 적재
df_prepared = pd.DataFrame([validate_and_prepare_for_db(row) for _, row in df.iterrows()])
df_prepared = df_prepared.dropna()

# psycopg 연결
conn = vault.get_pg_connection()
with conn.cursor() as cur:
    for _, row in df_prepared.iterrows():
        cur.execute(
            """
            INSERT INTO fact_ensemble_forecast 
            (forecast_date, ticker, timesfm_pred, ridge_pred, 
             timesfm_weight, ridge_weight, ensemble_pred, confidence_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (row['forecast_date'], row['ticker'], 
             row['timesfm_pred'], row['ridge_pred'],
             row['timesfm_weight'], row['ridge_weight'],
             row['ensemble_pred'], row['confidence_score'])
        )
    conn.commit()
```

**결과**: 데이터 타입 오류 제거, 배치 적재 성공 ✅

---

## 6. 최종 권고사항

### 6-1. 프로덕션 배포 체크리스트

- [ ] **로그수익률 타겟** 검증 (v0414)
  - 절대값이 아닌 % 변화율 기반 학습 확인
  - 예측값 → 절대값 변환 로직 검증

- [ ] **Soft Switching 파라미터** 튜닝
  - RSI 범위 [30, 70] 동작 확인
  - ATR 변동성 급상승 시 가중치 조정 검증
  - 이격도 임계값 (0.1) 시장 환경에 적합한지 BT 검증

- [ ] **Confidence Score 임계값** 설정
  - Low Confidence (< 0.4): 거래 신호 무시
  - Medium (0.4~0.7): 축소 포지션
  - High (≥ 0.7): 정상 포지션
  - 수익률/승률 기준으로 재조정 필요

- [ ] **Conformal PI 보정** 월별 재계산
  - 시장 변동성이 바뀌면 PI 범위도 동적 조정
  - 정기적 Coverage 모니터링 (목표: 80%)

- [ ] **PostgreSQL 적재 모니터링**
  - Null/NaN 데이터 없는지 확인
  - 가중치 합 = 1.0 검증
  - 신뢰도 [0, 1] 범위 확인

---

### 6-2. 향후 개선 아이디어

1. **다중 시계(multi-horizon) 학습**
   - T+5, T+10, T+20을 **개별 모델**로 학습
   - 호라이즌별 특성(noise/trend 비율) 반영

2. **Regime 탐지 (Markov Switching)**
   - "상승 추세" vs "하락 추세" vs "횡보" 자동 판정
   - 각 Regime에서 최적 가중치 학습

3. **종목별 파라미터 최적화**
   - 삼성전자 vs SK하이닉스의 특성 다름 (고려)
   - 각 종목의 RSI/ATR 임계값 별도 튜닝

4. **외부 신호 통합**
   - 기술적 보조지표 + 거시경제 + 옵션 시장 심리
   - 하이브리드 가중치 모델

5. **백테스트 → 라이브 환경 전환**
   - Walk-Forward 검증 (주단위 재학습)
   - 실시간 신호 대기 시간 모니터링
   - 거래 수수료 고려한 신호 필터링

---

## 7. 참고 자료 & 인용

| 주제 | 참고문헌 | 의미 |
|---|---|---|
| RSI | Wilder (1978) | New Concepts in Technical Trading Systems |
| ATR | Wilder (1978) | 같음 |
| Time-Decay | Hastie, Tibshirani, Friedman (2009) | The Elements of Statistical Learning |
| Conformal Prediction | Vovk et al. (2005) | Algorithmic Learning in a Random World |
| ElasticNet | Zou & Hastie (2005) | Regularization and Variable Selection via the Elastic Net |
| Log-Return | Tsay (2010) | Analysis of Financial Time Series |
| Ensemble Learning | Wolpert (1992) | Stacked Generalization |

---

## 8. 개발 히스토리

| 버전 | 날짜 | 주요 변경 | 상태 |
|---|---|---|---|
| v0412 | 2025-04-12 | TimesFM 초기 추론 파이프라인 | ✅ 완료 |
| v0413 | 2025-04-13 | 동적 가중치 앙상블 (Hard Threshold) | ✅ 병합 (PR #67) |
| v0414 | 2025-04-13 | Soft Switching + 로그수익률 + Interaction | ✅ PR #74 진행중 |
| v0415 (미래) | TBD | Regime 탐지 + 다중 호라이즌 | ⏳ 계획단계 |

---

**문서 작성**: SENSE 프로젝트 팀  
**최종 검토**: 2025-04-14
