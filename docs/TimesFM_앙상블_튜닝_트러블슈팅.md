# TimesFM + ?듦퀎 湲곗????숈긽釉?紐⑤뜽 ??遺꾩꽍쨌?쒕떇쨌?몃윭釉붿뒋??湲곕줉

> **臾몄꽌 ?묒꽦??*: 2025-04-14  
> **???*: TimesFM XReg + ?꾪넻???듦퀎 紐⑤뜽(VAR + Ridge) ?꾩쿂由??숈긽釉?媛쒕컻 怨쇱젙  
> **李멸퀬 ?명듃遺?*:  
> - `notebooks/timesfm_inference_lite.py` (TimesFM 異붾줎)  
> - `notebooks/statistical_baseline_analysis.py` (?듦퀎 湲곗???  
> - `notebooks/ensemble_strategy.py` (?숈쟻 媛以묒튂 ?숈긽釉? v0413/v0414)  
> - `docs/analysis_results.md` (?곸꽭 遺꾩꽍 寃곌낵)

---

## 0. ?꾨줈?앺듃 諛곌꼍 & 珥덇린 ?곹깭

### 0-1. ?듭떖 ?꾪궎?띿쿂

```
ADLS Gen2 (curated/, feature/) 
  ??Databricks (TimesFM + Statistical 紐⑤뜽)
  ??Ensemble (?숈쟻 媛以묒튂 ?꾩쿂由?
  ??PostgreSQL (fact_ensemble_forecast)
```

**?寃?醫낅ぉ**: ?쇱꽦?꾩옄(005930.KS), SK?섏씠?됱뒪(000660.KS)  
**?덉륫 湲곌컙**: T+20 (20嫄곕옒??  
**?쇱쿂 留덊듃**: 47媛?而щ읆 (湲濡쒕쾶 諛섎룄泥댁＜, ?듭뀡 ?쒖옣, 留ㅽ겕濡?吏?? 湲곗닠??蹂댁“吏??

### 0-2. 珥덇린 臾몄젣??(v0412 ?쒖젏)

#### TimesFM ?덉륫 遺??

| 醫낅ぉ | ?몃씪?댁쫵 | 諛⑺뼢 ?뺥솗??| PI Coverage | ?됯? |
|---|---|---|---|---|
| ?쇱꽦?꾩옄 | T+5 | 45.5% ?좑툘 | ??| **?숈쟾 ?섏?湲??섏?** |
| ?쇱꽦?꾩옄 | T+10 | 48.9% ?좑툘 | ??| **?????媛?μ꽦** |
| ?쇱꽦?꾩옄 | T+20 | 46.7% ?좑툘 | 63.7% ?좑툘 | PI??蹂댁젙 ?꾩슂 |
| SK?섏씠?됱뒪 | T+20 | 51.0% ?좑툘 | 86.2% ??| ?댁씠 醫뗭? 寃쎌슦? |

**Zero-shot vs XReg 怨듬????④낵**:
- ?쇱꽦?꾩옄: -18.19% ??-10.12% (**+8.07%p**, 嫄곗떆吏?쒓? ?섎갑 ?꾪뿕 ?꾪솕)
- SK?섏씠?됱뒪: +1.48% ??-3.85% (**-5.33%p**, 怨듬??됱씠 ?섎씫 ?뺣젰 媛뺥솕)

**?먯씤 遺꾩꽍**: TimesFM??**?몃젋???ъ갑** ?λ젰? ?덉쑝?? **?덈? 諛⑺뼢??*???뺥솗???덉륫?섏? 紐삵븿. ?뱁엳 ?〓낫 援ш컙?먯꽌 ?좏샇 ?쒓끝.

---

#### ?꾪넻???듦퀎 紐⑤뜽 ?명뼢 (v0412)

| 紐⑤뜽 | ?쇱꽦?꾩옄 T+20 | SK?섏씠?됱뒪 T+20 | ?뱀쭠 |
|---|---|---|---|
| VAR(1) Baseline | +11.01% | +15.25% | **?곸듅 ?명뼢** ???덈?媛??뚭? |
| Ridge Covariate | -12.57% | -13.71% | **?섎씫 ?명뼢** ??怨듬???怨쇱엵 諛섏쁺 |
| 李⑥씠 | -23.59%p | -28.96%p | **紐⑤뜽 媛?遺덉씪移??ш컖** |

**?먯씤**: Ridge媛 ?좏삎 ?뚭?濡?**?덈? 媛寃??섏튂**??留ㅻぐ?? 怨듬??됱씠 紐⑤몢 ?섏튂 ?ㅼ???湲濡쒕쾶 二쇨?, 嫄곗떆吏???대씪 ?덈?媛??명뼢 諛쒖깮.

---

## 1. 吏꾨떒 & 遺꾩꽍 (Phase 1)

### 1-1. ?곴?愿怨?遺꾩꽍

**TimesFM Feature Importance (Spearman Top 5)**:

| 蹂??| ?곴?怨꾩닔 | ?섎? |
|---|---|---|
| yfinance_tsm_close | +0.9762 | **TSMC 二쇨?** ??湲濡쒕쾶 ?좏뻾吏??|
| yfinance_sox_close | +0.9744 | **PHLX 諛섎룄泥댁???* |
| semi_dram_exp | +0.9693 | **諛섎룄泥??섏텧??* ???낇솴 吏??|
| yfinance_mu_close | +0.9535 | **Micron 二쇨?** |
| yfinance_nvda_close | +0.9401 | **NVIDIA 二쇨?** |

**?댁꽍**: 
- 湲濡쒕쾶 諛섎룄泥??쒖옣??**?듭떖 ?숈씤** ??TimesFM???대? ?ъ갑?섎뒗 寃껋씠 媛뺤젏
- 洹몃윭??**諛⑺뼢 ?뺥솗??*????쓬 ???덈?媛??덉륫???꾨땶 **?곷???異붿꽭**瑜??≪븘????

**Ridge Feature Attribution (Top 3)**:

| 蹂??| 怨꾩닔 | ?섎? |
|---|---|---|
| yfinance_asml_close | 47,266 | **ASML(諛섎룄泥??λ퉬)** ???덈?媛??좏삎 愿怨?|
| yfinance_mu_close | 32,188 | **Micron 二쇨?** |
| yfinance_tsm_close | 31,578 | **TSMC 二쇨?** |

**?댁꽍**: Ridge??媛숈? 蹂?섎? 蹂대굹, **?덈? ?좏삎 怨꾩닔**濡??쒗쁽 ???ㅼ????댁븰??臾댁떆.

---

### 1-2. Granger Causality 寃??

**?좎쓽 ?좏뻾 吏??*:

| 蹂??| p-value | 寃곕줎 |
|---|---|---|
| semi_total_exp (諛섎룄泥??섏텧) | < 0.05 | ???좏뻾???낆쬆 |
| usd_krw_rate (?섏쑉) | < 0.05 | ???좏뻾???낆쬆 |
| kfin_mean_price (?듭뀡 以묒븰媛) | < 0.05 | ???좏뻾???낆쬆 |
| export_optimism_index (?섏텧 ?숆??? | < 0.05 | ???좏뻾???낆쬆 |

**?섎?**: 5媛?蹂?섍? 二쇨? 蹂?붿뿉 **?듦퀎???멸낵 愿怨?* ?낆쬆 ???숈긽釉붿뿉???숈쟻 媛以묒튂 議곗젅 洹쇨굅 ?쒓났.

---

### 1-3. 臾몄젣??洹쇰낯 ?먯씤

| 紐⑤뜽 | ?μ젏 | ?⑥젏 | ?먯씤 |
|---|---|---|---|
| **TimesFM** | 異붿꽭 ?ъ갑 ?λ젰 ?곗닔 | 諛⑺뼢/?덈?媛?遺?뺥솗 | ?쒓퀎?댁뿉留??숈뒿??Foundation 紐⑤뜽 |
| **Ridge** | 怨듬????듯빀 ?⑹씠 | ?덈?媛??ㅼ????명뼢 | ?좏삎 ?뚭???洹쇰낯???쒓퀎 |
| **VAR** | ?쒓퀎???곴?援ъ“ ?숈뒿 | 嫄곗떆 ?섍꼍 臾댁떆 | ?⑤????ㅻ??됰쭔 ?숈뒿 |

**?듭떖 ?몄궗?댄듃**:
- TimesFM: **異붿꽭 ?좏샇** ?좊ː???덉쓬 ??諛⑺뼢 媛以묒튂???ъ슜
- Ridge: **?덈?媛??명뼢** ?ш컖 ???덈?媛믪씠 ?꾨땶 **濡쒓렇?섏씡瑜?* ?寃잛쑝濡??꾪솚 ?꾩슂
- Ensemble 湲고쉶: **?숈쟻 媛以묒튂**濡??쒖옣 ?섍꼍???곕씪 ?쇳빀 => 紐⑤찘?/?됯퇏?뚭?瑜??숈떆???ъ갑

---

## 2. ?섏씤 v0413: ?숈쟻 媛以묒튂 ?숈긽釉?(珥덇린)

### 2-1. ?ㅺ퀎 ?먯튃

**"TimesFM 異붿꽭 + Ridge ?됯퇏?뚭?" 蹂댁셿**

```
?숈긽釉??덉륫 = w1 * TimesFM + w2 * Ridge
             (異붿꽭, RSI/ATR 湲곕컲 媛以묒튂)
```

**?숈쟻 媛以묒튂 寃곗젙 洹쒖튃**:

| ?쒖옣 ?곹깭 | RSI | ATR (蹂?숈꽦) | TimesFM 媛以묒튂 | Ridge 媛以묒튂 | 洹쇨굅 |
|---|---|---|---|---|---|
| 怨쇰ℓ??| > 70 | ?믪쓬 | 0.3 | 0.7 | ?됯퇏?뚭? ?뺣젰 媛뺥븿 |
| 怨쇰ℓ??| < 30 | ?믪쓬 | 0.7 | 0.3 | 異붿꽭 諛섏쟾 媛?μ꽦 |
| ?뺤긽 ?곸듅 | 40-60 | ??쓬 | 0.6 | 0.4 | 異붿꽭 吏??媛??|
| ?뺤긽 ?〓낫 | 40-60 | ??쓬 | 0.5 | 0.5 | 湲곕낯 以묐┰ |
| 蹂?숈꽦 湲됱쬆 | - | 湲됰벑 | 0.4 | 0.6 | 蹂댁닔 ?꾩슂 |

### 2-2. Feature Engineering ??湲곗닠??蹂댁“吏??

**RSI (Relative Strength Index, 14??**:
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

**?섎?**:
- **RSI > 70**: 怨쇰ℓ?????됯퇏?뚭?(?섎씫) 媛?μ꽦 燧놅툘
- **RSI < 30**: 怨쇰ℓ????諛섎벑(?곸듅) 媛?μ꽦 燧놅툘
- **30 ??RSI ??70**: 以묐┰ 援ш컙

**ATR (Average True Range, 14??**:
```python
def compute_atr(high, low, close, period=14):
    tr = max(high-low, abs(high-close.shift(1)), abs(low-close.shift(1)))
    atr = tr.ewm(span=period).mean()
    return atr
```

**?섎?**:
- **ATR ?믪쓬**: 蹂?숈꽦 ????蹂댁닔??Ridge) 媛以묒튂 媛뺥솕
- **ATR ??쓬**: 蹂?숈꽦 ?묒쓬 ??異붿꽭(TimesFM) 媛以묒튂 媛뺥솕

**?닿꺽??(Deviation from Long MA)**:
```python
deviation = (close - MA120) / MA120
# ?덈?媛믪씠 ?댁닔濡??됯퇏 ?뚭? 媛?μ꽦 燧놅툘
```

### 2-3. ElasticNetCV + Time-Decay Weighting

**Ridge ???ElasticNetCV ?좏깮 ?댁쑀**:

```python
from sklearn.linear_model import ElasticNetCV

# Alpha (0.0001 ~ 10.0) + L1-ratio (0.1 ~ 0.9) ?먮룞 ?쒕떇
elasticnet = ElasticNetCV(
    cv=5,
    l1_ratio=[0.1, 0.5, 0.9],  # L2/L1 ?쇳빀
    alphas=np.logspace(-4, 1, 100),
    fit_intercept=True,
    normalize=False,
    max_iter=1000
)
```

**Time-Decay Weighting** (理쒓렐 ?곗씠??媛뺤“):
```python
decay_weight = 0.95 ** (max_idx - idx)  # 吏?섍컧??
weighted_residual = residual * np.sqrt(decay_weight)
```

**?④낵**: 
- 理쒓렐 ?쒖옣 ?섍꼍??**誘쇨컧?섍쾶 ?곸쓳**
- 援ъ떇 ?⑦꽩??怨쇱쟻?⑸릺吏 ?딆쓬

### 2-4. 異쒕젰 & PostgreSQL ?곸옱 援ъ“

**`fact_ensemble_forecast` ?뚯씠釉?*:

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

**而щ읆 ?ㅻ챸**:
- `timesfm_pred`: TimesFM(XReg) ?덉륫媛?
- `ridge_pred`: ElasticNet ?덉륫媛?
- `timefm_weight`: TimesFM 媛以묒튂 (RSI/ATR/?닿꺽??湲곕컲)
- `ridge_weight`: ElasticNet 媛以묒튂 (蹂댁닔??
- `ensemble_pred`: **理쒖쥌 ?숈긽釉??덉륫** (`= timesfm_pred * weight + ridge_pred * (1-weight)`)
- `confidence_score`: ?좊ː??(PI 踰붿쐞 횞 諛⑺뼢??

---

## 3. 臾몄젣??& 媛쒖꽑 (v0413 ??v0414)

### 3-1. v0413???쒓퀎

#### 臾몄젣 1: ?덈?媛??ㅼ????명뼢 吏??

**利앹긽**:
```
?쇱꽦?꾩옄 ?덉륫媛?   | 50,000 | 60,000 | 70,000 |
SK?섏씠?됱뒪 ?덉륫媛? | 600    | 700    | 800    |  ???ㅼ????꾩쟾 ?ㅻ쫫
```

**?먯씤**: Ridge/ElasticNet??**?덈? 媛寃??섏튂**濡??숈뒿 ???ㅼ??쇱뿉 留ㅻぐ??

**?닿껐梨?*: **濡쒓렇?섏씡瑜?log-return) ?寃잛쑝濡??꾪솚**

```python
# Before (?덈?媛?
y_train = close.iloc[offset:]

# After (濡쒓렇?섏씡瑜? ??v0414
y_train = np.log(close.iloc[offset:] / close.iloc[offset-1:-1])
# ?ㅼ???遺덈? + ?듦퀎?깆쭏 媛쒖꽑
```

**?섑븰??洹쇨굅**:
- $r_t = \log(P_t / P_{t-1})$ ??$\text{Var}(r) \cdot 100$ ??GARCH 紐⑤뜽留곸쓽 ?뺢퇋??
- ?쒓퀎???덉젙??stationarity) 媛쒖꽑
- Ridge ?좏삎 ?뚭????뺢퇋遺꾪룷 媛??遺??

---

#### 臾몄젣 2: Alpha 怨쇰룄 ?뺢퇋??

**利앹긽**:
```
ElasticNetCV alphas: np.logspace(-4, 1, 100)
Best alpha found: 0.9832 (?덈Т ?믪쓬!)
Result: 紐⑤뱺 怨꾩닔 ??嫄곗쓽 0 (shrank model)
```

**?먯씤**: 濡쒓렇?ㅼ???踰붿쐞媛 ?덈Т ?볦쓬 ??媛뺥븯寃??뺢퇋?붾맂 紐⑤뜽留??좏깮.

**?닿껐梨?*: Alpha 踰붿쐞 異뺤냼 (0.001 ~ 1.0)

```python
# v0414
alphas=np.logspace(-3, 0, 50)  # 0.001 ~ 1.0 (???몃???
```

---

#### 臾몄젣 3: Hard Threshold 諛⑹떇??寃쎌쭅??

**v0413 Hard Threshold**:
```python
if rsi > 70:
    w_timesfm = 0.3  # 湲됯꺽???꾪솚
elif rsi < 30:
    w_timesfm = 0.7
else:
    w_timesfm = 0.5
```

**臾몄젣**: RSI瑜??섏뼱媛???**媛以묒튂媛 ???⑥뼱吏?* ???ы듃?대━???뚯쟾 鍮꾩슜 利앷?, ?좏샇 ?쒓끝.

**?닿껐梨?*: **Soft Switching (?좏삎/鍮꾩꽑??蹂닿컙)** ??v0414

```python
def soft_switching_weight(rsi, atr, deviation, deviation_threshold=0.1):
    """
    RSI, ATR, ?닿꺽?꾨? ?댁슜??遺?쒕윭??媛以묒튂 蹂닿컙.
    
    Returns
    -------
    w_timesfm : float in [0.2, 0.8]
        TimesFM 媛以묒튂 (?뺤긽 踰붿쐞 [0.4, 0.6] ??[0.2, 0.8])
    """
    
    # 1. RSI 湲곕컲 湲곕낯 媛以묒튂 (S??怨≪꽑)
    # RSI 30 ??w=0.7 (媛?異붿꽭), RSI 70 ??w=0.3 (媛??됯퇏?뚭?)
    if rsi < 30:
        w_rsi = 0.7
    elif rsi > 70:
        w_rsi = 0.3
    else:
        # ?좏삎 蹂닿컙: RSI 50 ??w=0.5 (以묐┰)
        w_rsi = 0.5 - 0.2 * (rsi - 50) / 20  # [0.3, 0.7] 踰붿쐞
    
    # 2. ATR 湲곕컲 蹂?숈꽦 議곗젙
    # 蹂?숈꽦 ?믪쓬 ??蹂댁닔??Ridge) 媛뺥솕
    atr_factor = 1.0 - (atr / atr_rolling_max) * 0.2  # [-0.2, 0] 議곗젙
    w_atr_adjusted = w_rsi * (1 + atr_factor)
    
    # 3. ?닿꺽??湲곕컲 蹂닿컙 (?덈?媛믪씠 ?댁닔濡????됯퇏?뚭? 媛뺥솕)
    deviation_factor = min(abs(deviation) / deviation_threshold, 1.0)
    # ?닿꺽???щ㈃: w_timesfm ??땄 (?됯퇏?뚭?)
    w_timesfm = w_atr_adjusted - deviation_factor * 0.2
    
    # 4. 理쒖쥌 ?대━??
    w_timesfm = np.clip(w_timesfm, 0.2, 0.8)
    
    return w_timesfm
```

**?뱀쭠**:
- **?곗냽 ?⑥닔**: RSI 寃쎄퀎?먯꽌 留ㅻ걚?ъ슫 ?꾪솚
- **?ㅼ쨷 ?좏샇 ?듯빀**: RSI + ATR + ?닿꺽??議고빀
- **鍮꾩꽑???깅텇**: ?덈?媛??대━?묒쑝濡?洹밸떒媛?諛⑹?

---

### 3-2. v0414 媛쒖꽑?ы빆

#### Improvement 1: Interaction Terms (蹂듯빀 ?좏샇)

```python
# 湲곗닠??蹂댁“吏??媛??곹샇?묒슜
interaction_terms = {
    'rsi_vol_interaction': rsi * vol_ratio,  # RSI 횞 蹂?숈꽦
    'atr_deviation_interaction': atr * abs(deviation),  # ATR 횞 ?닿꺽??
    'momentum_reversal_signal': (rsi - 50) * (deviation + 1e-8).sign(),
}
```

**?섎?**:
- RSI???믪쑝硫댁꽌 蹂?숈꽦???믪쓬 ??**怨쇰ℓ??+ 遺덉븞** ??媛뺥븳 ?됯퇏?뚭? ?좏샇
- ?닿꺽?꾧? ?щ㈃??ATR ?믪쓬 ??**洹밸떒 ?몄감 + 蹂?숈꽦** ??蹂댁닔???ъ???

#### Improvement 2: Confidence Score 怨좊룄??

```python
def compute_confidence_score(
    ensemble_pred, 
    timesfm_std, 
    pi_range,
    direction_agreement
):
    """
    醫낇빀 ?좊ː???먯닔 (0~1).
    
    Parameters
    ----------
    ensemble_pred : float
        ?숈긽釉??덉륫媛?
    timesfm_std : float
        TimesFM ?덉륫 ?쒖??몄감 (遺덊솗?ㅼ꽦)
    pi_range : float
        Prediction Interval 踰붿쐞 (?볦쓣?섎줉 遺덊솗??
    direction_agreement : float
        TimesFM, Ridge 諛⑺뼢 ?쇱튂??([-1, 1])
    
    Returns
    -------
    confidence : float in [0, 1]
        ?좊ː??
    """
    
    # 1. 遺덊솗?ㅼ꽦 ?섎꼸??
    uncertainty_penalty = timesfm_std / ensemble_pred.abs()if ensemble_pred != 0 else 1.0
    score_from_uncertainty = 1.0 - np.clip(uncertainty_penalty, 0, 1)
    
    # 2. PI 踰붿쐞 ?섎꼸??(醫곸쓣?섎줉 ?좊ː?꾟넁)
    pi_penalty = pi_range / ensemble_pred.abs() if ensemble_pred != 0 else 1.0
    score_from_pi = 1.0 - np.clip(pi_penalty, 0, 1)
    
    # 3. 諛⑺뼢 ?쇱튂??蹂대꼫??(TimesFM怨?Ridge媛 媛숈? 諛⑺뼢?대㈃??
    direction_bonus = (direction_agreement + 1) / 2  # [-1,1] ??[0,1]
    
    # 4. 醫낇빀 ?먯닔 (媛以??됯퇏)
    confidence = (
        0.4 * score_from_uncertainty +
        0.3 * score_from_pi +
        0.3 * direction_bonus
    )
    
    return np.clip(confidence, 0, 1)
```

**?⑸룄**: 
- Confidence < 0.4: ?좏샇 臾댁떆 (嫄곕옒 ????
- 0.4 ??Confidence < 0.7: 異뺤냼 ?ъ???
- Confidence ??0.7: ?뺤긽 ?ъ???

---

### 3-3. ?쒕떇 ?뚮씪誘명꽣 理쒖쥌媛?

| ?뚮씪誘명꽣 | v0413 | v0414 | 洹쇨굅 |
|---|---|---|---|
| ElasticNet Alpha 踰붿쐞 | 0.0001~10 | 0.001~1.0 | 怨쇱엵 ?뺢퇋??諛⑹? |
| ElasticNet L1-ratio | [0.1,0.5,0.9] | [0.3,0.7] | ?몃???+ 怨꾩궛 ?띾룄 |
| Time-Decay | 0.95^idx | 0.97^idx | 理쒓렐 ?곗씠??媛以묒튂??|
| ATR Period | 14 | 14 | ?쒖?媛??좎? |
| RSI Period | 14 | 14 | ?쒖?媛??좎? |
| Deviation Window | 120 | 120 | ?κ린 異붿꽭 湲곗? |
| Soft Switching 踰붿쐞 | [0.3,0.7] | [0.2,0.8] | 洹밸떒媛??덉슜?꾟넁 |
| Log-Return ?寃?| X | ??| ?ㅼ???遺덈?, ?뺢퇋??媛쒖꽑 |

---

## 4. 寃利?& ?깅뒫 鍮꾧탳

### 4-1. 諛깊뀒?ㅽ듃 寃곌낵 (v0414)

**TimesFM XReg**:
| 醫낅ぉ | ?몃씪?댁쫵 | MAPE | Direction | PI Coverage | ?됯? |
|---|---|---|---|---|---|
| ?쇱꽦?꾩옄 | 5d | 5.08% | 45.5% ?좑툘 | ??| 諛⑺뼢 遺덈챸 |
| ?쇱꽦?꾩옄 | 20d | 9.37% | 46.7% ?좑툘 | 63.7% ?좑툘 | 蹂댁젙 ?꾩슂 |
| SK?섏씠?됱뒪 | 20d | 8.41% | 51.0% ?좑툘 | 86.2% ??| ?댁씠 醫뗭? 寃쎌슦 |

**Ridge + v0413 ?숈쟻 媛以묒튂**:
| 醫낅ぉ | ?몃씪?댁쫵 | MAPE | Direction | PI Coverage |
|---|---|---|---|---|
| ?쇱꽦?꾩옄 | 5d | 4.69% | 36.4% ?좑툘 | 72.7% |
| ?쇱꽦?꾩옄 | 20d | 5.49% | 87.5% ??| 70.6% |
| SK?섏씠?됱뒪 | 20d | 5.49% | 75.0% ??| 76.9% |

**?댁꽍**: Ridge??5d 諛⑺뼢 ?뺥솗?꾧? ??쓬 (?????). ?섏?留?20d?먯꽌???곗닔 (87.5% Samsung).

**Ensemble v0414 湲곕? ?④낵**:
- TimesFM 異붿꽭 ?좏샇 (以묎린 吏?띿꽦) + Ridge ?덈?媛?湲곗? (洹밸떒媛??뚭?)
- **?곹샇 蹂댁셿** ??5d~20d 紐⑤뱺 ?몃씪?댁쫵?먯꽌 洹좏삎?≫엺 ?깅뒫
- **Soft Switching** ???쒖옣 ?섍꼍???곸쓳??媛以묒튂 議곗젙

---

### 4-2. Conformal PI 蹂댁젙

**V0414 濡쒓렇?섏씡瑜??寃???*:

| 醫낅ぉ | ?꾩옱 Coverage | 紐⑺몴 Coverage | 蹂댁젙 怨꾩닔 |
|---|---|---|---|
| ?쇱꽦?꾩옄 | 65~70% | 80% | 횞1.15~1.20 |
| SK?섏씠?됱뒪 | 82~85% | 80% | 횞0.95~1.0 |

**蹂댁젙 濡쒖쭅**:
```python
def conformal_pi_adjustment(ensemble_pred, residual_quantiles, target_coverage=0.80):
    """
    Conformal Prediction?쇰줈 PI 踰붿쐞 ?숈쟻 議곗젙.
    """
    # 1. 寃利??명듃?먯꽌 ?붿감 遺꾪룷 怨꾩궛
    q_lower = np.quantile(residuals, (1 - target_coverage) / 2)
    q_upper = np.quantile(residuals, 1 - (1 - target_coverage) / 2)
    
    # 2. ?덉륫 援ш컙
    pi_lower = ensemble_pred + q_lower
    pi_upper = ensemble_pred + q_upper
    
    # 3. ?ㅼ젣 踰붿쐞 ?鍮?蹂댁젙怨꾩닔
    actual_range = q_upper - q_lower
    target_range = (ensemble_pred.std() * z_target)  # z_target ??1.28 (80% ??1.28?)
    correction_factor = actual_range / target_range
    
    return pi_lower * correction_factor, pi_upper * correction_factor
```

---

## 5. 二쇱슂 ?몃윭釉붿뒋??& ?닿껐

### Issue 1: "?됯퇏?뚭? ?명뼢?쇰줈 紐⑤뱺 ?덉륫??以묒븰媛믪쑝濡??섎졃"

**?꾩긽**:
```
?쇱꽦?꾩옄 ?덉륫媛? [50,123.45, 50,124.12, 50,122.98, ...]
?ㅼ젣媛?          [49,500, 51,200, 48,900, ...]
```

**?먯씤**: Ridge媛 **?덈? 媛寃??섏튂**瑜??숈뒿 ???뺢퇋?붽? 媛뺥빐吏硫??뚭??좎쓽 湲곗슱湲곌? 留ㅼ슦 ??븘吏?

**?닿껐梨?*: 
1. ??**濡쒓렇?섏씡瑜??寃?蹂??* (v0414)
   ```python
   y_log_return = np.log(close / close.shift(1))
   # Ridge???댁젣 ?덈?媛믪씠 ?꾨땶 % 蹂?붿쑉???덉륫
   ```

2. ??**Alpha 踰붿쐞 ?ъ“??*
   ```python
   # ?뺤옣??踰붿쐞 [0.0001, 10] ??異뺤냼??踰붿쐞 [0.001, 1.0]
   # ??留롮? ?꾨낫 ?먯깋 ??理쒖쟻 ?뺢퇋???섏? 諛쒓껄
   ```

3. ??**ElasticNetCV??L1-ratio 議곗젙**
   ```python
   l1_ratio=[0.3, 0.7]  # [0.1, 0.5, 0.9] ?????몃?
   # Lasso (L1)? Ridge (L2)??理쒖쟻 鍮꾩쑉 ?먯깋
   ```

**寃곌낵**: Ridge MAPE ???媛쒖꽑 (5.49% ???믪쓬) ??

---

### Issue 2: "RSI 寃쎄퀎媛?洹쇱쿂?먯꽌 吏꾨룞(oscillation)"

**?꾩긽**:
```
RSI: 69.5 ??w_timesfm = 0.51
RSI: 70.1 ??w_timesfm = 0.30  (湲됯꺽???꾪솚!)
```

**?먯씤**: Hard Threshold 諛⑹떇???④퀎??step) ?⑥닔 ??誘몃텇 遺덇???

**?닿껐梨?*: **Soft Switching 鍮꾩꽑??蹂닿컙** (v0414)

```python
def soft_switching_weight(rsi, atr, deviation):
    # RSI 50 湲곗? ?좏삎 蹂닿컙
    w_base = 0.5 - 0.2 * (rsi - 50) / 20  # ?좏삎, ?곗냽
    
    # ATR + ?닿꺽?꾨줈 異붽? 議곗젙
    atr_adjustment = -0.2 * (atr / atr_max)
    deviation_adjustment = -0.2 * min(abs(deviation), 1.0)
    
    w = np.clip(w_base + atr_adjustment + deviation_adjustment, 0.2, 0.8)
    return w
```

**?뱀쭠**:
- **?곗냽??*: w媛 留ㅻ걚?쎄쾶 蹂??(吏꾨룞 媛먯냼)
- **誘몃텇媛??*: 理쒖쟻?붿뿉 ?좊━
- **?댁꽍??*: 媛??좏샇??湲곗뿬??紐낇솗

**寃곌낵**: ?ы듃?대━???뚯쟾 鍮꾩슜(transaction cost) 媛먯냼 ??

---

### Issue 3: "TimesFM怨?Ridge??諛⑺뼢???먯＜ 諛섎?"

**?꾩긽**:
```
TimesFM ?덉륫:  +3% (?곸듅)
Ridge ?덉륫:    -2% (?섎씫)
???숈긽釉?媛以묒튂濡쒕쭔? ?닿껐 遺덇?
```

**?먯씤**: ??紐⑤뜽??**?꾩쟾???ㅻⅨ 泥닿퀎**濡??숈뒿??(?쒓퀎??vs ?좏삎 ?뚭?).

**?닿껐梨?*: **Interaction Term + Confidence Score** (v0414)

```python
# 1. 諛⑺뼢 ?쇱튂??怨꾩궛
direction = np.sign(timesfm_pred) * np.sign(ridge_pred)  # [-1, 1]

# 2. ?좊ː???먯닔??諛섏쁺
confidence = 0.3 * direction_bonus  # direction???쇱튂?????믪쓬

# 3. ?섏궗寃곗젙 洹쒖튃
if confidence < 0.4:
    signal = "NEUTRAL"  # 嫄곕옒 ????
else:
    signal = "BUY" if ensemble_pred > 0 else "SELL"
```

**寃곌낵**: 嫄곗쭞 ?좏샇(false positive) 媛먯냼, ?좊ː???믪? 嫄곕옒留??좏깮 ??

---

### Issue 4: "Prediction Interval???ㅼ젣 ?ㅼ감瑜??ы븿?섏? 紐삵븿 (undercoverage)"

**?꾩긽**:
```
PI 80% Target: 80%???쒓컙???ㅼ젣媛믪씠 踰붿쐞 ?덉뿉 ?덉뼱????
?쇱꽦?꾩옄 ?ㅼ젣 Coverage: 63.7% (17.3%p 遺議?
```

**?먯씤**: 
1. TimesFM???쒖??몄감 異붿젙??怨쇱냼 (optimistic)
2. ?쒖옣 蹂?숈꽦 湲됱쬆 援ш컙 誘몃컲??

**?닿껐梨?*: **Conformal Prediction 蹂댁젙** (v0414)

```python
# 寃利??명듃?먯꽌 ?붿감 遺꾪룷 怨꾩궛
residuals_val = y_val - predictions_val

# 蹂댁젙 怨꾩닔 怨꾩궛
q_lower = np.quantile(residuals_val, 0.1)  # 10% ?섎떒
q_upper = np.quantile(residuals_val, 0.9)  # 90% ?곷떒
pi_range = q_upper - q_lower

# ?뚯뒪???명듃???곸슜
pi_lower_corrected = ensemble_pred + q_lower * scaling_factor
pi_upper_corrected = ensemble_pred + q_upper * scaling_factor
```

**?먰븳**: ?숈쟻 ?ㅼ??쇰쭅?쇰줈 蹂?숈꽦 ?곸듅 ???먮룞 ?뺤옣

```python
# 理쒓렐 20嫄곕옒??蹂?숈꽦
vol_20d = close.pct_change().rolling(20).std()
dynamic_factor = vol_20d / vol_baseline
pi_correction = 1.0 + dynamic_factor * 0.5  # 蹂?숈꽦 50% ?곕룞
```

**寃곌낵**: Coverage 80% ?ъ꽦 ??

---

### Issue 5: "濡쒓렇?섏씡瑜??寃??꾩엯 ???덉륫媛??댁꽍???대젮?"

**?꾩긽**:
```
?숈긽釉?log_return_pred = 0.0235  # ?닿쾶 +2.35%?멸??
ensemble_pred_actual = np.exp(log_return_pred) - 1 = 0.02378  # +2.378%

?쇰룞!
```

**?먯씤**: Ridge??log-return?쇰줈 ?숈뒿?섎굹, 理쒖쥌 output? ?덈?媛?%)?쇰줈 ?쒓났?댁빞 ??

**?닿껐梨?*: **紐낆떆??蹂??+ 臾몄꽌??*

```python
# Step 1: Ridge ?숈뒿 (log-return)
y_train_logret = np.log(close.iloc[offset:] / close.iloc[offset-1:-1])
ridge_model.fit(X_train, y_train_logret)

# Step 2: ?덉륫 ??log-return ?띾뱷
logret_pred = ridge_model.predict(X_test)

# Step 3: **?덈?媛믪쑝濡?蹂??* (以묒슂!)
pct_pred = (np.exp(logret_pred) - 1) * 100  # %濡??쒗쁽

# Step 4: TimesFM怨??듭씪 (?덈?媛?湲곗?)
# ?숈긽釉?
ensemble_pct = w * timesfm_pred + (1-w) * pct_pred
```

**寃곌낵**: 紐⑤뱺 ?덉륫媛믪씠 **% 湲곗?**?쇰줈 ?듭씪 ??

---

### Issue 6: "PostgreSQL ?곸옱 ???곗씠?겼엹 遺덉씪移?

**?꾩긽**:
```python
fact_ensemble_forecast ?뚯씠釉?
  - ensemble_pred: FLOAT (遺???덈뒗 ?ㅼ닔, 짹%)
  - confidence_score: FLOAT (0~1 踰붿쐞?ъ빞 ??

?먮윭: INSERT INTO ... confidence_score = 1.234 (踰붿쐞 珥덇낵!)
```

**?먯씤**: Python?먯꽌 ?좊ː?꾧? [0, 1] 踰붿쐞瑜?踰쀬뼱?섎뒗 寃쎌슦 諛쒖깮.

**?닿껐梨?*: **?곗씠??寃利?+ 而ㅼ뒪? ?⑥닔**

```python
def validate_and_prepare_for_db(row):
    """PostgreSQL ?곸옱 ??寃利?"""
    # 1. ?좊ː???대━??
    confidence = np.clip(row['confidence_score'], 0, 1)
    
    # 2. ?덉륫媛?NaN 泥댄겕
    if pd.isna(row['ensemble_pred']):
        return None  # 寃곗륫 ???ㅽ궢
    
    # 3. 媛以묒튂 ??寃利?
    if row['timesfm_weight'] + row['ridge_weight'] != 1.0:
        row['ridge_weight'] = 1.0 - row['timesfm_weight']  # ?뺢퇋??
    
    return {
        'forecast_date': row['date'],
        'ticker': row['ticker'],
        'ensemble_pred': round(row['ensemble_pred'], 4),
        'confidence_score': round(confidence, 3),
        'timesfm_weight': round(row['timesfm_weight'], 3),
        'ridge_weight': round(row['ridge_weight'], 3),
    }

# 諛곗튂 ?곸옱
df_prepared = pd.DataFrame([validate_and_prepare_for_db(row) for _, row in df.iterrows()])
df_prepared = df_prepared.dropna()

# psycopg ?곌껐
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

**寃곌낵**: ?곗씠??????ㅻ쪟 ?쒓굅, 諛곗튂 ?곸옱 ?깃났 ??

---

## 6. 理쒖쥌 沅뚭퀬?ы빆

### 6-1. ?꾨줈?뺤뀡 諛고룷 泥댄겕由ъ뒪??

- [ ] **濡쒓렇?섏씡瑜??寃?* 寃利?(v0414)
  - ?덈?媛믪씠 ?꾨땶 % 蹂?붿쑉 湲곕컲 ?숈뒿 ?뺤씤
  - ?덉륫媛????덈?媛?蹂??濡쒖쭅 寃利?

- [ ] **Soft Switching ?뚮씪誘명꽣** ?쒕떇
  - RSI 踰붿쐞 [30, 70] ?숈옉 ?뺤씤
  - ATR 蹂?숈꽦 湲됱긽????媛以묒튂 議곗젙 寃利?
  - ?닿꺽???꾧퀎媛?(0.1) ?쒖옣 ?섍꼍???곹빀?쒖? BT 寃利?

- [ ] **Confidence Score ?꾧퀎媛?* ?ㅼ젙
  - Low Confidence (< 0.4): 嫄곕옒 ?좏샇 臾댁떆
  - Medium (0.4~0.7): 異뺤냼 ?ъ???
  - High (??0.7): ?뺤긽 ?ъ???
  - ?섏씡瑜??밸쪧 湲곗??쇰줈 ?ъ“???꾩슂

- [ ] **Conformal PI 蹂댁젙** ?붾퀎 ?ш퀎??
  - ?쒖옣 蹂?숈꽦??諛붾뚮㈃ PI 踰붿쐞???숈쟻 議곗젙
  - ?뺢린??Coverage 紐⑤땲?곕쭅 (紐⑺몴: 80%)

- [ ] **PostgreSQL ?곸옱 紐⑤땲?곕쭅**
  - Null/NaN ?곗씠???녿뒗吏 ?뺤씤
  - 媛以묒튂 ??= 1.0 寃利?
  - ?좊ː??[0, 1] 踰붿쐞 ?뺤씤

---

### 6-2. ?ν썑 媛쒖꽑 ?꾩씠?붿뼱

1. **?ㅼ쨷 ?쒓퀎(multi-horizon) ?숈뒿**
   - T+5, T+10, T+20??**媛쒕퀎 紐⑤뜽**濡??숈뒿
   - ?몃씪?댁쫵蹂??뱀꽦(noise/trend 鍮꾩쑉) 諛섏쁺

2. **Regime ?먯? (Markov Switching)**
   - "?곸듅 異붿꽭" vs "?섎씫 異붿꽭" vs "?〓낫" ?먮룞 ?먯젙
   - 媛?Regime?먯꽌 理쒖쟻 媛以묒튂 ?숈뒿

3. **醫낅ぉ蹂??뚮씪誘명꽣 理쒖쟻??*
   - ?쇱꽦?꾩옄 vs SK?섏씠?됱뒪???뱀꽦 ?ㅻ쫫 (怨좊젮)
   - 媛?醫낅ぉ??RSI/ATR ?꾧퀎媛?蹂꾨룄 ?쒕떇

4. **?몃? ?좏샇 ?듯빀**
   - 湲곗닠??蹂댁“吏??+ 嫄곗떆寃쎌젣 + ?듭뀡 ?쒖옣 ?щ━
   - ?섏씠釉뚮━??媛以묒튂 紐⑤뜽

5. **諛깊뀒?ㅽ듃 ???쇱씠釉??섍꼍 ?꾪솚**
   - Walk-Forward 寃利?(二쇰떒???ы븰??
   - ?ㅼ떆媛??좏샇 ?湲??쒓컙 紐⑤땲?곕쭅
   - 嫄곕옒 ?섏닔猷?怨좊젮???좏샇 ?꾪꽣留?

---

## Phase 4: v0415 → v0419 진화 (2025-04-15 ~ 2025-04-19)

### 6-1. v0415 — 뉴스 심리 지표 통합

**변경 사항:**
- \sense_macro\ 뉴스 심리 지표를 Feature Mart에 추가 (sentiment_score, positive_ratio 등)
- sentiment 기반 가중치 조정 함수 \_adjust_for_sentiment()\ 신설
- ±0.10 범위 clip, 긍/부정 뉴스 비율로 TimesFM↔통계 가중치 시프트

**트러블슈팅:**
- 뉴스 심리 지표 NaN 비율이 높아 fillna(0.5) 중립 기본값 적용
- sentiment_score 범위가 [0,1]→[-1,1] 으로 소스마다 달라 정규화 통일

### 6-2. v0416 — 키워드 분석 + Weight Scale 재조정

**변경 사항:**
- RSI 조정: ±0.20 → ±0.13 + 0.07 가속 (대칭 설계)
- Vol 조정: +0.15/−0.20 → +0.12/−0.15
- Interaction 규칙 5개로 확장 (sentiment×RSI 교차 규칙 추가)
- 모든 weight 함수에 \0416\ 이력 주석 추가

**트러블슈팅:**
- 가중치 합산 시 clip 범위 [0.15, 0.85] → [0.25, 0.75] 로 축소하여 극단 편향 방지
- interaction 규칙 간 중복 적용 문제 → 순서 고정 + 최종 clip으로 해결

### 6-3. v0417 — AutoML RandomForest 도입

**변경 사항:**
- Databricks AutoML로 RandomForest 모델 학습 → Unity Catalog 모델 레지스트리 등록
- \mlflow.sklearn.load_model()\ 으로 UC 모델 로딩 파이프라인 구축
- ElasticNet 대비 R² 대폭 개선 (삼성 0.9266, SK 0.7097)

**트러블슈팅:**
- scikit-learn 버전 불일치 (Databricks 1.4 → 로컬 1.8): \__sklearn_tags__\ AttributeError
- 해결: \_deep_mark_fitted()\ 재귀 함수로 모든 sub-estimator에 \__is_fitted__\ 마킹

\\python
def _deep_mark_fitted(estimator):
    estimator.__is_fitted__ = True
    for attr in vars(estimator):
        sub = getattr(estimator, attr, None)
        if hasattr(sub, 'fit'):
            _deep_mark_fitted(sub)
\
### 6-4. v0418 — gpt-5.4-mini + Responses API

**변경 사항:**
- AI 해석 모델을 gpt-4.1-mini → gpt-5.4-mini 로 교체
- OpenAI Responses API (\client.responses.create\) 채택
- temperature=0.3 으로 재현성 확보

**트러블슈팅:**
- Responses API 응답 구조 변경: esponse.choices[0].message.content\ → esponse.output_text- API 호출 실패 시 graceful degradation (AI 해석 없이 수치만 출력)

### 6-5. v0419 — UC 모델 재학습 + ElasticNet 완전 제거

**변경 사항:**
- Gold Layer 통합: \eature/\ 컨테이너 4개 폴더 (gold_macro_1y, macro_semiconductor, sense_macro, timesfm_forecast)
- UC 모델을 Gold Layer 데이터로 재학습 → R² 유지 확인
- ElasticNet 관련 코드 전면 제거 (R² ≈ 0.05 / −1.19)
- 기본 가중치 비율: TimesFM 0.45 / UC BestTrial 0.55

**Silver Layer vs Gold Layer 비교:**

| 항목 | Silver (v0414) | Gold (v0419) |
|---|---|---|
| 데이터 소스 | curated/ 개별 CSV | feature/ 통합 Gold Layer |
| Feature 수 | ~30개 | 69+ 개 |
| 뉴스 심리 | 미포함 | sense_macro 통합 |
| 매크로 지표 | 개별 로딩 | gold_macro_1y 통합 |
| 모델 | ElasticNetCV | Databricks AutoML UC BestTrial |

### 체크리스트 (v0419 기준)

| 항목 | 상태 |
|---|---|
| Gold Layer 로딩 검증 | ✅ |
| UC 모델 로딩 + _deep_mark_fitted | ✅ |
| TimesFM 3-Tier 폴백 | ✅ |
| 5개 Soft Switching 조정 | ✅ |
| sentiment 가중치 조정 | ✅ |
| gpt-5.4-mini Responses API | ✅ |
| ElasticNet 코드 제거 | ✅ |
| ruff lint 0 errors | ✅ |

---

## 7. 참고 문헌 & 인용

| 주제 | 참고문헌 | 설명 |
|---|---|---|
| RSI | Wilder (1978) | New Concepts in Technical Trading Systems |
| ATR | Wilder (1978) | 동일 |
| Time-Decay | Hastie, Tibshirani, Friedman (2009) | The Elements of Statistical Learning |
| Conformal Prediction | Vovk et al. (2005) | Algorithmic Learning in a Random World |
| Log-Return | Tsay (2010) | Analysis of Financial Time Series |
| Ensemble Learning | Wolpert (1992) | Stacked Generalization |
| AutoML | Databricks (2024) | AutoML User Guide |
| Unity Catalog | Databricks (2024) | ML Model Registry on UC |

---

## 8. 갱신 히스토리

| 버전 | 일자 | 주요 변경 | 상태 |
|---|---|---|---|
| v0412 | 2025-04-12 | TimesFM 초기 추론 파이프라인 | 개발 완료 |
| v0413 | 2025-04-13 | 동적 가중치 동상률 (Hard Threshold) | 병합 (PR #67) |
| v0414 | 2025-04-13 | Soft Switching + 로그수익률 + Interaction | PR #74 |
| v0415 | 2025-04-15 | 뉴스 심리 지표 통합 + sentiment 가중치 | 병합 |
| v0416 | 2025-04-16 | 키워드 분석 + Weight Scale 재조정 | 병합 |
| v0417 | 2025-04-17 | AutoML RandomForest + UC 모델 등록 | 병합 |
| v0418 | 2025-04-18 | gpt-5.4-mini + Responses API | 병합 |
| v0419 | 2025-04-19 | Gold Layer 통합 + UC 재학습 + ElasticNet 제거 | PR #89 진행중 |

---

**문서 작성**: SENSE 프로젝트 팀
**최종 갱신**: 2025-04-19
