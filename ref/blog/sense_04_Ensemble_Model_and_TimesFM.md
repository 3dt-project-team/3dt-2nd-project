# SENSE 프로젝트 4부: TimesFM 2.5 + AutoML UC — 동적 가중치 앙상블 설계

> **시리즈**: Azure + Databricks + TimesFM으로 반도체 주가 예측 파이프라인 구축하기  
> **분류**: MLOps, Ensemble, TimesFM, AutoML, Databricks Unity Catalog, Dynamic Weighting  
> **작성일**: 2026년 4월 17일  

---

## 들어가며 — 왜 단일 모델이 아닌 앙상블인가

주식 시장에는 영원한 승자 전략이 없습니다. 트렌드 추종(Trend Following) 전략은 강한 모멘텀 장세에서 빛나지만, 급격한 반전 구간에서 큰 손실을 냅니다. 평균 회귀(Mean Reversion) 전략은 과매수/과매도 구간에서 정확하지만, 추세가 지속되는 상승장에서 기회를 놓칩니다.

반도체 섹터는 이 두 국면이 매우 극적으로 교차합니다. 2024년 AI 붐으로 NVIDIA가 10배 상승하던 기간은 전형적인 추세 장세였습니다. 그러나 2024년 8월, 경기 침체 공포로 하루 만에 반도체 ETF가 9% 급락했습니다 — 이것은 평균 회귀를 기대한 구간이었습니다.

이 두 전략을 **시장 국면에 따라 동적으로 배합**하는 것이 SENSE 앙상블의 핵심 아이디어였습니다.

---

## 1. 두 모델의 역할 분담

### 1.1 TimesFM 2.5 — 추세 추종의 축

TimesFM(Time Series Foundation Model)은 Google DeepMind가 개발한 시계열 예측 Foundation Model입니다. 2억 개의 파라미터를 가진 `timesfm-2.5-200m-pytorch`는 수억 개의 실제 시계열 데이터로 사전 학습되었습니다. Fine-tuning 없이도 다양한 도메인의 시계열을 예측할 수 있습니다.

TimesFM의 특별한 능력은 **XReg(External Regressor, 외부 공변량 주입)**입니다. 예측 시점에 추가적인 공변량을 제공하면 모델이 이를 컨텍스트로 활용합니다.

```python
# notebooks/timesfm_inference.py (핵심 부분)

import timesfm

# 모델 로드 — Hugging Face Hub에서 자동 다운로드
tfm = timesfm.TimesFm(
    hparams=timesfm.TimesFmHparams(
        backend="pytorch",
        per_core_batch_size=32,
        horizon_len=20,  # T+20 예측
        input_patch_len=32,
        output_patch_len=128,
        num_layers=20,
        model_dims=1280,
    ),
    checkpoint=timesfm.TimesFmCheckpoint(
        huggingface_repo_id="google/timesfm-2.5-200m-pytorch"
    ),
)
tfm.load_from_checkpoint(repo_id="google/timesfm-2.5-200m-pytorch")

# XReg 공변량 구성 — 미래 20거래일의 매크로 지표
xreg_future = df_features[XREG_COLUMNS].iloc[-20:].values  # 7개 공변량

# TimesFM 예측 실행
point_forecast, interval_forecast = tfm.forecast_on_df(
    inputs=df_hist,
    freq="B",             # Business day frequency
    value_name="close",
    xreg_cols=XREG_COLUMNS,
    num_jobs=-1,
)
```

XReg 공변량으로 주입한 7개 변수: `nvda_log_return`, `sox_log_return`, `yield_spread`, `usd_krw_rate`, `avg_sentiment`, `macro_stress_score`, `semi_exp_yoy`

이 변수들이 "미래 20거래일 동안의 거시환경을 알고 있다고 가정하면"이라는 조건부 예측을 가능하게 합니다.

### 1.2 Databricks AutoML UC BestTrial — 평균 회귀의 축

Databricks AutoML은 여러 ML 알고리즘(Random Forest, XGBoost, LightGBM, ElasticNet 등)을 자동으로 시험하고 최적 하이퍼파라미터를 찾습니다. 이 과정이 끝나면 **BestTrial 모델이 Unity Catalog에 자동 등록**됩니다.

우리의 최종 UC BestTrial 모델은 **Random Forest**였습니다:

```
삼성전자 AutoML BestTrial:
  - 알고리즘: RandomForestRegressor
  - n_estimators: 400
  - max_depth: 8
  - min_samples_leaf: 2
  - max_features: "sqrt"
  - UC 경로: sense_databricks.models.automl_삼성전자_t20
  - R²(검증): 0.9266

SK하이닉스 AutoML BestTrial:
  - 알고리즘: RandomForestRegressor  
  - n_estimators: 350
  - max_depth: 7
  - UC 경로: sense_databricks.models.automl_SK하이닉스_t20
  - R²(검증): 0.7097
```

Random Forest가 ElasticNet보다 훨씬 높은 R²를 기록한 이유는 **비선형 관계**입니다. RSI가 70을 넘는 구간에서 뉴스 감성이 부정적이면 하락 가능성이 높아진다 — 이런 조건부 비선형 규칙을 트리 기반 모델은 자동으로 학습합니다. 선형 모델은 이를 교호작용 피처로 명시해야만 포착할 수 있습니다.

#### sklearn 버전 호환성 패치

UC에 저장된 모델이 sklearn 1.4.2로 직렬화되었는데, 추론 환경에서 sklearn 1.8.0이 설치되어 있었습니다. 이 버전 차이가 역직렬화 오류를 일으켰습니다.

```python
# ensemble_strategy.py — sklearn 역직렬화 패치

import sklearn.utils.validation

def _deep_mark_fitted(estimator):
    """sklearn 1.4→1.8 역직렬화 패치: 재귀적으로 is_fitted 마킹"""
    if hasattr(estimator, "__sklearn_is_fitted__"):
        return  # 이미 패치됨
    
    # sklearn 1.8에서 __sklearn_is_fitted__ 속성을 요구하는 검사 우회
    estimator.__sklearn_is_fitted__ = lambda: True
    
    # SimpleImputer._fill_dtype 누락 패치
    if hasattr(estimator, "_fill_dtype") is False and hasattr(estimator, "statistics_"):
        estimator._fill_dtype = estimator.statistics_.dtype
    
    # 하위 추정기 재귀 처리 (Pipeline, ColumnTransformer 등)
    for attr in ["estimators_", "steps", "transformers_"]:
        if hasattr(estimator, attr):
            children = getattr(estimator, attr)
            if isinstance(children, list):
                for child in children:
                    if hasattr(child, "fit"):
                        _deep_mark_fitted(child)

# 모델 로드 후 즉시 패치 적용
model = mlflow.sklearn.load_model(f"models:/{model_uri}")
_deep_mark_fitted(model)
```

---

## 2. Soft Switching — 연속 가중치 조정의 설계

### 2.1 Hard Threshold의 문제

초기 버전(v0413)에서는 RSI 임계값으로 모델을 전환했습니다:

```python
# v0413 — Hard Threshold (나쁜 예시)
if rsi > 70:
    w_timesfm, w_ucmodel = 0.2, 0.8  # 과매수: UC 강화
elif rsi < 30:
    w_timesfm, w_ucmodel = 0.8, 0.2  # 과매도: TimesFM 강화
else:
    w_timesfm, w_ucmodel = 0.5, 0.5
```

이 방식의 치명적 문제: RSI가 69.9에서 70.1로 변하는 순간, 가중치가 0.5/0.5에서 0.2/0.8로 **불연속적으로 점프**합니다. 예측값이 하루 사이에 급변하는 **Spike 현상**이 발생합니다.

### 2.2 Soft Switching — 연속 보간 함수

v0414에서 도입한 Soft Switching은 RSI 변화에 따라 **선형 또는 비선형으로 부드럽게 가중치가 변화**합니다.

```python
def compute_dynamic_weights(
    rsi: float,
    vol_ratio: float,
    disparity_120d: float,
    avg_sentiment: float,
    news_vol_surge: float,
    base_timesfm: float = 0.45,  # v0419 기준값
    base_ucmodel: float = 0.55,
    clip_range: tuple = (0.25, 0.75),
) -> tuple[float, float]:
    """
    5개 시장 신호를 바탕으로 두 모델의 가중치를 동적 계산.
    모든 조정값의 합이 0이 되어 합계 = 1.0이 항상 유지됨.
    """
    adj = 0.0  # TimesFM 방향 조정량
    
    # ① RSI 신호 — 과매수/과매도 (최대 ±0.20)
    if rsi > 70:
        # 과매수: UC(평균회귀) 강화. 1.5승으로 70→100 구간 가속
        adj -= 0.20 * ((rsi - 70) / 30) ** 1.5
    elif rsi < 30:
        # 과매도: TimesFM(추세) 강화
        adj += 0.20 * ((30 - rsi) / 30) ** 1.5
    
    # ② 실현 변동성 비율 — 변동성 급증 (최대 ±0.15)
    if vol_ratio > 1.5:
        adj -= 0.15 * min((vol_ratio - 1.5) / 1.0, 1.0)  # 급등 변동성: UC 강화
    
    # ③ 120일 이격도 — 장기 괴리율 (최대 ±0.15)
    if abs(disparity_120d) > 10:
        sign = -1 if disparity_120d > 0 else 1  # 고이격도: UC 강화 / 저이격도: TimesFM 강화
        adj += sign * 0.15 * min((abs(disparity_120d) - 10) / 20, 1.0) ** 1.5
    
    # ④ 뉴스 평균 감성 (최대 ±0.10)
    if avg_sentiment > 0.3:
        adj += 0.10 * min((avg_sentiment - 0.3) / 0.4, 1.0)   # 강한 호재: TimesFM 강화
    elif avg_sentiment < -0.3:
        adj -= 0.10 * min((-avg_sentiment - 0.3) / 0.4, 1.0)  # 강한 악재: UC 강화
    
    # ⑤ 뉴스 언급량 급증 (최대 ±0.10)
    if news_vol_surge > 0.5:
        adj -= 0.10 * min(news_vol_surge / 2.0, 1.0)  # 뉴스 폭발: UC 강화(불확실성)
    
    # 최종 가중치 계산 및 클리핑
    w_timesfm = float(np.clip(base_timesfm + adj, clip_range[0], clip_range[1]))
    w_ucmodel = 1.0 - w_timesfm
    return w_timesfm, w_ucmodel
```

**클리핑 [0.25, 0.75]**의 이유: 어떤 극단적 시장 상황에서도 한 모델이 75% 이상을 차지하지 않습니다. 이것은 모델 편향을 막고, 예측 다양성을 유지하는 안전장치입니다.

---

## 3. 레짐 분류 — 시장 국면 명명

앙상블 예측값과 함께 현재 시장 국면(Regime)을 분류하여 사용자에게 제공합니다.

```python
def classify_regime(w_timesfm: float, w_ucmodel: float, threshold: float = 0.55) -> str:
    """
    가중치 기반 레짐 분류:
    - TREND: TimesFM 가중치 ≥ 0.55 → 추세 지속 국면
    - MEAN_REV: UC 가중치 ≥ 0.55 → 과열/평균회귀 국면  
    - NEUTRAL: 둘 다 0.55 미만 → 방향성 불확실
    """
    if w_timesfm >= threshold:
        return "TREND"
    elif w_ucmodel >= threshold:
        return "MEAN_REV"
    else:
        return "NEUTRAL"
```

이 레짐 정보는 웹 대시보드에서 한/영 병기로 표시됩니다: "추세 장세 (Trend Regime)", "평균회귀 국면 (Mean Reversion Regime)".

---

## 4. Confidence Score — 예측 신뢰도의 수치화

예측값 하나만 제공하는 것은 불완전합니다. "R² 0.93"이 검증 데이터 기준의 평균 성능이지, 특정 예측 인스턴스의 신뢰도는 아닙니다. 현재 시장 상황이 학습 데이터의 분포를 크게 벗어났다면 그 예측은 덜 신뢰할 수 있습니다.

Confidence Score는 5개 요소의 가중 평균으로 계산합니다:

```python
def compute_confidence_score(
    pi_coverage: float,          # 예측 구간 실제 포함율 (이상적: 0.90)
    pi_width_norm: float,        # 정규화된 예측 구간 폭 (좁을수록 높은 신뢰도)
    model_agreement: float,      # 두 모델 예측값의 방향 일치도
    regime_strength: float,      # 레짐 결정의 확신도 (50→75% 사이 거리)
    sentiment_stability: float,  # 뉴스 감성의 안정성 (변동성 역수)
) -> float:
    """0~10 스케일의 신뢰도 점수"""
    weights = [0.30, 0.25, 0.25, 0.10, 0.10]
    
    scores = [
        min(pi_coverage / 0.90, 1.0) * 10,
        max(0, (1.0 - pi_width_norm)) * 10,
        model_agreement * 10,
        regime_strength * 10,
        sentiment_stability * 10,
    ]
    
    return round(sum(w * s for w, s in zip(weights, scores)), 2)
```

**model_agreement**가 핵심입니다. TimesFM이 +5% 상승을 예측하는데 UC BestTrial이 -3% 하락을 예측한다면, 두 모델이 **반대 방향**을 보고 있습니다. 이 경우 앙상블 평균값은 +1%지만 신뢰도가 낮습니다. 반대로 두 모델이 모두 +4%, +5%를 예측하면 신뢰도가 높습니다.

---

## 5. AutoML 실험 관리 — MLflow와 Unity Catalog

### 5.1 Databricks AutoML 실행

```python
# Databricks AutoML 실행 코드 (notebooks/automl_best_trial.py)

from databricks import automl

summary = automl.regress(
    dataset=spark.table("sense_databricks.features.samsung_t20"),
    target_col="target_log_return_20d",
    primary_metric="r2",
    timeout_minutes=60,
    exclude_frameworks=["sklearn"],  # sklearn ElasticNet 제외
    experiment_dir="/Experiments/samsung_automl",
    data_dir="dbfs:/automl/samsung_t20",
)

print(f"최적 모델: {summary.best_trial.model_description}")
print(f"최적 R²: {summary.best_trial.metrics['val_r2']:.4f}")
```

### 5.2 Unity Catalog 모델 등록

AutoML이 완료되면 최적 모델을 Unity Catalog에 등록합니다:

```python
import mlflow

mlflow.set_registry_uri("databricks-uc")

# BestTrial 모델을 UC에 등록
mlflow.register_model(
    model_uri=f"runs:/{summary.best_trial.mlflow_run_id}/model",
    name="sense_databricks.models.automl_삼성전자_t20",
    tags={
        "git_commit": dbutils.notebook.getContext().tags().get("gitCommit", "unknown"),
        "r2_score": str(summary.best_trial.metrics["val_r2"]),
        "trained_at": datetime.datetime.now().isoformat(),
    }
)
```

MLflow 실험에 `git_commit` 태그를 추가하는 것은 **추적 가능성(Traceability)**의 원칙입니다. 어떤 코드 버전에서 어떤 모델이 나왔는지 언제든 확인할 수 있습니다.

### 5.3 추론 파이프라인

```python
# ensemble_strategy.py — UC 모델 추론

def load_uc_model(stock: str) -> Any:
    model_name = {
        "005930.KS": "sense_databricks.models.automl_삼성전자_t20",
        "000660.KS": "sense_databricks.models.automl_SK하이닉스_t20",
    }[stock]
    
    model = mlflow.sklearn.load_model(f"models:/{model_name}/latest")
    _deep_mark_fitted(model)  # sklearn 버전 호환 패치
    return model

def run_ensemble_forecast(df_features: pd.DataFrame, stock: str) -> pd.DataFrame:
    # UC 모델 예측
    uc_model = load_uc_model(stock)
    X = df_features[FEATURE_COLUMNS].iloc[-1:].values
    uc_pred_log_return = float(uc_model.predict(X)[0])
    uc_pred_price = df_features["close"].iloc[-1] * np.exp(uc_pred_log_return)
    
    # TimesFM 예측 로드 (ADLS에 사전 저장된 결과)
    timesfm_preds = _load_timesfm_forecast(stock)  # ADLS feature/timesfm_forecast/
    
    results = []
    for horizon in range(1, 21):
        # 각 horizon별 동적 가중치 계산
        w_tf, w_uc = compute_dynamic_weights(
            rsi=df_features["rsi_14"].iloc[-1],
            vol_ratio=df_features["vol_ratio"].iloc[-1],
            disparity_120d=df_features["disparity_120d"].iloc[-1],
            avg_sentiment=df_features["avg_sentiment"].iloc[-1],
            news_vol_surge=df_features["news_vol_surge"].iloc[-1],
        )
        
        # 앙상블
        tf_price = timesfm_preds.loc[horizon, "price_forecast"]
        ensemble_price = w_tf * tf_price + w_uc * uc_pred_price
        
        # 신뢰 구간 (두 모델 예측의 표준편차 기반)
        spread = abs(tf_price - uc_pred_price)
        pi_lower = ensemble_price - 1.645 * spread  # 90% CI
        pi_upper = ensemble_price + 1.645 * spread
        
        results.append({
            "stock_code": stock,
            "horizon": horizon,
            "price_forecast": ensemble_price,
            "pi_lower": pi_lower,
            "pi_upper": pi_upper,
            "weight_timesfm": w_tf,
            "weight_ucmodel": w_uc,
            "regime": classify_regime(w_tf, w_uc),
        })
    
    return pd.DataFrame(results)
```

---

## 6. 가중치 진화 과정 — v0413에서 v0419까지

| 버전 | 날짜 | TimesFM | UC | 핵심 변경 |
|---|---|---|---|---|
| v0413 | 4/13 | 0.50 | 0.50 | Hard Threshold 3신호, 동등 기여도 |
| v0414 | 4/14 | 동적 | 동적 | Soft Switching 도입, RSI·이격도·변동성 3신호 |
| v0416 | 4/16 | 동적 | 동적 | 감성·뉴스량 2신호 추가 → 5신호 |
| v0419 | 4/19 | **0.45** | **0.55** | Base 가중치 조정 (UC R² 우위 반영), ElasticNet 완전 제거 |

v0419에서 base 가중치를 0.50/0.50에서 0.45/0.55로 조정한 근거는 명확합니다: UC BestTrial의 검증 R²(삼성 0.9266, SK 0.7097)가 TimesFM 방향 정확도(46~51%)보다 높습니다. 순수 성능 기준으로 UC 모델이 더 신뢰할 만하지만, TimesFM의 추세 포착 능력은 여전히 필요합니다. 그 균형점이 0.45/0.55였습니다.

---

## 마치며 — 다음 편 예고

이번 편에서는 TimesFM 2.5의 XReg 공변량 주입 방식, AutoML UC BestTrial 등록 및 추론, Soft Switching 동적 가중치의 수학적 설계, sklearn 버전 호환 패치를 다뤘습니다.

마지막 편에서는 이 시스템을 만들면서 마주쳤던 실제 장애들의 원인과 해결 과정, 그리고 완성된 시스템을 Azure App Service에 Blue-Green 배포한 과정을 P-C-S 프레임워크로 기록합니다.
