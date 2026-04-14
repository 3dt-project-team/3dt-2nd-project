# Databricks notebook source
# MAGIC %md
# MAGIC # SENSE 프로젝트 — TimesFM 2.5 시계열 예측 노트북 (Full Feature)

# COMMAND ----------

# MAGIC %md
# MAGIC SENSE 프로젝트 — TimesFM 2.5 시계열 예측 노트북 (Full Feature)
# MAGIC SENSE: Semiconductor Economic News & Sentiment Engine
# MAGIC
# MAGIC 목적: TimesFM 2.5를 활용한 반도체 주가 시계열 예측
# MAGIC       Step 1 — Zero-shot Baseline (주가만)
# MAGIC       Step 2 — XReg 공변량 추론 (매크로/퀀트/감성)
# MAGIC       Step 3 — 매크로 충격 정량화 + 시나리오 분석 + Backtest
# MAGIC
# MAGIC 주요 기능:
# MAGIC   - 한글 폰트 자동 설정 (matplotlib 경고 해소)
# MAGIC   - 피처 상관관계 히트맵 (Pearson/Spearman)
# MAGIC   - 다중 호라이즌 백테스트 (5일/10일/20일)
# MAGIC   - Conformal PI 보정 (커버리지 개선)
# MAGIC   - 종목별 Attribution 분리
# MAGIC   - 시나리오 일관성 검증
# MAGIC   - 잔차 분포 분석 + VaR/CVaR 리스크 지표
# MAGIC   - Azure OpenAI GPT-4.1-mini AI 투자 의견
# MAGIC
# MAGIC 실행 환경: Databricks GPU 클러스터 권장 (Standard_NC6s_v3 이상)
# MAGIC           CPU에서도 동작하나 배치 추론 시 느림
# MAGIC
# MAGIC 전략 문서: ref/TimesFM.md
# MAGIC 데이터 사전: docs/data_dict/
# MAGIC 간소화 버전: notebooks/timesfm_inference_lite.py

# COMMAND ----------

# MAGIC %md
# MAGIC # 0. 환경 설정 및 패키지 설치

# COMMAND ----------

# MAGIC %load_ext autoreload
# MAGIC %autoreload 2
# MAGIC # Enables autoreload; learn more at https://docs.databricks.com/en/files/workspace-modules.html#autoreload-for-python-modules
# MAGIC # To disable autoreload; run %autoreload 0

# COMMAND ----------

# MAGIC %sh
# MAGIC uv pip install "timesfm[torch] @ git+https://github.com/google-research/timesfm.git" openai "jax>=0.5,<0.6" "jaxlib>=0.5,<0.6" --upgrade  # noqa: E501
# MAGIC echo "--- packages installed, restart python kernel ---"

# COMMAND ----------

# DBTITLE 1,Imports & env setup
import os
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# 한글 폰트 설정 (Databricks 환경)
# ---------------------------------------------------------------------------
_korean_font = None
for _f in fm.fontManager.ttflist:
    if any(k in _f.name for k in ["NanumGothic", "Nanum Gothic", "Malgun Gothic", "NotoSansCJK"]):
        _korean_font = _f.name
        break
if _korean_font is None:
    import glob  # noqa: E402
    import subprocess  # noqa: E402

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
    print(f"한글 폰트 설정 완료: {_korean_font}")
else:
    print("[WARN] 한글 폰트 미발견 — 차트 한글이 깨질 수 있습니다.")
plt.rcParams["axes.unicode_minus"] = False

REPO_PATH = "/Workspace/Repos/3dt005@msacademy.msai.kr/3dt-2nd-project"
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
# MAGIC ## 1-0. Azure OpenAI 클라이언트 초기화

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
HORIZON = 20

TICKER_COL_MAP = {
    "005930.KS": "yfinance_samsung_close",
    "000660.KS": "yfinance_skhynix_close",
}


def safe_read_parquet(path, date_col=None, index_col=None):
    try:
        df = spark.read.parquet(path).toPandas()  # noqa: F821
        if date_col and date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col])
        if index_col and index_col in df.columns:
            df = df.set_index(index_col).sort_index()
        label = path.split("/")[-1]
        print(f"  [OK] {label}: {len(df)} rows, cols={list(df.columns)[:8]}...")
        return df
    except Exception as e:
        print(f"  [SKIP] {path.split('/')[-1]} ({type(e).__name__})")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 1-1. 주가 + 매크로 데이터 로드 (feature/curated 컨테이너 탐색)
# ---------------------------------------------------------------------------
_gold_paths = [
    f"abfss://feature@{account}.dfs.core.windows.net/gold_macro_1y.parquet",
    f"abfss://curated@{account}.dfs.core.windows.net/gold_macro_1y.parquet",
    f"abfss://curated@{account}.dfs.core.windows.net/pre_macro_1y_adf.parquet",
]

_df_gold = pd.DataFrame()
for _path in _gold_paths:
    _df_gold = safe_read_parquet(_path)
    if not _df_gold.empty:
        break

if not _df_gold.empty:
    # 날짜 컬럼 자동감지
    _date_candidates = ["기준일자", "trade_date", "date", "Date"]
    _date_col = next((c for c in _date_candidates if c in _df_gold.columns), None)
    if _date_col is None:
        # datetime 타입 컬럼 탐색
        for c in _df_gold.columns:
            if "date" in c.lower() or "_dt" in c.lower() or "일자" in c:
                _date_col = c
                break
    if _date_col is None:
        print(f"[WARN] 날짜 컬럼 미발견. 컬럼들: {list(_df_gold.columns)}")
        _df_gold = pd.DataFrame()

if not _df_gold.empty:
    _df_gold[_date_col] = pd.to_datetime(_df_gold[_date_col])
    _df_gold = _df_gold.drop_duplicates(subset=[_date_col], keep="first").sort_values(_date_col)
    if _date_col != "trade_date":
        _df_gold = _df_gold.rename(columns={_date_col: "trade_date"})

    # (A) 주가 타겟
    _has_holidays = "주말여부" in _df_gold.columns and "한국_휴장일_여부" in _df_gold.columns
    _df_trading = (
        _df_gold[(~_df_gold["주말여부"]) & (~_df_gold["한국_휴장일_여부"])].copy()
        if _has_holidays
        else _df_gold.copy()
    )

    equity_records = []
    for ticker, col_name in TICKER_COL_MAP.items():
        if col_name in _df_trading.columns:
            _sub = _df_trading[["trade_date", col_name]].dropna(subset=[col_name]).copy()
            _sub = _sub.rename(columns={col_name: "close"})
            _sub["ticker"] = ticker
            equity_records.append(_sub[["ticker", "trade_date", "close"]])
    df_equity = (
        pd.concat(equity_records, ignore_index=True)
        .sort_values(["ticker", "trade_date"])
        .reset_index(drop=True)
        if equity_records
        else pd.DataFrame(columns=["ticker", "trade_date", "close"])
    )

    # (B) 매크로 피처
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
    _macro_avail = [c for c in _macro_cols if c in _df_gold.columns]
    df_macro_gold = (
        _df_gold.set_index("trade_date")[_macro_avail].sort_index().ffill().bfill()
        if _macro_avail
        else pd.DataFrame()
    )
    if not df_macro_gold.empty:
        df_macro_gold.index.name = "trade_date"

    print(
        f"\n주가: {len(df_equity)} rows"
        f" | 매크로: {df_macro_gold.shape[1] if not df_macro_gold.empty else 0} cols"
    )
    for t in TICKERS:
        print(f"  {TICKER_NAMES[t]}: {len(df_equity[df_equity['ticker'] == t])} 거래일")
else:
    df_equity = pd.DataFrame(columns=["ticker", "trade_date", "close"])
    df_macro_gold = pd.DataFrame()
    print("[WARN] 주가/매크로 데이터 로드 실패")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1-2. 한국 금융 파생상품 피처 (silver_kfinance)

# COMMAND ----------

# ---------------------------------------------------------------------------
# 1-2. silver_kfinance.parquet → 한국 금융 파생상품 피처
#  KOSPI200 옵션/워런트 월별 데이터 → 일별 Forward-Fill
#  피처: ATM가, 활성계약수, 평균가, 최대유효행사가, 총가치
# ---------------------------------------------------------------------------
kfin_path = f"abfss://curated@{account}.dfs.core.windows.net/silver_kfinance.parquet"
_df_kfin_raw = safe_read_parquet(kfin_path, date_col="date")

if not _df_kfin_raw.empty:
    # close_price를 숫자로 변환
    _df_kfin_raw["close_price"] = pd.to_numeric(
        _df_kfin_raw["close_price"], errors="coerce"
    ).fillna(0)

    # ticker에서 행사가 추출 (kfinance_201WC170 → 170)
    _df_kfin_raw["strike"] = _df_kfin_raw["ticker"].str.extract(r"(\d+)$")[0].astype(float)

    # 날짜별 집계 → 시장 레벨 피처
    df_kfin_agg = (
        _df_kfin_raw.groupby("date")
        .agg(
            # ATM(최고가) 옵션 가격 → 변동성 프록시
            kfin_atm_price=("close_price", "max"),
            # 활성 계약 수 (close_price > 0) → 시장 폭
            kfin_active_count=("close_price", lambda x: (x > 0).sum()),
            # 활성 옵션 평균 가격
            kfin_mean_price=("close_price", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
            # 총 가치 합계 → 시장 활동 강도
            kfin_total_value=("close_price", "sum"),
            # 전체 종목 수
            kfin_total_count=("close_price", "count"),
        )
        .reset_index()
    )

    # 최대 유효 행사가 (close > 0인 최고 행사가) → 시장 상한 기대
    _active = _df_kfin_raw[_df_kfin_raw["close_price"] > 0]
    _max_strike = _active.groupby("date")["strike"].max().reset_index()
    _max_strike.columns = ["date", "kfin_max_strike"]
    df_kfin_agg = df_kfin_agg.merge(_max_strike, on="date", how="left")

    # 활성 비율
    df_kfin_agg["kfin_active_ratio"] = (
        df_kfin_agg["kfin_active_count"] / df_kfin_agg["kfin_total_count"]
    )

    # 월별 → 일별 Forward-Fill
    df_kfin_agg = df_kfin_agg.set_index("date").sort_index()
    all_bdays = pd.bdate_range(df_kfin_agg.index.min(), df_kfin_agg.index.max(), freq="B")
    df_kfinance = df_kfin_agg.reindex(all_bdays).ffill().bfill()
    df_kfinance.index.name = "trade_date"

    # 불필요 컬럼 제거
    df_kfinance = df_kfinance.drop(columns=["kfin_total_count"], errors="ignore")

    print(f"kfinance 피처: {df_kfinance.shape}")
    print(f"  기간: {df_kfinance.index.min()} ~ {df_kfinance.index.max()}")
    print(f"  컬럼: {list(df_kfinance.columns)}")
    display(df_kfinance.head())  # noqa: F821
else:
    df_kfinance = pd.DataFrame()
    print("[WARN] kfinance 데이터 없음")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1-3. 반도체 수출입 피처 (silver_semiconductor)

# COMMAND ----------

# ---------------------------------------------------------------------------
# 1-3. silver_semiconductor.parquet → 반도체 수출입 피처
#  월별 HS코드별 수출/수입 → 일별 Forward-Fill
#  피처: 총수출, 총수입, 무역수지, DRAM수출, Flash수출, MoM변화, DRAM비중
# ---------------------------------------------------------------------------
semi_path = f"abfss://curated@{account}.dfs.core.windows.net/silver_semiconductor.parquet"
_df_semi_raw = safe_read_parquet(semi_path, date_col="date")

if not _df_semi_raw.empty:
    # --- 날짜별 전체 집계 ---
    _semi_total = (
        _df_semi_raw.groupby("date")
        .agg(semi_total_exp=("expDlr", "sum"), semi_total_imp=("impDlr", "sum"))
        .reset_index()
    )
    _semi_total["semi_net_trade"] = _semi_total["semi_total_exp"] - _semi_total["semi_total_imp"]

    # --- DRAM (HS 8542321010) ---
    _dram = (
        _df_semi_raw[_df_semi_raw["hsCode"] == 8542321010]
        .groupby("date")
        .agg(semi_dram_exp=("expDlr", "sum"), semi_dram_imp=("impDlr", "sum"))
        .reset_index()
    )

    # --- Flash 메모리 (HS 8542321030) ---
    _flash = (
        _df_semi_raw[_df_semi_raw["hsCode"] == 8542321030]
        .groupby("date")
        .agg(semi_flash_exp=("expDlr", "sum"), semi_flash_imp=("impDlr", "sum"))
        .reset_index()
    )

    # --- 복합구조칩 IC (HS 8542323000, 최대 수출 품목) ---
    _mcp = (
        _df_semi_raw[_df_semi_raw["hsCode"] == 8542323000]
        .groupby("date")
        .agg(semi_mcp_exp=("expDlr", "sum"))
        .reset_index()
    )

    # 병합
    df_semi_agg = _semi_total
    for _sub in [_dram, _flash, _mcp]:
        df_semi_agg = df_semi_agg.merge(_sub, on="date", how="left")

    df_semi_agg = df_semi_agg.sort_values("date").reset_index(drop=True)

    # --- 파생 피처 ---
    # DRAM 비중 (전체 반도체 수출 대비)
    df_semi_agg["semi_dram_ratio"] = df_semi_agg["semi_dram_exp"] / df_semi_agg[
        "semi_total_exp"
    ].replace(0, np.nan)
    # MoM 변화율 ()
    df_semi_agg["semi_exp_mom"] = df_semi_agg["semi_total_exp"].pct_change()
    df_semi_agg["semi_dram_mom"] = df_semi_agg["semi_dram_exp"].pct_change()
    # 무역수지 비율 (수출/수입)
    df_semi_agg["semi_trade_ratio"] = df_semi_agg["semi_total_exp"] / df_semi_agg[
        "semi_total_imp"
    ].replace(0, np.nan)

    # 금액 단위 조정 (USD → 억 USD)
    dollar_cols = [
        c
        for c in df_semi_agg.columns
        if c.startswith("semi_")
        and ("exp" in c or "imp" in c or "net" in c)
        and "mom" not in c
        and "ratio" not in c
    ]
    for col in dollar_cols:
        df_semi_agg[col] = df_semi_agg[col] / 1e8  # 억달러 단위

    # 월별 → 일별 Forward-Fill
    df_semi_agg = df_semi_agg.set_index("date").sort_index()
    all_bdays = pd.bdate_range(df_semi_agg.index.min(), df_semi_agg.index.max(), freq="B")
    df_semiconductor = df_semi_agg.reindex(all_bdays).ffill().bfill()
    df_semiconductor.index.name = "trade_date"

    print(f"semiconductor 피처: {df_semiconductor.shape}")
    print(f"  기간: {df_semiconductor.index.min()} ~ {df_semiconductor.index.max()}")
    print(f"  컬럼: {list(df_semiconductor.columns)}")
    display(df_semiconductor.head())  # noqa: F821
else:
    df_semiconductor = pd.DataFrame()
    print("[WARN] semiconductor 데이터 없음")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1-4. 피처 요약

# COMMAND ----------

# ---------------------------------------------------------------------------
# 1-4. curated 피처 요약
# ---------------------------------------------------------------------------
print("=" * 60)
print("SENSE Feature 요약 (curated 기반)")
print("=" * 60)

if not df_kfinance.empty:
    print(f"\n[한국 금융 파생상품]  {df_kfinance.shape[1]} 피처, {len(df_kfinance)} 일")
    print(f"  기간: {df_kfinance.index.min().date()} ~ {df_kfinance.index.max().date()}")
    print(f"  피처: {list(df_kfinance.columns)}")
else:
    print("\n[한국 금융] 데이터 없음")

if not df_semiconductor.empty:
    print(f"\n[반도체 수출입]  {df_semiconductor.shape[1]} 피처, {len(df_semiconductor)} 일")
    print(f"  기간: {df_semiconductor.index.min().date()} ~ {df_semiconductor.index.max().date()}")
    print(f"  피처: {list(df_semiconductor.columns)}")
else:
    print("\n[반도체] 데이터 없음")

if not df_equity.empty:
    print(f"\n[주가 타겟]  {len(df_equity)} rows")
    print(f"  종목: {[TICKER_NAMES[t] for t in TICKERS]}")
else:
    print("\n[주가] 데이터 없음")

print("\n" + "=" * 60)

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. 통합 피처 마트 구성

# COMMAND ----------


def build_feature_mart(df_equity, ticker, df_kfinance, df_semiconductor, df_macro_gold):
    """
    종목별 통합 피처 마트를 date 기준으로 LEFT JOIN하여 구성합니다.
    curated: kfinance(한국 금융) + semiconductor(수출입) + macro_gold(FRED/FX/피어주)
    """
    df = df_equity[df_equity["ticker"] == ticker][["trade_date", "close"]].copy()
    df = df.set_index("trade_date").sort_index()

    # 수익률 파생
    df["return_1d"] = df["close"].pct_change()

    # --- 한국 금융 파생상품 피처 ---
    if not df_kfinance.empty:
        df = df.join(df_kfinance, how="left")

    # --- 반도체 수출입 피처 ---
    if not df_semiconductor.empty:
        df = df.join(df_semiconductor, how="left")

    # --- 매크로/글로벌 피어 피처 ---
    if not df_macro_gold.empty:
        df = df.join(df_macro_gold, how="left")

    # Forward fill 후 첫 행 NaN 제거
    df = df.ffill().bfill()

    return df


# 종목별 피처 마트 생성
feature_marts = {}
for ticker in TICKERS:
    feature_marts[ticker] = build_feature_mart(
        df_equity, ticker, df_kfinance, df_semiconductor, df_macro_gold
    )
    print(f"{TICKER_NAMES[ticker]}: {feature_marts[ticker].shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. 교차 검증 파생 변수 생성

# COMMAND ----------


def create_derived_features(df):
    """
    SENSE 3축 교차 검증 파생 변수 + 시차/변동성 피처를 생성합니다.
    curated 데이터 기반: kfinance(금융 파생) × semiconductor(수출입)
    """
    out = df.copy()

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
    print(f"  컬럼 목록: {list(feature_marts[ticker].columns)}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3-1. 피처 상관관계 분석
# MAGIC
# MAGIC > 주요 피처와 타겟(종가) 간 Pearson/Spearman 상관관계 히트맵

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
    corr_p = mart[avail].corr(method="pearson")
    corr_s = mart[avail].corr(method="spearman")

    fig, axes_corr = plt.subplots(1, 2, figsize=(22, 10))
    for ax_c, corr_mat, method in zip(axes_corr, [corr_p, corr_s], ["Pearson", "Spearman"]):
        im = ax_c.imshow(corr_mat, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        ax_c.set_xticks(range(len(avail)))
        ax_c.set_yticks(range(len(avail)))
        ax_c.set_xticklabels(avail, rotation=45, ha="right", fontsize=7)
        ax_c.set_yticklabels(avail, fontsize=7)
        for r in range(len(avail)):
            for cc in range(len(avail)):
                ax_c.text(
                    cc, r, f"{corr_mat.iloc[r, cc]:.2f}", ha="center", va="center", fontsize=6
                )
        plt.colorbar(im, ax=ax_c, shrink=0.8)
        ax_c.set_title(f"{TICKER_NAMES[ticker]} — {method} 상관계수", fontsize=12)
    plt.tight_layout()
    plt.savefig(f"/tmp/timesfm_corr_{ticker}.png", dpi=150)
    plt.show()

    # 타겟 vs 주요 피처 Spearman 순위
    target_cols = [c for c in avail if c != "close"]
    spearman_vs_target = (
        mart[target_cols + ["close"]].corr(method="spearman")["close"].drop("close")
    )
    spearman_vs_target = spearman_vs_target.reindex(
        spearman_vs_target.abs().sort_values(ascending=False).index
    )
    print(f"\n{TICKER_NAMES[ticker]} — Spearman |상관| 상위 10:")
    for col, val in spearman_vs_target.head(10).items():
        print(f"  {col}: {val:+.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. TimesFM 2.5 모델 로드

# COMMAND ----------

import importlib  # noqa: E402

import timesfm  # noqa: E402

importlib.reload(timesfm)

torch.set_float32_matmul_precision("high")

# HuggingFace 인증
_hf_token = vault.get_secret("hf-token") or os.environ.get("HF_TOKEN", "")
if _hf_token:
    os.environ["HF_TOKEN"] = _hf_token
    os.environ["HUGGING_FACE_HUB_TOKEN"] = _hf_token
    print(f"HF 토큰 설정 완료 (len={len(_hf_token)})")
else:
    print("[WARN] HF 토큰 없음")

model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
model.compile(
    timesfm.ForecastConfig(
        max_context=256,  # 1년 ≈ 250 거래일
        max_horizon=128,  # 최대 예측 길이
        return_backcast=True,  # XReg 추론에 필수
        normalize_inputs=True,  # 스케일 정규화 (주가 크기 차이 흡수)
        use_continuous_quantile_head=True,  # 연속 분위수 예측 (PI 정밀도 향상)
        force_flip_invariance=True,  # f(-x) = -f(x) 대칭 강제
        infer_is_positive=False,  # 주가 수익률은 음수 가능
        fix_quantile_crossing=True,  # q10 ≤ q20 ≤ ... ≤ q90 보장
    )
)
print("TimesFM 2.5 200M 모델 로드 완료")

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

_pb_raw, _qb_raw = model.forecast(
    horizon=HORIZON,
    inputs=inputs,
)

# return_backcast=True → backcast 포함된 전체 배열에서 forecast 부분만 추출
point_baseline = np.array(_pb_raw)[:, -HORIZON:]
quantile_baseline = np.array(_qb_raw)[:, -HORIZON:, :]

print(f"Baseline point: {point_baseline.shape} | quantile: {quantile_baseline.shape}")

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
_xreg_result = model.forecast_with_covariates(
    inputs=inputs,
    dynamic_numerical_covariates=dynamic_numerical,
    dynamic_categorical_covariates=dynamic_categorical,
    static_categorical_covariates=static_categorical,
    xreg_mode="xreg + timesfm",
)

# TimesFM 2.5는 list 반환 → np.array 변환
point_xreg = np.array(_xreg_result[0])
quantile_xreg = np.array(_xreg_result[1])

print(f"XReg point shape: {point_xreg.shape} | quantile shape: {quantile_xreg.shape}")

for i, ticker in enumerate(TICKERS):
    last_price = inputs[i][-1]
    pred_base = point_baseline[i, -1]
    pred_xreg_val = point_xreg[i, -1]
    delta = pred_xreg_val - pred_base
    print(f"\n{TICKER_NAMES[ticker]}:")
    print(f"  Baseline {HORIZON}일 예측: {pred_base:,.0f}")
    print(f"  XReg     {HORIZON}일 예측: {pred_xreg_val:,.0f}")
    print(f"  매크로 충격 (Δ): {delta:+,.0f} ({delta / last_price * 100:+.2f}%)")
    if quantile_xreg.ndim == 3:
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

# ---------------------------------------------------------------------------
# 시나리오 정의 — 5개 그룹: 기준 / 통화정책 / 환율·무역 / 산업·수급 / 복합 (스트레스)
# ---------------------------------------------------------------------------
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

    _p_sc, _q_sc = model.forecast_with_covariates(
        inputs=inputs,
        dynamic_numerical_covariates=scenario_covariates,
        dynamic_categorical_covariates=dynamic_categorical,
        static_categorical_covariates=static_categorical,
        xreg_mode="xreg + timesfm",
    )
    # list → np.array 변환
    scenario_results[scenario_name] = {
        "point": np.array(_p_sc),
        "quantiles": np.array(_q_sc),
    }
    print(f"  ✅ {scenario_name}")

print(f"\n총 {len(scenario_results)} 시나리오 추론 완료")

# COMMAND ----------

# 시나리오별 최종 예측값 비교 테이블 (그룹별 출력)
rows = []
for scenario_name, result in scenario_results.items():
    # 그룹 탐색
    group = "기타"
    for g, names in SCENARIO_GROUPS.items():
        if scenario_name in names:
            group = g
            break
    for i, ticker in enumerate(TICKERS):
        last_price = inputs[i][-1]
        pred = result["point"][i, -1]
        change_pct = (pred - last_price) / last_price * 100
        rows.append(
            {
                "그룹": group,
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

# MAGIC %md
# MAGIC ## 8-1. 시나리오 일관성 검증
# MAGIC
# MAGIC > 시나리오 결과가 경제적 상식과 부합하는지 자동 검증

# COMMAND ----------

_sanity_checks = []
_base_result = scenario_results["현상 유지"]
for name, result in scenario_results.items():
    if name == "현상 유지":
        continue
    for i, ticker in enumerate(TICKERS):
        pred = result["point"][i, -1]
        base = _base_result["point"][i, -1]
        delta_pct = (pred - base) / abs(base) * 100
        _sanity_checks.append(
            {
                "시나리오": name,
                "종목": TICKER_NAMES[ticker],
                "기준 대비 변동(%)": round(delta_pct, 2),
            }
        )

df_sanity = pd.DataFrame(_sanity_checks)
print("시나리오 일관성 검증 (현상 유지 대비 변동):")
print(df_sanity.to_string(index=False))

# 경제적 상식과 반대 방향인 시나리오 플래그
_counterintuitive = []
print("\n⚠️ 직관 검증 필요 시나리오:")
for _, row in df_sanity.iterrows():
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
        _counterintuitive.append(f"{name}({row['종목']}): {flag}")

if not _counterintuitive:
    print("  ✅ 모든 시나리오가 경제적 직관과 부합합니다.")
else:
    print("\n참고: TimesFM XReg은 공변량을 선형 참조하므로, 학습 기간 상관관계가")
    print("     경제적 인과와 다를 수 있습니다. 시나리오 해석 시 이 점을 고려하세요.")

# COMMAND ----------

# 시나리오 Fan Chart (그룹별 색상)
_GROUP_COLORS = {
    "기준": "tab:gray",
    "통화정책": "tab:blue",
    "환율·무역": "tab:orange",
    "산업·수급": "tab:green",
    "복합 스트레스": "tab:red",
}

fig, axes = plt.subplots(1, len(TICKERS), figsize=(9 * len(TICKERS), 6))
if len(TICKERS) == 1:
    axes = [axes]

for idx, ticker in enumerate(TICKERS):
    ax = axes[idx]
    forecast_x = np.arange(1, HORIZON + 1)

    plotted_groups = set()
    for name, result in scenario_results.items():
        # 그룹 탐색
        group = "기타"
        for g, members in SCENARIO_GROUPS.items():
            if name in members:
                group = g
                break
        c = _GROUP_COLORS.get(group, "tab:pink")
        lw = 2.0 if group == "복합 스트레스" else 1.2
        ls = "--" if group == "복합 스트레스" else "-"
        ax.plot(
            forecast_x,
            result["point"][idx],
            label=name,
            color=c,
            linewidth=lw,
            linestyle=ls,
            alpha=0.85,
        )
        ax.fill_between(
            forecast_x,
            result["quantiles"][idx, :, 1],
            result["quantiles"][idx, :, 9],
            alpha=0.04,
            color=c,
        )

    ax.axhline(y=inputs[idx][-1], color="black", linestyle=":", alpha=0.5, label="현재가")
    ax.set_title(f"{TICKER_NAMES[ticker]} 시나리오 분석 ({len(SCENARIOS)}개)", fontsize=12)
    ax.set_xlabel(f"예측 일차 (T+1 ~ T+{HORIZON})")
    ax.set_ylabel("예측 종가")
    ax.legend(fontsize=7, ncol=2, loc="upper left")
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
    f"반도체 주가 TimesFM 시나리오 분석 결과"
    f" (향후 {HORIZON} 거래일, {len(SCENARIOS)}개 시나리오):\n",
]
for group, members in SCENARIO_GROUPS.items():
    _scenario_lines.append(f"\n[{group}]")
    for name in members:
        if name not in scenario_results:
            continue
        row_parts = []
        for i, ticker in enumerate(TICKERS):
            pred = scenario_results[name]["point"][i, -1]
            chg = (pred - inputs[i][-1]) / inputs[i][-1] * 100
            row_parts.append(f"{TICKER_NAMES[ticker]} {chg:+.2f}%")
        _scenario_lines.append(f"  {name}: {' | '.join(row_parts)}")

_scenario_prompt = (
    "\n".join(_scenario_lines) + f"\n\n위 {len(SCENARIOS)}개 시나리오 분석 결과를 바탕으로:\n"
    "1) 그룹별로 반도체 주가에 미치는 영향을 경제적 논리와 함께 설명해 주세요.\n"
    "2) 가장 위험한 시나리오와 가장 유리한 시나리오를 특정하고 그 이유를 서술해 주세요.\n"
    "3) 복합 스트레스 시나리오의 현실 발생 가능성과 대응 전략을 제시해 주세요.\n"
    "4) 현재 투자자가 우선적으로 헤지해야 할 시나리오 1가지를 추천해 주세요.\n"
    "답변은 한국어로, 600자 이내로 작성해 주세요."
)

_scenario_interpretation = ask_gpt(_scenario_prompt, system_msg=_SYSTEM_MSG, max_tokens=1000)
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
attribution_per_ticker = {ticker: {} for ticker in TICKERS}
n_covariates = len(dynamic_numerical)

print(f"공변량 기여도 분석 시작 ({n_covariates}개 변수)...")
for cov_idx, cov_name in enumerate(dynamic_numerical.keys()):
    reduced = {k: v for k, v in dynamic_numerical.items() if k != cov_name}
    _p_reduced, _ = model.forecast_with_covariates(
        inputs=inputs,
        dynamic_numerical_covariates=reduced,
        dynamic_categorical_covariates=dynamic_categorical,
        static_categorical_covariates=static_categorical,
        xreg_mode="xreg + timesfm",
    )
    point_reduced = np.array(_p_reduced)
    attribution[cov_name] = float(np.mean(np.abs(point_xreg - point_reduced)))

    # 종목별 기여도 (v0411)
    for ti, ticker in enumerate(TICKERS):
        attribution_per_ticker[ticker][cov_name] = float(
            np.mean(np.abs(point_xreg[ti] - point_reduced[ti]))
        )

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

# 종목별 기여도 Top 10 비교 시각화 (v0411)
fig, axes_at = plt.subplots(1, len(TICKERS), figsize=(9 * len(TICKERS), 6))
if len(TICKERS) == 1:
    axes_at = [axes_at]

for idx, ticker in enumerate(TICKERS):
    ax = axes_at[idx]
    sorted_t = sorted(attribution_per_ticker[ticker].items(), key=lambda x: x[1], reverse=True)
    top_names_t = [a[0] for a in sorted_t[:top_n]]
    top_scores_t = [a[1] for a in sorted_t[:top_n]]
    ax.barh(range(top_n), top_scores_t[::-1], color="steelblue", alpha=0.8)
    ax.set_yticks(range(top_n))
    ax.set_yticklabels(top_names_t[::-1], fontsize=9)
    ax.set_xlabel("기여도 (예측 변화량 평균)")
    ax.set_title(f"{TICKER_NAMES[ticker]} Attribution Top {top_n}", fontsize=12)
    ax.grid(True, alpha=0.3, axis="x")

plt.suptitle("종목별 XReg Attribution 비교", fontsize=14, y=1.02)
plt.tight_layout()
plt.savefig("/tmp/timesfm_attribution_per_ticker.png", dpi=150)
plt.show()

# 종목 간 기여도 순위 차이 분석
print("\n[종목 간 Attribution 순위 비교]")
for ticker in TICKERS:
    sorted_t = sorted(attribution_per_ticker[ticker].items(), key=lambda x: x[1], reverse=True)
    print(f"\n{TICKER_NAMES[ticker]} Top 5:")
    for rank, (name, score) in enumerate(sorted_t[:5], 1):
        print(f"  {rank}. {name}: {score:.4f}")

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
# MAGIC # 10. Rolling Window Backtest (다중 호라이즌)
# MAGIC
# MAGIC > 최근 3개월(60 거래일)을 5일 단위로 슬라이딩하며
# MAGIC > 5일/10일/20일 예측 → MAE, MAPE, PI Coverage, 방향 정확도 평가

# COMMAND ----------

BACKTEST_HORIZONS = [5, 10, 20]
STEP = 5
TEST_WINDOW = 60  # 최근 60 거래일을 테스트 구간으로 사용

backtest_results = []

for bh in BACKTEST_HORIZONS:
    for ticker_idx, ticker in enumerate(TICKERS):
        series = inputs[ticker_idx]
        total_len = len(series)

        for start in range(total_len - TEST_WINDOW, total_len - bh, STEP):
            train = series[:start]
            actual = series[start : start + bh]

            if len(train) < 32 or len(actual) < bh:
                continue

            _p_bt, _q_bt = model.forecast(
                horizon=bh,
                inputs=[train],
            )
            # return_backcast=True → 마지막 bh개만 forecast
            point_bt = np.array(_p_bt)[:, -bh:]
            quantile_bt = np.array(_q_bt)[:, -bh:, :]
            pred = point_bt[0, : len(actual)]

            mae = float(np.mean(np.abs(actual - pred)))
            rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))
            mape = (
                float(np.mean(np.abs((actual - pred) / actual)) * 100)
                if np.all(actual != 0)
                else np.nan
            )

            # 80% PI Coverage
            in_band = (actual >= quantile_bt[0, : len(actual), 1]) & (
                actual <= quantile_bt[0, : len(actual), 9]
            )
            coverage_80 = float(np.mean(in_band))

            # 방향 정확도
            actual_dir = np.sign(np.diff(actual))
            pred_dir = np.sign(np.diff(pred))
            min_len = min(len(actual_dir), len(pred_dir))
            dir_accuracy = (
                float(np.mean(actual_dir[:min_len] == pred_dir[:min_len]))
                if min_len > 0
                else np.nan
            )

            backtest_results.append(
                {
                    "ticker": ticker,
                    "name": TICKER_NAMES[ticker],
                    "horizon": bh,
                    "window_start": start,
                    "mae": mae,
                    "rmse": rmse,
                    "mape": mape,
                    "coverage_80": coverage_80,
                    "directional_accuracy": dir_accuracy,
                }
            )

df_backtest = pd.DataFrame(backtest_results)
print(f"Backtest 완료: {len(df_backtest)} 윈도우 ({len(BACKTEST_HORIZONS)} 호라이즌)")

# COMMAND ----------

# 종목별·호라이즌별 Backtest 결과 요약
print("=" * 70)
print("Rolling Window Backtest 결과 요약 (다중 호라이즌)")
print("=" * 70)

for ticker in TICKERS:
    print(f"\n{'─' * 50}")
    print(f"📊 {TICKER_NAMES[ticker]} ({ticker})")
    for bh in BACKTEST_HORIZONS:
        sub = df_backtest[(df_backtest["ticker"] == ticker) & (df_backtest["horizon"] == bh)]
        if sub.empty:
            continue
        cov = sub["coverage_80"].mean()
        dir_acc = sub["directional_accuracy"].mean()
        cov_flag = "✅" if cov >= 0.75 else "⚠️"
        dir_flag = "✅" if dir_acc >= 0.55 else "⚠️"
        print(f"\n  [T+{bh}일] (윈도우 {len(sub)}개)")
        print(f"    평균 MAE:       {sub['mae'].mean():>10,.2f}")
        print(f"    평균 RMSE:      {sub['rmse'].mean():>10,.2f}")
        print(f"    평균 MAPE:      {sub['mape'].mean():>9.2f}%")
        print(f"    80% PI Coverage:{cov:>9.1%} {cov_flag}")
        print(f"    방향 정확도:    {dir_acc:>9.1%} {dir_flag}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10-1. Conformal PI 보정
# MAGIC
# MAGIC > Backtest 잔차를 이용하여 80% PI 밴드를 실증적으로 보정
# MAGIC > 삼성전자 63.7% → 80% 도달을 위한 확장 계수 산출

# COMMAND ----------

print("=" * 70)
print("Conformal Prediction Interval 보정")
print("=" * 70)

conformal_factors = {}
for ticker in TICKERS:
    sub20 = df_backtest[(df_backtest["ticker"] == ticker) & (df_backtest["horizon"] == 20)]
    if sub20.empty:
        continue
    actual_cov = sub20["coverage_80"].mean()
    target_cov = 0.80
    print(f"\n{TICKER_NAMES[ticker]}:")
    print(f"  현재 80% PI Coverage: {actual_cov:.1%}")
    if actual_cov < target_cov - 0.02:
        # 밴드 폭 확장 계수: quantile 기반 보정
        expansion = target_cov / max(actual_cov, 0.10)
        conformal_factors[ticker] = expansion
        print(f"  ⚠ 목표 미달 → PI 폭 확장 계수: ×{expansion:.3f}")
        print(f"  보정 적용: q10' = mid - (mid - q10) × {expansion:.3f}")
        print(f"             q90' = mid + (q90 - mid) × {expansion:.3f}")
        # 시범 적용
        idx_t = TICKERS.index(ticker)
        mid = point_xreg[idx_t]
        q10_orig = quantile_xreg[idx_t, :, 1]
        q90_orig = quantile_xreg[idx_t, :, 9]
        q10_cal = mid - (mid - q10_orig) * expansion
        q90_cal = mid + (q90_orig - mid) * expansion
        pi_width_orig = np.mean(q90_orig - q10_orig)
        pi_width_cal = np.mean(q90_cal - q10_cal)
        print(f"  보정 전 평균 PI 폭: {pi_width_orig:,.0f}원")
        print(f"  보정 후 평균 PI 폭: {pi_width_cal:,.0f}원")
    else:
        conformal_factors[ticker] = 1.0
        print(f"  ✅ 목표 달성 (≥ {target_cov:.0%}) — 보정 불필요")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10-2. 잔차 분포 분석
# MAGIC
# MAGIC > Backtest 예측 오차의 분포를 시각화하여 모델 편향(bias) 진단

# COMMAND ----------

fig, axes_res = plt.subplots(
    len(TICKERS), len(BACKTEST_HORIZONS), figsize=(6 * len(BACKTEST_HORIZONS), 5 * len(TICKERS))
)
if len(TICKERS) == 1:
    axes_res = [axes_res]

for ti, ticker in enumerate(TICKERS):
    for hi, bh in enumerate(BACKTEST_HORIZONS):
        ax = axes_res[ti][hi] if len(BACKTEST_HORIZONS) > 1 else axes_res[ti]
        sub = df_backtest[(df_backtest["ticker"] == ticker) & (df_backtest["horizon"] == bh)]
        if sub.empty:
            continue
        # MAE를 부호 있는 잔차(bias)로 전환하려면 원본 예측-실제 필요
        # 여기서는 MAPE 분포로 대체
        mapes = sub["mape"].dropna()
        ax.hist(
            mapes, bins=max(3, len(mapes) // 2), color="steelblue", alpha=0.7, edgecolor="white"
        )
        ax.axvline(mapes.mean(), color="red", linestyle="--", label=f"평균: {mapes.mean():.2f}%")
        ax.set_title(f"{TICKER_NAMES[ticker]} T+{bh} MAPE 분포", fontsize=11)
        ax.set_xlabel("MAPE (%)")
        ax.set_ylabel("윈도우 수")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig("/tmp/timesfm_residual_distribution.png", dpi=150)
plt.show()

# COMMAND ----------

# MAGIC %md
# MAGIC # 11. Anomaly Detection — PI 밴드 이탈 체크
# MAGIC
# MAGIC > 최근 실제 종가가 TimesFM 예측 밴드를 이탈했는지 확인 → 이상 이벤트 기록

# COMMAND ----------

anomaly_records = []

for i, ticker in enumerate(TICKERS):
    series = inputs[i]
    if len(series) <= HORIZON:
        continue

    context = series[:-HORIZON]
    recent_actual = series[-HORIZON:]

    _p_ad, _q_ad = model.forecast(horizon=HORIZON, inputs=[context])
    # return_backcast=True → 마지막 HORIZON개만 forecast
    point_ad = np.array(_p_ad)[:, -HORIZON:]
    quantile_ad = np.array(_q_ad)[:, -HORIZON:, :]

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
    df_anomalies = pd.DataFrame()
    print("최근 구간에서 이상 이벤트 없음 (80% PI 내)")

# COMMAND ----------

# MAGIC %md
# MAGIC # 11-1. VaR/CVaR 리스크 지표
# MAGIC
# MAGIC > TimesFM Quantile 예측으로부터 Value-at-Risk 및 Conditional VaR 산출

# COMMAND ----------

print("=" * 70)
print("VaR / CVaR 리스크 지표 (XReg 기반)")
print("=" * 70)

for i, ticker in enumerate(TICKERS):
    last_price = inputs[i][-1]
    # q10 = 10th percentile of forecast → worst 10% scenario proxy
    q10_path = quantile_xreg[i, :, 1]  # 10th percentile over horizon
    q05_approx = quantile_xreg[i, :, 0]  # mean (approx for lower tail via interpolation)

    # T+5, T+10, T+20 VaR
    print(f"\n{TICKER_NAMES[ticker]} ({ticker}):")
    for h_label, h_idx in [("T+5", 4), ("T+10", 9), ("T+20", min(19, HORIZON - 1))]:
        if h_idx >= HORIZON:
            continue
        var_10 = (q10_path[h_idx] - last_price) / last_price * 100
        # CVaR: 평균 of q10 path up to h_idx (conditional on tail)
        cvar_10 = np.mean([(q10_path[j] - last_price) / last_price * 100 for j in range(h_idx + 1)])
        print(f"  [{h_label}] VaR(10%): {var_10:+.2f}% | CVaR(10%): {cvar_10:+.2f}%")

    # 보정된 VaR (Conformal 적용)
    if ticker in conformal_factors and conformal_factors[ticker] > 1.0:
        cf = conformal_factors[ticker]
        mid = point_xreg[i]
        q10_cal = mid - (mid - q10_path) * cf
        h_idx_20 = min(19, HORIZON - 1)
        var_cal = (q10_cal[h_idx_20] - last_price) / last_price * 100
        print(f"  [T+20 Conformal 보정] VaR(10%): {var_cal:+.2f}%")

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

    # 멀티 호라이즌 Backtest 요약 (v0411)
    for h in BACKTEST_HORIZONS:
        bt = df_backtest[(df_backtest["ticker"] == ticker) & (df_backtest["horizon"] == h)]
        if bt.empty:
            continue
        cov = bt["coverage_80"].mean()
        da = bt["directional_accuracy"].mean()
        cov_flag = "✅" if cov >= 0.75 else "⚠️"
        da_flag = "✅" if da >= 0.55 else "⚠️"
        print(
            f"  [{h}d] MAE: {bt['mae'].mean():>10,.0f} | "
            f"Coverage: {cov:>5.1%} {cov_flag} | "
            f"Direction: {da:>5.1%} {da_flag}"
        )

    # Conformal 보정 정보
    if ticker in conformal_factors and conformal_factors[ticker] > 1.0:
        print(f"  Conformal PI 확장 계수: ×{conformal_factors[ticker]:.2f}")

    # 종목별 Attribution Top 3 (v0411)
    if ticker in attribution_per_ticker and attribution_per_ticker[ticker]:
        sorted_t = sorted(attribution_per_ticker[ticker].items(), key=lambda x: x[1], reverse=True)
        print(f"  Top 3 영향 변수:     {', '.join([a[0] for a in sorted_t[:3]])}")
    else:
        print(f"  Top 3 영향 변수:     {', '.join([a[0] for a in sorted_attr[:3]])}")

# 시나리오 요약 (그룹별)
print(f"\n{'─' * 50}")
print(f"📋 시나리오 분석 결과 ({len(SCENARIOS)}개):")

# 최선/최악 시나리오 계산 (현상 유지 대비)
_sc_avg = {}
_base_preds = scenario_results.get("현상 유지", {})
for name in SCENARIOS:
    if name == "현상 유지":
        continue
    _sc_avg[name] = np.mean(
        [
            (scenario_results[name]["point"][i, -1] - _base_preds["point"][i, -1])
            / abs(_base_preds["point"][i, -1])
            * 100
            for i in range(len(TICKERS))
        ]
    )
_best_name = max(_sc_avg, key=_sc_avg.get)
_worst_name = min(_sc_avg, key=_sc_avg.get)

for group, members in SCENARIO_GROUPS.items():
    print(f"\n  ── {group} ──")
    for name in members:
        if name not in scenario_results:
            continue
        parts = []
        for i, ticker in enumerate(TICKERS):
            pred = scenario_results[name]["point"][i, -1]
            base_p = _base_preds["point"][i, -1]
            change = (pred - base_p) / abs(base_p) * 100
            parts.append(f"{TICKER_NAMES[ticker]}: {change:+.2f}%")
        tag = ""
        if name == _best_name:
            tag = " ← 최선"
        elif name == _worst_name:
            tag = " ← 최악"
        print(f"    [{name}] {' | '.join(parts)}{tag}")

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

# 시나리오 요약 (최선/최악, 현상 유지 대비)
_sc_changes = {}
_base_preds_fin = scenario_results.get("현상 유지", {})
for name in SCENARIOS:
    if name == "현상 유지":
        continue
    avg_chg = np.mean(
        [
            (scenario_results[name]["point"][i, -1] - _base_preds_fin["point"][i, -1])
            / abs(_base_preds_fin["point"][i, -1])
            * 100
            for i in range(len(TICKERS))
        ]
    )
    _sc_changes[name] = avg_chg
_best_sc = max(_sc_changes, key=_sc_changes.get)
_worst_sc = min(_sc_changes, key=_sc_changes.get)
_final_lines.append(f"최선 시나리오: [{_best_sc}] 평균 {_sc_changes[_best_sc]:+.2f}%")
_final_lines.append(f"최악 시나리오: [{_worst_sc}] 평균 {_sc_changes[_worst_sc]:+.2f}%")

# 그룹별 시나리오 요약 (복합 스트레스 강조)
for group, members in SCENARIO_GROUPS.items():
    for name in members:
        if name not in _sc_changes:
            continue
        _final_lines.append(f"  [{group}] {name}: 평균 {_sc_changes[name]:+.2f}%")

# Backtest 지표 (멀티 호라이즌 — v0411)
if not df_backtest.empty:
    _final_lines.append("\n[Backtest 품질 평가]")
    for ticker in TICKERS:
        for h in BACKTEST_HORIZONS:
            sub = df_backtest[(df_backtest["ticker"] == ticker) & (df_backtest["horizon"] == h)]
            if not sub.empty:
                cov = sub["coverage_80"].mean()
                da = sub["directional_accuracy"].mean()
                cov_warn = " ⚠️신뢰구간 부족" if cov < 0.75 else ""
                da_warn = " ⚠️방향성 미달" if da < 0.55 else ""
                _final_lines.append(
                    f"  [{TICKER_NAMES[ticker]} {h}d] MAE: {sub['mae'].mean():,.0f} | "
                    f"Coverage: {cov:.1%}{cov_warn} | Direction: {da:.1%}{da_warn}"
                )
        # Conformal 보정 여부
        if ticker in conformal_factors and conformal_factors[ticker] > 1.0:
            _final_lines.append(f"  → Conformal PI ×{conformal_factors[ticker]:.2f} 보정 적용 권장")

# 시나리오 일관성 경고 (v0411)
_final_lines.append("\n[시나리오 일관성 참고]")
_final_lines.append("일부 시나리오(금리 인하/인상")
_final_lines.append("등)에서 경제적 직관과 반대 방향의 결과가 관측됨.")
_final_lines.append("XReg 선형 참조 한계로 인한 것이므로 해석 시 유의 필요.")

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
    "★ 핵심 리스크 요인 (3가지, 해당 시나리오 명시)\n"
    "★ 핵심 기회 요인 (3가지, 해당 시나리오 명시)\n"
    "★ 복합 스트레스 테스트 시사점 (1문장)\n"
    "★ 단기 모니터링 포인트 (3가지)\n\n"
    "답변은 한국어로, 실제 애널리스트 보고서 수준으로 작성해 주세요. "
    "단, 투자 손실에 대한 책임 면책 문구를 마지막에 한 줄 추가해 주세요."
)

_final_interpretation = ask_gpt(_final_prompt, system_msg=_SYSTEM_MSG, max_tokens=1500)
print("=" * 70)
print("🤖 AI 종합 투자 의견 (SENSE × TimesFM × GPT-4.1-mini)")
print("=" * 70)
print(_final_interpretation)
print(f"\n{'=' * 70}")
