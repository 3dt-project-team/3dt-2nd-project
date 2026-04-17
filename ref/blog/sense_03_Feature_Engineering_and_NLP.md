# SENSE 프로젝트 3부: 47개 피처 엔지니어링 — 기술적 지표, 리스크 시그널, ABSA 뉴스 감성

> **시리즈**: Azure + Databricks + TimesFM으로 반도체 주가 예측 파이프라인 구축하기  
> **분류**: Feature Engineering, NLP, ABSA, Time Series, Quant Finance  
> **작성일**: 2026년 4월 17일  

---

## 들어가며 — 피처 엔지니어링이 모델보다 중요하다

머신러닝 실무에서 반복적으로 확인되는 사실이 있습니다: **피처 품질이 모델 선택보다 예측 성능에 더 큰 영향을 미친다**. 동일한 Random Forest 모델도 피처 설계에 따라 R²=0.05와 R²=0.93의 차이를 보입니다. SENSE에서 실제로 겪은 일입니다.

프로젝트 초반, 우리는 단순히 야후 파이낸스에서 받은 OHLCV와 몇 가지 기술적 지표를 ElasticNet에 넣었습니다. 결과는 삼성전자 R²=0.05, SK하이닉스 R²=-1.19. 음수 R²은 "모델이 평균을 그냥 출력하는 것보다 못하다"는 뜻입니다.

무엇이 문제였을까요? 이번 편에서 그 진단과 해결 과정을 상세히 풀겠습니다.

---

## 1. 실패 분석 — 왜 초기 피처셋이 작동하지 않았는가

### 1.1 스케일 불일치 문제

초기 피처셋의 가장 큰 문제는 **변수들의 스케일(Scale) 불일치**였습니다.

삼성전자 주가: ~60,000원  
NVIDIA 주가: ~$880 (약 1,180,000원)  
FRED DGS10 금리: ~4.5 (%)  

이 세 변수를 정규화 없이 ElasticNet에 넣으면, 절대값이 큰 NVIDIA 주가가 모델을 지배합니다. ElasticNet의 L1/L2 정규화는 계수 크기를 줄이는데, 이미 스케일이 다른 변수들에 같은 패널티를 적용하면 정보가 왜곡됩니다.

**해결책**: 절대 가격 대신 **로그수익률(Log Return)**을 사용합니다. `log(P_t / P_{t-1})`은 스케일에 무관하며, 복리 계산에서 가산성(Additivity)을 가집니다.

### 1.2 타겟 변수 재정의

초기에는 타겟을 **T+20일 절대 주가**로 설정했습니다. 이것은 두 가지 문제를 만듭니다.

첫째, 주가는 비정상(Non-stationary) 시계열입니다. 절대값은 추세(Trend)가 있어 모델이 과거 추세를 학습합니다. 둘째, 과거에 6만원대였던 삼성전자 주가와 현재 주가를 같은 스케일로 취급할 수 없습니다.

**해결책**: 타겟을 `log(P_{t+20} / P_t)` — **T+20일 누적 로그수익률**로 재정의합니다. 이 값은 오늘 기준으로 20거래일 후에 몇 퍼센트 변화할지를 나타내며, 정상성(Stationarity)에 가깝습니다.

---

## 2. 기술적 보조지표 — 시장 미시구조 포착

### 2.1 RSI(14) — 과매수/과매도의 수치화

RSI(Relative Strength Index)는 최근 14일간 상승 폭 대비 하락 폭의 비율로 과매수/과매도 상태를 0-100 사이 수치로 표현합니다.

```
RSI = 100 - 100 / (1 + RS)
RS = EMA(14일간 일일 상승분) / EMA(14일간 일일 하락분)
```

RSI가 70 이상이면 과매수(매도 신호), 30 이하면 과매도(매수 신호)로 해석합니다. SENSE에서 RSI는 예측 피처이기도 하지만, **앙상블 가중치를 동적으로 조절하는 핵심 신호**이기도 합니다. 이 역할은 4편에서 상세히 다룹니다.

```python
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
```

### 2.2 ATR(14) — 절대 변동성의 수치화

ATR(Average True Range)은 최근 14일의 True Range(일중 최대 가격 변동폭)의 지수이동평균입니다.

```
True Range = max(High - Low, |High - Prev_Close|, |Low - Prev_Close|)
ATR(14) = EMA(True Range, 14)
```

ATR 자체는 원화 단위이므로 종목 간 비교가 어렵습니다. **ATR%** = ATR / Close × 100 으로 정규화하여 삼성전자와 SK하이닉스의 변동성을 같은 스케일로 비교합니다.

흥미로운 점은, OHLC 데이터가 없고 종가(Close)만 있는 경우(예: ETF, 일부 데이터 소스)를 위해 별도의 함수를 구현했습니다:

```python
def compute_atr_from_close(close: pd.Series, period: int = 14) -> pd.Series:
    """종가만 있을 때 ATR 근사 계산: 일별 |log return| × close"""
    abs_log_ret = close.pct_change().abs()
    return abs_log_ret.ewm(span=period, adjust=False).mean() * close
```

### 2.3 120일 이격도 — 장기 추세 대비 괴리율

이격도(Disparity)는 현재 주가가 이동평균에서 얼마나 벗어났는지를 백분율로 표현합니다.

```
이격도 = (현재가 - N일 이동평균) / N일 이동평균 × 100
```

120일 이격도를 선택한 이유는 **반기(6개월) 추세를 기준으로 현재 주가의 위치**를 파악하기 위해서입니다. 이격도가 +20% 이상이면 단기 과열 가능성이 있고, -20% 이하면 저평가 가능성이 있습니다. 이 변수는 평균 회귀(Mean Reversion) 시그널로 활용됩니다.

### 2.4 실현 변동성 비율 (vol_ratio) — 변동성 가속 탐지

단기(5거래일)와 장기(20거래일) 실현 변동성의 비율입니다.

```
realized_vol_5d = std(log_return_daily, window=5) × √252
realized_vol_20d = std(log_return_daily, window=20) × √252  
vol_ratio = realized_vol_5d / realized_vol_20d
```

`vol_ratio > 1.5`는 최근 5일의 변동성이 한 달 평균의 1.5배를 넘는다는 뜻입니다. 이것은 급등락이 시작되고 있다는 신호입니다. 이 비율이 앙상블에서 AutoML 모델의 가중치를 높이는 데 사용됩니다.

---

## 3. sense_macro — 23개 리스크 시그널

기술적 지표가 개별 종목의 가격 행동을 포착한다면, **sense_macro** 변수군은 거시경제적 리스크 환경을 포착합니다.

### 3.1 매크로 스트레스 지수 (macro_stress_score)

```python
def compute_macro_stress_score(df: pd.DataFrame) -> pd.Series:
    """
    복수의 리스크 신호를 정규화하여 0~1 사이의 복합 스트레스 지수 계산
    
    구성 요소:
    - yield_spread: 10년-2년 금리차 (역전 시 경기침체 신호)
    - hy_spread: 하이일드 스프레드 (신용 위험 프리미엄)
    - vix_zscore: VIX 공포지수 Z-score
    - usd_krw_vol: 환율 변동성 (외환 불안)
    """
    signals = pd.DataFrame({
        "yield_inversion": (-df["T10Y2Y"]).clip(lower=0),  # 역전 구간만
        "hy_risk": df["BAMLH0A0HYM2"].pct_change(20),       # 20일 변화율
        "fx_vol": df["usd_krw_rate"].pct_change(5).abs(),   # 5일 환율 변동
    })
    
    # 각 신호를 0-1로 정규화 후 동등 가중 평균
    normalized = (signals - signals.min()) / (signals.max() - signals.min())
    return normalized.mean(axis=1)
```

### 3.2 공포 복합 지수 (fear_composite)

```
fear_composite = 0.4 × macro_stress_score
               + 0.3 × (hy_spread_zscore)
               + 0.3 × (usd_krw_volatility_zscore)
```

`macro_stress_score`가 구조적 리스크를 측정한다면, `fear_composite`는 시장의 즉각적 공포 반응을 측정합니다. 레만 브라더스 사태, 코로나 쇼크 같은 급격한 시장 붕괴 국면에서 `fear_composite`는 빠르게 상승합니다.

### 3.3 반도체 수출 리스크 시그널 (semi_risk_signal)

```python
# 관세청 HS 8542 데이터에서 파생
semi_export_mom3m = df["semi_expDlr"].pct_change(3)  # 3개월 모멘텀
semi_import_ratio = df["semi_impDlr"] / df["semi_expDlr"]  # 수입/수출 비율

# 수출 감소 + 수입 급증 = 공급망 압박 신호
semi_risk_signal = (
    (-semi_export_mom3m).clip(lower=0) * 0.6 +
    semi_import_ratio.pct_change(1).clip(lower=0) * 0.4
)
```

이 변수가 Granger 인과관계 검정에서 p < 0.05를 기록했습니다. 반도체 수출 통계가 주가 변화에 **통계적으로 유의미한 선행 신호**라는 것을 검증했습니다.

---

## 4. ABSA 뉴스 감성 분석 — 텍스트를 수치로

### 4.1 단순 감성 vs ABSA

기존 감성 분석(단순 Positive/Negative)의 한계를 극복하기 위해 **ABSA(Aspect-Based Sentiment Analysis)**를 도입했습니다.

| 분석 방식 | 예시 뉴스 | 결과 |
|---|---|---|
| 단순 감성 | "삼성전자 HBM3E 수율 70% 달성" | Positive (?) |
| ABSA | 동일 기사 | `수율` Aspect: 0.2 (긍정적이나 경쟁사 대비 낮음), `경쟁력` Aspect: -0.3 (부정적 함의) |

ABSA는 뉴스 하나에서 여러 비즈니스 속성(Aspect)을 추출하고 각각의 감성을 독립적으로 분석합니다. 반도체 뉴스에서 우리가 정의한 Aspect 카테고리는:

- **수율(Yield)**: HBM, 3D NAND 수율 이슈
- **수요(Demand)**: AI 서버용 메모리 수요 전망
- **공급망(Supply Chain)**: TSMC 의존도, 소재 공급 이슈
- **규제(Regulation)**: 미국 수출 규제, 중국 제재
- **경쟁(Competition)**: NVIDIA, Micron 대비 경쟁 포지션
- **거시경제(Macro)**: 금리, 환율의 업황 영향

### 4.2 Azure OpenAI 프롬프트 설계

```python
ABSA_SYSTEM_PROMPT = """당신은 반도체 투자 분석 전문가입니다.
다음 뉴스 기사를 분석하여 JSON 형식으로 응답하세요.

응답 형식:
{
  "category": "실적|공급망|규제|기술|거시경제|수급|기타",
  "core_summary": "3줄 이내 핵심 요약",
  "aspects": [
    {
      "aspect": "수율|수요|공급망|규제|경쟁|거시경제",
      "score": -1.0 ~ 1.0,  // 강한 부정(-1) ~ 강한 긍정(+1)
      "rationale": "점수 근거 한 문장"
    }
  ],
  "overall_sentiment": -1.0 ~ 1.0
}"""

def analyze_absa(article_text: str, client: AzureOpenAI) -> dict:
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": ABSA_SYSTEM_PROMPT},
            {"role": "user", "content": f"기사:\n{article_text[:2000]}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,  # 일관된 분석을 위해 낮게 설정
    )
    return json.loads(response.choices[0].message.content)
```

`temperature=0.1`로 설정한 이유는 감성 분석의 **재현성**을 높이기 위해서입니다. 같은 기사를 두 번 분석해도 유사한 점수가 나와야 합니다.

### 4.3 뉴스 감성 파생변수 6개

ABSA 원시 점수에서 다음 6개 파생변수를 계산합니다:

| 변수 | 계산식 | 의미 |
|---|---|---|
| `avg_sentiment` | EMA(absa_score, 7일) | 7일 지수이동평균 감성 (노이즈 제거) |
| `sentiment_momentum` | avg_sentiment - avg_sentiment.shift(7) | 감성의 변화 방향 및 속도 |
| `news_vol_surge` | news_vol / news_vol.rolling(20).mean() - 1 | 뉴스 언급량 폭발 비율 (전월 대비) |
| `sentiment_vol_7d` | std(absa_score, 7일) | 단기 감성 불안정도 |
| `sent_price_decouple` | corr(avg_sentiment, log_return, 20일) | 감성-주가 디커플링 탐지 |
| `keyword_surge_count` | (keyword_momentum > 300%).sum() | 300% 이상 급증 키워드 수 |

**`news_vol_surge`**는 특히 중요합니다. 갑자기 뉴스가 폭발적으로 늘어난다는 것은 —호재든 악재든— 어떤 이벤트가 발생했다는 신호입니다. 이것이 앙상블 가중치 조정의 5번째 신호로 사용됩니다.

---

## 5. 키워드 교호작용 피처 — 감성과 기술적 지표의 결합

단순히 감성 점수와 기술적 지표를 따로 피처로 넣는 것을 넘어, **두 정보의 교호작용(Interaction)**을 명시적으로 피처화했습니다.

| 교호작용 변수 | 계산 | 의미 |
|---|---|---|
| `keyword_surge_x_rsi` | `keyword_surge_count` × `rsi_14` | 뉴스 폭발 + 과매수: 추가 상승 vs 반락 신호 |
| `keyword_div_x_vol` | `keyword_diversity_ma7` × `realized_vol_5d` | 다양한 키워드 + 고변동성: 불확실성 집중 |
| `sentiment_x_surge` | `avg_sentiment` × `news_vol_surge` | 긍정 감성 + 뉴스 급증: 모멘텀 강화 |
| `kw_positive_x_disparity` | `avg_sentiment.clip(0)` × `disparity_120d` | 긍정 뉴스에도 고이격도: 과열 경보 |

이 교호작용 피처들은 단일 변수로는 포착하기 어려운 **비선형 패턴**을 선형 모델에 명시적으로 주입하는 기법입니다. Random Forest 같은 트리 기반 모델은 비선형 관계를 자동으로 학습하지만, 교호작용 피처를 명시적으로 추가하면 학습 효율을 높일 수 있습니다.

---

## 6. Granger 인과관계 검정 — "이 변수가 정말 예측에 도움이 되는가"

피처를 추가할 때마다 스스로에게 물어야 하는 질문이 있습니다: **"이 변수가 주가 변화에 선행하는가, 아니면 동행·후행하는가?"** 선행 관계 없이 동행하는 변수는 미래 예측에 사용할 수 없습니다.

**Granger 인과관계 검정(Granger Causality Test)**은 "변수 X의 과거값이 변수 Y의 현재값 예측에 통계적으로 유의미한 정보를 추가하는가"를 검정합니다. 엄밀히 말하면 인과관계가 아니라 **선행성(Precedence)**을 검정하는 것입니다.

```python
from statsmodels.tsa.stattools import grangercausalitytests

# 반도체 수출 → 삼성전자 주가 선행성 검정
result = grangercausalitytests(
    df[["samsung_log_return", "semi_total_exp_yoy"]].dropna(),
    maxlag=5
)
# 결과: lag=1에서 p-value=0.031 → 반도체 수출이 주가 변화에 1개월 선행 ✅
```

**유의미한 선행 변수 (p < 0.05)**:

| 변수 | lag | p-value | 해석 |
|---|---|---|---|
| `semi_total_exp` (반도체 수출액) | 1개월 | 0.031 | 수출 감소 → 주가 하락 선행 |
| `usd_krw_rate` (환율) | 2주 | 0.018 | 원화 약세 → 수출주 주가 선행 |
| `kfin_mean_price` (옵션 중앙가) | 1주 | 0.044 | 옵션 시장 가격 → 현물 선행 |
| `export_optimism_index` | 1개월 | 0.029 | 수출 기업 경기전망 → 주가 선행 |

반면 **동행 또는 후행** 변수들은 피처에서 제거하거나 가중치를 낮췄습니다.

---

## 7. 최종 피처셋 구성 — 47개

전체 피처를 6개 그룹으로 분류합니다:

| 그룹 | 변수 수 | 대표 변수 |
|---|---|---|
| 가격·기술 | 8 | `log_return`, `rsi_14`, `realized_vol_5d/20d`, `vol_ratio`, `disparity_120d`, `atr_14`, `atr_pct` |
| 글로벌 반도체 | 7 | `nvda_log_return`, `sox_log_return`, `tsm_close_norm`, `mu_close_norm`, `asml_close_norm`, `usd_krw_rate`, `gold_norm` |
| FRED 금리 | 6 | `DGS10`, `DGS2`, `T10Y2Y`, `BAMLH0A0HYM2`, `DFF`, `DFII10` |
| sense_macro 리스크 | 8 | `macro_stress_score`, `fear_composite`, `semi_risk_signal`, `yield_spread`, `risk_off_flag`, `fx_vol_20d`, `nvda_sox_beta`, `semi_export_mom3m` |
| 뉴스 감성 | 6 | `avg_sentiment`, `sentiment_momentum`, `news_vol_surge`, `sentiment_vol_7d`, `sent_price_decouple`, `keyword_surge_count` |
| 교호작용 | 4 | `keyword_surge_x_rsi`, `keyword_div_x_vol`, `sentiment_x_surge`, `kw_positive_x_disparity` |
| 관세청 파생 | 4 | `semi_expDlr`, `semi_impDlr`, `semi_exp_yoy`, `semi_import_ratio` |
| KFinance 옵션 | 4 | `kfin_mean_price`, `kfin_call_put_ratio`, `kfin_impl_vol`, `kfin_open_interest` |

---

## 8. 전후 성능 비교 — 피처 엔지니어링의 효과

| 단계 | 삼성전자 R² | SK하이닉스 R² | 주요 변화 |
|---|---|---|---|
| 초기 (절대 주가 타겟, 원시 OHLCV) | 0.05 | -1.19 | ElasticNet 과잉 정규화 |
| 로그수익률 타겟 전환 | 0.31 | 0.18 | 비정상성 제거 효과 |
| sense_macro 추가 | 0.54 | 0.41 | 거시 리스크 신호 효과 |
| ABSA 뉴스 감성 추가 | 0.67 | 0.58 | 텍스트 정보 효과 |
| 교호작용 피처 추가 + AutoML 교체 | **0.9266** | **0.7097** | 비선형 관계 포착 + 모델 교체 |

로그수익률로의 타겟 재정의만으로 R²가 0.05→0.31로 6배 개선되었습니다. 피처 엔지니어링과 타겟 설계의 중요성을 직접 경험한 순간이었습니다.

---

## 마치며 — 다음 편 예고

이번 편에서는 47개 피처가 어떤 이유로 설계되었는지, ElasticNet 실패의 원인이 무엇이었는지, ABSA 감성 분석이 어떻게 구현되었는지 살펴봤습니다.

다음 편에서는 이 47개 피처를 사용하는 핵심 — TimesFM 2.5와 AutoML UC BestTrial을 동적 가중치로 결합하는 앙상블 전략을 상세히 다룹니다.
