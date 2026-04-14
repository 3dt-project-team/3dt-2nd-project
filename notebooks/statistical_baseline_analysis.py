# Databricks notebook source
# MAGIC %md
# MAGIC # SENSE 프로젝트 — 전통적 통계 분석 노트북 (Full Feature)
# MAGIC
# MAGIC > TimesFM(`timesfm_inference.py`)과 동일 데이터·피처·백테스트 프레임워크를 사용하되,
# MAGIC > **전통적 통계 모델(VAR + Ridge)** 로 예측하여 딥러닝 모델과 비교
# MAGIC
# MAGIC | 항목 | 내용 |
# MAGIC |---|---|
# MAGIC | 모델 | Baseline: VAR(p), Covariate: Ridge Regression |
# MAGIC | 타겟 | 삼성전자(005930.KS), SK하이닉스(000660.KS) close |
# MAGIC | 데이터 | ADLS `curated/`, `feature/` parquet — 1년 일별 |
# MAGIC | 평가 | MAE, MAPE, 80% PI Coverage, Direction Accuracy |
# MAGIC | AI 해석 | Azure OpenAI GPT-4.1-mini |
# MAGIC
# MAGIC ---
# MAGIC 주요 기능:
# MAGIC - 한글 폰트 자동 설정 (matplotlib 경고 해소)
# MAGIC - 피처 상관관계 히트맵 (Pearson/Spearman)
# MAGIC - 다중 호라이즌 백테스트 (5일/10일/20일)
# MAGIC - Conformal PI 보정
# MAGIC - Granger Causality Tests
# MAGIC - Permutation Importance
# MAGIC - 시나리오 일관성 검증
# MAGIC - 잔차 분포 분석 + VaR/CVaR 리스크 지표
# MAGIC - Azure OpenAI GPT-4.1-mini AI 투자 의견
# MAGIC
# MAGIC 간소화 버전: notebooks/statistical_baseline_analysis_lite.py

# COMMAND ----------

# DBTITLE 1,0. 환경 설정 및 패키지 설치
# MAGIC %sh
# MAGIC uv pip install scikit-learn statsmodels scipy openai psycopg[binary] --upgrade --quiet

# COMMAND ----------

import datetime
import os
import sys
import warnings

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests

warnings.filterwarnings("ignore", category=FutureWarning)

REPO_PATH = "/Workspace/Repos/3dt005@msacademy.msai.kr/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"

from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()
vault.get_storage_client()
account = vault.get_secret("adls-account-name")  # "3dtteam1adls"

# COMMAND ----------

# DBTITLE 1,한글 폰트 설정 (Databricks)
import glob  # noqa: E402
import subprocess  # noqa: E402

_korean_font = None
for _f in fm.fontManager.ttflist:
    if any(k in _f.name for k in ["Nanum", "Malgun", "NotoSansCJK"]):
        _korean_font = _f.name
        break
if _korean_font is None:
    subprocess.run(["apt-get", "install", "-y", "fonts-nanum"], capture_output=True, text=True)  # noqa: S603 S607
    subprocess.run(["fc-cache", "-fv"], capture_output=True, text=True)  # noqa: S603 S607
    # 직접 폰트 파일을 찾아 등록 (fm._load_fontmanager보다 안정적)
    _nanum_paths = glob.glob("/usr/share/fonts/**/Nanum*.ttf", recursive=True)
    if not _nanum_paths:
        _nanum_paths = glob.glob("/usr/share/fonts/**/nanum*.ttf", recursive=True)
    for _fp in _nanum_paths:
        fm.fontManager.addfont(_fp)
    if _nanum_paths:
        _prop = fm.FontProperties(fname=_nanum_paths[0])
        _korean_font = _prop.get_name()
    else:
        # fallback: fontmanager 재로드
        fm._load_fontmanager(try_read_cache=False)
        for _f in fm.fontManager.ttflist:
            if "Nanum" in _f.name:
                _korean_font = _f.name
                break
if _korean_font:
    plt.rcParams["font.family"] = _korean_font
    print(f"한글 폰트 설정: {_korean_font}")
else:
    print("[WARN] 한글 폰트를 찾을 수 없습니다.")
plt.rcParams["axes.unicode_minus"] = False

# COMMAND ----------

# DBTITLE 1,Azure OpenAI 클라이언트
from openai import AzureOpenAI  # noqa: E402

OPENAI_DEPLOYMENT = "gpt-4.1-mini"
OPENAI_API_VERSION = "2025-03-01-preview"

_openai_endpoint = vault.get_secret("azure-openai-endpoint")
_openai_key = vault.get_secret("azure-openai-key")
openai_client = AzureOpenAI(
    azure_endpoint=_openai_endpoint,
    api_key=_openai_key,
    api_version=OPENAI_API_VERSION,
)

_SYSTEM_MSG = (
    "당신은 SENSE 프로젝트의 반도체 시장 전문 애널리스트입니다. "
    "전통적 통계 모델(VAR, Ridge Regression) 결과를 바탕으로 "
    "한국어로 간결하고 전문적인 투자 인사이트를 제공합니다. "
    "숫자는 반드시 원본 그대로 인용하세요."
)


def ask_gpt(prompt, system_msg=_SYSTEM_MSG, max_tokens=800):
    try:
        resp = openai_client.chat.completions.create(
            model=OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[OpenAI 호출 실패] {e}"


# COMMAND ----------

# MAGIC %md
# MAGIC # 1. ADLS Gen2 연결 및 데이터 로드
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §1 과 **동일한 데이터 소스·로드 로직**

# COMMAND ----------

curated = f"abfss://curated@{account}.dfs.core.windows.net"
feature = f"abfss://feature@{account}.dfs.core.windows.net"

# --- 매크로 ---
_macro_paths = [
    f"{feature}/gold_macro_1y.parquet",
    f"{curated}/gold_macro_1y.parquet",
    f"{curated}/pre_macro_1y_adf.parquet",
]
raw_macro = None
for p in _macro_paths:
    try:
        raw_macro = spark.read.parquet(p).toPandas()  # noqa: F821
        print(f"매크로 로드 성공: {p} ({raw_macro.shape})")
        break
    except Exception:
        continue
if raw_macro is None:
    raise FileNotFoundError("매크로 데이터를 로드할 수 없습니다")

# --- KFinance ---
raw_kfin = spark.read.parquet(f"{curated}/silver_kfinance.parquet").toPandas()  # noqa: F821
print(f"KFinance 로드: {raw_kfin.shape}")

# --- 반도체 수출 ---
raw_semi = spark.read.parquet(f"{curated}/silver_semiconductor.parquet").toPandas()  # noqa: F821
print(f"반도체 수출 로드: {raw_semi.shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. 통합 피처 마트 구성
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §2 와 **동일**

# COMMAND ----------

TICKERS = ["005930.KS", "000660.KS"]
TICKER_NAMES = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스"}
HORIZON = 20

TICKER_COL_MAP = {
    "005930.KS": "yfinance_samsung_close",
    "000660.KS": "yfinance_skhynix_close",
}

# ---------------------------------------------------------------------------
# (A) 날짜 정규화 & 주가 타겟 (df_equity)
# ---------------------------------------------------------------------------
raw_macro["date"] = pd.to_datetime(raw_macro["date"])
macro = raw_macro.sort_values("date").drop_duplicates("date")

equity_records = []
for ticker, col_name in TICKER_COL_MAP.items():
    if col_name in macro.columns:
        _sub = macro[["date", col_name]].dropna(subset=[col_name]).copy()
        _sub = _sub.rename(columns={col_name: "close", "date": "trade_date"})
        _sub["ticker"] = ticker
        equity_records.append(_sub[["ticker", "trade_date", "close"]])
df_equity = (
    pd.concat(equity_records, ignore_index=True)
    .sort_values(["ticker", "trade_date"])
    .reset_index(drop=True)
    if equity_records
    else pd.DataFrame(columns=["ticker", "trade_date", "close"])
)
print(f"주가: {len(df_equity)} rows")
for t in TICKERS:
    print(f"  {TICKER_NAMES[t]}: {len(df_equity[df_equity['ticker'] == t])} 거래일")

# ---------------------------------------------------------------------------
# (B) 매크로 피처 (df_macro_gold)
# ---------------------------------------------------------------------------
_macro_cols = [
    "usd_krw_rate",
    "yfinance_nvda_close",
    "yfinance_amd_close",
    "yfinance_mu_close",
    "yfinance_tsm_close",
    "yfinance_asml_close",
    "yfinance_sox_close",
    "fred_dff",
    "fred_dgs10",
    "fred_dgs2",
    "fred_t10y2y",
    "fred_dfii10",
    "fred_bamlh0a0hym2",
]
_macro_avail = [c for c in _macro_cols if c in macro.columns]
df_macro_gold = (
    macro.rename(columns={"date": "trade_date"})
    .set_index("trade_date")[_macro_avail]
    .sort_index()
    .ffill()
    .bfill()
    if _macro_avail
    else pd.DataFrame()
)
if not df_macro_gold.empty:
    df_macro_gold.index.name = "trade_date"
print(f"매크로 피처: {df_macro_gold.shape}")

# ---------------------------------------------------------------------------
# (C) KFinance 피처 (df_kfinance)
# ---------------------------------------------------------------------------
raw_kfin["date"] = pd.to_datetime(raw_kfin["date"])
raw_kfin["close_price"] = pd.to_numeric(raw_kfin["close_price"], errors="coerce").fillna(0)
raw_kfin["strike"] = raw_kfin["ticker"].str.extract(r"(\d+)$")[0].astype(float)

df_kfin_agg = (
    raw_kfin.groupby("date")
    .agg(
        kfin_atm_price=("close_price", "max"),
        kfin_active_count=("close_price", lambda x: (x > 0).sum()),
        kfin_mean_price=("close_price", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
        kfin_total_value=("close_price", "sum"),
        kfin_total_count=("close_price", "count"),
    )
    .reset_index()
)
_active = raw_kfin[raw_kfin["close_price"] > 0]
_max_strike = _active.groupby("date")["strike"].max().reset_index()
_max_strike.columns = ["date", "kfin_max_strike"]
df_kfin_agg = df_kfin_agg.merge(_max_strike, on="date", how="left")
df_kfin_agg["kfin_active_ratio"] = (
    df_kfin_agg["kfin_active_count"] / df_kfin_agg["kfin_total_count"]
)
df_kfin_agg = df_kfin_agg.set_index("date").sort_index()
_bdays_kfin = pd.bdate_range(df_kfin_agg.index.min(), df_kfin_agg.index.max(), freq="B")
df_kfinance = df_kfin_agg.reindex(_bdays_kfin).ffill().bfill()
df_kfinance.index.name = "trade_date"
df_kfinance = df_kfinance.drop(columns=["kfin_total_count"], errors="ignore")
print(f"kfinance 피처: {df_kfinance.shape}")

# ---------------------------------------------------------------------------
# (D) 반도체 수출입 피처 (df_semiconductor)
# ---------------------------------------------------------------------------
raw_semi["date"] = pd.to_datetime(raw_semi["date"])
_semi_total = (
    raw_semi.groupby("date")
    .agg(semi_total_exp=("expDlr", "sum"), semi_total_imp=("impDlr", "sum"))
    .reset_index()
)
_semi_total["semi_net_trade"] = _semi_total["semi_total_exp"] - _semi_total["semi_total_imp"]

_dram = (
    raw_semi[raw_semi["hsCode"] == 8542321010]
    .groupby("date")
    .agg(semi_dram_exp=("expDlr", "sum"), semi_dram_imp=("impDlr", "sum"))
    .reset_index()
)
_flash = (
    raw_semi[raw_semi["hsCode"] == 8542321030]
    .groupby("date")
    .agg(semi_flash_exp=("expDlr", "sum"), semi_flash_imp=("impDlr", "sum"))
    .reset_index()
)
_mcp = (
    raw_semi[raw_semi["hsCode"] == 8542323000]
    .groupby("date")
    .agg(semi_mcp_exp=("expDlr", "sum"))
    .reset_index()
)

df_semi_agg = _semi_total
for _sub in [_dram, _flash, _mcp]:
    df_semi_agg = df_semi_agg.merge(_sub, on="date", how="left")
df_semi_agg = df_semi_agg.sort_values("date").reset_index(drop=True)

df_semi_agg["semi_dram_ratio"] = df_semi_agg["semi_dram_exp"] / df_semi_agg[
    "semi_total_exp"
].replace(0, np.nan)
df_semi_agg["semi_exp_mom"] = df_semi_agg["semi_total_exp"].pct_change()
df_semi_agg["semi_dram_mom"] = df_semi_agg["semi_dram_exp"].pct_change()
df_semi_agg["semi_trade_ratio"] = df_semi_agg["semi_total_exp"] / df_semi_agg[
    "semi_total_imp"
].replace(0, np.nan)

_dollar_cols = [
    c
    for c in df_semi_agg.columns
    if c.startswith("semi_")
    and ("exp" in c or "imp" in c or "net" in c)
    and "mom" not in c
    and "ratio" not in c
]
for col in _dollar_cols:
    df_semi_agg[col] = df_semi_agg[col] / 1e8

df_semi_agg = df_semi_agg.set_index("date").sort_index()
_bdays_semi = pd.bdate_range(df_semi_agg.index.min(), df_semi_agg.index.max(), freq="B")
df_semiconductor = df_semi_agg.reindex(_bdays_semi).ffill().bfill()
df_semiconductor.index.name = "trade_date"
print(f"semiconductor 피처: {df_semiconductor.shape}")


# ---------------------------------------------------------------------------
# (E) 통합 피처 마트 구성
# ---------------------------------------------------------------------------
def build_feature_mart(df_eq, ticker, df_kfin, df_semi, df_macro):
    """종목별 통합 피처 마트를 date 기준으로 LEFT JOIN하여 구성합니다."""
    df = df_eq[df_eq["ticker"] == ticker][["trade_date", "close"]].copy()
    df = df.set_index("trade_date").sort_index()
    df["return_1d"] = df["close"].pct_change()
    if not df_kfin.empty:
        df = df.join(df_kfin, how="left")
    if not df_semi.empty:
        df = df.join(df_semi, how="left")
    if not df_macro.empty:
        df = df.join(df_macro, how="left")
    df = df.ffill().bfill()
    # date 컬럼 추가 (PostgreSQL 적재 등에서 필요)
    df["date"] = df.index
    df = df.reset_index(drop=True)
    return df


feature_marts = {}
for ticker in TICKERS:
    feature_marts[ticker] = build_feature_mart(
        df_equity, ticker, df_kfinance, df_semiconductor, df_macro_gold
    )
    print(f"{TICKER_NAMES[ticker]}: {feature_marts[ticker].shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. 파생 변수 생성
# MAGIC
# MAGIC > `timesfm_inference.py` §3 동일

# COMMAND ----------


def create_derived_features(df):
    """timesfm_inference.py와 동일한 47개 파생 변수 생성."""
    out = df.copy()

    # 기본 수익률/이동평균
    if "close" in out.columns:
        out["return_1d"] = out["close"].pct_change()
        out["return_5d"] = out["close"].pct_change(5)
        out["ma_5"] = out["close"].rolling(5).mean()
        out["ma_20"] = out["close"].rolling(20).mean()

    # === 교호 작용 파생 변수 ===

    # 금융 × 수출: 옵션 시장 활성도 × 수출 모멘텀
    if "kfin_active_ratio" in out.columns and "semi_exp_mom" in out.columns:
        out["finance_export_synergy"] = out["kfin_active_ratio"] * out["semi_exp_mom"].fillna(0)

    # 옵션 ATM가 × DRAM 수출: 시장 기대 × DRAM 실적
    if "kfin_atm_price" in out.columns and "semi_dram_exp" in out.columns:
        out["atm_dram_cross"] = (
            out["kfin_atm_price"] / out["kfin_atm_price"].rolling(5, min_periods=1).mean()
        ) * (out["semi_dram_exp"] / out["semi_dram_exp"].rolling(3, min_periods=1).mean())

    # 무역수지 × 옵션 총가치: 실물 × 금융 복합 지표
    if "semi_net_trade" in out.columns and "kfin_total_value" in out.columns:
        out["trade_finance_compound"] = (
            out["semi_net_trade"]
            / out["semi_net_trade"].abs().rolling(3, min_periods=1).mean().replace(0, np.nan)
        ) * (
            out["kfin_total_value"]
            / out["kfin_total_value"].rolling(5, min_periods=1).mean().replace(0, np.nan)
        )

    # DRAM 비중 변화 × 주가 수익률: DRAM 의존도 신호
    if "semi_dram_ratio" in out.columns and "return_1d" in out.columns:
        dram_ratio_delta = out["semi_dram_ratio"] - out["semi_dram_ratio"].shift(1)
        out["dram_dependency_signal"] = dram_ratio_delta.fillna(0) * np.sign(
            out["return_1d"].fillna(0)
        )

    # 수출입 비율 × 최대행사가: 수출 강세 + 옵션 낙관 복합
    if "semi_trade_ratio" in out.columns and "kfin_max_strike" in out.columns:
        out["export_optimism_index"] = (
            out["semi_trade_ratio"]
            / out["semi_trade_ratio"].rolling(3, min_periods=1).mean().replace(0, np.nan)
        ) * (
            out["kfin_max_strike"]
            / out["kfin_max_strike"].rolling(5, min_periods=1).mean().replace(0, np.nan)
        )

    # === 시차(Lag) 기반 피처 ===
    if "kfin_atm_price" in out.columns:
        out["kfin_atm_lag1"] = out["kfin_atm_price"].shift(1)
        out["kfin_atm_delta_5d"] = out["kfin_atm_price"] - out["kfin_atm_price"].shift(5)

    if "semi_total_exp" in out.columns:
        out["semi_exp_ma3"] = out["semi_total_exp"].rolling(3, min_periods=1).mean()

    if "semi_dram_exp" in out.columns:
        out["semi_dram_ma3"] = out["semi_dram_exp"].rolling(3, min_periods=1).mean()

    if "kfin_active_ratio" in out.columns:
        out["kfin_active_ratio_ma5"] = out["kfin_active_ratio"].rolling(5, min_periods=1).mean()

    # === 변동성 피처 ===
    if "return_1d" in out.columns:
        out["realized_vol_5d"] = out["return_1d"].rolling(5, min_periods=1).std()
        out["realized_vol_20d"] = out["return_1d"].rolling(20, min_periods=1).std()
        out["vol_ratio"] = out["realized_vol_5d"] / out["realized_vol_20d"].replace(0, np.nan)
    if "close" in out.columns:
        out["gap_from_ma20"] = (out["close"] - out["close"].rolling(20).mean()) / out[
            "close"
        ].rolling(20).mean()

    # 구버전 호환: export_optimism_index fallback
    if "export_optimism_index" not in out.columns:
        exp_cols = [c for c in out.columns if "exp" in c.lower() and "date" not in c.lower()]
        if exp_cols and "close" in out.columns:
            out["export_optimism_index"] = out[exp_cols].mean(axis=1)

    # NaN 정리
    out = out.ffill().bfill()
    return out


for ticker in TICKERS:
    feature_marts[ticker] = create_derived_features(feature_marts[ticker])
    print(f"[{TICKER_NAMES[ticker]}] 파생 변수 포함 컬럼: {feature_marts[ticker].shape[1]}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3-1. 피처 상관관계 분석
# MAGIC
# MAGIC > `timesfm_inference.py` §3-1 동일: Pearson + Spearman 이중 히트맵

# COMMAND ----------

_corr_cols = [
    "close",
    "return_1d",
    "kfin_atm_price",
    "kfin_max_strike",
    "kfin_mean_price",
    "kfin_active_ratio",
    "semi_total_exp",
    "semi_dram_exp",
    "semi_exp_mom",
    "usd_krw_rate",
    "yfinance_nvda_close",
    "yfinance_tsm_close",
    "yfinance_sox_close",
    "export_optimism_index",
    "finance_export_synergy",
    "realized_vol_5d",
    "vol_ratio",
    "gap_from_ma20",
]

for ticker in TICKERS:
    mart = feature_marts[ticker]
    avail = [c for c in _corr_cols if c in mart.columns]
    sub = mart[avail].dropna()
    if sub.empty:
        continue
    pearson = sub.corr(method="pearson")
    spearman = sub.corr(method="spearman")

    fig, axes = plt.subplots(1, 2, figsize=(22, 9))
    for ax, corr_mat, title in zip(axes, [pearson, spearman], ["Pearson", "Spearman"]):
        im = ax.imshow(corr_mat, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(avail)))
        ax.set_yticks(range(len(avail)))
        ax.set_xticklabels(avail, rotation=45, ha="right", fontsize=7)
        ax.set_yticklabels(avail, fontsize=7)
        for r in range(len(avail)):
            for c_idx in range(len(avail)):
                ax.text(
                    c_idx,
                    r,
                    f"{corr_mat.iloc[r, c_idx]:.2f}",
                    ha="center",
                    va="center",
                    fontsize=6,
                )
        ax.set_title(f"{TICKER_NAMES[ticker]} — {title} Correlation", fontsize=12)
    plt.colorbar(im, ax=axes, shrink=0.8, label="Correlation")
    plt.tight_layout()
    plt.savefig(f"/tmp/stat_corr_heatmap_{ticker}.png", dpi=150)
    plt.show()

    spear_vs_close = spearman["close"].drop("close").sort_values(ascending=False)
    print(f"\n{TICKER_NAMES[ticker]} — Spearman 순위 상관 (vs close) Top 10:")
    for col, val in spear_vs_close.head(10).items():
        print(f"  {col}: {val:.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. 모델 구성 — VAR + Ridge Regression
# MAGIC
# MAGIC > TimesFM 대신 전통적 시계열 모델 사용
# MAGIC > - **VAR**: Baseline 추론 — target 시계열만 (TimesFM Zero-shot 대응)
# MAGIC > - **Ridge**: Covariate 추론 — 전체 피처 (TimesFM XReg 대응)

# COMMAND ----------

_exclude = {"date", "ticker", "close", "open", "high", "low", "volume"}
numerical_cols = {}
for ticker in TICKERS:
    mart = feature_marts[ticker]
    num_cols = [c for c in mart.select_dtypes(include=[np.number]).columns if c not in _exclude]
    numerical_cols[ticker] = num_cols
    print(f"[{TICKER_NAMES[ticker]}] 수치형 피처: {len(num_cols)}개")

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. Step 1 — VAR Baseline 추론
# MAGIC
# MAGIC > 두 종목 close 시계열로 VAR(p) 구성 — TimesFM Zero-shot과 대응

# COMMAND ----------

_var_data = pd.DataFrame()
for ticker in TICKERS:
    mart = feature_marts[ticker]
    _var_data[TICKER_NAMES[ticker]] = mart["close"].values[: min(len(mart), 243)]

_var_data = _var_data.dropna()
print(f"VAR 학습 데이터: {_var_data.shape}")

var_model = VAR(_var_data)
_bic_results = {}
for lag in range(1, 11):
    try:
        _res = var_model.fit(lag)
        _bic_results[lag] = _res.bic
    except Exception:
        pass
optimal_lag = min(_bic_results, key=_bic_results.get) if _bic_results else 2
print(f"최적 시차(BIC): p={optimal_lag}")

var_result = var_model.fit(optimal_lag)
print(var_result.summary())

# Forecast
var_forecast = var_result.forecast(_var_data.values[-optimal_lag:], steps=HORIZON)
var_forecast_df = pd.DataFrame(var_forecast, columns=[TICKER_NAMES[t] for t in TICKERS])

print(f"\nVAR Baseline 추론 (T+1 ~ T+{HORIZON}):")
for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    last_price = _var_data[name].iloc[-1]
    final_pred = var_forecast_df[name].iloc[-1]
    change = (final_pred - last_price) / last_price * 100
    print(f"  {name}: 현재 {last_price:,.0f} → T+{HORIZON} {final_pred:,.0f} ({change:+.2f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC # 6. Step 2 — Ridge Regression Covariate 추론
# MAGIC
# MAGIC > 전체 피처를 이용한 T+HORIZON close 예측 — TimesFM XReg과 대응

# COMMAND ----------

ridge_models = {}
ridge_predictions = {}
ridge_scalers = {}

for ticker in TICKERS:
    mart = feature_marts[ticker].copy()
    mart["target"] = mart["close"].shift(-HORIZON)
    mart_clean = mart.dropna(subset=["target"])

    feat_cols = [c for c in numerical_cols[ticker] if c in mart_clean.columns]
    X = mart_clean[feat_cols].fillna(0).values
    y = mart_clean["target"].values

    X_train, y_train = X[:-1], y[:-1]
    X_last = X[-1:].reshape(1, -1)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_last_s = scaler.transform(X_last)

    ridge = RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0, 1000.0], cv=5)
    ridge.fit(X_train_s, y_train)

    pred = ridge.predict(X_last_s)[0]
    ridge_models[ticker] = ridge
    ridge_predictions[ticker] = pred
    ridge_scalers[ticker] = (scaler, feat_cols)

    last_price = mart["close"].iloc[-1]
    change = (pred - last_price) / last_price * 100
    print(
        f"[{TICKER_NAMES[ticker]}] Ridge T+{HORIZON}: {pred:,.0f} ({change:+.2f}%), "
        f"alpha={ridge.alpha_:.1f}, R²={ridge.score(X_train_s, y_train):.4f}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6-1. AI 해석 — 예측 결과

# COMMAND ----------

_pred_lines = []
for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    mart = feature_marts[ticker]
    last_price = mart["close"].iloc[-1]
    var_pred = var_forecast_df[name].iloc[-1]
    ridge_pred = ridge_predictions[ticker]
    var_pct = (var_pred - last_price) / last_price * 100
    ridge_pct = (ridge_pred - last_price) / last_price * 100
    impact = ridge_pred - var_pred
    impact_pct = impact / last_price * 100
    _pred_lines.append(
        f"[{name}] 현재가: {last_price:,.0f} | "
        f"VAR T+{HORIZON}: {var_pred:,.0f} ({var_pct:+.2f}%) | "
        f"Ridge T+{HORIZON}: {ridge_pred:,.0f} ({ridge_pct:+.2f}%) | "
        f"공변량 효과: {impact:+,.0f} ({impact_pct:+.2f}%)"
    )

_interp = ask_gpt(
    "\n".join(_pred_lines) + "\n\n위 전통적 모델(VAR, Ridge) 결과를 분석해 주세요:\n"
    "1) VAR Baseline vs Ridge Covariate 차이 해석\n"
    "2) 각 종목별 투자 시사점\n"
    "3) TimesFM 같은 딥러닝 모델 대비 전통 모델의 한계",
    max_tokens=600,
)
print("🤖 AI 해석 — VAR vs Ridge 예측 비교")
print(_interp)

# COMMAND ----------

# MAGIC %md
# MAGIC # 7. 공변량 충격 분석 및 시각화
# MAGIC
# MAGIC > Ridge − VAR 차이 = 공변량이 가격에 미치는 순 충격 (TimesFM §7 대응)

# COMMAND ----------

print("=" * 60)
print("Ridge − VAR: 공변량 충격 분석")
print("=" * 60)

fig, axes = plt.subplots(1, len(TICKERS), figsize=(7 * len(TICKERS), 5))
if len(TICKERS) == 1:
    axes = [axes]
for idx, ticker in enumerate(TICKERS):
    ax = axes[idx]
    name = TICKER_NAMES[ticker]
    last_p = feature_marts[ticker]["close"].iloc[-1]
    var_p = var_forecast_df[name].iloc[-1]
    ridge_p = ridge_predictions[ticker]
    vals = [last_p, var_p, ridge_p]
    labels = ["현재가", f"VAR T+{HORIZON}", f"Ridge T+{HORIZON}"]
    colors = ["#555555", "#3498db", "#e74c3c"]
    ax.bar(labels, vals, color=colors, alpha=0.8)
    for j, v in enumerate(vals):
        ax.text(j, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=9)
    ax.set_title(f"{name}", fontsize=13)
    ax.set_ylabel("₩")
    ax.grid(True, alpha=0.3, axis="y")

plt.suptitle(f"VAR Baseline vs Ridge Covariate (T+{HORIZON})", fontsize=14, y=1.02)
plt.tight_layout()
plt.savefig("/tmp/stat_impact_comparison.png", dpi=150)
plt.show()

# COMMAND ----------

# MAGIC %md
# MAGIC # 8. 시나리오 분석 (Ridge coefficient-based)
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §8 과 **동일한 12개 시나리오** 정의

# COMMAND ----------

# 현재 최신 값 가져오기 (시나리오 절댓값 기준; timesfm_inference.py §8 동일 방식)
mart = feature_marts[TICKERS[0]]
current_vals = {col: mart[col].iloc[-1] for col in mart.columns}

SCENARIOS = {
    # ── 기준 ──
    "현상 유지": {},
    # ── 통화정책 시나리오 ──
    "금리 인하 (-50bp)": {
        "fred_dgs10": current_vals.get("fred_dgs10", 4.0) - 0.5,
        "fred_dgs2": current_vals.get("fred_dgs2", 4.0) - 0.5,
        "fred_t10y2y": current_vals.get("fred_t10y2y", 0.0) + 0.3,
    },
    "금리 인상 (+50bp)": {
        "fred_dgs10": current_vals.get("fred_dgs10", 4.0) + 0.5,
        "fred_dgs2": current_vals.get("fred_dgs2", 4.0) + 0.5,
        "fred_t10y2y": current_vals.get("fred_t10y2y", 0.0) - 0.3,
    },
    "스프레드 급등 (+100bp)": {
        "fred_bamlh0a0hym2": current_vals.get("fred_bamlh0a0hym2", 3.5) + 1.0,
        "fred_dfii10": current_vals.get("fred_dfii10", 2.0) + 0.5,
    },
    # ── 환율·무역 시나리오 ──
    "원화 약세 (+5%)": {
        "usd_krw_rate": current_vals.get("usd_krw_rate", 1400.0) * 1.05,
    },
    "원화 강세 (-5%)": {
        "usd_krw_rate": current_vals.get("usd_krw_rate", 1400.0) * 0.95,
    },
    # ── 산업·수급 시나리오 ──
    "반도체 수출 급증 (+20%)": {
        "semi_total_exp": current_vals.get("semi_total_exp", 300.0) * 1.20,
        "semi_dram_exp": current_vals.get("semi_dram_exp", 80.0) * 1.20,
        "semi_exp_mom": 0.20,
    },
    "반도체 수출 급감 (-20%)": {
        "semi_total_exp": current_vals.get("semi_total_exp", 300.0) * 0.80,
        "semi_dram_exp": current_vals.get("semi_dram_exp", 80.0) * 0.80,
        "semi_exp_mom": -0.20,
    },
    "AI 수요 폭증 (NVDA +15%)": {
        "yfinance_nvda_close": current_vals.get("yfinance_nvda_close", 120.0) * 1.15,
        "yfinance_tsm_close": current_vals.get("yfinance_tsm_close", 170.0) * 1.10,
        "yfinance_mu_close": current_vals.get("yfinance_mu_close", 90.0) * 1.10,
    },
    "글로벌 반도체 약세 (SOX -10%)": {
        "yfinance_sox_close": current_vals.get("yfinance_sox_close", 4500.0) * 0.90,
        "yfinance_nvda_close": current_vals.get("yfinance_nvda_close", 120.0) * 0.90,
        "yfinance_tsm_close": current_vals.get("yfinance_tsm_close", 170.0) * 0.90,
    },
    # ── 복합 시나리오 (스트레스 테스트) ──
    "복합 호재: 금리인하 + 수출급증": {
        "fred_dgs10": current_vals.get("fred_dgs10", 4.0) - 0.5,
        "fred_t10y2y": current_vals.get("fred_t10y2y", 0.0) + 0.3,
        "semi_total_exp": current_vals.get("semi_total_exp", 300.0) * 1.20,
        "semi_dram_exp": current_vals.get("semi_dram_exp", 80.0) * 1.20,
        "yfinance_nvda_close": current_vals.get("yfinance_nvda_close", 120.0) * 1.10,
    },
    "복합 악재: 금리인상 + 원화약세 + 수출감소": {
        "fred_dgs10": current_vals.get("fred_dgs10", 4.0) + 0.5,
        "usd_krw_rate": current_vals.get("usd_krw_rate", 1400.0) * 1.08,
        "semi_total_exp": current_vals.get("semi_total_exp", 300.0) * 0.85,
        "semi_dram_exp": current_vals.get("semi_dram_exp", 80.0) * 0.85,
        "yfinance_sox_close": current_vals.get("yfinance_sox_close", 4500.0) * 0.90,
    },
}

SCENARIO_GROUPS = {
    "기준": ["현상 유지"],
    "통화정책": ["금리 인하 (-50bp)", "금리 인상 (+50bp)", "스프레드 급등 (+100bp)"],
    "환율·무역": ["원화 약세 (+5%)", "원화 강세 (-5%)"],
    "산업·수급": [
        "반도체 수출 급증 (+20%)",
        "반도체 수출 급감 (-20%)",
        "AI 수요 폭증 (NVDA +15%)",
        "글로벌 반도체 약세 (SOX -10%)",
    ],
    "복합 스트레스": [
        "복합 호재: 금리인하 + 수출급증",
        "복합 악재: 금리인상 + 원화약세 + 수출감소",
    ],
}

# Ridge 계수 기반 시나리오 분석 (절댓값 직접 오버라이드 방식 — timesfm_inference.py §8 동일)
scenario_results_stat = {}
for sc_name, overrides in SCENARIOS.items():
    sc_preds = {}
    for ticker in TICKERS:
        scaler, feat_cols = ridge_scalers[ticker]
        ridge = ridge_models[ticker]
        last_row = feature_marts[ticker][feat_cols].iloc[-1:].copy()
        for col, override_val in overrides.items():
            if col in last_row.columns:
                last_row[col] = override_val
        X_sc = scaler.transform(last_row.fillna(0).values)
        sc_preds[ticker] = ridge.predict(X_sc)[0]
    scenario_results_stat[sc_name] = sc_preds

# 시나리오 결과 테이블
print("=" * 70)
print(f"시나리오 분석 결과 (Ridge → T+{HORIZON})")
print("=" * 70)
for group, members in SCENARIO_GROUPS.items():
    print(f"\n── {group} ──")
    for name in members:
        if name not in scenario_results_stat:
            continue
        parts = []
        for ticker in TICKERS:
            pred = scenario_results_stat[name][ticker]
            last_p = feature_marts[ticker]["close"].iloc[-1]
            chg = (pred - last_p) / last_p * 100
            parts.append(f"{TICKER_NAMES[ticker]}: {pred:,.0f} ({chg:+.2f}%)")
        print(f"  [{name}] {' | '.join(parts)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8-1. 시나리오 일관성 검증
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §8-1 동일 로직

# COMMAND ----------

_sanity_stat = []
_base_result_stat = scenario_results_stat.get("현상 유지", {})
for sc_name, preds in scenario_results_stat.items():
    if sc_name == "현상 유지":
        continue
    for ticker in TICKERS:
        last_p = feature_marts[ticker]["close"].iloc[-1]
        base_p = _base_result_stat.get(ticker, last_p)
        delta_pct = (preds[ticker] - base_p) / abs(base_p) * 100
        _sanity_stat.append(
            {
                "시나리오": sc_name,
                "종목": TICKER_NAMES[ticker],
                "기준 대비 변동(%)": round(delta_pct, 2),
            }
        )

df_sanity_stat = pd.DataFrame(_sanity_stat)
print("시나리오 일관성 검증 (현상 유지 대비 변동):")
print(df_sanity_stat.to_string(index=False))

print("\n⚠️ 직관 검증 필요 시나리오:")
_counterintuitive_stat = []
for _, row in df_sanity_stat.iterrows():
    name, delta = row["시나리오"], row["기준 대비 변동(%)"]
    flag = None
    if "금리 인하" in name and delta < -5:
        flag = f"금리 인하인데 {delta:+.2f}% 하락"
    elif "금리 인상" in name and delta > 5:
        flag = f"금리 인상인데 {delta:+.2f}% 상승"
    elif "수출 급증" in name and delta < -5:
        flag = f"수출 급증인데 {delta:+.2f}% 하락"
    elif "수출 급감" in name and delta > 5:
        flag = f"수출 급감인데 {delta:+.2f}% 상승"
    if flag:
        print(f"  ⚠ {name} ({row['종목']}): {flag}")
        _counterintuitive_stat.append(f"{name}({row['종목']}): {flag}")

if not _counterintuitive_stat:
    print("  ✅ 모든 시나리오가 경제적 직관과 부합합니다.")
else:
    print(
        "\n참고: Ridge Regression은 학습 기간 내 선형 상관관계를 학습하므로,\n"
        "     경제적 인과와 다를 수 있습니다."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8-2. AI 해석 — 시나리오 분석

# COMMAND ----------

_sc_lines = ["[Ridge 시나리오 분석 결과]"]
for group, members in SCENARIO_GROUPS.items():
    _sc_lines.append(f"\n{group}:")
    for name in members:
        if name not in scenario_results_stat:
            continue
        for ticker in TICKERS:
            pred = scenario_results_stat[name][ticker]
            last_p = feature_marts[ticker]["close"].iloc[-1]
            chg = (pred - last_p) / last_p * 100
            _sc_lines.append(f"  {name} → {TICKER_NAMES[ticker]}: {chg:+.2f}%")

_sc_interp = ask_gpt(
    "\n".join(_sc_lines) + "\n\n위 Ridge Regression 시나리오 분석을 해석해 주세요:\n"
    "1) 각 시나리오 그룹별 핵심 시사점\n"
    "2) 가장 주의해야 할 리스크 시나리오\n"
    "3) 가장 유망한 기회 시나리오",
    max_tokens=800,
)
print("🤖 AI 해석 — 시나리오 분석")
print(_sc_interp)

# COMMAND ----------

# MAGIC %md
# MAGIC # 9. Feature Attribution (Ridge 계수 + Permutation Importance)
# MAGIC
# MAGIC > TimesFM Leave-One-Out Attribution (§9)에 대응

# COMMAND ----------

# (1) Ridge 표준화 계수 기반 기여도
attribution_ridge = {}
attribution_per_ticker_stat = {}

for ticker in TICKERS:
    scaler, feat_cols = ridge_scalers[ticker]
    ridge = ridge_models[ticker]
    importance = dict(zip(feat_cols, np.abs(ridge.coef_)))
    attribution_per_ticker_stat[ticker] = importance
    for col, val in importance.items():
        attribution_ridge[col] = attribution_ridge.get(col, 0) + val

sorted_attr_stat = sorted(attribution_ridge.items(), key=lambda x: x[1], reverse=True)
top_n = min(15, len(sorted_attr_stat))

print(f"\n[Ridge Coefficient Attribution] Top {top_n}:")
for rank, (name, score) in enumerate(sorted_attr_stat[:top_n], 1):
    print(f"  {rank}. {name}: {score:.4f}")

# (2) Permutation Importance
print("\n[Permutation Importance] (Ridge, 10 repeats):")
for ticker in TICKERS:
    mart = feature_marts[ticker].copy()
    scaler, feat_cols = ridge_scalers[ticker]
    ridge = ridge_models[ticker]

    mart["target"] = mart["close"].shift(-HORIZON)
    mart_clean = mart.dropna(subset=["target"])
    X = scaler.transform(mart_clean[feat_cols].fillna(0).values)
    y = mart_clean["target"].values

    perm = permutation_importance(
        ridge, X, y, n_repeats=10, random_state=42, scoring="neg_mean_absolute_error"
    )
    perm_sorted = sorted(zip(feat_cols, perm.importances_mean), key=lambda x: x[1], reverse=True)

    print(f"\n  {TICKER_NAMES[ticker]} Top 10:")
    for rank, (name, score) in enumerate(perm_sorted[:10], 1):
        print(f"    {rank}. {name}: {score:.4f}")

# COMMAND ----------

# 종목별 Ridge Attribution 시각화
fig, axes = plt.subplots(1, len(TICKERS), figsize=(9 * len(TICKERS), 6))
if len(TICKERS) == 1:
    axes = [axes]
for idx, ticker in enumerate(TICKERS):
    ax = axes[idx]
    sorted_t = sorted(attribution_per_ticker_stat[ticker].items(), key=lambda x: x[1], reverse=True)
    names = [a[0] for a in sorted_t[:top_n]]
    scores = [a[1] for a in sorted_t[:top_n]]
    ax.barh(range(top_n), scores[::-1], color="steelblue", alpha=0.8)
    ax.set_yticks(range(top_n))
    ax.set_yticklabels(names[::-1], fontsize=8)
    ax.set_xlabel("Ridge |coefficient|")
    ax.set_title(f"{TICKER_NAMES[ticker]} Feature Attribution (Ridge)", fontsize=12)
    ax.grid(True, alpha=0.3, axis="x")
plt.tight_layout()
plt.savefig("/tmp/stat_attribution_per_ticker.png", dpi=150)
plt.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9-1. AI 해석 — Feature Attribution

# COMMAND ----------

_attr_lines = ["[Ridge Feature Attribution 결과]"]
for ticker in TICKERS:
    sorted_t = sorted(attribution_per_ticker_stat[ticker].items(), key=lambda x: x[1], reverse=True)
    _attr_lines.append(f"\n{TICKER_NAMES[ticker]} Top 5:")
    for rank, (name, score) in enumerate(sorted_t[:5], 1):
        _attr_lines.append(f"  {rank}. {name}: {score:.4f}")

_attr_interp = ask_gpt(
    "\n".join(_attr_lines)
    + "\n\n위 Ridge Regression 계수 기반 Feature Attribution을 분석해 주세요:\n"
    "1) 가장 영향력 있는 변수의 경제적 의미\n"
    "2) 종목 간 차이 해석\n"
    "3) 변수 선택 개선 제안",
    max_tokens=600,
)
print("🤖 AI 해석 — Feature Attribution")
print(_attr_interp)

# COMMAND ----------

# MAGIC %md
# MAGIC # 10. Rolling Window Backtest (Multi-horizon)
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §10 과 **동일 프레임워크**
# MAGIC > (BACKTEST_HORIZONS = [5, 10, 20], STEP=5, TEST_WINDOW=60)

# COMMAND ----------

from statsmodels.tsa.ar_model import AutoReg  # noqa: E402

BACKTEST_HORIZONS = [5, 10, 20]
STEP = 5
TEST_WINDOW = 60
N_BOOT = 200  # bootstrap PI 반복 횟수

backtest_results_stat = []
for horizon_eval in BACKTEST_HORIZONS:
    for ticker in TICKERS:
        mart = feature_marts[ticker]
        close_series = mart["close"].values
        feat_cols_t = numerical_cols[ticker]
        X_all = mart[feat_cols_t].fillna(0).values
        n = len(close_series)

        for start in range(n - TEST_WINDOW, n - horizon_eval, STEP):
            if start < 30:
                continue
            actual = close_series[start : start + horizon_eval]
            if len(actual) < horizon_eval:
                continue

            # --- VAR Baseline --- (AutoReg 다단계 예측으로 교체)
            train_close = close_series[:start]
            try:
                ar_lag = min(optimal_lag, max(1, len(train_close) // 10))
                ar_model_bt = AutoReg(train_close, lags=ar_lag).fit()
                var_pred = ar_model_bt.forecast(steps=horizon_eval)
            except Exception:
                # fallback: random walk (drift)
                drift = np.mean(np.diff(train_close[-20:])) if len(train_close) >= 21 else 0
                var_pred = np.array(
                    [train_close[-1] + drift * (i + 1) for i in range(horizon_eval)]
                )

            # --- Ridge ---
            y_train_bt = close_series[horizon_eval : start + horizon_eval]
            X_train_bt = X_all[:start]
            if len(y_train_bt) < len(X_train_bt):
                X_train_bt = X_train_bt[: len(y_train_bt)]
            if len(X_train_bt) < 10:
                continue

            scaler_bt = StandardScaler()
            X_train_s = scaler_bt.fit_transform(X_train_bt)
            ridge_bt = Ridge(alpha=100.0)
            ridge_bt.fit(X_train_s, y_train_bt)

            X_test_s = scaler_bt.transform(X_all[start : start + 1])
            ridge_pred_val = ridge_bt.predict(X_test_s)[0]
            ridge_pred_arr = np.linspace(close_series[start - 1], ridge_pred_val, horizon_eval)

            # Metrics
            mae_var = np.mean(np.abs(actual - var_pred[: len(actual)]))
            mape_var = np.mean(np.abs((actual - var_pred[: len(actual)]) / actual)) * 100
            mae_ridge = np.mean(np.abs(actual - ridge_pred_arr[: len(actual)]))
            mape_ridge = np.mean(np.abs((actual - ridge_pred_arr[: len(actual)]) / actual)) * 100

            # PI: Bootstrap 잔차 기반 80% 예측 구간
            train_resid = y_train_bt - ridge_bt.predict(X_train_s)
            rng = np.random.default_rng(42)
            boot_preds = np.array(
                [ridge_pred_arr + rng.choice(train_resid, size=horizon_eval) for _ in range(N_BOOT)]
            )
            pi_lo = np.percentile(boot_preds, 10, axis=0)
            pi_hi = np.percentile(boot_preds, 90, axis=0)
            coverage = np.mean((actual >= pi_lo[: len(actual)]) & (actual <= pi_hi[: len(actual)]))

            # Direction: step-wise (TimesFM 동일)
            actual_dir = np.sign(np.diff(actual))
            pred_dir = np.sign(np.diff(ridge_pred_arr))
            min_dir_len = min(len(actual_dir), len(pred_dir))
            dir_acc = (
                float(np.mean(actual_dir[:min_dir_len] == pred_dir[:min_dir_len]))
                if min_dir_len > 0
                else 0.0
            )

            backtest_results_stat.append(
                {
                    "ticker": ticker,
                    "horizon": horizon_eval,
                    "window_start": start,
                    "mae_var": mae_var,
                    "mape_var": mape_var,
                    "mae_ridge": mae_ridge,
                    "mape_ridge": mape_ridge,
                    "coverage_80": coverage,
                    "directional_accuracy": dir_acc,
                }
            )

df_backtest_stat = pd.DataFrame(backtest_results_stat)
if not df_backtest_stat.empty:
    print("Rolling Window Backtest 결과 (전통적 모델):")
    for h in BACKTEST_HORIZONS:
        print(f"\n[{h}d Horizon]")
        for ticker in TICKERS:
            sub = df_backtest_stat[
                (df_backtest_stat["ticker"] == ticker) & (df_backtest_stat["horizon"] == h)
            ]
            if sub.empty:
                continue
            cov = sub["coverage_80"].mean()
            da = sub["directional_accuracy"].mean()
            cov_flag = "✅" if cov >= 0.75 else "⚠️"
            da_flag = "✅" if da >= 0.55 else "⚠️"
            print(
                f"  {TICKER_NAMES[ticker]}: "
                f"VAR MAE={sub['mae_var'].mean():,.0f} MAPE={sub['mape_var'].mean():.2f}% | "
                f"Ridge MAE={sub['mae_ridge'].mean():,.0f} MAPE={sub['mape_ridge'].mean():.2f}% | "
                f"Coverage={cov:.1%} {cov_flag} | Direction={da:.1%} {da_flag}"
            )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10-1. Conformal PI Calibration
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §10-1 동일

# COMMAND ----------

conformal_factors_stat = {}
for ticker in TICKERS:
    sub = df_backtest_stat[
        (df_backtest_stat["ticker"] == ticker) & (df_backtest_stat["horizon"] == 20)
    ]
    if sub.empty:
        continue
    actual_coverage = sub["coverage_80"].mean()
    target = 0.80
    print(f"\n{TICKER_NAMES[ticker]}:")
    print(f"  현재 Coverage: {actual_coverage:.1%}")
    if actual_coverage < target:
        expansion = target / max(actual_coverage, 0.01)
        conformal_factors_stat[ticker] = expansion
        print(f"  PI 확장 필요: ×{expansion:.2f}")
    else:
        conformal_factors_stat[ticker] = 1.0
        print("  ✅ 목표 달성")

# COMMAND ----------

# MAGIC %md
# MAGIC # 11. Anomaly Detection (Ridge 잔차 기반)
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §11 대응 — Ridge 잔차의 z-score 기반

# COMMAND ----------

anomaly_records_stat = []
for ticker in TICKERS:
    mart = feature_marts[ticker]
    scaler, feat_cols = ridge_scalers[ticker]
    ridge = ridge_models[ticker]

    X_all = scaler.transform(mart[feat_cols].fillna(0).values[:-HORIZON])
    y_actual = mart["close"].values[HORIZON:]
    min_len = min(len(X_all), len(y_actual))
    X_all, y_actual = X_all[:min_len], y_actual[:min_len]

    y_pred = ridge.predict(X_all)
    residuals = y_actual - y_pred
    mu, sigma = np.mean(residuals), np.std(residuals)

    for j, r in enumerate(residuals[-20:]):
        z = (r - mu) / sigma if sigma > 0 else 0
        if abs(z) > 2.0:
            anomaly_records_stat.append(
                {
                    "ticker": ticker,
                    "offset": j - 20,
                    "residual": r,
                    "z_score": z,
                }
            )

if anomaly_records_stat:
    print(f"⚠️ 이상 감지: {len(anomaly_records_stat)}건")
    for a in anomaly_records_stat[:10]:
        print(f"  [{TICKER_NAMES[a['ticker']]}] T{a['offset']:+d}: z={a['z_score']:+.2f}")
else:
    print("✅ 최근 구간에서 이상 이벤트 없음")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11-1. 잔차 분포 분석
# MAGIC
# MAGIC > `timesfm_inference_0411.py` §10-2 대응

# COMMAND ----------

for ticker in TICKERS:
    mart = feature_marts[ticker]
    scaler, feat_cols = ridge_scalers[ticker]
    ridge = ridge_models[ticker]

    X_all = scaler.transform(mart[feat_cols].fillna(0).values[:-HORIZON])
    y_actual = mart["close"].values[HORIZON:]
    min_len = min(len(X_all), len(y_actual))
    y_pred = ridge.predict(X_all[:min_len])
    residuals = y_actual[:min_len] - y_pred
    mape_dist = np.abs(residuals / y_actual[:min_len]) * 100

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(residuals, bins=30, color="steelblue", alpha=0.7, edgecolor="white")
    axes[0].axvline(0, color="red", linestyle="--")
    axes[0].set_title(f"{TICKER_NAMES[ticker]} Ridge 잔차 분포")
    axes[0].set_xlabel("잔차 (원)")

    axes[1].hist(mape_dist, bins=30, color="coral", alpha=0.7, edgecolor="white")
    axes[1].axvline(
        np.median(mape_dist),
        color="red",
        linestyle="--",
        label=f"median={np.median(mape_dist):.1f}%",
    )
    axes[1].set_title(f"{TICKER_NAMES[ticker]} MAPE 분포")
    axes[1].set_xlabel("MAPE (%)")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(f"/tmp/stat_residual_{ticker}.png", dpi=150)
    plt.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11-2. VaR/CVaR 리스크 지표 (Ridge 잔차 기반)
# MAGIC
# MAGIC > `timesfm_inference.py` §11-1 대응 — Ridge 잔차 분포로부터
# MAGIC > Value-at-Risk 및 Conditional VaR 산출

# COMMAND ----------

print("VaR/CVaR 리스크 지표 (Ridge 잔차 기반)")
print("=" * 60)

for ticker in TICKERS:
    mart = feature_marts[ticker]
    scaler, feat_cols = ridge_scalers[ticker]
    ridge = ridge_models[ticker]
    last_price = mart["close"].iloc[-1]

    X_all = scaler.transform(mart[feat_cols].fillna(0).values[:-HORIZON])
    y_actual = mart["close"].values[HORIZON:]
    min_len = min(len(X_all), len(y_actual))
    y_pred = ridge.predict(X_all[:min_len])
    residuals = y_actual[:min_len] - y_pred

    # 잔차 → 수익률 잔차로 변환 (% 기준)
    pct_residuals = residuals / y_actual[:min_len] * 100

    print(f"\n{TICKER_NAMES[ticker]}:")
    for h_label, h_days in [("T+5", 5), ("T+10", 10), ("T+20", 20)]:
        # √t 스케일링으로 다중 호라이즌 VaR 추정
        scale = np.sqrt(h_days)
        var_10 = np.percentile(pct_residuals, 10) * scale
        cvar_10 = np.mean(pct_residuals[pct_residuals <= np.percentile(pct_residuals, 10)]) * scale
        print(f"  [{h_label}] VaR(10%): {var_10:+.2f}% | CVaR(10%): {cvar_10:+.2f}%")

    # Conformal 보정 VaR
    if ticker in conformal_factors_stat and conformal_factors_stat[ticker] > 1.0:
        cf = conformal_factors_stat[ticker]
        scale_20 = np.sqrt(20)
        var_cal = np.percentile(pct_residuals, 10) * scale_20 * cf
        print(f"  [T+20] Conformal VaR(10%): {var_cal:+.2f}% (보정 ×{cf:.2f})")

# COMMAND ----------

# MAGIC %md
# MAGIC # 12. Granger Causality Tests
# MAGIC
# MAGIC > 전통적 통계 분석 고유 섹션: 주요 피처 → close 간 인과 검정

# COMMAND ----------

_granger_features = [
    "semi_total_exp",
    "semi_dram_exp",
    "usd_krw_rate",
    "kfin_mean_price",
    "export_optimism_index",
]

print("Granger Causality Tests (피처 → close, maxlag=5):")
for ticker in TICKERS:
    mart = feature_marts[ticker]
    print(f"\n{TICKER_NAMES[ticker]}:")
    for feat in _granger_features:
        if feat not in mart.columns:
            continue
        test_data = mart[["close", feat]].dropna()
        if len(test_data) < 20:
            continue
        try:
            result = grangercausalitytests(test_data.values, maxlag=5, verbose=False)
            min_p = min(result[lag][0]["ssr_ftest"][1] for lag in result)
            sig = "✅ 유의" if min_p < 0.05 else "❌ 미유의"
            print(f"  {feat} → close: min p={min_p:.4f} {sig}")
        except Exception as e:
            print(f"  {feat}: 검정 실패 ({e})")

# COMMAND ----------

# MAGIC %md
# MAGIC # 13. 결과 PostgreSQL 적재
# MAGIC
# MAGIC > `fact_stat_forecast` 테이블 — `timesfm_inference_0411.py`의
# MAGIC > `fact_timesfm_forecast`와 동일 포맷

# COMMAND ----------

rows = []
run_ts = datetime.datetime.now()

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    mart = feature_marts[ticker]
    last_price = mart["close"].iloc[-1]
    last_date = mart["date"].iloc[-1]

    # VAR Baseline
    var_pred = var_forecast_df[name].iloc[-1]
    rows.append(
        {
            "ticker": ticker,
            "base_date": last_date,
            "horizon": HORIZON,
            "model": "VAR",
            "model_type": "baseline",
            "prediction": round(float(var_pred), 2),
            "change_pct": round((var_pred - last_price) / last_price * 100, 4),
            "scenario": "현상 유지",
            "run_timestamp": run_ts,
        }
    )

    # Ridge Covariate
    ridge_pred = ridge_predictions[ticker]
    rows.append(
        {
            "ticker": ticker,
            "base_date": last_date,
            "horizon": HORIZON,
            "model": "Ridge",
            "model_type": "covariate",
            "prediction": round(float(ridge_pred), 2),
            "change_pct": round((ridge_pred - last_price) / last_price * 100, 4),
            "scenario": "현상 유지",
            "run_timestamp": run_ts,
        }
    )

    # 시나리오별 Ridge
    for sc_name, preds in scenario_results_stat.items():
        rows.append(
            {
                "ticker": ticker,
                "base_date": last_date,
                "horizon": HORIZON,
                "model": "Ridge",
                "model_type": "scenario",
                "prediction": round(float(preds[ticker]), 2),
                "change_pct": round((preds[ticker] - last_price) / last_price * 100, 4),
                "scenario": sc_name,
                "run_timestamp": run_ts,
            }
        )

df_output_stat = pd.DataFrame(rows)
print(f"PostgreSQL 적재 대상: {len(df_output_stat)}행")
display(df_output_stat.head(10))  # noqa: F821

try:
    engine = vault.get_pg_connection("sqlalchemy")
    df_output_stat.to_sql(
        "fact_stat_forecast", engine, schema="public", if_exists="append", index=False
    )
    print(f"✅ fact_stat_forecast 적재 완료: {len(df_output_stat)}행")
except Exception as e:
    print(f"⚠️ PostgreSQL 적재 실패 (오프라인 모드): {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 14. 실행 결과 요약

# COMMAND ----------

print("=" * 70)
print("SENSE × 전통적 통계 분석 — 결과 요약")
print("=" * 70)

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    mart = feature_marts[ticker]
    last_price = mart["close"].iloc[-1]
    var_pred = var_forecast_df[name].iloc[-1]
    ridge_pred = ridge_predictions[ticker]

    print(f"\n{'─' * 50}")
    print(f"📊 {name} ({ticker})")
    print(f"  현재가:              {last_price:>12,.0f}")
    print(
        f"  VAR T+{HORIZON}:         {var_pred:>12,.0f}  "
        f"({(var_pred - last_price) / last_price * 100:+.2f}%)"
    )
    print(
        f"  Ridge T+{HORIZON}:       {ridge_pred:>12,.0f}  "
        f"({(ridge_pred - last_price) / last_price * 100:+.2f}%)"
    )

    # 멀티 호라이즌 Backtest
    for h in BACKTEST_HORIZONS:
        bt = df_backtest_stat[
            (df_backtest_stat["ticker"] == ticker) & (df_backtest_stat["horizon"] == h)
        ]
        if bt.empty:
            continue
        cov = bt["coverage_80"].mean()
        da = bt["directional_accuracy"].mean()
        cov_flag = "✅" if cov >= 0.75 else "⚠️"
        da_flag = "✅" if da >= 0.55 else "⚠️"
        print(
            f"  [{h}d] Ridge MAE: {bt['mae_ridge'].mean():>10,.0f} | "
            f"Coverage: {cov:>5.1%} {cov_flag} | Direction: {da:>5.1%} {da_flag}"
        )

    # Top 3 Attribution
    sorted_t = sorted(attribution_per_ticker_stat[ticker].items(), key=lambda x: x[1], reverse=True)
    print(f"  Top 3 영향 변수:     {', '.join([a[0] for a in sorted_t[:3]])}")

# 시나리오 요약
print(f"\n{'─' * 50}")
print(f"📋 시나리오 분석 결과 ({len(SCENARIOS)}개):")
_sc_avg = {}
_base_preds_stat = scenario_results_stat.get("현상 유지", {})
for name in SCENARIOS:
    if name == "현상 유지":
        continue
    _sc_avg[name] = np.mean(
        [
            (
                scenario_results_stat[name][t]
                - _base_preds_stat.get(t, feature_marts[t]["close"].iloc[-1])
            )
            / abs(_base_preds_stat.get(t, feature_marts[t]["close"].iloc[-1]))
            * 100
            for t in TICKERS
        ]
    )
_best_name = max(_sc_avg, key=_sc_avg.get)
_worst_name = min(_sc_avg, key=_sc_avg.get)

for group, members in SCENARIO_GROUPS.items():
    print(f"\n  ── {group} ──")
    for name in members:
        if name not in scenario_results_stat:
            continue
        parts = []
        for ticker in TICKERS:
            pred = scenario_results_stat[name][ticker]
            base_p = _base_preds_stat.get(ticker, feature_marts[ticker]["close"].iloc[-1])
            chg = (pred - base_p) / abs(base_p) * 100
            parts.append(f"{TICKER_NAMES[ticker]}: {chg:+.2f}%")
        tag = " ← 최선" if name == _best_name else (" ← 최악" if name == _worst_name else "")
        print(f"    [{name}] {' | '.join(parts)}{tag}")

if anomaly_records_stat:
    print(f"\n⚠️ 이상 이벤트: {len(anomaly_records_stat)}건 감지됨")
else:
    print("\n✅ 이상 이벤트: 없음")

print(f"\n{'=' * 70}")
print("비교 대상: timesfm_inference_0411.py (TimesFM 2.5)")
print("다음 단계: 두 파이프라인 결과 교차 비교 → Consensus 판정")

# COMMAND ----------

# MAGIC %md
# MAGIC # 15. AI 종합 분석 의견

# COMMAND ----------

_final_lines = [
    "SENSE 전통적 통계 분석 종합 요약:\n",
    f"분석 대상: {', '.join(f'{TICKER_NAMES[t]}({t})' for t in TICKERS)}",
    f"분석 방법: VAR(p={optimal_lag}) Baseline + Ridge Regression Covariate",
    f"예측 기간: 향후 {HORIZON} 거래일\n",
]

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    lp = feature_marts[ticker]["close"].iloc[-1]
    var_p = var_forecast_df[name].iloc[-1]
    ridge_p = ridge_predictions[ticker]
    _final_lines.append(
        f"[{name}] VAR: {(var_p - lp) / lp * 100:+.2f}% | "
        f"Ridge: {(ridge_p - lp) / lp * 100:+.2f}% | "
        f"Δ: {(ridge_p - var_p) / lp * 100:+.2f}%"
    )

_final_lines.append(f"\n핵심 영향 변수 Top 3: {', '.join([a[0] for a in sorted_attr_stat[:3]])}")
_final_lines.append(f"\n최선 시나리오: [{_best_name}] 평균 {_sc_avg[_best_name]:+.2f}%")
_final_lines.append(f"최악 시나리오: [{_worst_name}] 평균 {_sc_avg[_worst_name]:+.2f}%")

# Backtest
if not df_backtest_stat.empty:
    _final_lines.append("\n[Backtest 품질 평가]")
    for ticker in TICKERS:
        for h in BACKTEST_HORIZONS:
            sub = df_backtest_stat[
                (df_backtest_stat["ticker"] == ticker) & (df_backtest_stat["horizon"] == h)
            ]
            if not sub.empty:
                cov = sub["coverage_80"].mean()
                da = sub["directional_accuracy"].mean()
                cov_warn = " ⚠️신뢰구간 부족" if cov < 0.75 else ""
                da_warn = " ⚠️방향성 미달" if da < 0.55 else ""
                _final_lines.append(
                    f"  [{TICKER_NAMES[ticker]} {h}d] Ridge MAE={sub['mae_ridge'].mean():,.0f} | "
                    f"Coverage={cov:.1%}{cov_warn} | Direction={da:.1%}{da_warn}"
                )

_final_prompt = (
    "\n".join(_final_lines)
    + "\n\n위 전통적 통계 분석 결과를 종합하여 다음 형식으로 의견을 작성해 주세요:\n\n"
    "★ 종합 시장 진단 (2문장)\n"
    "★ 삼성전자 분석 의견 (2문장)\n"
    "★ SK하이닉스 분석 의견 (2문장)\n"
    "★ VAR vs Ridge 모델 비교 시사점 (2문장)\n"
    "★ 핵심 리스크 요인 (3가지)\n"
    "★ 핵심 기회 요인 (3가지)\n"
    "★ TimesFM 딥러닝 모델과 비교 시 참고사항 (2문장)\n"
    "★ 단기 모니터링 포인트 (3가지)\n\n"
    "한국어로, 전문 보고서체로 작성하세요. "
    "마지막에 투자 책임 면책 문구 1줄 추가."
)

_final_interp = ask_gpt(_final_prompt, max_tokens=1500)
print("=" * 70)
print("🤖 AI 종합 분석 의견 (SENSE × VAR/Ridge × GPT-4.1-mini)")
print("=" * 70)
print(_final_interp)
print(f"\n{'=' * 70}")
