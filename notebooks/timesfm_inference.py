# Databricks notebook source
# SENSE 프로젝트 — TimesFM 2.5 시계열 예측 노트북
# SENSE: Semiconductor Economic News & Sentiment Engine
#
# 목적: TimesFM 2.5를 활용한 반도체 주가 시계열 예측
#       Step 1 — Zero-shot Baseline (주가만)
#       Step 2 — XReg 공변량 추론 (매크로/퀀트/감성)
#       Step 3 — 매크로 충격 정량화 + 시나리오 분석 + Backtest
#
# 실행 환경: Databricks GPU 클러스터 권장 (Standard_NC6s_v3 이상)
#           CPU에서도 동작하나 배치 추론 시 느림
#
# 전략 문서: ref/TimesFM.md
# 데이터 사전: docs/data_dict/

# COMMAND ----------

# MAGIC %md
# MAGIC # 0. 환경 설정 및 패키지 설치

# COMMAND ----------

# MAGIC %pip install timesfm[torch,xreg] openai --quiet

# COMMAND ----------

import os
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch

warnings.filterwarnings("ignore", category=FutureWarning)

REPO_PATH = "/Workspace/Repos/{your-email}/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"

# COMMAND ----------

# MAGIC %md
# MAGIC # 1. ADLS Gen2 연결 및 데이터 로드

# COMMAND ----------

from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()
vault.get_storage_client()  # Spark OAuth conf 자동 설정
account = vault.get_secret("adls-account-name")  # "3dtteam1adls"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0-1. Azure OpenAI 클라이언트 초기화

# COMMAND ----------

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
    "당신은 반도체 주식 시장 전문 퀀트 애널리스트입니다. "
    "TimesFM 시계열 예측 결과를 바탕으로 한국어로 간결하고 "
    "전문적인 투자 인사이트를 제공합니다. "
    "수치 근거를 반드시 포함하고, 리스크도 균형있게 언급하세요."
)


def ask_gpt(prompt: str, system_msg: str | None = None, max_tokens: int = 1200) -> str:
    """Azure OpenAI GPT에 프롬프트를 보내고 응답 문자열을 반환합니다."""
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = openai_client.chat.completions.create(
            model=OPENAI_DEPLOYMENT,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        return f"[OpenAI 오류] {e}"


print(f"Azure OpenAI 연결 완료 | 엔드포인트: {_openai_endpoint} | 배포: {OPENAI_DEPLOYMENT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1-1. 타겟 시계열 — 주가 OHLCV

# COMMAND ----------

TICKERS = ["005930.KS", "000660.KS"]
TICKER_NAMES = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스"}
HORIZON = 20  # 향후 20 거래일 (약 4주)

# ---------------------------------------------------------------------------
# ADLS 경로 헬퍼 — 경로가 아직 적재되지 않았을 경우 빈 DataFrame 반환
# ---------------------------------------------------------------------------
from pyspark.sql.utils import AnalysisException  # noqa: E402


def safe_read_parquet(path: str, date_col: str | None = None, index_col: str | None = None):
    """
    ADLS parquet을 읽습니다.
    경로가 없거나 미적재 상태면 경고 후 빈 DataFrame을 반환합니다.
    - date_col  : pd.to_datetime() 변환할 컬럼명
    - index_col : set_index()할 컬럼명
    """
    try:
        df = spark.read.parquet(path).toPandas()  # noqa: F821
        if date_col and date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col])
        if index_col and index_col in df.columns:
            df = df.set_index(index_col).sort_index()
        print(f"  [OK] {path.split('/')[-2] or path}: {len(df)} rows")
        return df
    except (AnalysisException, Exception) as e:  # noqa: BLE001
        print(f"  [SKIP] 경로 없음 또는 미적재 — {path}\n         ({type(e).__name__})")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 1-1. 타겟 시계열 — 주가 OHLCV
# ---------------------------------------------------------------------------
#  컨테이너: feature  /  경로: equity/ohlcv/
#  컬럼: ticker, trade_date, open, high, low, close, volume
equity_path = f"abfss://feature@{account}.dfs.core.windows.net/equity/ohlcv/"
_df_eq_raw = safe_read_parquet(equity_path, date_col="trade_date")

if _df_eq_raw.empty:
    # 데이터가 아직 없으면 curated 컨테이너에서도 시도
    equity_path_curated = f"abfss://curated@{account}.dfs.core.windows.net/equity/ohlcv/"
    _df_eq_raw = safe_read_parquet(equity_path_curated, date_col="trade_date")

df_equity = (
    _df_eq_raw[_df_eq_raw["ticker"].isin(TICKERS)]
    .sort_values(["ticker", "trade_date"])
    .reset_index(drop=True)
    if not _df_eq_raw.empty and "ticker" in _df_eq_raw.columns
    else pd.DataFrame(columns=["ticker", "trade_date", "close"])
)

if not df_equity.empty:
    _start = df_equity["trade_date"].min()
    _end = df_equity["trade_date"].max()
    print(f"주가 데이터: {len(df_equity)} rows, 기간: {_start} ~ {_end}")
    for t in TICKERS:
        n = len(df_equity[df_equity["ticker"] == t])
        print(f"  {TICKER_NAMES[t]} ({t}): {n} 거래일")
else:
    print("[WARN] 주가 데이터 없음 — 이후 셀에서 오류 발생 가능")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1-2. 매크로 환경 지표

# COMMAND ----------

# --- FRED 금리 데이터 ---
#  컨테이너: feature  /  경로: macro/fred/
#  컬럼: observed_date, series_code, rate_value
fred_path = f"abfss://feature@{account}.dfs.core.windows.net/macro/fred/"
df_fred_raw = safe_read_parquet(fred_path, date_col="observed_date")

if not df_fred_raw.empty and "series_code" in df_fred_raw.columns:
    FRED_SERIES = ["DGS10", "DGS2", "T10Y2Y", "BAMLH0A0HYM2", "DFF", "DFII10"]
    df_fred = (
        df_fred_raw.pivot_table(index="observed_date", columns="series_code", values="rate_value")
        .sort_index()
        .ffill()
    )
else:
    df_fred = pd.DataFrame()

# --- Yahoo Finance 매크로 지표 (DXY, WTI, Gold, Copper) ---
#  컨테이너: feature  /  경로: macro/daily/
#  컬럼: trade_date, ticker, open, high, low, close, volume
macro_path = f"abfss://feature@{account}.dfs.core.windows.net/macro/daily/"
df_macro_raw = safe_read_parquet(macro_path, date_col="trade_date")

MACRO_TICKERS = {
    "DX-Y.NYB": "dxy",
    "CL=F": "wti",
    "GC=F": "gold",
    "HG=F": "copper",
}
if not df_macro_raw.empty and "ticker" in df_macro_raw.columns:
    df_macro = (
        df_macro_raw.pivot_table(index="trade_date", columns="ticker", values="close")
        .sort_index()
        .ffill()
    )
    df_macro.columns = [MACRO_TICKERS.get(c, c) for c in df_macro.columns]
else:
    df_macro = pd.DataFrame()

# --- 환율 USD/KRW ---
#  컨테이너: feature  /  경로: fx/usd_krw/
#  컬럼: trade_date, close  또는  trade_date, usd_krw
fx_path = f"abfss://feature@{account}.dfs.core.windows.net/fx/usd_krw/"
df_fx = safe_read_parquet(fx_path, date_col="trade_date", index_col="trade_date")
# 컬럼명 정규화: close → usd_krw
if not df_fx.empty and "close" in df_fx.columns and "usd_krw" not in df_fx.columns:
    df_fx = df_fx.rename(columns={"close": "usd_krw"})

print(
    f"FRED: {len(df_fred)} rows | Macro: {len(df_macro)} rows | FX: {len(df_fx)} rows"
    if not (df_fred.empty and df_macro.empty and df_fx.empty)
    else "[WARN] 매크로 데이터 모두 미적재"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1-3. 퀀트 선행 지표

# COMMAND ----------

# --- SOX 동조화 ---
#  컨테이너: feature  /  경로: quant/sox_sync/
#  컬럼: kr_effective_date, sox_return_1d, nvda_return_1d
sox_path = f"abfss://feature@{account}.dfs.core.windows.net/quant/sox_sync/"
df_sox = safe_read_parquet(sox_path, date_col="kr_effective_date", index_col="kr_effective_date")

# --- 메모리 기업 Proxy (MU + WDC 가중 수익률) ---
#  컨테이너: feature  /  경로: quant/memory_proxy/
#  컬럼: trade_date, memory_sentiment_index
memory_path = f"abfss://feature@{account}.dfs.core.windows.net/quant/memory_proxy/"
df_memory = safe_read_parquet(memory_path, date_col="trade_date", index_col="trade_date")

# --- PCR (Put/Call Ratio) ---
#  컨테이너: feature  /  경로: quant/pcr/
#  컬럼: trade_date, pcr_ratio
pcr_path = f"abfss://feature@{account}.dfs.core.windows.net/quant/pcr/"
df_pcr = safe_read_parquet(pcr_path, date_col="trade_date", index_col="trade_date")

# --- 관세청 수출 통계 (10일 주기 → 일별 Forward Fill) ---
#  컨테이너: feature  /  경로: quant/customs/
#  컬럼: trade_date, yoy_change_pct
customs_path = f"abfss://feature@{account}.dfs.core.windows.net/quant/customs/"
df_customs_raw = safe_read_parquet(customs_path, date_col="trade_date")

if not df_customs_raw.empty and "trade_date" in df_customs_raw.columns:
    df_customs = df_customs_raw.set_index("trade_date").sort_index()
    # 10일 주기 → 일별 Full Forward Fill
    if "yoy_change_pct" in df_customs.columns:
        all_dates = pd.date_range(df_customs.index.min(), df_customs.index.max(), freq="B")
        df_customs = df_customs.reindex(all_dates).ffill()
else:
    df_customs = pd.DataFrame()

print(
    f"SOX: {len(df_sox)} | Memory: {len(df_memory)}"
    f" | PCR: {len(df_pcr)} | Customs: {len(df_customs)}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1-4. 뉴스 감성 지표 (일별 집계)

# COMMAND ----------

# --- 뉴스 감성 일별 집계 ---
#  컨테이너: feature  /  경로: news/daily_sentiment/
#  컬럼: published_date, absa_daily_score, absa_supply_chain, absa_regulation, keyword_momentum_max
news_agg_path = f"abfss://feature@{account}.dfs.core.windows.net/news/daily_sentiment/"
df_news_agg = safe_read_parquet(
    news_agg_path, date_col="published_date", index_col="published_date"
)

print(f"뉴스 감성: {len(df_news_agg)} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. 통합 피처 마트 구성

# COMMAND ----------


def build_feature_mart(
    df_equity,
    ticker,
    df_fred,
    df_macro,
    df_fx,
    df_sox,
    df_memory,
    df_pcr,
    df_news_agg,
    df_customs=None,
):
    """종목별 통합 피처 마트를 date 기준으로 LEFT JOIN하여 구성합니다."""
    df = df_equity[df_equity["ticker"] == ticker][["trade_date", "close"]].copy()
    df = df.set_index("trade_date").sort_index()

    # 수익률 파생
    df["return_1d"] = df["close"].pct_change()

    # --- 매크로 환경 지표 ---
    if not df_fred.empty and "DGS10" in df_fred.columns:
        df = df.join(df_fred[["DGS10", "DGS2", "T10Y2Y", "BAMLH0A0HYM2"]], how="left")
    if not df_macro.empty:
        for col in ["dxy", "wti", "gold", "copper"]:
            if col in df_macro.columns:
                df = df.join(df_macro[[col]].rename(columns={col: f"{col}_close"}), how="left")
    if not df_fx.empty:
        if "usd_krw" in df_fx.columns:
            df = df.join(df_fx[["usd_krw"]], how="left")
        elif "close" in df_fx.columns:
            df = df.join(df_fx[["close"]].rename(columns={"close": "usd_krw"}), how="left")

    # --- 퀀트 선행 지표 ---
    if not df_sox.empty:
        sox_cols = [c for c in ["sox_return_1d", "nvda_return_1d"] if c in df_sox.columns]
        if sox_cols:
            df = df.join(df_sox[sox_cols], how="left")
    if not df_memory.empty and "memory_sentiment_index" in df_memory.columns:
        df = df.join(df_memory[["memory_sentiment_index"]], how="left")
    if not df_pcr.empty and "pcr_ratio" in df_pcr.columns:
        df = df.join(df_pcr[["pcr_ratio"]], how="left")

    # --- 관세청 수출 (10일 주기 → 일별 Forward Fill 완료 상태로 입력) ---
    if df_customs is not None and not df_customs.empty and "yoy_change_pct" in df_customs.columns:
        df = df.join(
            df_customs[["yoy_change_pct"]].rename(columns={"yoy_change_pct": "customs_yoy_pct"}),
            how="left",
        )
        df["customs_yoy_pct"] = df["customs_yoy_pct"].ffill()

    # --- 뉴스 감성 ---
    if not df_news_agg.empty:
        news_cols = [
            c
            for c in [
                "absa_daily_score",
                "absa_supply_chain",
                "absa_regulation",
                "keyword_momentum_max",
            ]
            if c in df_news_agg.columns
        ]
        if news_cols:
            df = df.join(df_news_agg[news_cols], how="left")

    # Forward fill 후 첫 행 NaN 제거
    df = df.ffill().bfill()

    return df


# 종목별 피처 마트 생성
feature_marts = {}
for ticker in TICKERS:
    feature_marts[ticker] = build_feature_mart(
        df_equity,
        ticker,
        df_fred,
        df_macro,
        df_fx,
        df_sox,
        df_memory,
        df_pcr,
        df_news_agg,
        df_customs=df_customs,
    )
    print(f"{TICKER_NAMES[ticker]}: {feature_marts[ticker].shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. 교차 검증 파생 변수 생성

# COMMAND ----------


def create_derived_features(df):
    """SENSE 3축 교차 검증 파생 변수 + 시차/변동성 피처를 생성합니다."""
    out = df.copy()

    # --- 교호 작용 파생 변수 (Interaction Features) ---

    # 환경 × 심리: 달러 강세인데 뉴스 긍정 → 시장 과열 경고
    if "dxy_close" in out.columns and "absa_daily_score" in out.columns:
        dxy_ret_5d = out["dxy_close"].pct_change(5)
        dxy_zscore = (dxy_ret_5d - dxy_ret_5d.rolling(20).mean()) / dxy_ret_5d.rolling(
            20
        ).std().replace(0, np.nan)
        out["macro_sentiment_divergence"] = dxy_zscore.fillna(0) - out["absa_daily_score"].fillna(0)

    # 선행 × 심리: SOX 방향과 뉴스 감성 방향 일치 여부
    if "sox_return_1d" in out.columns and "absa_daily_score" in out.columns:
        out["sox_news_confirm"] = np.sign(out["sox_return_1d"]) * np.sign(out["absa_daily_score"])

    # 환경 × 선행: 금리역전 × 메모리주 하락 = 복합 위기
    if "T10Y2Y" in out.columns and "memory_sentiment_index" in out.columns:
        out["rate_memory_cross"] = out["T10Y2Y"] * out["memory_sentiment_index"]

    # 선행 × 선행: PCR × 수출 동반 하방
    if "pcr_ratio" in out.columns:
        out["pcr_customs_momentum"] = out["pcr_ratio"]  # customs는 10일 주기라 추후 join

    # 환경 × 환경: 금/구리 비율 — Risk-off 강도
    if "gold_close" in out.columns and "copper_close" in out.columns:
        out["gold_copper_ratio"] = out["gold_close"] / out["copper_close"].replace(0, np.nan)

    # 환경 × 심리: 신용 스프레드 × 감성 악화 = 복합 불안
    if "BAMLH0A0HYM2" in out.columns and "absa_daily_score" in out.columns:
        out["vix_absa_compound"] = out["BAMLH0A0HYM2"] * (1 - out["absa_daily_score"].fillna(0))

    # --- 시차(Lag) 기반 피처 ---
    if "sox_return_1d" in out.columns:
        out["sox_lag1_return"] = out["sox_return_1d"].shift(1)

    if "DGS10" in out.columns:
        out["dgs10_delta_5d"] = out["DGS10"] - out["DGS10"].shift(5)

    if "absa_daily_score" in out.columns:
        out["absa_ma5"] = out["absa_daily_score"].rolling(5, min_periods=1).mean()

    if "memory_sentiment_index" in out.columns:
        out["memory_sentiment_ma5"] = out["memory_sentiment_index"].rolling(5, min_periods=1).mean()

    # --- 변동성 피처 ---
    out["realized_vol_5d"] = out["return_1d"].rolling(5, min_periods=1).std()
    out["realized_vol_20d"] = out["return_1d"].rolling(20, min_periods=1).std()
    out["vol_ratio"] = out["realized_vol_5d"] / out["realized_vol_20d"].replace(0, np.nan)
    out["gap_from_ma20"] = (out["close"] - out["close"].rolling(20).mean()) / out["close"].rolling(
        20
    ).mean()

    # NaN 정리
    out = out.ffill().bfill()

    return out


for ticker in TICKERS:
    feature_marts[ticker] = create_derived_features(feature_marts[ticker])
    print(f"{TICKER_NAMES[ticker]} 파생 변수 포함: {feature_marts[ticker].shape[1]} 컬럼")

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. TimesFM 2.5 모델 로드

# COMMAND ----------

import timesfm  # noqa: E402

torch.set_float32_matmul_precision("high")

model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
model.compile(
    timesfm.ForecastConfig(
        max_context=256,  # 1년 ≈ 250 거래일
        max_horizon=HORIZON,  # 20 거래일 예측
        normalize_inputs=True,  # 스케일 정규화 (필수)
        use_continuous_quantile_head=True,  # 분위수 예측 활성화
        force_flip_invariance=True,  # f(-x) = -f(x)
        infer_is_positive=False,  # 주가 수익률은 음수 가능
        fix_quantile_crossing=True,  # q10 ≤ q20 ≤ ... ≤ q90 보장
    )
)
print("TimesFM 2.5 모델 로드 완료")

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. Step 1 — Zero-shot Baseline 추론
# MAGIC
# MAGIC > 반도체 주가 종가 시계열만 입력 → 순수 가격 패턴 기반 예측

# COMMAND ----------

inputs = []
for ticker in TICKERS:
    series = feature_marts[ticker]["close"].values.astype(np.float32)
    inputs.append(series)

point_baseline, quantile_baseline = model.forecast(
    horizon=HORIZON,
    inputs=inputs,
)

print(f"Baseline point forecast shape: {point_baseline.shape}")
print(f"Baseline quantile forecast shape: {quantile_baseline.shape}")

for i, ticker in enumerate(TICKERS):
    last_price = inputs[i][-1]
    pred_final = point_baseline[i, -1]
    change_pct = (pred_final - last_price) / last_price * 100
    print(f"\n{TICKER_NAMES[ticker]}:")
    print(f"  현재가: {last_price:,.0f}")
    print(f"  {HORIZON}일 후 예측: {pred_final:,.0f} ({change_pct:+.2f}%)")
    print(f"  80% PI: [{quantile_baseline[i, -1, 1]:,.0f}, {quantile_baseline[i, -1, 9]:,.0f}]")

# COMMAND ----------

# MAGIC %md
# MAGIC # 6. Step 2 — XReg 공변량 추론
# MAGIC
# MAGIC > 매크로/퀀트/감성 지표를 외부 회귀 변수(External Regressors)로 추가.
# MAGIC > 모델 파라미터를 재학습하지 않고, 추론 시점에만 공변량을 참고합니다.

# COMMAND ----------


def prepare_covariate(series_values, total_len):
    """공변량 배열을 context + horizon 길이에 맞추고, 부족분은 마지막 값으로 패딩합니다."""
    values = np.asarray(series_values, dtype=np.float32)
    # NaN 제거
    mask = np.isfinite(values)
    if not mask.all():
        valid = values[mask]
        if len(valid) == 0:
            return np.zeros(total_len, dtype=np.float32)
        values = np.interp(np.arange(len(values)), np.where(mask)[0], valid).astype(np.float32)
    if len(values) < total_len:
        pad = np.full(total_len - len(values), values[-1], dtype=np.float32)
        values = np.concatenate([values, pad])
    return values[:total_len]


# 공변량으로 사용할 컬럼 목록 (타겟 'close' 및 파생 수익률 제외)
EXCLUDE_COLS = {"close", "return_1d"}

# 각 종목별 공변량을 구성
dynamic_numerical = {}
for col in feature_marts[TICKERS[0]].columns:
    if col in EXCLUDE_COLS:
        continue
    arrays = []
    for ticker in TICKERS:
        mart = feature_marts[ticker]
        context_len = len(mart)
        total_len = context_len + HORIZON
        arrays.append(prepare_covariate(mart[col].values, total_len))
    dynamic_numerical[col] = arrays

# 요일 카테고리 (0=월 ~ 4=금)
dynamic_categorical = {}
day_of_week_arrays = []
for ticker in TICKERS:
    mart = feature_marts[ticker]
    dates = mart.index
    dow = [str(d.weekday()) for d in dates]
    # 미래 요일: 마지막 거래일부터 비즈니스 데이 기준 생성
    future_dates = pd.bdate_range(dates[-1] + pd.Timedelta(days=1), periods=HORIZON)
    dow_future = [str(d.weekday()) for d in future_dates]
    day_of_week_arrays.append(dow + dow_future)
dynamic_categorical["day_of_week"] = day_of_week_arrays

# 종목 구분 (Static)
static_categorical = {"ticker": list(TICKERS)}

print(f"Dynamic numerical covariates: {len(dynamic_numerical)} 개")
print(f"  컬럼: {list(dynamic_numerical.keys())}")

# COMMAND ----------

# XReg 추론 — xreg_mode="xreg + timesfm"
# 매크로 영향을 선형 회귀로 먼저 반영 → 잔차를 TimesFM이 예측
point_xreg, quantile_xreg = model.forecast_with_covariates(
    inputs=inputs,
    dynamic_numerical_covariates=dynamic_numerical,
    dynamic_categorical_covariates=dynamic_categorical,
    static_categorical_covariates=static_categorical,
    xreg_mode="xreg + timesfm",
)

print(f"XReg point forecast shape: {point_xreg.shape}")

for i, ticker in enumerate(TICKERS):
    last_price = inputs[i][-1]
    pred_base = point_baseline[i, -1]
    pred_xreg = point_xreg[i, -1]
    delta = pred_xreg - pred_base
    print(f"\n{TICKER_NAMES[ticker]}:")
    print(f"  Baseline {HORIZON}일 예측: {pred_base:,.0f}")
    print(f"  XReg     {HORIZON}일 예측: {pred_xreg:,.0f}")
    print(f"  매크로 충격 (Δ): {delta:+,.0f} ({delta / last_price * 100:+.2f}%)")
    print(f"  XReg 80% PI: [{quantile_xreg[i, -1, 1]:,.0f}, {quantile_xreg[i, -1, 9]:,.0f}]")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6-1. AI 해석 — 예측 결과 (Zero-shot vs XReg)

# COMMAND ----------

# GPT-4.1-mini로 Step 1 + Step 2 예측 결과를 투자 관점에서 해석
_forecast_summary_lines = [
    f"SENSE TimesFM 2.5 모델 — 향후 {HORIZON} 거래일(약 4주) 주가 예측 결과입니다.\n",
]
for i, ticker in enumerate(TICKERS):
    lp = inputs[i][-1]
    b_fin = point_baseline[i, -1]
    x_fin = point_xreg[i, -1]
    delta = x_fin - b_fin
    b_pct = (b_fin - lp) / lp * 100
    x_pct = (x_fin - lp) / lp * 100
    d_pct = delta / lp * 100
    _forecast_summary_lines.append(
        f"[{TICKER_NAMES[ticker]} ({ticker})]\n"
        f"  현재가: {lp:,.0f}원\n"
        f"  Zero-shot Baseline T+{HORIZON}: {b_fin:,.0f}원 ({b_pct:+.2f}%)\n"
        f"  XReg(매크로반영) T+{HORIZON}: {x_fin:,.0f}원 ({x_pct:+.2f}%)\n"
        f"  매크로 충격 Δ: {delta:+,.0f}원 ({d_pct:+.2f}%) "
        f"→ {'매크로가 주가를 끌어올리는 방향' if delta > 0 else '매크로가 주가를 억누르는 방향'}\n"
        f"  XReg 80% PI: [{quantile_xreg[i, -1, 1]:,.0f}, {quantile_xreg[i, -1, 9]:,.0f}]원\n"
    )

_forecast_prompt = (
    "\n".join(_forecast_summary_lines) + "\n위 예측 결과를 바탕으로:\n"
    "1) 두 종목의 단기 방향성과 매크로 환경의 영향을 종합 해석해 주세요.\n"
    "2) Zero-shot과 XReg 차이(매크로 충격)의 의미를 설명해 주세요.\n"
    "3) 투자자가 주목해야 할 핵심 포인트 2~3가지를 제시해 주세요.\n"
    "답변은 한국어로, 300자 이내로 핵심만 간결하게 작성해 주세요."
)

_forecast_interpretation = ask_gpt(_forecast_prompt, system_msg=_SYSTEM_MSG, max_tokens=600)
print("=" * 70)
print("🤖 AI 해석 — 예측 결과")
print("=" * 70)
print(_forecast_interpretation)

# COMMAND ----------

# MAGIC %md
# MAGIC # 7. 매크로 충격 분석 및 시각화

# COMMAND ----------

fig, axes = plt.subplots(len(TICKERS), 1, figsize=(14, 5 * len(TICKERS)), sharex=True)
if len(TICKERS) == 1:
    axes = [axes]

for i, ticker in enumerate(TICKERS):
    ax = axes[i]
    context_len = len(inputs[i])
    context_x = np.arange(context_len)
    forecast_x = np.arange(context_len, context_len + HORIZON)

    # 최근 60일 + 예측
    show_from = max(0, context_len - 60)

    ax.plot(
        context_x[show_from:],
        inputs[i][show_from:],
        color="black",
        linewidth=1.5,
        label="실제 종가",
    )

    # Baseline
    ax.plot(
        forecast_x,
        point_baseline[i],
        color="tab:blue",
        linewidth=1.5,
        linestyle="--",
        label="Baseline (Zero-shot)",
    )
    ax.fill_between(
        forecast_x,
        quantile_baseline[i, :, 1],
        quantile_baseline[i, :, 9],
        alpha=0.15,
        color="tab:blue",
        label="Baseline 80% PI",
    )

    # XReg
    ax.plot(
        forecast_x, point_xreg[i], color="tab:orange", linewidth=1.5, label="XReg (매크로 반영)"
    )
    ax.fill_between(
        forecast_x,
        quantile_xreg[i, :, 1],
        quantile_xreg[i, :, 9],
        alpha=0.15,
        color="tab:orange",
        label="XReg 80% PI",
    )

    ax.axvline(x=context_len - 0.5, color="gray", linestyle=":", alpha=0.5)
    ax.set_title(f"{TICKER_NAMES[ticker]} ({ticker}) — {HORIZON}일 예측", fontsize=13)
    ax.set_ylabel("종가")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

plt.xlabel("거래일 인덱스")
plt.tight_layout()
plt.savefig("/tmp/timesfm_forecast_comparison.png", dpi=150)
plt.show()
print("시각화 저장: /tmp/timesfm_forecast_comparison.png")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7-1. 매크로 충격 타임라인

# COMMAND ----------

macro_impact = point_xreg - point_baseline

fig, axes = plt.subplots(len(TICKERS), 1, figsize=(14, 4 * len(TICKERS)), sharex=True)
if len(TICKERS) == 1:
    axes = [axes]

for i, ticker in enumerate(TICKERS):
    ax = axes[i]
    days = np.arange(1, HORIZON + 1)
    impact = macro_impact[i]
    colors = ["tab:red" if v < 0 else "tab:green" for v in impact]
    ax.bar(days, impact, color=colors, alpha=0.7)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_title(f"{TICKER_NAMES[ticker]} — 매크로 충격 (XReg − Baseline)", fontsize=12)
    ax.set_ylabel("충격 (원)")
    ax.grid(True, alpha=0.3, axis="y")

plt.xlabel("예측 일차 (T+n)")
plt.tight_layout()
plt.savefig("/tmp/timesfm_macro_impact.png", dpi=150)
plt.show()

# COMMAND ----------

# MAGIC %md
# MAGIC # 8. 시나리오 분석 (What-If Simulation)
# MAGIC
# MAGIC > 미래 공변량 값을 시나리오별로 교체하여 "만약 X가 발생하면?" 질문에 즉시 답변

# COMMAND ----------

# 현재 최신 값 가져오기
mart = feature_marts[TICKERS[0]]
current_vals = {col: mart[col].iloc[-1] for col in mart.columns}

SCENARIOS = {
    "금리 인하 (-50bp)": {
        "DGS10": current_vals.get("DGS10", 4.0) - 0.5,
        "T10Y2Y": current_vals.get("T10Y2Y", 0.0) + 0.3,
    },
    "현상 유지": {},  # 공변량 변경 없음
    "금리 인상 (+50bp)": {
        "DGS10": current_vals.get("DGS10", 4.0) + 0.5,
        "T10Y2Y": current_vals.get("T10Y2Y", 0.0) - 0.3,
    },
    "달러 급등 (+5%)": {
        "dxy_close": current_vals.get("dxy_close", 105.0) * 1.05,
        "usd_krw": current_vals.get("usd_krw", 1350.0) * 1.05,
    },
    "강달러 + 금리 인상": {
        "DGS10": current_vals.get("DGS10", 4.0) + 0.5,
        "dxy_close": current_vals.get("dxy_close", 105.0) * 1.05,
        "usd_krw": current_vals.get("usd_krw", 1350.0) * 1.05,
    },
}

scenario_results = {}

for scenario_name, overrides in SCENARIOS.items():
    scenario_covariates = {}
    for key, arrays in dynamic_numerical.items():
        modified_arrays = []
        for arr in arrays:
            new_arr = arr.copy()
            if key in overrides:
                context_len = len(inputs[0])
                new_arr[context_len:] = overrides[key]
            modified_arrays.append(new_arr)
        scenario_covariates[key] = modified_arrays

    point_sc, quantile_sc = model.forecast_with_covariates(
        inputs=inputs,
        dynamic_numerical_covariates=scenario_covariates,
        dynamic_categorical_covariates=dynamic_categorical,
        static_categorical_covariates=static_categorical,
        xreg_mode="xreg + timesfm",
    )
    scenario_results[scenario_name] = {"point": point_sc, "quantiles": quantile_sc}
    print(f"  ✅ {scenario_name}")

print(f"\n총 {len(scenario_results)} 시나리오 추론 완료")

# COMMAND ----------

# 시나리오별 최종 예측값 비교 테이블
rows = []
for scenario_name, result in scenario_results.items():
    for i, ticker in enumerate(TICKERS):
        last_price = inputs[i][-1]
        pred = result["point"][i, -1]
        change_pct = (pred - last_price) / last_price * 100
        rows.append(
            {
                "시나리오": scenario_name,
                "종목": TICKER_NAMES[ticker],
                "현재가": last_price,
                f"T+{HORIZON} 예측": pred,
                "변동률 (%)": round(change_pct, 2),
            }
        )

df_scenarios = pd.DataFrame(rows)
print(df_scenarios.to_string(index=False))

# COMMAND ----------

# 시나리오 Fan Chart
fig, axes = plt.subplots(1, len(TICKERS), figsize=(7 * len(TICKERS), 5))
if len(TICKERS) == 1:
    axes = [axes]

colors = ["tab:green", "tab:gray", "tab:red", "tab:purple", "tab:brown"]

for idx, ticker in enumerate(TICKERS):
    ax = axes[idx]
    forecast_x = np.arange(1, HORIZON + 1)

    for j, (name, result) in enumerate(scenario_results.items()):
        c = colors[j % len(colors)]
        ax.plot(forecast_x, result["point"][idx], label=name, color=c, linewidth=1.5)
        ax.fill_between(
            forecast_x,
            result["quantiles"][idx, :, 1],
            result["quantiles"][idx, :, 9],
            alpha=0.08,
            color=c,
        )

    ax.axhline(y=inputs[idx][-1], color="black", linestyle=":", alpha=0.5, label="현재가")
    ax.set_title(f"{TICKER_NAMES[ticker]} 시나리오 분석", fontsize=12)
    ax.set_xlabel(f"예측 일차 (T+1 ~ T+{HORIZON})")
    ax.set_ylabel("예측 종가")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig("/tmp/timesfm_scenario_analysis.png", dpi=150)
plt.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8-1. AI 해석 — 시나리오 분석

# COMMAND ----------

# GPT-4.1-mini로 시나리오별 결과를 경제적 맥락에서 해석
_scenario_lines = [
    f"반도체 주가 TimesFM 시나리오 분석 결과 (향후 {HORIZON} 거래일):\n",
]
for name in SCENARIOS:
    row_parts = []
    for i, ticker in enumerate(TICKERS):
        pred = scenario_results[name]["point"][i, -1]
        chg = (pred - inputs[i][-1]) / inputs[i][-1] * 100
        row_parts.append(f"{TICKER_NAMES[ticker]} {chg:+.2f}%")
    _scenario_lines.append(f"  [{name}]: {' | '.join(row_parts)}")

_scenario_prompt = (
    "\n".join(_scenario_lines) + "\n\n위 5가지 시나리오 분석 결과를 바탕으로:\n"
    "1) 각 시나리오가 반도체 주가에 미치는 영향을 경제적 논리와 함께 설명해 주세요.\n"
    "2) 가장 위험한 시나리오와 가장 유리한 시나리오를 특정하고 그 이유를 서술해 주세요.\n"
    "3) 현재 투자자가 헤지해야 할 시나리오 1가지를 추천해 주세요.\n"
    "답변은 한국어로, 400자 이내로 작성해 주세요."
)

_scenario_interpretation = ask_gpt(_scenario_prompt, system_msg=_SYSTEM_MSG, max_tokens=700)
print("=" * 70)
print("🤖 AI 해석 — 시나리오 분석")
print("=" * 70)
print(_scenario_interpretation)

# COMMAND ----------

# MAGIC %md
# MAGIC # 9. XReg Attribution — 공변량 기여도 분석
# MAGIC
# MAGIC > Leave-One-Out 방식: 공변량을 하나씩 제외하며 추론 → 예측 변화량 = 해당 변수의 기여도

# COMMAND ----------

attribution = {}
n_covariates = len(dynamic_numerical)

print(f"공변량 기여도 분석 시작 ({n_covariates}개 변수)...")
for cov_idx, cov_name in enumerate(dynamic_numerical.keys()):
    reduced = {k: v for k, v in dynamic_numerical.items() if k != cov_name}
    point_reduced, _ = model.forecast_with_covariates(
        inputs=inputs,
        dynamic_numerical_covariates=reduced,
        dynamic_categorical_covariates=dynamic_categorical,
        static_categorical_covariates=static_categorical,
        xreg_mode="xreg + timesfm",
    )
    # 기여도 = |전체 XReg 예측 - 해당 변수 제외 예측|의 평균
    attribution[cov_name] = float(np.mean(np.abs(point_xreg - point_reduced)))

    if (cov_idx + 1) % 5 == 0:
        print(f"  {cov_idx + 1}/{n_covariates} 완료...")

print("기여도 분석 완료")

# COMMAND ----------

# 기여도 상위 10개 시각화
sorted_attr = sorted(attribution.items(), key=lambda x: x[1], reverse=True)
top_n = 10
names = [a[0] for a in sorted_attr[:top_n]]
scores = [a[1] for a in sorted_attr[:top_n]]

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.barh(  # noqa: F841
    range(top_n), scores[::-1], color="steelblue", alpha=0.8
)
ax.set_yticks(range(top_n))
ax.set_yticklabels(names[::-1], fontsize=10)
ax.set_xlabel("기여도 (예측 변화량 평균)")
ax.set_title(f"XReg Attribution — 예측에 가장 큰 영향을 미친 변수 Top {top_n}", fontsize=12)
ax.grid(True, alpha=0.3, axis="x")
plt.tight_layout()
plt.savefig("/tmp/timesfm_xreg_attribution.png", dpi=150)
plt.show()

print("\n[XReg 기여도 Top 5]")
for name, score in sorted_attr[:5]:
    print(f"  {name}: {score:.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9-1. AI 해석 — 공변량 기여도 (XReg Attribution)

# COMMAND ----------

# GPT-4.1-mini로 상위 기여 변수의 의미와 투자 시사점을 해석
_attr_lines = [
    "TimesFM XReg Leave-One-Out Attribution 분석 결과 (예측에 영향을 가장 크게 미친 변수):\n",
]
for rank, (name, score) in enumerate(sorted_attr[:10], 1):
    _attr_lines.append(f"  {rank}위. {name}: 기여도 {score:.4f}")

_attr_prompt = (
    "\n".join(_attr_lines) + "\n\n위 변수 기여도 분석 결과를 바탕으로:\n"
    "1) 상위 3개 변수가 왜 반도체 주가 예측에 중요한지 경제적 논리를 설명해 주세요.\n"
    "2) 현재 시장 상황에서 이 변수들이 시사하는 리스크 또는 기회를 서술해 주세요.\n"
    "3) 향후 모니터링이 가장 중요한 변수 2가지와 그 이유를 제시해 주세요.\n"
    "답변은 한국어로, 350자 이내로 작성해 주세요."
)

_attr_interpretation = ask_gpt(_attr_prompt, system_msg=_SYSTEM_MSG, max_tokens=650)
print("=" * 70)
print("🤖 AI 해석 — XReg Attribution (핵심 영향 변수)")
print("=" * 70)
print(_attr_interpretation)

# COMMAND ----------

# MAGIC %md
# MAGIC # 10. Rolling Window Backtest
# MAGIC
# MAGIC > 최근 3개월(60 거래일)을 5일 단위로 슬라이딩하며
# MAGIC > 20일 예측 → MAE, PI Coverage, 방향 정확도 평가

# COMMAND ----------

BACKTEST_HORIZON = 20
STEP = 5
TEST_WINDOW = 60  # 최근 60 거래일을 테스트 구간으로 사용

backtest_results = []

for ticker_idx, ticker in enumerate(TICKERS):
    series = inputs[ticker_idx]
    total_len = len(series)

    for start in range(total_len - TEST_WINDOW, total_len - BACKTEST_HORIZON, STEP):
        train = series[:start]
        actual = series[start : start + BACKTEST_HORIZON]

        if len(train) < 32 or len(actual) < BACKTEST_HORIZON:
            continue

        point_bt, quantile_bt = model.forecast(
            horizon=BACKTEST_HORIZON,
            inputs=[train],
        )
        pred = point_bt[0, : len(actual)]

        mae = float(np.mean(np.abs(actual - pred)))
        rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))
        mape = (
            float(np.mean(np.abs((actual - pred) / actual)) * 100)
            if np.all(actual != 0)
            else np.nan
        )

        # 80% PI Coverage: 실제값이 q10~q90 안에 들어온 비율
        in_band = (actual >= quantile_bt[0, : len(actual), 1]) & (
            actual <= quantile_bt[0, : len(actual), 9]
        )
        coverage_80 = float(np.mean(in_band))

        # 방향 정확도: 다음 날 상승/하락을 맞췄는가
        actual_dir = np.sign(np.diff(actual))
        pred_dir = np.sign(np.diff(pred))
        min_len = min(len(actual_dir), len(pred_dir))
        dir_accuracy = (
            float(np.mean(actual_dir[:min_len] == pred_dir[:min_len])) if min_len > 0 else np.nan
        )

        backtest_results.append(
            {
                "ticker": ticker,
                "name": TICKER_NAMES[ticker],
                "window_start": start,
                "mae": mae,
                "rmse": rmse,
                "mape": mape,
                "coverage_80": coverage_80,
                "directional_accuracy": dir_accuracy,
            }
        )

df_backtest = pd.DataFrame(backtest_results)

# COMMAND ----------

# 종목별 Backtest 결과 요약
print("=" * 70)
print("Rolling Window Backtest 결과 요약")
print("=" * 70)

for ticker in TICKERS:
    sub = df_backtest[df_backtest["ticker"] == ticker]
    if sub.empty:
        continue
    print(f"\n{TICKER_NAMES[ticker]} ({ticker}):")
    print(f"  평균 MAE:           {sub['mae'].mean():,.2f}")
    print(f"  평균 RMSE:          {sub['rmse'].mean():,.2f}")
    print(f"  평균 MAPE:          {sub['mape'].mean():.2f}%")
    print(f"  80% PI Coverage:    {sub['coverage_80'].mean():.1%}")
    print(f"  방향 정확도:         {sub['directional_accuracy'].mean():.1%}")
    print(f"  (윈도우 수: {len(sub)})")

# COMMAND ----------

# MAGIC %md
# MAGIC # 11. Anomaly Detection — PI 밴드 이탈 체크
# MAGIC
# MAGIC > 최근 실제 종가가 TimesFM 예측 밴드를 이탈했는지 확인 → 이상 이벤트 기록

# COMMAND ----------

anomaly_records = []

for i, ticker in enumerate(TICKERS):
    series = inputs[i]
    # 최근 HORIZON일 전까지를 context로, 이후를 평가 구간으로 사용
    if len(series) <= HORIZON:
        continue

    context = series[:-HORIZON]
    recent_actual = series[-HORIZON:]

    point_ad, quantile_ad = model.forecast(horizon=HORIZON, inputs=[context])

    lower_80 = quantile_ad[0, :, 1]  # 10th percentile
    upper_80 = quantile_ad[0, :, 9]  # 90th percentile
    dates = feature_marts[ticker].index[-HORIZON:]

    for j in range(HORIZON):
        actual_val = recent_actual[j]
        if actual_val < lower_80[j]:
            anomaly_records.append(
                {
                    "ticker": ticker,
                    "name": TICKER_NAMES[ticker],
                    "date": dates[j],
                    "actual": actual_val,
                    "lower_80": lower_80[j],
                    "upper_80": upper_80[j],
                    "type": "하방 이탈",
                    "severity": "CRITICAL",
                    "deviation_pct": (actual_val - lower_80[j]) / lower_80[j] * 100,
                }
            )
        elif actual_val > upper_80[j]:
            anomaly_records.append(
                {
                    "ticker": ticker,
                    "name": TICKER_NAMES[ticker],
                    "date": dates[j],
                    "actual": actual_val,
                    "lower_80": lower_80[j],
                    "upper_80": upper_80[j],
                    "type": "상방 이탈",
                    "severity": "WARNING",
                    "deviation_pct": (actual_val - upper_80[j]) / upper_80[j] * 100,
                }
            )

if anomaly_records:
    df_anomalies = pd.DataFrame(anomaly_records)
    print(f"이상 이벤트 {len(df_anomalies)}건 감지:")
    print(df_anomalies.to_string(index=False))
else:
    print("최근 구간에서 이상 이벤트 없음 (모든 종가가 80% PI 내)")

# COMMAND ----------

# MAGIC %md
# MAGIC # 12. 결과 PostgreSQL 적재

# COMMAND ----------

# 예측 결과를 DataFrame으로 구조화
forecast_rows = []
for i, ticker in enumerate(TICKERS):
    last_date = feature_marts[ticker].index[-1]
    future_dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=HORIZON)

    for j in range(HORIZON):
        forecast_rows.append(
            {
                "ticker": ticker,
                "forecast_date": future_dates[j],
                "base_date": last_date,
                "horizon_day": j + 1,
                "baseline_point": float(point_baseline[i, j]),
                "baseline_q10": float(quantile_baseline[i, j, 1]),
                "baseline_q90": float(quantile_baseline[i, j, 9]),
                "xreg_point": float(point_xreg[i, j]),
                "xreg_q10": float(quantile_xreg[i, j, 1]),
                "xreg_q90": float(quantile_xreg[i, j, 9]),
                "macro_impact": float(point_xreg[i, j] - point_baseline[i, j]),
            }
        )

df_forecast = pd.DataFrame(forecast_rows)
print(f"예측 결과: {len(df_forecast)} rows")
print(df_forecast.head(10).to_string(index=False))

# COMMAND ----------

# PostgreSQL 적재
# 운영 환경에서는 아래 주석을 해제하고 실행

# conn = vault.get_pg_connection()
# df_forecast.to_sql(
#     "fact_timesfm_forecast",
#     conn,
#     if_exists="append",
#     index=False,
#     method="multi",
# )
# print(f"PostgreSQL 적재 완료: {len(df_forecast)} rows → fact_timesfm_forecast")

# XReg Attribution 결과도 적재
# df_attr = pd.DataFrame([
#     {"covariate": k, "attribution_score": v, "base_date": str(last_date)}
#     for k, v in sorted_attr
# ])
# df_attr.to_sql("fact_timesfm_attribution", conn, if_exists="append", index=False)
# print(f"Attribution 적재 완료: {len(df_attr)} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC # 13. 실행 결과 요약
# MAGIC
# MAGIC > 이 노트북의 출력물을 ADF 배치 파이프라인에
# MAGIC > 포함하여 매일 자동 실행할 수 있습니다.

# COMMAND ----------

print("=" * 70)
print("SENSE × TimesFM 2.5 — 추론 결과 요약")
print("=" * 70)

for i, ticker in enumerate(TICKERS):
    last_price = inputs[i][-1]
    base_final = point_baseline[i, -1]
    xreg_final = point_xreg[i, -1]
    impact = xreg_final - base_final

    print(f"\n{'─' * 50}")
    print(f"📊 {TICKER_NAMES[ticker]} ({ticker})")
    print(f"  현재가:              {last_price:>12,.0f}")
    base_pct = (base_final - last_price) / last_price * 100
    print(f"  Baseline T+{HORIZON}:     {base_final:>12,.0f}  ({base_pct:+.2f}%)")
    xreg_pct = (xreg_final - last_price) / last_price * 100
    print(f"  XReg     T+{HORIZON}:     {xreg_final:>12,.0f}  ({xreg_pct:+.2f}%)")
    print(f"  매크로 충격 (Δ):     {impact:>+12,.0f}  ({impact / last_price * 100:+.2f}%)")

    # Backtest
    bt = df_backtest[df_backtest["ticker"] == ticker]
    if not bt.empty:
        print(f"  Backtest MAE:        {bt['mae'].mean():>12,.2f}")
        print(f"  Backtest Coverage:   {bt['coverage_80'].mean():>11.1%}")
        print(f"  방향 정확도:         {bt['directional_accuracy'].mean():>11.1%}")

    # Attribution Top 3
    print(f"  Top 3 영향 변수:     {', '.join([a[0] for a in sorted_attr[:3]])}")

# 시나리오 요약
print(f"\n{'─' * 50}")
print("📋 시나리오 분석 결과:")
for name in SCENARIOS:
    for i, ticker in enumerate(TICKERS):
        pred = scenario_results[name]["point"][i, -1]
        change = (pred - inputs[i][-1]) / inputs[i][-1] * 100
        print(f"  [{name}] {TICKER_NAMES[ticker]}: {change:+.2f}%")

# Anomaly
if anomaly_records:
    print(f"\n⚠️ 이상 이벤트: {len(anomaly_records)}건 감지됨")
else:
    print("\n✅ 이상 이벤트: 없음")

print(f"\n{'=' * 70}")
print("전략 문서: ref/TimesFM.md")
print("다음 단계: XGBoost/LightGBM 분류 결과와 교차 합의(Consensus) 판정")

# COMMAND ----------

# MAGIC %md
# MAGIC # 14. AI 종합 투자 의견

# COMMAND ----------

# GPT-4.1-mini가 모든 분석 결과를 종합하여 최종 투자 의견을 생성
_final_lines = [
    "SENSE TimesFM 전체 분석 종합 요약:\n",
    f"분석 대상: {', '.join(f'{TICKER_NAMES[t]}({t})' for t in TICKERS)}",
    f"예측 기간: 향후 {HORIZON} 거래일\n",
]

# 예측 방향성
for i, ticker in enumerate(TICKERS):
    lp = inputs[i][-1]
    x_fin = point_xreg[i, -1]
    x_pct = (x_fin - lp) / lp * 100
    delta_pct = (point_xreg[i, -1] - point_baseline[i, -1]) / lp * 100
    _final_lines.append(
        f"[{TICKER_NAMES[ticker]}] XReg 예측: {x_pct:+.2f}% | 매크로 충격: {delta_pct:+.2f}%"
    )

# Attribution Top 3
_final_lines.append(f"\n핵심 영향 변수 Top 3: {', '.join([a[0] for a in sorted_attr[:3]])}")

# 시나리오 요약 (최선/최악)
_sc_changes = {}
for name in SCENARIOS:
    avg_chg = np.mean(
        [
            (scenario_results[name]["point"][i, -1] - inputs[i][-1]) / inputs[i][-1] * 100
            for i in range(len(TICKERS))
        ]
    )
    _sc_changes[name] = avg_chg
_best_sc = max(_sc_changes, key=_sc_changes.get)
_worst_sc = min(_sc_changes, key=_sc_changes.get)
_final_lines.append(f"최선 시나리오: [{_best_sc}] 평균 {_sc_changes[_best_sc]:+.2f}%")
_final_lines.append(f"최악 시나리오: [{_worst_sc}] 평균 {_sc_changes[_worst_sc]:+.2f}%")

# Backtest 지표
if not df_backtest.empty:
    for ticker in TICKERS:
        sub = df_backtest[df_backtest["ticker"] == ticker]
        if not sub.empty:
            _final_lines.append(
                f"[{TICKER_NAMES[ticker]}] Backtest — "
                f"MAE: {sub['mae'].mean():,.0f} | "
                f"방향 정확도: {sub['directional_accuracy'].mean():.1%} | "
                f"80% PI Coverage: {sub['coverage_80'].mean():.1%}"
            )

# 이상 감지
_final_lines.append(
    f"\n이상 이벤트: {'없음' if not anomaly_records else f'{len(anomaly_records)}건 감지'}"
)

_final_prompt = (
    "\n".join(_final_lines)
    + "\n\n위 SENSE 전체 분석을 종합하여 다음 형식으로 최종 투자 의견을 작성해 주세요:\n\n"
    "★ 종합 시장 진단 (2문장)\n"
    "★ 삼성전자 투자 의견 및 근거 (2문장)\n"
    "★ SK하이닉스 투자 의견 및 근거 (2문장)\n"
    "★ 핵심 리스크 요인 (2가지)\n"
    "★ 핵심 기회 요인 (2가지)\n"
    "★ 단기 모니터링 포인트 (2가지)\n\n"
    "답변은 한국어로, 실제 애널리스트 보고서 수준으로 작성해 주세요. "
    "단, 투자 손실에 대한 책임 면책 문구를 마지막에 한 줄 추가해 주세요."
)

_final_interpretation = ask_gpt(_final_prompt, system_msg=_SYSTEM_MSG, max_tokens=1500)
print("=" * 70)
print("🤖 AI 종합 투자 의견 (SENSE × TimesFM × GPT-4.1-mini)")
print("=" * 70)
print(_final_interpretation)
print(f"\n{'=' * 70}")
