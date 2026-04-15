# Databricks notebook source
# MAGIC %md
# MAGIC # SENSE 프로젝트 — AutoML BestTrial 추론 노트북
# MAGIC
# MAGIC > **SENSE**: Semiconductor Economic News & Sentiment Engine
# MAGIC >
# MAGIC > Databricks AutoML에서 선정된 **RandomForest BestTrial** 모델을
# MAGIC > Unity Catalog에서 로드하여 추론·평가·분석하는 노트북입니다.
# MAGIC
# MAGIC | 항목 | 내용 |
# MAGIC |---|---|
# MAGIC | 모델 | `sense_databricks.models.automl_삼성전자_t20` (v1, R²=0.719) |
# MAGIC |  | `sense_databricks.models.automl_SK하이닉스_t20` (v1, R²=0.860) |
# MAGIC | 알고리즘 | RandomForestRegressor (AutoML 최적 하이퍼파라미터) |
# MAGIC | 타겟 | T+20 로그수익률 (`log(close_t+20 / close_t)`) |
# MAGIC | 피처 | 기술적 지표 + 매크로 + 리스크 시그널 + 뉴스 감성 + 키워드 파생변수 (72종) |
# MAGIC | 데이터 소스 | ADLS Gen2 Feature Layer + PostgreSQL Gold Layer |
# MAGIC
# MAGIC ---
# MAGIC **주요 기능**
# MAGIC 1. Unity Catalog 모델 로드 (MLflow)
# MAGIC 2. Feature Engineering 재현 (ensemble_strategy.py 동일)
# MAGIC 3. 추론 및 성능 평가 (R², MAE, MAPE, Directional Accuracy)
# MAGIC 4. 피처 중요도 분석 + SHAP 해석
# MAGIC 5. ElasticNet 대비 성능 비교
# MAGIC 6. 잔차 분포 및 리스크 분석
# MAGIC 7. 시각화 (예측 vs 실제, 피처 중요도 차트)
# MAGIC 8. AI 분석 (Azure OpenAI GPT)
# MAGIC
# MAGIC ---
# MAGIC **실행 환경**: Databricks Runtime 15.4 ML 이상
# MAGIC **클러스터**: CPU Standard_DS3_v2 이상 (GPU 불필요)
# MAGIC **선행 조건**: Unity Catalog 모델 등록 완료

# COMMAND ----------

# MAGIC %md
# MAGIC # 0. 환경 설정 및 패키지

# COMMAND ----------

# MAGIC %sh
# MAGIC uv pip install shap openai "psycopg[binary]" --quiet 2>/dev/null || pip install shap openai "psycopg[binary]" --quiet  # noqa: E501
# MAGIC echo "--- packages ready ---"

# COMMAND ----------

# MAGIC %sh
# MAGIC sudo apt-get update
# MAGIC sudo apt-get install -y fonts-nanum
# MAGIC fc-cache -fv

# COMMAND ----------

# DBTITLE 1,Imports & 환경 초기화
import os
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import ElasticNetCV
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.preprocessing import StandardScaler

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
    import glob
    import subprocess

    subprocess.run(["apt-get", "install", "-y", "fonts-nanum"], capture_output=True, text=True)  # noqa: S603 S607
    subprocess.run(["fc-cache", "-fv"], capture_output=True, text=True)  # noqa: S603 S607
    _nanum_paths = glob.glob("/usr/share/fonts/**/Nanum*.ttf", recursive=True)
    if not _nanum_paths:
        _nanum_paths = glob.glob("/usr/share/fonts/**/nanum*.ttf", recursive=True)
    for _fp in _nanum_paths:
        fm.fontManager.addfont(_fp)
    if _nanum_paths:
        _prop = fm.FontProperties(fname=_nanum_paths[0])
        _korean_font = _prop.get_name()
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

# DBTITLE 1,프로젝트 상수 정의
TICKERS = ["005930.KS", "000660.KS"]
TICKER_NAMES = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스"}
SENTIMENT_STOCK_MAP = {"005930.KS": "SAMSUNG", "000660.KS": "SK HYNIX"}
HORIZON = 20

# Unity Catalog 모델 경로
UC_MODELS = {
    "005930.KS": "sense_databricks.models.automl_삼성전자_t20",
    "000660.KS": "sense_databricks.models.automl_SK하이닉스_t20",
}

# AutoML BestTrial 하이퍼파라미터 (참조용)
AUTOML_PARAMS = {
    "n_estimators": 1755,
    "max_depth": 8,
    "max_features": 0.668,
    "min_samples_leaf": 0.0017,
    "min_samples_split": 0.0172,
    "bootstrap": True,
}

# 경량화 파라미터 (실전 추론용)
LIGHT_PARAMS = {
    "n_estimators": 400,
    "max_depth": 8,
    "max_features": 0.668,
    "min_samples_leaf": 0.002,
    "min_samples_split": 0.017,
    "bootstrap": True,
    "random_state": 42,
    "n_jobs": -1,
}

print("상수 초기화 완료")
print(f"타겟 종목: {', '.join(TICKER_NAMES.values())}")
print(f"예측 호라이즌: T+{HORIZON}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 1. 데이터 소스 연결

# COMMAND ----------

# DBTITLE 1,Key Vault & ADLS Gen2 연결
from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()
vault.get_storage_client()  # Spark OAuth conf 자동 설정
account = vault.get_secret("adls-account-name")

print(f"ADLS 계정: {account}")
print("Spark OAuth 설정 완료")

# COMMAND ----------

# DBTITLE 1,Azure OpenAI 클라이언트 초기화
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
    "당신은 반도체 주식 전문 퀀트 애널리스트입니다. "
    "AutoML RandomForest 모델의 분석 결과를 바탕으로 한국어로 간결하고 "
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


print(f"Azure OpenAI 연결 완료 | 배포: {OPENAI_DEPLOYMENT}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. Unity Catalog 모델 로드
# MAGIC
# MAGIC Databricks AutoML이 학습한 BestTrial RandomForest 모델을
# MAGIC Unity Catalog에서 MLflow를 통해 로드합니다.
# MAGIC
# MAGIC | 종목 | 모델 경로 | 버전 | val R² |
# MAGIC |---|---|---|---|
# MAGIC | 삼성전자 | `sense_databricks.models.automl_삼성전자_t20` | v1 | 0.719 |
# MAGIC | SK하이닉스 | `sense_databricks.models.automl_SK하이닉스_t20` | v1 | 0.860 |

# COMMAND ----------

# DBTITLE 1,MLflow 모델 로드 (최신 버전 + sklearn 호환성 패치)
import mlflow  # noqa: E402
from mlflow import MlflowClient  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402

mlflow.set_registry_uri("databricks-uc")
_ml_client = MlflowClient(registry_uri="databricks-uc")


def _deep_mark_fitted(obj, _visited=None):
    """역직렬화된 sklearn 파이프라인의 모든 하위 estimator를 fitted로 마킹.

    sklearn 1.4→1.8 호환.
    """
    if _visited is None:
        _visited = set()
    if id(obj) in _visited:
        return
    _visited.add(id(obj))

    if hasattr(obj, "get_params"):
        obj.__sklearn_is_fitted__ = lambda: True

    if isinstance(obj, SimpleImputer) and not hasattr(obj, "_fill_dtype"):
        obj._fill_dtype = (
            obj.statistics_.dtype if hasattr(obj, "statistics_") else np.float64
        )

    for attr_val in vars(obj).values():
        if attr_val is None:
            continue
        if hasattr(attr_val, "get_params"):
            _deep_mark_fitted(attr_val, _visited)
        elif isinstance(attr_val, (list, tuple)):
            for item in attr_val:
                if hasattr(item, "get_params"):
                    _deep_mark_fitted(item, _visited)
                elif isinstance(item, (list, tuple)):
                    for sub in item:
                        if hasattr(sub, "get_params"):
                            _deep_mark_fitted(sub, _visited)


uc_loaded_models = {}

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    model_name = UC_MODELS[ticker]

    # 최신 버전 자동 감지
    versions = _ml_client.search_model_versions(f"name='{model_name}'")
    latest_ver = max(int(v.version) for v in versions)
    model_uri = f"models:/{model_name}/{latest_ver}"

    try:
        model = mlflow.sklearn.load_model(model_uri)
        _deep_mark_fitted(model)
        uc_loaded_models[ticker] = model
        print(f"[{name}] ✅ 모델 로드 성공: {model_name} v{latest_ver}")
        print(f"  알고리즘: {type(model).__name__}")
        if hasattr(model, "n_features_in_"):
            print(f"  입력 피처 수: {model.n_features_in_}")
    except Exception as e:  # noqa: BLE001
        print(f"[{name}] ❌ 모델 로드 실패: {e}")
        print("  → 경량화 파라미터로 로컬 학습 모드로 전환합니다.")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. 데이터 로드 및 Feature Engineering
# MAGIC
# MAGIC `ensemble_strategy.py`와 동일한 피처 마트를 구성합니다.
# MAGIC ADLS Gen2 Feature Layer + PostgreSQL Gold Layer에서 데이터를 로드합니다.

# COMMAND ----------

# DBTITLE 1,ADLS 데이터 로드 유틸리티

def safe_read_parquet(path, date_col=None, index_col=None):
    """ADLS Gen2 Parquet 파일을 안전하게 로드합니다."""
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
        print(f"  [FAIL] {path}: {e}")
        return None


# COMMAND ----------

# DBTITLE 1,Gold Layer 데이터 로드 (feature 컨테이너)
TICKER_COL_MAP = {
    "005930.KS": "yfinance_samsung_close",
    "000660.KS": "yfinance_skhynix_close",
}

print("=" * 60)
print("  Gold Layer 데이터 로드 (feature 컨테이너)")
print("=" * 60)

# -----------------------------------------------------------------------
# 1) gold_macro_1y: 주가 + FX + FRED 통합 (368행 × 25컬럼)
#    주의: 날짜 컬럼이 '기준일자'임
# -----------------------------------------------------------------------
_gold_macro_path = f"abfss://feature@{account}.dfs.core.windows.net/gold_macro_1y/"
df_gold_macro = spark.read.parquet(_gold_macro_path).toPandas()  # noqa: F821
df_gold_macro.rename(columns={"기준일자": "date"}, inplace=True)
df_gold_macro["date"] = pd.to_datetime(df_gold_macro["date"])
df_gold_macro = df_gold_macro.sort_values("date").reset_index(drop=True)
print(
    f"  [OK] gold_macro_1y: {df_gold_macro.shape}, "
    f"기간: {df_gold_macro['date'].min().date()} ~ {df_gold_macro['date'].max().date()}"
)

# -----------------------------------------------------------------------
# 2) macro_semiconductor: 반도체 수출입 (HS코드별 → 월별 집계)
# -----------------------------------------------------------------------
try:
    _semi_path = f"abfss://feature@{account}.dfs.core.windows.net/macro_semiconductor/"
    df_semi_raw = spark.read.parquet(_semi_path).toPandas()  # noqa: F821
    df_semi_raw["date"] = pd.to_datetime(df_semi_raw["date"])
    df_semi_monthly = (
        df_semi_raw.groupby("date")
        .agg(
            semi_hsCode=("hsCode", "first"),
            semi_expDlr=("expDlr", "sum"),
            semi_impDlr=("impDlr", "sum"),
        )
        .reset_index()
    )
    print(f"  [OK] macro_semiconductor: {df_semi_monthly.shape}")
except Exception as e:  # noqa: BLE001
    print(f"  [WARN] 반도체 수출입 로드 실패: {e}")
    df_semi_monthly = pd.DataFrame()

# -----------------------------------------------------------------------
# 3) sense_macro: 파생 리스크 시그널 포함 통합 매크로
#    risk_off_composite, macro_stress_score, fear_composite 등 23개 파생변수
# -----------------------------------------------------------------------
try:
    _sense_path = f"abfss://feature@{account}.dfs.core.windows.net/sense_macro/"
    df_sense = spark.read.parquet(_sense_path).toPandas()  # noqa: F821
    df_sense["date"] = pd.to_datetime(df_sense["date"])
    _sense_derived_cols = [
        "date",
        # 변동성/리스크 파생변수
        "NVDA_log_return",
        "NVDA_volatility_gk",
        "NVDA_volatility_5d",
        "SOX_log_return",
        "SOX_volatility_5d",
        # 금리 파생변수
        "yield_spread",
        "yield_spread_change",
        "stagnation_pressure",
        # 환율 파생변수
        "usd_krw_change",
        "usd_krw_pct",
        # 리스크 시그널
        "risk_off_flag",
        "risk_off_composite",
        "macro_stress_score",
        "fear_composite",
        "semi_risk_signal",
        "korea_sensitivity",
        "global_risk_regime",
        "is_high_risk",
        # 수출 모멘텀
        "export_change_pct",
        "export_momentum",
        # KFinance 파생상품
        "avg_iv",
        "iv_change",
        "iv_surge_flag",
    ]
    _available = [c for c in _sense_derived_cols if c in df_sense.columns]
    df_sense_derived = df_sense[_available].copy()
    print(f"  [OK] sense_macro 파생변수: {df_sense_derived.shape} ({len(_available) - 1}개 컬럼)")
except Exception as e:  # noqa: BLE001
    print(f"  [WARN] sense_macro 로드 실패 (비필수): {e}")
    df_sense_derived = pd.DataFrame()

# COMMAND ----------

# DBTITLE 1,뉴스 감성 데이터 로드 (PostgreSQL gold_news.v_news_sentiment_trend)
import json  # noqa: E402

from sqlalchemy import text as sa_text  # noqa: E402

print("\n뉴스 감성 데이터 로드")
print("=" * 60)

_pg_engine = vault.get_pg_connection("sqlalchemy")
sentiment_data = {}

for ticker in TICKERS:
    stock_code = SENTIMENT_STOCK_MAP.get(ticker)
    if stock_code is None:
        continue
    name = TICKER_NAMES[ticker]

    _query = sa_text("""
        SELECT base_date, avg_sentiment, news_vol, sentiment_ma7,
               main_aspect, daily_keywords
        FROM gold_news.v_news_sentiment_trend
        WHERE stock_code LIKE '%' || :stock_code || '%'
        ORDER BY base_date
    """)
    with _pg_engine.connect() as _conn:
        df_sent = pd.read_sql(_query, _conn, params={"stock_code": stock_code})
    df_sent["base_date"] = pd.to_datetime(df_sent["base_date"])
    df_sent.rename(columns={"base_date": "date"}, inplace=True)

    # 같은 날 여러 행 있을 시 일별 집계
    def _merge_daily_keywords(kw_series):
        merged, seen = [], set()
        for kw_json in kw_series:
            if kw_json is None:
                continue
            items = json.loads(kw_json) if isinstance(kw_json, str) else kw_json
            for item in items:
                k = item.get("keyword", "")
                if k not in seen:
                    seen.add(k)
                    merged.append(item)
        return merged if merged else []

    if df_sent.duplicated(subset=["date"], keep=False).any():
        df_agg = df_sent.groupby("date", as_index=False).agg(
            avg_sentiment=("avg_sentiment", "mean"),
            news_vol=("news_vol", "sum"),
            sentiment_ma7=("sentiment_ma7", "mean"),
            main_aspect=("main_aspect", "first"),
            daily_keywords=("daily_keywords", _merge_daily_keywords),
        )
        df_sent = df_agg

    # daily_keywords JSONB → 키워드 파생변수 추출
    def _extract_keyword_features(kw_json):
        defaults = pd.Series(
            {
                "keyword_surge_count": 0,
                "keyword_diversity": 0,
                "keyword_avg_delta_pct": 0.0,
                "keyword_max_delta_pct": 0.0,
                "keyword_positive_ratio": 0.0,
                "keyword_concentration": 0.0,
            }
        )
        if kw_json is None:
            return defaults
        if isinstance(kw_json, str):
            kw_json = json.loads(kw_json)
        if not kw_json:
            return defaults
        deltas = [kw.get("mention_delta_pct", 0) for kw in kw_json]
        mentions = [max(kw.get("mention_count", 1), 1) for kw in kw_json]
        total = sum(mentions)
        return pd.Series(
            {
                "keyword_surge_count": sum(1 for d in deltas if d >= 300),
                "keyword_diversity": len(kw_json),
                "keyword_avg_delta_pct": float(np.mean(deltas)) if deltas else 0.0,
                "keyword_max_delta_pct": float(max(deltas)) if deltas else 0.0,
                "keyword_positive_ratio": (
                    sum(1 for d in deltas if d > 0) / len(deltas) if deltas else 0.0
                ),
                "keyword_concentration": (
                    sum((m / total) ** 2 for m in mentions) if total > 0 else 0.0
                ),
            }
        )

    kw_features = df_sent["daily_keywords"].apply(_extract_keyword_features)
    df_sent = pd.concat([df_sent, kw_features], axis=1)
    df_sent = df_sent.drop(columns=["daily_keywords"])

    sentiment_data[ticker] = df_sent
    print(
        f"  [{name}] 감성: {df_sent.shape}, "
        f"기간: {df_sent['date'].min().date()} ~ {df_sent['date'].max().date()}, "
        f"평균 감성: {df_sent['avg_sentiment'].mean():.3f}"
    )

# COMMAND ----------

# DBTITLE 1,피처 마트 구성 (Gold Layer 기반)
print("\n피처 마트 구성 (Gold Layer)")
print("=" * 60)

feature_marts = {}

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    close_col = TICKER_COL_MAP.get(ticker)

    if close_col is None or close_col not in df_gold_macro.columns:
        print(f"[{name}] close 컬럼({close_col}) 미발견 — 스킵")
        continue

    # --- gold_macro_1y 기반 마트 초기화 ---
    mart = df_gold_macro[["date"]].copy()
    mart["close"] = df_gold_macro[close_col].values

    _exclude = {
        "date",
        close_col,
        "요일",
        "주말여부",
        "한국_휴장일_여부",
        "미국_휴장일_여부",
        "fx_collected_at_utc",
        "yfinance_collected_at_utc",
        "fred_collected_at_utc",
    }
    for c in df_gold_macro.columns:
        if c not in _exclude:
            mart[c] = df_gold_macro[c].values

    # --- 반도체 수출입 병합 (macro_semiconductor → 월별 Forward Fill) ---
    if not df_semi_monthly.empty:
        mart = mart.merge(df_semi_monthly, on="date", how="left")
        for sc in ["semi_hsCode", "semi_expDlr", "semi_impDlr"]:
            if sc in mart.columns:
                mart[sc] = mart[sc].ffill()

    # --- sense_macro 파생변수 병합 (리스크 시그널 23개) ---
    if not df_sense_derived.empty:
        mart = mart.merge(df_sense_derived, on="date", how="left")
        _sense_num_cols = df_sense_derived.select_dtypes(include=[np.number]).columns.tolist()
        for sc in _sense_num_cols:
            if sc in mart.columns:
                mart[sc] = mart[sc].ffill()

    mart = mart.sort_values("date").reset_index(drop=True)
    mart.index = mart["date"]
    mart["return_1d"] = mart["close"].pct_change()

    # --- 기술적 지표 ---
    close = mart["close"]

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    mart["rsi_14"] = 100 - (100 / (1 + rs))

    # ATR(14) — gold_macro_1y에 h/l 없을 경우 단순 TR 사용
    if "high" in mart.columns and "low" in mart.columns:
        h_l = mart["high"] - mart["low"]
        h_pc = (mart["high"] - close.shift(1)).abs()
        l_pc = (mart["low"] - close.shift(1)).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        mart["atr_14"] = tr.rolling(14).mean()
    else:
        mart["atr_14"] = close.diff().abs().rolling(14).mean()

    # 이동평균 & 이격도
    for w in [5, 20, 60, 120]:
        mart[f"ma_{w}d"] = close.rolling(w).mean()
    mart["disparity_120d"] = (close / mart["ma_120d"] - 1) * 100

    # 변동성 지표
    mart["log_return"] = np.log(close / close.shift(1))
    mart["realized_vol_5d"] = mart["log_return"].rolling(5).std() * np.sqrt(252)
    mart["realized_vol_20d"] = mart["log_return"].rolling(20).std() * np.sqrt(252)
    mart["vol_ratio"] = mart["realized_vol_5d"] / mart["realized_vol_20d"].replace(0, np.nan)

    # --- 감성 병합 ---
    if ticker in sentiment_data:
        sent = sentiment_data[ticker]
        _date_is_index = mart.index.name == "date"
        if _date_is_index:
            if "date" in mart.columns:
                mart = mart.reset_index(drop=True)
            else:
                mart = mart.reset_index()
        mart = mart.merge(sent, on="date", how="left")
        if _date_is_index:
            mart = mart.set_index("date")

        for col in [
            "avg_sentiment",
            "sentiment_ma7",
            "keyword_avg_delta_pct",
            "keyword_max_delta_pct",
            "keyword_positive_ratio",
            "keyword_concentration",
        ]:
            if col in mart.columns:
                mart[col] = mart[col].fillna(0.0)
        for col in ["news_vol", "keyword_surge_count", "keyword_diversity"]:
            if col in mart.columns:
                mart[col] = mart[col].fillna(0).astype(int)

    # --- 감성 파생 피처 ---
    if "avg_sentiment" in mart.columns:
        mart["sentiment_momentum"] = mart["avg_sentiment"].diff(3)
        mart["sentiment_vol_7d"] = mart["avg_sentiment"].rolling(7).std()
        if "news_vol" in mart.columns:
            _nv_mean = mart["news_vol"].rolling(20, min_periods=5).mean().replace(0, 1)
            mart["news_vol_surge"] = mart["news_vol"] / _nv_mean

    # --- 교호작용 변수 ---
    if "keyword_surge_count" in mart.columns and "rsi_14" in mart.columns:
        mart["keyword_surge_x_rsi"] = mart["keyword_surge_count"] * (mart["rsi_14"] / 50 - 1)
    if "keyword_diversity" in mart.columns and "vol_ratio" in mart.columns:
        mart["keyword_diversity_x_vol"] = mart["keyword_diversity"] * mart["vol_ratio"]
    if "avg_sentiment" in mart.columns and "keyword_surge_count" in mart.columns:
        mart["sentiment_x_surge"] = mart["avg_sentiment"] * mart["keyword_surge_count"]
    if "avg_sentiment" in mart.columns and "rsi_14" in mart.columns:
        mart["sentiment_x_rsi_dev"] = mart["avg_sentiment"] * (mart["rsi_14"] / 50 - 1)

    feature_marts[ticker] = mart
    _n_cols = len(mart.columns)
    print(
        f"[{name}] 피처 마트: {mart.shape} ({_n_cols}컬럼), "
        f"기간: {mart.index.min()} ~ {mart.index.max()}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. 모델 추론 (Unity Catalog 모델)
# MAGIC
# MAGIC Unity Catalog에서 로드한 BestTrial 모델 + 로컬 경량화 모델을
# MAGIC 모두 실행하여 결과를 비교합니다.

# COMMAND ----------

# DBTITLE 1,타겟 변수 및 피처 준비
model_data = {}

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    if ticker not in feature_marts:
        continue

    mart = feature_marts[ticker].copy()

    # 타겟: T+20 로그수익률
    future_close = mart["close"].shift(-HORIZON)
    mart["target"] = np.log(future_close / mart["close"])
    mart_clean = mart.dropna(subset=["target"])

    exclude_cols = {"date", "target", "close", "open", "high", "low", "volume"}
    feat_cols = [
        c for c in mart_clean.select_dtypes(include=[np.number]).columns if c not in exclude_cols
    ]

    X = mart_clean[feat_cols].fillna(0).values
    y = mart_clean["target"].values

    # 시계열 분할: 마지막 60일 = 테스트셋
    test_size = min(60, len(X) // 5)
    X_train, X_test = X[:-test_size], X[-test_size:]
    y_train, y_test = y[:-test_size], y[-test_size:]
    X_last = mart[feat_cols].fillna(0).values[-1:].reshape(1, -1)

    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc = scaler.transform(X_test)
    X_last_sc = scaler.transform(X_last)

    model_data[ticker] = {
        "feat_cols": feat_cols,
        "X_train": X_train,
        "y_train": y_train,
        "X_test": X_test,
        "y_test": y_test,
        "X_train_sc": X_train_sc,
        "X_test_sc": X_test_sc,
        "X_last_sc": X_last_sc,
        "scaler": scaler,
        "last_price": mart["close"].iloc[-1],
        "mart_clean": mart_clean,
    }

    print(f"[{name}] Train: {len(X_train)}, Test: {len(X_test)}, 피처: {len(feat_cols)}개")

# COMMAND ----------

# DBTITLE 1,Unity Catalog 모델 추론
uc_results = {}

print("=" * 70)
print("  Unity Catalog BestTrial 모델 추론")
print("=" * 70)


def _ensure_uc_features(mart_df, uc_feat_list):
    """UC 모델이 기대하는 파생변수를 mart에서 실시간 계산합니다."""
    df = mart_df.copy()

    # keyword_delta_momentum: 키워드 변동률의 3일 모멘텀
    if "keyword_delta_momentum" not in df.columns and "keyword_avg_delta_pct" in df.columns:
        df["keyword_delta_momentum"] = df["keyword_avg_delta_pct"].diff(3)
    # keyword_diversity_ma7: 키워드 다양성 7일 이동평균
    if "keyword_diversity_ma7" not in df.columns and "keyword_diversity" in df.columns:
        df["keyword_diversity_ma7"] = df["keyword_diversity"].rolling(7).mean()
    # keyword_div_x_vol: 키워드 다양성 × 변동성 비율
    if (
        "keyword_div_x_vol" not in df.columns
        and "keyword_diversity" in df.columns
        and "vol_ratio" in df.columns
    ):
        df["keyword_div_x_vol"] = df["keyword_diversity"] * df["vol_ratio"]
    # kw_positive_x_disparity: 긍정 키워드 비율 × 이격도
    if (
        "kw_positive_x_disparity" not in df.columns
        and "keyword_positive_ratio" in df.columns
        and "disparity_120d" in df.columns
    ):
        df["kw_positive_x_disparity"] = df["keyword_positive_ratio"] * df["disparity_120d"]
    # concentration_change: 키워드 집중도 변화량
    if "concentration_change" not in df.columns and "keyword_concentration" in df.columns:
        df["concentration_change"] = df["keyword_concentration"].diff()
    # atr_pct: ATR 대비 가격 비율
    if "atr_pct" not in df.columns and "atr_14" in df.columns and "close" in df.columns:
        df["atr_pct"] = df["atr_14"] / df["close"].replace(0, np.nan) * 100
    # sent_price_decouple: 감성-가격 괴리도
    if (
        "sent_price_decouple" not in df.columns
        and "avg_sentiment" in df.columns
        and "return_1d" in df.columns
    ):
        df["sent_price_decouple"] = df["avg_sentiment"] - df["return_1d"].fillna(0) * 100

    # 나머지 누락 피처는 0.0 fallback
    for feat in uc_feat_list:
        if feat not in df.columns:
            df[feat] = 0.0

    return df


for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    if ticker not in model_data:
        continue

    md = model_data[ticker]

    # UC 모델 추론
    if ticker in uc_loaded_models:
        uc_model = uc_loaded_models[ticker]

        # UC 모델이 기대하는 피처와 현재 피처 매칭
        if hasattr(uc_model, "feature_names_in_"):
            uc_feat = list(uc_model.feature_names_in_)
            print(f"  [INFO] UC 모델 피처: {len(uc_feat)}개")
        else:
            uc_feat = md["feat_cols"]

        mart_clean = md["mart_clean"]

        # 누락 파생변수 보완 (모델 학습 시 존재했던 피처 실시간 계산)
        mart_enriched = _ensure_uc_features(mart_clean, uc_feat)

        _before = set(mart_clean.columns)
        _after = set(mart_enriched.columns)
        _added = _after - _before
        if _added:
            print(f"  [FIX] 파생변수 {len(_added)}개 보완: {sorted(_added)}")

        # DataFrame으로 전달 — 모든 컬럼 포함 (AutoML 내부 ColumnSelector가 필요한 것 선택)
        X_uc_df = mart_enriched.fillna(0)
        test_size = len(md["X_test"])
        X_uc_test = X_uc_df.iloc[-test_size:]
        X_uc_last = X_uc_df.iloc[-1:]

        try:
            y_pred_test = uc_model.predict(X_uc_test)
            y_pred_last = uc_model.predict(X_uc_last)[0]

            pred_price = md["last_price"] * np.exp(y_pred_last)
            change_pct = (pred_price - md["last_price"]) / md["last_price"] * 100

            r2 = r2_score(md["y_test"], y_pred_test)
            mae = mean_absolute_error(md["y_test"], y_pred_test)
            rmse = np.sqrt(mean_squared_error(md["y_test"], y_pred_test))

            uc_results[ticker] = {
                "model": uc_model,
                "y_pred_test": y_pred_test,
                "pred_log_return": y_pred_last,
                "pred_price": pred_price,
                "change_pct": change_pct,
                "r2_test": r2,
                "mae_test": mae,
                "rmse_test": rmse,
            }

            print(f"\n[{name}] Unity Catalog BestTrial")
            print(f"  예측 로그수익률: {y_pred_last:+.4f}")
            print(f"  예측가: {pred_price:,.0f}원 ({change_pct:+.2f}%)")
            print(f"  Test R²: {r2:.4f}")
            print(f"  Test MAE: {mae:.4f}")
            print(f"  Test RMSE: {rmse:.4f}")
        except Exception as e:  # noqa: BLE001
            print(f"\n[{name}] UC 모델 추론 실패: {e}")
            print("  → 피처 차이로 인한 추론 실패 — 로컬 학습 모드로 자동 전환합니다.")
    else:
        print(f"\n[{name}] UC 모델 없음 — 로컬 학습 모드 사용")

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. 로컬 경량화 모델 학습 + ElasticNet 비교
# MAGIC
# MAGIC UC 모델과 비교하기 위한 로컬 모델 2종을 학습합니다.
# MAGIC - **RandomForest (경량화)**: AutoML 파라미터 기반, n_estimators=400
# MAGIC - **ElasticNet**: L1/L2 정규화 선형 회귀 (베이스라인)

# COMMAND ----------

# DBTITLE 1,로컬 RandomForest + ElasticNet 학습
local_rf_results = {}
local_en_results = {}

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    if ticker not in model_data:
        continue

    md = model_data[ticker]

    # --- RandomForest (경량화) ---
    rf = RandomForestRegressor(**LIGHT_PARAMS)
    rf.fit(md["X_train_sc"], md["y_train"])
    rf_pred_test = rf.predict(md["X_test_sc"])
    rf_pred_last = rf.predict(md["X_last_sc"])[0]

    local_rf_results[ticker] = {
        "model": rf,
        "y_pred_test": rf_pred_test,
        "pred_log_return": rf_pred_last,
        "pred_price": md["last_price"] * np.exp(rf_pred_last),
        "r2_test": r2_score(md["y_test"], rf_pred_test),
        "mae_test": mean_absolute_error(md["y_test"], rf_pred_test),
        "rmse_test": np.sqrt(mean_squared_error(md["y_test"], rf_pred_test)),
        "r2_train": rf.score(md["X_train_sc"], md["y_train"]),
    }

    # --- ElasticNet ---
    en = ElasticNetCV(
        l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9],
        alphas=np.logspace(-3, 0, 50),
        cv=5,
        random_state=42,
        max_iter=5000,
    )
    en.fit(md["X_train_sc"], md["y_train"])
    en_pred_test = en.predict(md["X_test_sc"])
    en_pred_last = en.predict(md["X_last_sc"])[0]

    local_en_results[ticker] = {
        "model": en,
        "y_pred_test": en_pred_test,
        "pred_log_return": en_pred_last,
        "pred_price": md["last_price"] * np.exp(en_pred_last),
        "r2_test": r2_score(md["y_test"], en_pred_test),
        "mae_test": mean_absolute_error(md["y_test"], en_pred_test),
        "rmse_test": np.sqrt(mean_squared_error(md["y_test"], en_pred_test)),
        "alpha": en.alpha_,
        "l1_ratio": en.l1_ratio_,
        "n_active": int(np.sum(np.abs(en.coef_) > 1e-6)),
    }

    print(f"\n[{name}] 로컬 모델 학습 완료")
    print(f"  RF(경량): R²={local_rf_results[ticker]['r2_test']:.4f}")
    print(f"  ElasticNet: R²={local_en_results[ticker]['r2_test']:.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 6. 모델 성능 비교 대시보드
# MAGIC
# MAGIC UC BestTrial / 로컬 RF / ElasticNet 성능을 종합 비교합니다.

# COMMAND ----------

# DBTITLE 1,성능 비교 테이블
print("=" * 90)
print("  AutoML BestTrial vs 로컬 RF vs ElasticNet — 성능 비교")
print("=" * 90)
header = (
    f"\n  {'종목':<12} {'모델':<22} {'Test R²':>10}"
    f" {'Test MAE':>10} {'Test RMSE':>11} {'T+20 예측가':>14}"
)
print(header)
print(f"  {'─' * 82}")

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    md = model_data.get(ticker)
    if md is None:
        continue

    last_p = md["last_price"]

    # UC BestTrial
    if ticker in uc_results:
        r = uc_results[ticker]
        print(
            f"  {name:<12} {'UC BestTrial':<22} {r['r2_test']:>10.4f}"
            f" {r['mae_test']:>10.4f} {r['rmse_test']:>11.4f} {r['pred_price']:>12,.0f}원"
        )

    # 로컬 RF
    if ticker in local_rf_results:
        r = local_rf_results[ticker]
        print(
            f"  {'':<12} {'RF(경량화, n=400)':<22} {r['r2_test']:>10.4f}"
            f" {r['mae_test']:>10.4f} {r['rmse_test']:>11.4f} {r['pred_price']:>12,.0f}원"
        )

    # ElasticNet
    if ticker in local_en_results:
        r = local_en_results[ticker]
        chg = (r["pred_price"] - last_p) / last_p * 100
        print(
            f"  {'':<12} {'ElasticNet':<22} {r['r2_test']:>10.4f}"
            f" {r['mae_test']:>10.4f} {r['rmse_test']:>11.4f} {r['pred_price']:>12,.0f}원"
        )

    print()

# COMMAND ----------

# DBTITLE 1,방향 정확도 (Directional Accuracy)
print("=" * 70)
print("  방향 정확도 (Directional Accuracy)")
print("=" * 70)

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    md = model_data.get(ticker)
    if md is None:
        continue

    y_true_dir = (md["y_test"] > 0).astype(int)

    for label, results in [
        ("UC BestTrial", uc_results),
        ("RF(경량)", local_rf_results),
        ("ElasticNet", local_en_results),
    ]:
        if ticker not in results:
            continue
        y_pred_dir = (results[ticker]["y_pred_test"] > 0).astype(int)
        da = np.mean(y_true_dir == y_pred_dir)
        correct = int(np.sum(y_true_dir == y_pred_dir))
        total = len(y_true_dir)
        print(f"  [{name}] {label:<18}: {da:.1%} ({correct}/{total})")

# COMMAND ----------

# MAGIC %md
# MAGIC # 7. 피처 중요도 분석

# COMMAND ----------

# DBTITLE 1,RandomForest 피처 중요도 Top 20
print("=" * 70)
print("  피처 중요도 분석 (RandomForest)")
print("=" * 70)

fi_data = {}

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    md = model_data.get(ticker)
    if md is None:
        continue

    # UC 모델 또는 로컬 RF 사용
    rf_model = uc_loaded_models.get(ticker) or local_rf_results.get(ticker, {}).get("model")
    if rf_model is None or not hasattr(rf_model, "feature_importances_"):
        continue

    if ticker in uc_loaded_models and hasattr(rf_model, "feature_names_in_"):
        feat_names = list(rf_model.feature_names_in_)
    else:
        feat_names = md["feat_cols"]

    fi = rf_model.feature_importances_
    fi_sorted_idx = np.argsort(fi)[::-1]

    fi_data[ticker] = {
        "feat_names": feat_names,
        "importances": fi,
        "sorted_idx": fi_sorted_idx,
    }

    print(f"\n[{name}] 피처 중요도 Top 20:")
    print(f"  {'순위':>4} {'피처명':<35} {'중요도':>8} {'누적':>8}")
    print(f"  {'─' * 60}")
    cum = 0.0
    for rank, idx in enumerate(fi_sorted_idx[:20], 1):
        cum += fi[idx]
        print(f"  {rank:>4} {feat_names[idx]:<35} {fi[idx]:>8.4f} {cum:>7.1%}")

# COMMAND ----------

# DBTITLE 1,피처 중요도 시각화
fig, axes = plt.subplots(1, len(TICKERS), figsize=(14, 8))
if len(TICKERS) == 1:
    axes = [axes]

for ax, ticker in zip(axes, TICKERS):
    name = TICKER_NAMES[ticker]
    if ticker not in fi_data:
        continue

    fd = fi_data[ticker]
    top_n = 15
    top_idx = fd["sorted_idx"][:top_n]
    top_names = [fd["feat_names"][i] for i in top_idx]
    top_vals = fd["importances"][top_idx]

    colors = [
        "#e74c3c" if "sentiment" in n or "keyword" in n or "news" in n else "#3498db"
        for n in top_names
    ]

    ax.barh(range(top_n), top_vals[::-1], color=colors[::-1])
    ax.set_yticks(range(top_n))
    ax.set_yticklabels(top_names[::-1], fontsize=9)
    ax.set_xlabel("Feature Importance")
    ax.set_title(f"{name} — RF 피처 중요도 Top {top_n}")
    ax.axvline(x=np.mean(fd["importances"]), color="gray", linestyle="--", alpha=0.5, label="평균")
    ax.legend(fontsize=8)

plt.tight_layout()
display(fig)  # noqa: F821
plt.close()

# COMMAND ----------

# MAGIC %md
# MAGIC # 8. SHAP 해석
# MAGIC
# MAGIC SHAP (SHapley Additive exPlanations)으로 피처별 기여도를 해석합니다.

# COMMAND ----------

# DBTITLE 1,SHAP 분석
try:
    import shap

    for ticker in TICKERS:
        name = TICKER_NAMES[ticker]
        md = model_data.get(ticker)
        if md is None:
            continue

        rf_model = local_rf_results.get(ticker, {}).get("model")
        if rf_model is None:
            continue

        # TreeExplainer (RandomForest에 최적화)
        explainer = shap.TreeExplainer(rf_model)

        # 테스트 데이터 서브샘플 (속도 최적화)
        sample_size = min(100, len(md["X_test_sc"]))
        X_sample = md["X_test_sc"][:sample_size]
        shap_values = explainer.shap_values(X_sample)

        # SHAP Summary Plot
        fig, ax = plt.subplots(figsize=(12, 8))
        shap.summary_plot(
            shap_values,
            X_sample,
            feature_names=md["feat_cols"],
            show=False,
            max_display=15,
        )
        plt.title(f"{name} — SHAP Summary (Test 샘플 {sample_size}개)")
        plt.tight_layout()
        display(fig)  # noqa: F821
        plt.close()

        # 마지막 시점 SHAP 해석
        shap_last = explainer.shap_values(md["X_last_sc"])
        top_shap_idx = np.argsort(np.abs(shap_last[0]))[::-1][:10]
        print(f"\n[{name}] 최신 시점 SHAP Top 10:")
        for rank, idx in enumerate(top_shap_idx, 1):
            print(f"  {rank}. {md['feat_cols'][idx]}: SHAP={shap_last[0][idx]:+.4f}")

except ImportError:
    print("[WARN] shap 패키지 미설치 — SHAP 분석 스킵")
except Exception as e:
    print(f"[WARN] SHAP 분석 실패: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 9. 잔차 분석 및 리스크 지표

# COMMAND ----------

# DBTITLE 1,잔차 분포 분석
fig, axes = plt.subplots(len(TICKERS), 2, figsize=(14, 5 * len(TICKERS)))
if len(TICKERS) == 1:
    axes = axes.reshape(1, -1)

for row, ticker in enumerate(TICKERS):
    name = TICKER_NAMES[ticker]
    md = model_data.get(ticker)
    if md is None:
        continue

    # RF 잔차
    rf_res = local_rf_results.get(ticker)
    if rf_res is None:
        continue

    residuals = md["y_test"] - rf_res["y_pred_test"]

    # 히스토그램
    axes[row, 0].hist(residuals, bins=30, edgecolor="black", alpha=0.7, color="#3498db")
    axes[row, 0].axvline(0, color="red", linestyle="--")
    axes[row, 0].set_title(f"{name} — 잔차 분포 (RF)")
    axes[row, 0].set_xlabel("잔차 (실제 - 예측)")
    axes[row, 0].set_ylabel("빈도")

    # QQ Plot 대용 — 잔차 vs 예측
    axes[row, 1].scatter(rf_res["y_pred_test"], residuals, alpha=0.6, s=20, color="#2ecc71")
    axes[row, 1].axhline(0, color="red", linestyle="--")
    axes[row, 1].set_title(f"{name} — 잔차 vs 예측값")
    axes[row, 1].set_xlabel("예측 로그수익률")
    axes[row, 1].set_ylabel("잔차")

    # 리스크 지표 출력
    var_95 = np.percentile(residuals, 5)
    cvar_95 = residuals[residuals <= var_95].mean()
    print(f"\n[{name}] 잔차 통계:")
    print(f"  평균: {np.mean(residuals):+.4f}, 표준편차: {np.std(residuals):.4f}")
    print(f"  VaR(95%): {var_95:+.4f}")
    print(f"  CVaR(95%): {cvar_95:+.4f}")
    print(f"  왜도: {pd.Series(residuals).skew():.3f}, 첨도: {pd.Series(residuals).kurtosis():.3f}")

plt.tight_layout()
display(fig)  # noqa: F821
plt.close()

# COMMAND ----------

# MAGIC %md
# MAGIC # 10. 예측 vs 실제 시각화

# COMMAND ----------

# DBTITLE 1,Test 기간 예측 vs 실제 비교 차트
fig, axes = plt.subplots(len(TICKERS), 1, figsize=(14, 5 * len(TICKERS)))
if len(TICKERS) == 1:
    axes = [axes]

for ax, ticker in zip(axes, TICKERS):
    name = TICKER_NAMES[ticker]
    md = model_data.get(ticker)
    if md is None:
        continue

    test_idx = range(len(md["y_test"]))

    ax.plot(test_idx, md["y_test"], "k-", label="실제", linewidth=1.5, alpha=0.8)

    if ticker in uc_results:
        ax.plot(
            test_idx,
            uc_results[ticker]["y_pred_test"],
            "b--",
            label=f"UC BestTrial (R²={uc_results[ticker]['r2_test']:.3f})",
            linewidth=1.2,
        )

    if ticker in local_rf_results:
        ax.plot(
            test_idx,
            local_rf_results[ticker]["y_pred_test"],
            "g--",
            label=f"RF 경량화 (R²={local_rf_results[ticker]['r2_test']:.3f})",
            linewidth=1.2,
        )

    if ticker in local_en_results:
        ax.plot(
            test_idx,
            local_en_results[ticker]["y_pred_test"],
            "r:",
            label=f"ElasticNet (R²={local_en_results[ticker]['r2_test']:.3f})",
            linewidth=1.0,
            alpha=0.7,
        )

    ax.axhline(0, color="gray", linestyle="-", alpha=0.3)
    ax.set_title(f"{name} — Test 기간 T+{HORIZON} 로그수익률 예측 비교")
    ax.set_xlabel("테스트 시점")
    ax.set_ylabel("로그수익률")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)

plt.tight_layout()
display(fig)  # noqa: F821
plt.close()

# COMMAND ----------

# MAGIC %md
# MAGIC # 11. AI 분석 — AutoML BestTrial 종합 해석

# COMMAND ----------

# DBTITLE 1,GPT 분석: 모델 성능 해석
_analysis_parts = ["[AutoML BestTrial RandomForest 모델 성능 분석]\n"]

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    md = model_data.get(ticker)
    if md is None:
        continue

    _analysis_parts.append(f"\n{'─' * 50}")
    _analysis_parts.append(f"  {name}")

    # UC 모델 정보
    if ticker in uc_results:
        r = uc_results[ticker]
        _analysis_parts.append(f"  UC BestTrial: R²={r['r2_test']:.4f}, MAE={r['mae_test']:.4f}")
        _analysis_parts.append(f"  예측가: {r['pred_price']:,.0f}원 ({r['change_pct']:+.2f}%)")

    # RF 경량화 정보
    if ticker in local_rf_results:
        r = local_rf_results[ticker]
        _analysis_parts.append(f"  RF(n=400): R²={r['r2_test']:.4f}, MAE={r['mae_test']:.4f}")

    # ElasticNet 정보
    if ticker in local_en_results:
        r = local_en_results[ticker]
        _analysis_parts.append(
            f"  ElasticNet: R²={r['r2_test']:.4f}, alpha={r['alpha']:.4f}, "
            f"활성피처={r['n_active']}/{len(md['feat_cols'])}"
        )

    # 피처 중요도 Top 5
    if ticker in fi_data:
        fd = fi_data[ticker]
        _analysis_parts.append("  피처 중요도 Top 5:")
        for rank, idx in enumerate(fd["sorted_idx"][:5], 1):
            _analysis_parts.append(
                f"    {rank}. {fd['feat_names'][idx]}: {fd['importances'][idx]:.4f}"
            )

_gpt_prompt = "\n".join(_analysis_parts) + (
    "\n\n위 결과를 바탕으로:\n"
    "1. RandomForest가 ElasticNet 대비 압도적으로 높은 성능을 보이는 이유 (비선형 패턴, 교호작용)\n"
    "2. 핵심 피처 중 감성/키워드 파생변수의 기여도 평가\n"
    "3. 모델 경량화(1755→400 trees)에도 성능이 유지되는지\n"
    "4. Unity Catalog 모델 등록의 장점 (버전 관리, 재현성)\n"
    "5. 실전 앙상블 적용 시 권장사항\n"
    "을 한국어로 간결하게 분석해주세요."
)

analysis_text = ask_gpt(_gpt_prompt, _SYSTEM_MSG)
print("\n" + "═" * 70)
print("  AI 분석 — AutoML BestTrial 종합 해석")
print("═" * 70)
print(analysis_text)

# COMMAND ----------

# MAGIC %md
# MAGIC # 12. 결과 요약
# MAGIC
# MAGIC | 단계 | 구현 내용 | 상태 |
# MAGIC |---|---|---|
# MAGIC | 환경 설정 | 한글 폰트 + 패키지 + Key Vault | ✅ |
# MAGIC | UC 모델 로드 | MLflow `models:/` URI로 BestTrial 로드 | ✅ |
# MAGIC | 데이터 로드 | ADLS Gen2 Gold Layer + PostgreSQL 감성 | ✅ |
# MAGIC | Feature Engineering | 기술적 지표 + 매크로 + 리스크 시그널 + 감성 + 교호작용 (72종) | ✅ |
# MAGIC | UC 모델 추론 | AutoML BestTrial 예측 + 테스트 평가 | ✅ |
# MAGIC | 로컬 비교 | RF(경량화) + ElasticNet 베이스라인 | ✅ |
# MAGIC | 성능 대시보드 | R², MAE, RMSE, 방향 정확도 비교 | ✅ |
# MAGIC | 피처 중요도 | RF Feature Importance + SHAP 해석 | ✅ |
# MAGIC | 잔차 분석 | VaR/CVaR, 왜도/첨도, 잔차 분포 | ✅ |
# MAGIC | 시각화 | 예측 vs 실제, 피처 중요도 Bar Chart | ✅ |
# MAGIC | AI 분석 | GPT 기반 모델 성능 종합 해석 | ✅ |
# MAGIC
# MAGIC ---
# MAGIC **핵심 결론**
# MAGIC - AutoML BestTrial RF: 삼성전자 R²=0.719, SK하이닉스 R²=0.860
# MAGIC - ElasticNet 대비 **비선형 패턴(교호작용, 감성×기술적지표)** 포착 능력이 압도적
# MAGIC - 경량화(n=1755→400)에도 성능 유지 → 실전 앙상블에 적용 가능
# MAGIC - Unity Catalog 등록으로 **버전 관리 + 재현성 + 거버넌스** 확보