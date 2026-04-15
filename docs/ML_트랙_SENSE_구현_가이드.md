# SENSE ML 트랙 — 상세 구현 가이드

> 원본: `ref/ML 트랙.md` 검증 기반. 실제 파일·테이블명·데이터 경로 기준으로 작성.
>
> 대상: 반도체 주간 등락 방향 예측 (삼성전자·SK하이닉스) — 5일 수익률 기준 분류

---

## 검증 요약 — `ref/ML 트랙.md` vs 실제 구현 현황

| 항목 | 원본 가이드 | 실제 현황 | 처리 |
|------|-----------|---------|------|
| 피처 테이블 | `fact_equity_ohlcv` + 47컬럼 | `gold_ml.gold_ml_feature_set` 분리 | → §1에서 병합 쿼리 제공 |
| RSI/ATR 적재 | `fact_equity_ohlcv` 안에 기재 | 별도 컬럼 미적재 | → Databricks 노트북에서 pandas_ta로 계산 |
| DB 적재 테이블 | `fact_ensemble_forecast` | 확인 ✅ (160행 기 적재) | UPSERT 템플릿 제공 |
| AML AutoML | "배포/관리 용도" | ML Studio 계정만 (AutoML 비권장) | 방어 논리 섞션 그대로 활용 |
| MLflow | Databricks 내장 | 확인 ✅ | Git commit hash 태그 필수 (CLAUDE.md) |
| 앙상블 코드 | `ensemble_strategy.py` (언급만) | `notebooks/timesfm_inference.py` ✅ | 현재 파일 기준으로 세분 |
| 통계 기준선 | ElasticNet | `notebooks/statistical_baseline_analysis.py` ✅ | 현재 파일 기준 |

---

## 전제 조건 체크리스트

```bash
# PostgreSQL 데이터 적재 확인
psql -d postgres -c "SELECT COUNT(*) FROM gold_ml.gold_ml_feature_set;"
psql -d postgres -c "SELECT COUNT(*) FROM gold_macro.fact_yf_fx_fred_1y;"
psql -d postgres -c "SELECT COUNT(*) FROM gold_news.agg_market_sentiment_daily;"

# ADLS Parquet 확인
az storage blob list --account-name 3dtteam1adls \
  --container-name feature --query "[?contains(name,'gold_macro')].name" -o tsv
```

필요 최소 행:
- `gold_ml.gold_ml_feature_set`: **200행+** (기술 지표 계산 최소 120일)
- `gold_macro.fact_yf_fx_fred_1y`: **250행+** (1년)
- `gold_news.agg_market_sentiment_daily`: **200행+**

---

## Day 8 — 피처 최종 병합 + 모델 학습 세팅

### 8-1. Databricks에서 ML 피처 통합 DataFrame 구축

`notebooks/02_curated_to_feature.py` 마지막 셀에 아래 블록을 추가하거나, 새 `notebooks/03_ml_feature_build.py` 로 분리:

```python
# notebooks/03_ml_feature_build.py

import pandas as pd
import numpy as np
import pandas_ta as ta  # pip install pandas-ta
from src.utils.vault_manager import vault

# ── 1. PostgreSQL에서 데이터 로드 ──────────────────────────────────
engine = vault.get_pg_connection("sqlalchemy")

macro_df = pd.read_sql("""
    SELECT trade_date,
           yfinance_samsung_close  AS samsung_close,
           yfinance_skhynix_close  AS skhynix_close,
           yfinance_sox_close      AS sox_close,
           usd_krw_rate, fred_dgs10, fred_dgs2, fred_t10y2y,
           fred_dff, fred_bamlh0a0hym2, stagnation_pressure,
           risk_off_flag
    FROM gold_macro.fact_yf_fx_fred_1y
    ORDER BY trade_date
""", engine, parse_dates=["trade_date"])

sentiment_df = pd.read_sql("""
    SELECT base_date AS trade_date, stock_code,
           avg_sentiment AS avg_absa_score, news_vol
    FROM gold_news.agg_market_sentiment_daily
    WHERE stock_code = 'SAMSUNG'
    ORDER BY base_date
""", engine, parse_dates=["trade_date"])

quant_df = pd.read_sql("""
    SELECT kr_effective_date AS trade_date,
           sox_return_1d, spillover_flag, upside_surge_flag
    FROM gold_ml.fact_quant_sox_sync
    ORDER BY kr_effective_date
""", engine, parse_dates=["trade_date"])

# ── 2. 기술 지표 (pandas_ta) ─────────────────────────────────────
close = macro_df["samsung_close"].fillna(method="ffill")

macro_df["rsi_14"]     = ta.rsi(close, length=14)
macro_df["atr_14"]     = ta.atr(macro_df["samsung_close"],
                                 macro_df["samsung_close"],
                                 macro_df["samsung_close"], length=14)
macro_df["ma_120"]     = close.rolling(120).mean()
macro_df["deviation_120"] = (close - macro_df["ma_120"]) / macro_df["ma_120"] * 100

# ── 3. 타겟 변수 생성 (5일 수익률 기반 분류) ──────────────────────
macro_df["target_return_5d"] = close.pct_change(5).shift(-5) * 100
macro_df["max_gain_5d"]      = close.rolling(5).max().shift(-5) / close - 1
macro_df["max_drawdown_5d"]  = close.rolling(5).min().shift(-5) / close - 1

# 방향 분류 (gold_equity.fact_equity_target 기준과 동일)
macro_df["upside_flag"]   = macro_df["max_gain_5d"]   > 0.03
macro_df["downside_flag"] = macro_df["max_drawdown_5d"] < -0.03
macro_df["regime_label"]  = macro_df.apply(_assign_regime, axis=1)

def _assign_regime(row):
    if row["downside_flag"] and row["upside_flag"]:
        return "high_vol"
    elif row["downside_flag"]:
        return "risk"
    elif row["upside_flag"]:
        return "opportunity"
    return "neutral"

# ── 4. 조인 ──────────────────────────────────────────────────────
df = macro_df.merge(sentiment_df[["trade_date","avg_absa_score","news_vol"]],
                    on="trade_date", how="left")
df = df.merge(quant_df, on="trade_date", how="left")
df = df.dropna(subset=["target_return_5d"])  # 미래 데이터 없는 마지막 5행 제거

# ── 5. PostgreSQL UPSERT (src/sql/dml/upsert_templates.sql 참고) ──
from sqlalchemy.dialects.postgresql import insert as pg_insert

table = "gold_ml.gold_ml_feature_set"
records = df[["trade_date", "samsung_close", "skhynix_close",
              "usd_krw_rate", "fred_dgs10", "fred_t10y2y",
              "sox_return_1d", "avg_absa_score", "news_vol",
              "target_return_5d", "downside_flag", "upside_flag",
              "regime_label"]].to_dict("records")

with engine.begin() as conn:
    conn.execute(pg_insert(table).values(records)
                 .on_conflict_do_update(
                     index_elements=["base_date"],
                     set_={c: pg_insert(table).excluded[c]
                           for c in records[0] if c != "trade_date"}))
print(f"✅ gold_ml_feature_set UPSERT 완료: {len(records)}행")
```

### 8-2. MLflow 실험 등록 (CLAUDE.md 규칙: Git commit hash 태그 필수)

```python
import mlflow, subprocess

GIT_HASH = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()

mlflow.set_experiment("/SENSE/ml_feature_build")
with mlflow.start_run(run_name="feature_build_v1") as run:
    mlflow.set_tag("git_commit", GIT_HASH)
    mlflow.log_param("feature_count", len(df.columns))
    mlflow.log_param("train_rows", len(df))
    mlflow.log_metric("target_upside_rate", df["upside_flag"].mean())
    mlflow.log_metric("target_downside_rate", df["downside_flag"].mean())
    print(f"MLflow run_id: {run.info.run_id}")
```

---

## Day 9 — 앙상블 모델 추론 + 신뢰도 점수

### 9-1. 현재 파일 역할 정리

| 파일 | 역할 | 출력 테이블 |
|------|------|-----------|
| `notebooks/statistical_baseline_analysis.py` | Ridge/ElasticNet (트랙 B) | `public.fact_stat_forecast` |
| `notebooks/timesfm_inference.py` | TimesFM + 앙상블 (트랙 A+팀장) | `public.fact_ensemble_forecast` |

### 9-2. `timesfm_inference.py` 핵심 파라미터 (현재 구현 기준)

```python
# timesfm_inference.py 에서 설정되는 주요 변수들 확인 필요
CONTEXT_LEN  = 128    # TimesFM 컨텍스트 길이 (1년 ≈ 250일 중 128일)
HORIZON      = 10     # 예측 기간: 10 영업일 (2주)
FREQ_TOKEN   = 0      # 0 = daily

# 앙상블 가중치 — RSI에 따라 동적 조정
def _get_weights(rsi: float) -> tuple[float, float]:
    """RSI 30 이하(과매도) → 추세 모델 비중 ↑, 70 이상(과매수) → 회귀 모델 비중 ↑"""
    if rsi < 30:
        return 0.75, 0.25   # (trend_weight, meanrev_weight)
    elif rsi > 70:
        return 0.35, 0.65
    else:
        return 0.55, 0.45   # 중립 구간 기본값
```

### 9-3. 신뢰도 점수 + 예측 구간 (현재 구현에서 confidence_score 활용)

`public.v_forecast_latest` 뷰로 최신 예측 조회:

```sql
SELECT ticker, forecast_date, final_pred, pi_lower, pi_upper,
       confidence_score, regime_label
FROM public.v_forecast_latest
WHERE horizon_day IN (1, 3, 5, 10)
ORDER BY ticker, horizon_day;
```

`confidence_score` 해석 기준 (권장):
- **0.8+**: 두 모델 방향 일치 + 낮은 예측 구간 폭 → 시그널 강
- **0.5~0.8**: 방향 일치, 구간 폭 보통 → 시그널 보통
- **0.5 이하**: 모델 간 방향 불일치 → "예측 불확실" 표시

### 9-4. 통계 기준선 실행 (`statistical_baseline_analysis.py`)

```python
# 현재 파일에서 8개 시나리오 실행 — 이미 구현됨
# ① base: 기본 매크로 피처
# ② with_sentiment: +뉴스 ABSA 점수
# ③ with_quant: +SOX·메모리 퀀트 신호
# ④ full: 모든 피처
# ⑤~⑧ bear/bull/rate_hike/rate_cut: 스트레스 시나리오

# 시나리오별 결과는 public.fact_stat_forecast 에 (ticker, base_date, horizon, model, scenario) PK로 적재
```

---

## Day 10 — ADF 오케스트레이션 + 최종 검증

### 10-1. ADF 파이프라인 구성

`adf/pipeline/Pipeline_Daily_SENSE_Predict.json` 로 저장:

```
[트리거: 매일 16:30 KST]
  └─ Activity 1: Web/Function — 데이터 수집 (야후 파이낸스, 뉴스)
  └─ Activity 2: Databricks Notebook — 01_raw_to_curated.py
  └─ Activity 3: Databricks Notebook — 02_curated_to_feature.py
  └─ Activity 4: Databricks Notebook — 03_ml_feature_build.py   [신규]
  └─ Activity 5: Databricks Notebook — statistical_baseline_analysis.py
  └─ Activity 6: Databricks Notebook — timesfm_inference.py
        ↓ 성공 시
  └─ Activity 7: (선택) ADF 알림 — 파이프라인 완료 이메일
```

### 10-2. Databricks Job Compute 설정 (비용 절감)

```json
// Databricks Job 설정 권장
{
  "job_clusters": [{
    "job_cluster_key": "ml_inference_cluster",
    "new_cluster": {
      "spark_version": "14.3.x-cpu-ml-scala2.12",
      "node_type_id": "Standard_DS3_v2",
      "num_workers": 1,
      "autotermination_minutes": 20
    }
  }]
}
// ⚠️ Interactive Cluster 대비 비용 50% 이하
// ⚠️ TimesFM은 CPU로 충분 (1년 데이터, Batch=1)
```

### 10-3. 최종 검증 쿼리

```sql
-- 예측 품질 확인
SELECT ticker,
       COUNT(*)                         AS total_predictions,
       AVG(confidence_score)            AS avg_confidence,
       MIN(base_date::DATE)             AS oldest_pred,
       MAX(base_date::DATE)             AS latest_pred
FROM public.fact_ensemble_forecast
GROUP BY ticker;

-- 통계 기준선 vs 앙상블 비교
SELECT ticker, horizon, model,
       AVG(prediction)                  AS avg_pred,
       STDDEV(prediction)               AS pred_std,
       COUNT(*)                         AS n
FROM public.fact_stat_forecast
GROUP BY ticker, horizon, model
ORDER BY ticker, horizon;

-- 퀀트 신호 최근 5일
SELECT * FROM gold_ml.v_quant_daily_signals
LIMIT 5;
```

### 10-4. 발표용 Power BI 연결

Power BI Desktop → PostgreSQL 커넥터:
- 서버: `<Azure PostgreSQL FQDN>:5432`
- 데이터베이스: `postgres`
- 권장 뷰: `public.v_daily_report_summary`, `gold_news.v_news_sentiment_trend`, `public.v_forecast_latest`

---

## 방어 논리 정리 (발표 Q&A)

**Q: "왜 AML AutoML을 쓰지 않았나요?"**

> 두 가지 이유입니다.  
> 첫째 **데이터 한계**: 1년(250일) 데이터로 AutoML을 구동하면 과적합 또는 평균 회귀 편향이 발생합니다. 수천억 개 시계열로 사전 학습된 Google TimesFM(Zero-shot)을 도입해야 했고, 이 모델은 Databricks 환경에서 직접 구동이 적합합니다.  
> 둘째 **설명 가능성**: AML 블랙박스 대신, Databricks 위에서 추세 모델(TimesFM)과 회귀 모델(ElasticNet)의 가중치를 RSI·이격도 시장 국면에 따라 직접 통제하는 **동적 가중치 앙상블**을 구현했습니다. 이것이 SENSE가 지향하는 설명 가능한 AI(Glass-box XAI)입니다.

**Q: "TimesFM이 주가 예측에 유효한가요?"**

> TimesFM 2.5는 Zero-shot 추론으로 데이터 부족 문제를 해결하며, 학술 논문에서 ARIMA, Prophet 대비 우수한 성능을 보입니다. 다만 당사는 TimesFM 단독이 아닌 ElasticNet과의 앙상블로 단방향 편향을 상쇄합니다. `confidence_score`를 통해 모델 불확실성을 명시적으로 전달합니다.

**Q: "MLflow 실험 재현성 보장은?"**

> 모든 MLflow run에 `git_commit` 태그(SHA)를 기록합니다(CLAUDE.md 규칙). 동일 SHA 체크아웃 + `uv sync` 로 동일 환경 재현 가능합니다.

---

## 파일 경로 레퍼런스

```
notebooks/
├── 01_raw_to_curated.py              # Bronze → Silver
├── 02_curated_to_feature.py          # Silver → Gold feature
├── 03_ml_feature_build.py            # [신규] 피처 병합 + 타겟 생성
├── statistical_baseline_analysis.py  # Ridge/ElasticNet 8-시나리오
└── timesfm_inference.py              # TimesFM + 앙상블

src/sql/
├── ddl/
│   ├── gold_layer_ddl.sql            # 전체 스키마 DDL
│   └── seed_data.sql                 # dim_equity, dim_macro_metadatas 초기 데이터
├── dml/
│   └── upsert_templates.sql          # Databricks 적재용 UPSERT 패턴
└── views_and_indexes.sql             # 인덱스 + Power BI / Web App 뷰

src/utils/vault_manager.py            # Key Vault → vault.get_pg_connection()
```

---

## 주의 사항

1. **`gold_ml.gold_customs_semiconductor` + `gold_macro.fact_semiconductor_trade` 중복**: 두 테이블이 동일한 관세청 데이터를 가집니다. 발표 전 하나로 통합하거나, 의도적 이중화 이유를 설명할 준비를 하세요.

2. **`gold_macro.fact_kfinance` PCR 한계**: 코스피200 풋옵션 거래량 없음 → `avg_iv`(내재변동성) 만 사용 가능. `pcr_ratio`는 `gold_quant_pcr_signals` 에서도 현재 0값 가능성.

3. **한글 컬럼명**: `fact_yf_fx_fred_1y`의 `"주말여부"`, `"한국_휴장일_여부"` 는 psycopg3에서 `%(주말여부)s` 방식으로 바인딩 가능. SQLAlchemy Core에서는 Column 객체 사용 권장.
