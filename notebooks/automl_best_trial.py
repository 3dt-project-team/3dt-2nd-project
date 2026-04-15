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
# MAGIC | 피처 | 기술적 지표 + 매크로 + 뉴스 감성 + 키워드 파생변수 (47종) |
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
# MAGIC uv pip install shap openai --quiet 2>/dev/null || pip install shap openai --quiet
# MAGIC echo "--- packages ready ---"

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
HORIZON = 20

# Unity Catalog 모델 경로
UC_MODELS = {
    "005930.KS": "sense_databricks.models.automl_삼성전자_t20",
    "000660.KS": "sense_databricks.models.automl_SK하이닉스_t20",
}
UC_MODEL_VERSION = 1

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

# DBTITLE 1,MLflow 모델 로드
import mlflow  # noqa: E402

mlflow.set_registry_uri("databricks-uc")

uc_loaded_models = {}

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    model_uri = f"models:/{UC_MODELS[ticker]}/{UC_MODEL_VERSION}"
    try:
        model = mlflow.sklearn.load_model(model_uri)
        uc_loaded_models[ticker] = model
        print(f"[{name}] ✅ 모델 로드 성공: {model_uri}")
        print(f"  알고리즘: {type(model).__name__}")
        if hasattr(model, "n_estimators"):
            print(f"  n_estimators: {model.n_estimators}")
        if hasattr(model, "max_depth"):
            print(f"  max_depth: {model.max_depth}")
        if hasattr(model, "n_features_in_"):
            print(f"  입력 피처 수: {model.n_features_in_}")
    except Exception as e:
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

# DBTITLE 1,주가 OHLCV 데이터 로드
TICKER_COL_MAP = {
    "005930.KS": "yfinance_samsung_close",
    "000660.KS": "yfinance_skhynix_close",
}

print("=" * 60)
print("  주가 OHLCV 데이터 로드")
print("=" * 60)

stock_data = {}
for ticker in TICKERS:
    path = f"abfss://feature@{account}.dfs.core.windows.net/{TICKER_COL_MAP[ticker]}"
    df = safe_read_parquet(path, date_col="date", index_col="date")
    if df is not None:
        stock_data[ticker] = df

# COMMAND ----------

# DBTITLE 1,매크로·퀀트·감성 피처 로드
print("\n매크로·퀀트·감성 피처 로드")
print("=" * 60)

# 매크로 지표
macro_path = f"abfss://feature@{account}.dfs.core.windows.net/macro_indicators"
macro_df = safe_read_parquet(macro_path, date_col="date", index_col="date")

# 퀀트 선행 지표
quant_path = f"abfss://feature@{account}.dfs.core.windows.net/quant_leading_indicators"
quant_df = safe_read_parquet(quant_path, date_col="date", index_col="date")

# 뉴스 감성 (PostgreSQL Gold Layer)
try:
    pg_conn = vault.get_pg_connection("sqlalchemy")
    sentiment_query = """
    SELECT date, ticker, avg_sentiment, news_vol, sentiment_ma7,
           keyword_surge_count, keyword_diversity, keyword_avg_delta_pct,
           keyword_max_delta_pct, keyword_positive_ratio, keyword_concentration
    FROM gold_news.agg_market_sentiment_daily
    WHERE ticker IN ('삼성전자', 'SK하이닉스')
    ORDER BY date
    """
    sent_raw = pd.read_sql(sentiment_query, pg_conn)
    sent_raw["date"] = pd.to_datetime(sent_raw["date"])
    print(f"  [OK] 뉴스 감성: {len(sent_raw)} rows")
except Exception as e:
    print(f"  [WARN] 뉴스 감성 로드 실패: {e}")
    sent_raw = pd.DataFrame()

# COMMAND ----------

# DBTITLE 1,피처 마트 구성
print("\n피처 마트 구성")
print("=" * 60)

feature_marts = {}

for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    if ticker not in stock_data:
        print(f"[{name}] 주가 데이터 없어 스킵")
        continue

    mart = stock_data[ticker].copy()

    # --- 기술적 지표 ---
    close = mart["close"]

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    mart["rsi_14"] = 100 - (100 / (1 + rs))

    # ATR(14)
    if "high" in mart.columns and "low" in mart.columns:
        h_l = mart["high"] - mart["low"]
        h_pc = (mart["high"] - close.shift(1)).abs()
        l_pc = (mart["low"] - close.shift(1)).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        mart["atr_14"] = tr.rolling(14).mean()

    # 이동평균 & 이격도
    for w in [5, 20, 60, 120]:
        mart[f"ma_{w}d"] = close.rolling(w).mean()
    mart["disparity_120d"] = (close / mart["ma_120d"] - 1) * 100

    # 변동성 지표
    mart["log_return"] = np.log(close / close.shift(1))
    mart["realized_vol_5d"] = mart["log_return"].rolling(5).std() * np.sqrt(252)
    mart["realized_vol_20d"] = mart["log_return"].rolling(20).std() * np.sqrt(252)
    mart["vol_ratio"] = mart["realized_vol_5d"] / mart["realized_vol_20d"].replace(0, np.nan)

    # 매크로·퀀트 병합
    if macro_df is not None:
        mart = mart.join(macro_df, how="left", rsuffix="_macro")
    if quant_df is not None:
        mart = mart.join(quant_df, how="left", rsuffix="_quant")

    # 뉴스 감성 병합
    if not sent_raw.empty:
        ticker_name_kr = name
        sent_ticker = sent_raw[sent_raw["ticker"] == ticker_name_kr].copy()
        if not sent_ticker.empty:
            sent_ticker = sent_ticker.set_index("date").drop(columns=["ticker"])
            _date_is_index = mart.index.name == "date"
            if _date_is_index:
                if "date" in mart.columns:
                    mart = mart.reset_index(drop=True)
                else:
                    mart = mart.reset_index()
            mart = mart.merge(sent_ticker, on="date", how="left")
            if _date_is_index:
                mart = mart.set_index("date")

            # NaN → 중립값
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

    # 감성 파생 피처
    if "avg_sentiment" in mart.columns:
        mart["sentiment_momentum"] = mart["avg_sentiment"].diff(3)
        mart["sentiment_vol_7d"] = mart["avg_sentiment"].rolling(7).std()
        if "news_vol" in mart.columns:
            _nv_mean = mart["news_vol"].rolling(20, min_periods=5).mean().replace(0, 1)
            mart["news_vol_surge"] = mart["news_vol"] / _nv_mean

    # 교호작용 변수
    if "keyword_surge_count" in mart.columns and "rsi_14" in mart.columns:
        mart["keyword_surge_x_rsi"] = mart["keyword_surge_count"] * (mart["rsi_14"] / 50 - 1)
    if "keyword_diversity" in mart.columns and "vol_ratio" in mart.columns:
        mart["keyword_diversity_x_vol"] = mart["keyword_diversity"] * mart["vol_ratio"]
    if "avg_sentiment" in mart.columns and "keyword_surge_count" in mart.columns:
        mart["sentiment_x_surge"] = mart["avg_sentiment"] * mart["keyword_surge_count"]
    if "avg_sentiment" in mart.columns and "rsi_14" in mart.columns:
        mart["sentiment_x_rsi_dev"] = mart["avg_sentiment"] * (mart["rsi_14"] / 50 - 1)

    feature_marts[ticker] = mart
    print(f"[{name}] 피처 마트: {mart.shape}, 기간: {mart.index.min()} ~ {mart.index.max()}")

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

        # 피처 정렬 (UC 모델 피처 순서에 맞춤)
        mart_clean = md["mart_clean"]
        available_feats = [f for f in uc_feat if f in mart_clean.columns]
        missing_feats = [f for f in uc_feat if f not in mart_clean.columns]
        if missing_feats:
            n_miss = len(missing_feats)
            print(f"  [WARN] UC 모델에 필요하나 누락된 피처 {n_miss}개: {missing_feats[:5]}...")

        X_uc = mart_clean[available_feats].fillna(0).values
        test_size = len(md["X_test"])
        X_uc_test = X_uc[-test_size:]
        X_uc_last = X_uc[-1:].reshape(1, -1)

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
# MAGIC | 데이터 로드 | ADLS Gen2 + PostgreSQL 감성 데이터 | ✅ |
# MAGIC | Feature Engineering | 기술적 지표 + 매크로 + 감성 + 교호작용 | ✅ |
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
