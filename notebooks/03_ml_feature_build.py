# Databricks notebook source
# SENSE 프로젝트 — ML 피처 병합 + 타겟 생성 (Gold Layer → gold_ml)
# SENSE: Semiconductor Economic News & Sentiment Engine
#
# 목적: Gold Layer PostgreSQL 테이블을 결합, 기술 지표·타겟 변수 생성 후 UPSERT
# 입력:
#   - gold_macro.fact_yf_fx_fred_1y    (주가·환율·매크로)
#   - gold_news.agg_market_sentiment_daily (뉴스 심리)
#   - gold_ml.fact_quant_sox_sync       (SOX 퀀트 신호)
# 출력:
#   - gold_ml.gold_ml_feature_set       (ML 피처 + 타겟)
# 실행: 02_curated_to_feature.py 완료 후 실행

# COMMAND ----------

# MAGIC %md
# MAGIC # 0. 환경 설정

# COMMAND ----------

# MAGIC %sh
# MAGIC uv pip install psycopg[binary] sqlalchemy pandas-ta mlflow scikit-learn --upgrade --quiet

# COMMAND ----------

# DBTITLE 1,Imports
import os
import subprocess
import sys
import warnings

import mlflow
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# COMMAND ----------

# MAGIC %md
# MAGIC # 1. vault_manager 초기화

# COMMAND ----------

REPO_PATH = "/Workspace/Repos/3dt030@msacademy.msai.kr/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"

from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()
engine = vault.get_pg_connection("sqlalchemy")

print("[OK] vault_manager 초기화 완료")

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. Gold Layer 데이터 로드 (PostgreSQL)

# COMMAND ----------

# ── 2-1. 주가·매크로 (gold_macro) ─────────────────────────────────────
macro_df = pd.read_sql(
    """
    SELECT trade_date,
           yfinance_samsung_close  AS samsung_close,
           yfinance_skhynix_close  AS skhynix_close,
           yfinance_sox_close      AS sox_close,
           usd_krw_rate,
           fred_dgs10,
           fred_dgs2,
           fred_t10y2y,
           fred_dff,
           fred_bamlh0a0hym2,
           stagnation_pressure,
           risk_off_flag
    FROM gold_macro.fact_yf_fx_fred_1y
    ORDER BY trade_date
    """,
    engine,
    parse_dates=["trade_date"],
)
date_min = macro_df["trade_date"].min()
date_max = macro_df["trade_date"].max()
print(f"[OK] macro_df: {len(macro_df)}행, {date_min} ~ {date_max}")

# COMMAND ----------

# ── 2-2. 뉴스 심리 (gold_news) ───────────────────────────────────────
sentiment_df = pd.read_sql(
    """
    SELECT base_date AS trade_date,
           stock_code,
           avg_sentiment AS avg_absa_score,
           news_vol
    FROM gold_news.agg_market_sentiment_daily
    ORDER BY base_date
    """,
    engine,
    parse_dates=["trade_date"],
)
# 삼성·SK 평균으로 대표 심리 지표 생성
sentiment_pivot = (
    sentiment_df.groupby("trade_date")[["avg_absa_score", "news_vol"]].mean().reset_index()
)
print(f"[OK] sentiment_pivot: {len(sentiment_pivot)}행")

# COMMAND ----------

# ── 2-3. SOX 퀀트 신호 (gold_ml) ──────────────────────────────────────
quant_df = pd.read_sql(
    """
    SELECT kr_effective_date AS trade_date,
           sox_return_1d,
           spillover_flag,
           upside_surge_flag
    FROM gold_ml.fact_quant_sox_sync
    ORDER BY kr_effective_date
    """,
    engine,
    parse_dates=["trade_date"],
)
print(f"[OK] quant_df: {len(quant_df)}행")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. 기술 지표 계산 (pandas_ta)

# COMMAND ----------

try:
    import pandas_ta as ta  # noqa: F401

    USE_PANDAS_TA = True
except ImportError:
    USE_PANDAS_TA = False
    print("[WARN] pandas_ta 없음 — 수동 계산으로 대체")


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI — pandas_ta 없을 때 fallback"""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(span=period).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _compute_atr(close: pd.Series, period: int = 14) -> pd.Series:
    """ATR (Close-only 간이 계산 — high/low 없을 때)"""
    tr = close.diff().abs()
    return tr.ewm(span=period).mean()


# ── 삼성전자 기술 지표 ──────────────────────────────────────────────
samsung_close = macro_df["samsung_close"].ffill()

if USE_PANDAS_TA:
    macro_df["rsi_14_samsung"] = ta.rsi(samsung_close, length=14)
    macro_df["atr_14_samsung"] = ta.atr(samsung_close, samsung_close, samsung_close, length=14)
else:
    macro_df["rsi_14_samsung"] = _compute_rsi(samsung_close)
    macro_df["atr_14_samsung"] = _compute_atr(samsung_close)

macro_df["ma_120_samsung"] = samsung_close.rolling(120, min_periods=60).mean()
macro_df["deviation_120_samsung"] = (
    (samsung_close - macro_df["ma_120_samsung"]) / macro_df["ma_120_samsung"] * 100
)

# ── SK하이닉스 기술 지표 ────────────────────────────────────────────
skhynix_close = macro_df["skhynix_close"].ffill()

if USE_PANDAS_TA:
    macro_df["rsi_14_skhynix"] = ta.rsi(skhynix_close, length=14)
    macro_df["atr_14_skhynix"] = ta.atr(skhynix_close, skhynix_close, skhynix_close, length=14)
else:
    macro_df["rsi_14_skhynix"] = _compute_rsi(skhynix_close)
    macro_df["atr_14_skhynix"] = _compute_atr(skhynix_close)

macro_df["ma_120_skhynix"] = skhynix_close.rolling(120, min_periods=60).mean()
macro_df["deviation_120_skhynix"] = (
    (skhynix_close - macro_df["ma_120_skhynix"]) / macro_df["ma_120_skhynix"] * 100
)

# ── 금리 스프레드 파생 ──────────────────────────────────────────────
macro_df["yield_spread_10_2"] = macro_df["fred_dgs10"] - macro_df["fred_dgs2"]

print("[OK] 기술 지표 계산 완료")

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. 타겟 변수 생성 (5일 수익률 기반 분류)

# COMMAND ----------


def _assign_regime(row: pd.Series) -> str:
    if row["downside_flag"] and row["upside_flag"]:
        return "high_vol"
    elif row["downside_flag"]:
        return "risk"
    elif row["upside_flag"]:
        return "opportunity"
    return "neutral"


def _build_targets(df: pd.DataFrame, close_col: str, prefix: str) -> pd.DataFrame:
    """5일 미래 수익률 기반 타겟 변수 + 방향 분류"""
    close = df[close_col].ffill()
    df[f"target_return_5d_{prefix}"] = close.pct_change(5).shift(-5) * 100
    df[f"max_gain_5d_{prefix}"] = close.rolling(5).max().shift(-5) / close - 1
    df[f"max_dd_5d_{prefix}"] = close.rolling(5).min().shift(-5) / close - 1
    df[f"upside_flag_{prefix}"] = df[f"max_gain_5d_{prefix}"] > 0.03
    df[f"downside_flag_{prefix}"] = df[f"max_dd_5d_{prefix}"] < -0.03
    df[f"regime_label_{prefix}"] = df.apply(
        lambda r: _assign_regime(
            pd.Series(
                {
                    "upside_flag": r[f"upside_flag_{prefix}"],
                    "downside_flag": r[f"downside_flag_{prefix}"],
                }
            )
        ),
        axis=1,
    )
    return df


macro_df = _build_targets(macro_df, "samsung_close", "samsung")
macro_df = _build_targets(macro_df, "skhynix_close", "skhynix")

print("[OK] 타겟 변수 생성 완료")

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. 데이터 조인 + 전처리

# COMMAND ----------

df = macro_df.merge(sentiment_pivot, on="trade_date", how="left")
df = df.merge(quant_df, on="trade_date", how="left")

# 미래 데이터 없는 마지막 5행(타겟 NaN) 제거
df = df.dropna(subset=["target_return_5d_samsung", "target_return_5d_skhynix"])

# 심리 지표 NaN → 중립값
df["avg_absa_score"] = df["avg_absa_score"].fillna(0.5)
df["news_vol"] = df["news_vol"].fillna(0)

# 퀀트 신호 NaN → 0
df["sox_return_1d"] = df["sox_return_1d"].fillna(0)
df["spillover_flag"] = df["spillover_flag"].fillna(0).astype(int)
df["upside_surge_flag"] = df["upside_surge_flag"].fillna(0).astype(int)

# 금리·매크로 전방향 채움
for col in [
    "fred_dgs10",
    "fred_dgs2",
    "fred_t10y2y",
    "fred_dff",
    "fred_bamlh0a0hym2",
    "usd_krw_rate",
    "yield_spread_10_2",
]:
    df[col] = df[col].ffill()

print(f"[OK] 조인 완료: {len(df)}행, 컬럼 수: {len(df.columns)}")
display(df.tail(3))  # noqa: F821

# COMMAND ----------

# MAGIC %md
# MAGIC # 6. PostgreSQL UPSERT (gold_ml.gold_ml_feature_set)

# COMMAND ----------

from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

UPSERT_COLS = [
    "trade_date",
    "samsung_close",
    "skhynix_close",
    "sox_close",
    "usd_krw_rate",
    "fred_dgs10",
    "fred_dgs2",
    "fred_t10y2y",
    "fred_dff",
    "fred_bamlh0a0hym2",
    "yield_spread_10_2",
    "stagnation_pressure",
    "risk_off_flag",
    "rsi_14_samsung",
    "atr_14_samsung",
    "deviation_120_samsung",
    "rsi_14_skhynix",
    "atr_14_skhynix",
    "deviation_120_skhynix",
    "sox_return_1d",
    "spillover_flag",
    "upside_surge_flag",
    "avg_absa_score",
    "news_vol",
    "target_return_5d_samsung",
    "upside_flag_samsung",
    "downside_flag_samsung",
    "regime_label_samsung",
    "target_return_5d_skhynix",
    "upside_flag_skhynix",
    "downside_flag_skhynix",
    "regime_label_skhynix",
]

records = df[UPSERT_COLS].copy()

# bool → int 변환 (PostgreSQL 호환)
for bool_col in [c for c in UPSERT_COLS if "flag" in c or "surge" in c]:
    records[bool_col] = records[bool_col].astype(int)

records_list = records.to_dict("records")

with engine.begin() as conn:
    # 테이블 존재 확인 — 없으면 to_sql로 초기 생성
    exists = conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'gold_ml' AND table_name = 'gold_ml_feature_set')"
        )
    ).scalar()

    if not exists:
        print("[INFO] 테이블 신규 생성 (to_sql)")
        records.to_sql(
            "gold_ml_feature_set",
            conn,
            schema="gold_ml",
            if_exists="replace",
            index=False,
        )
    else:
        stmt = pg_insert("gold_ml.gold_ml_feature_set").values(records_list)
        update_cols = {c: stmt.excluded[c] for c in UPSERT_COLS if c != "trade_date"}
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["trade_date"],
                set_=update_cols,
            )
        )

print(f"✅ gold_ml_feature_set UPSERT 완료: {len(records_list)}행")

# COMMAND ----------

# MAGIC %md
# MAGIC # 7. MLflow 실험 등록 (CLAUDE.md: Git commit hash 태그 필수)

# COMMAND ----------

try:
    GIT_HASH = (
        subprocess.check_output(
            ["git", "-C", REPO_PATH, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        .decode()
        .strip()
    )
except Exception:
    GIT_HASH = "unknown"

mlflow.set_experiment("/SENSE/ml_feature_build")

with mlflow.start_run(run_name="03_ml_feature_build") as run:
    mlflow.set_tag("git_commit", GIT_HASH)
    mlflow.set_tag("notebook", "03_ml_feature_build.py")

    mlflow.log_param("feature_count", len(UPSERT_COLS))
    mlflow.log_param("train_rows", len(df))
    mlflow.log_param(
        "date_range", f"{df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}"
    )

    mlflow.log_metric("samsung_upside_rate", float(df["upside_flag_samsung"].mean()))
    mlflow.log_metric("samsung_downside_rate", float(df["downside_flag_samsung"].mean()))
    mlflow.log_metric("skhynix_upside_rate", float(df["upside_flag_skhynix"].mean()))
    mlflow.log_metric("skhynix_downside_rate", float(df["downside_flag_skhynix"].mean()))
    mlflow.log_metric("avg_sentiment", float(df["avg_absa_score"].mean()))

    print(f"[OK] MLflow run_id: {run.info.run_id}")
    print(f"     git_commit: {GIT_HASH}")
    print(f"     삼성 upside 비율: {df['upside_flag_samsung'].mean():.1%}")
    print(f"     SK   upside 비율: {df['upside_flag_skhynix'].mean():.1%}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 완료 요약

# COMMAND ----------

print("=" * 60)
print("03_ml_feature_build 완료")
print(f"  - 적재 행수: {len(records_list)}")
print(f"  - 피처 컬럼: {len(UPSERT_COLS)}개")
print(f"  - 기간: {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}")
print(f"  - 삼성 regime 분포:\n{df['regime_label_samsung'].value_counts().to_string()}")
print(f"  - SK    regime 분포:\n{df['regime_label_skhynix'].value_counts().to_string()}")
print("=" * 60)
