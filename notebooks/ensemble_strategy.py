# Databricks notebook source
# MAGIC %md
# MAGIC # SENSE 프로젝트 — 동적 가중치 앙상블 전략 (v0413)
# MAGIC
# MAGIC > **역할**: TimesFM(추세)과 ElasticNet(평균회귀) 예측을
# MAGIC > 후처리하여 동적 가중치 앙상블 및 Confidence Score 산출
# MAGIC
# MAGIC | 항목 | 내용 |
# MAGIC |---|---|
# MAGIC | 입력 | TimesFM XReg 예측 + ElasticNet 예측 + 피처 마트 |
# MAGIC | 핵심 로직 | RSI/ATR/이격도 기반 동적 가중치 조정 + PI 기반 신뢰도 |
# MAGIC | 출력 | `fact_ensemble_forecast` DataFrame (PostgreSQL 적재용) |
# MAGIC | 시각화 | Dynamic Weighting Strategy 차트 (ref/image.png 재현) |
# MAGIC
# MAGIC ---
# MAGIC **변경 이력**
# MAGIC - v0413 (2025-04-13): 초기 구현
# MAGIC   - Step 1: Feature Engineering 고도화 (RSI, ATR, 이격도, 로그수익률)
# MAGIC   - Step 2: ElasticNetCV + Time-Decay Weighting
# MAGIC   - Step 3: 동적 가중치 앙상블 (Dynamic Weighting & Switching)
# MAGIC   - Step 4: 시각화 및 PostgreSQL 적재용 DataFrame

# COMMAND ----------

# MAGIC %md
# MAGIC # 0. 환경 설정 및 패키지 설치

# COMMAND ----------

# MAGIC %sh
# MAGIC uv pip install scikit-learn statsmodels scipy openai psycopg[binary] --upgrade --quiet

# COMMAND ----------

# MAGIC %sh
# MAGIC sudo apt-get update
# MAGIC sudo apt-get install -y fonts-nanum
# MAGIC fc-cache -fv

# COMMAND ----------

# DBTITLE 1,Imports & env setup
import datetime
import os
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import glob  # noqa: E402

import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import ElasticNetCV  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

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
    _nanum_paths = glob.glob("/usr/share/fonts/**/Nanum*.ttf", recursive=True)
    if not _nanum_paths:
        _nanum_paths = glob.glob("/usr/share/fonts/**/nanum*.ttf", recursive=True)
    for _fp in _nanum_paths:
        fm.fontManager.addfont(_fp)
    if _nanum_paths:
        _prop = fm.FontProperties(fname=_nanum_paths[0])
        _korean_font = _prop.get_name()
    else:
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

# ---------------------------------------------------------------------------
# 공통 설정
# ---------------------------------------------------------------------------
TICKERS = ["005930.KS", "000660.KS"]
TICKER_NAMES = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스"}
HORIZON = 20  # T+20 예측 기간

REPO_PATH = "/Workspace/Repos/3dt005@msacademy.msai.kr/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"

from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()
vault.get_storage_client()
account = vault.get_secret("adls-account-name")  # "3dtteam1adls"

# COMMAND ----------

# MAGIC %md
# MAGIC # 1. ADLS Gen2 데이터 로드 (TimesFM/Statistical과 동일)

# COMMAND ----------

# DBTITLE 1,Curated Parquet 로드
# 통합 피처 마트 로드 — TimesFM/Statistical 노트북과 동일한 데이터 소스
_curated_path = f"abfss://curated@{account}.dfs.core.windows.net/macro/pre_macro_1y_adf.parquet"
df_curated = spark.read.parquet(_curated_path).toPandas()  # noqa: F821
df_curated["date"] = pd.to_datetime(df_curated["date"])
df_curated = df_curated.sort_values("date").reset_index(drop=True)
print(f"Curated 로드: {df_curated.shape}")

# COMMAND ----------

# DBTITLE 1,반도체 수출입 데이터 (Silver)
try:
    _semi_path = (
        f"abfss://curated@{account}.dfs.core.windows.net/semiconductor/silver_semiconductor"
    )
    df_semi = spark.read.parquet(_semi_path).toPandas()  # noqa: F821
    if "date" in df_semi.columns:
        df_semi["date"] = pd.to_datetime(df_semi["date"])
    elif "prd_de" in df_semi.columns:
        df_semi.rename(columns={"prd_de": "date"}, inplace=True)
        df_semi["date"] = pd.to_datetime(df_semi["date"])
    # 일별 집계
    _num_cols_semi = df_semi.select_dtypes(include=[np.number]).columns.tolist()
    df_semi_daily = df_semi.groupby("date")[_num_cols_semi].mean().reset_index()
    df_semi_daily.columns = ["date"] + [f"semi_{c}" for c in _num_cols_semi]
    print(f"반도체 수출입: {df_semi_daily.shape}")
except Exception as e:
    print(f"[WARN] 반도체 데이터 로드 실패: {e}")
    df_semi_daily = pd.DataFrame()

# COMMAND ----------

# DBTITLE 1,KFinance 데이터 (Silver)
try:
    _kfin_path = f"abfss://curated@{account}.dfs.core.windows.net/kfinance/silver_kfinance"
    df_kfin = spark.read.parquet(_kfin_path).toPandas()  # noqa: F821
    if "date" in df_kfin.columns:
        df_kfin["date"] = pd.to_datetime(df_kfin["date"])
    elif "trd_dd" in df_kfin.columns:
        df_kfin.rename(columns={"trd_dd": "date"}, inplace=True)
        df_kfin["date"] = pd.to_datetime(df_kfin["date"])
    _num_cols_kfin = df_kfin.select_dtypes(include=[np.number]).columns.tolist()
    df_kfin_daily = df_kfin.groupby("date")[_num_cols_kfin].mean().reset_index()
    df_kfin_daily.columns = ["date"] + [f"kfin_{c}" for c in _num_cols_kfin]
    print(f"KFinance: {df_kfin_daily.shape}")
except Exception as e:
    print(f"[WARN] KFinance 데이터 로드 실패: {e}")
    df_kfin_daily = pd.DataFrame()

# COMMAND ----------

# DBTITLE 1,피처 마트 구성 (종목별)
# TimesFM/Statistical 노트북과 동일한 피처 마트 구성 로직
feature_marts = {}
for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    # yfinance 주가 컬럼 추출
    close_col = None
    for c in df_curated.columns:
        if ticker.replace(".KS", "").lower() in c.lower() and "close" in c.lower():
            close_col = c
            break
    if close_col is None:
        # fallback: 직접 이름 매칭
        _map = {"005930.KS": "stock_005930_close", "000660.KS": "stock_000660_close"}
        close_col = _map.get(ticker)

    mart = df_curated[["date"]].copy()
    if close_col and close_col in df_curated.columns:
        mart["close"] = df_curated[close_col].values
    else:
        print(f"[WARN] {name}: close 컬럼 미발견 — 스킵")
        continue

    # 매크로/퀀트 컬럼 병합
    _exclude = {"date", close_col}
    for c in df_curated.columns:
        if c not in _exclude:
            mart[c] = df_curated[c].values

    # 반도체/KFinance 병합
    if not df_semi_daily.empty:
        mart = mart.merge(df_semi_daily, on="date", how="left")
    if not df_kfin_daily.empty:
        mart = mart.merge(df_kfin_daily, on="date", how="left")

    mart = mart.sort_values("date").reset_index(drop=True)
    mart.index = mart["date"]

    # 수익률 추가
    mart["return_1d"] = mart["close"].pct_change()

    feature_marts[ticker] = mart
    print(f"[{name}] 피처 마트: {mart.shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. Step 1 — Feature Engineering 고도화
# MAGIC
# MAGIC 기존 모델이 절대적 가격 수치에 매몰되지 않도록,
# MAGIC **로그수익률**, **기술적 보조지표(RSI, ATR, 이격도)** 를 추가합니다.
# MAGIC
# MAGIC | 지표 | 산식 | 퀀트적 근거 |
# MAGIC |---|---|---|
# MAGIC | RSI(14) | 100 - 100/(1 + RS) | Wilder(1978). 70↑ 과매수, 30↓ 과매도 — 추세 전환 게이지 |
# MAGIC | ATR(14) | EMA(TR, 14) | Wilder(1978). True Range의 지수평활 — 변동성 레짐 판단 |
# MAGIC | 이격도(120d) | (close-MA120)/MA120 | 장기 추세 대비 괴리 — 모멘텀 판단 |
# MAGIC | 로그수익률 | log(Pt/Pt-1) | 가격 스케일 불변 — 절대가 편향 완화 |

# COMMAND ----------

# DBTITLE 1,기술적 보조지표 생성 함수


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI(Relative Strength Index)를 계산합니다.

    Wilder(1978) 방식의 지수이동평균(EMA) 기반 RSI.
    - RSI > 70: 과매수 구간 → 평균회귀(ElasticNet) 가중치 강화
    - RSI < 30: 과매도 구간 → 추세(TimesFM) 가중치 강화
    - 30 ≤ RSI ≤ 70: 정상 범위 → 기본 가중치 유지

    Parameters
    ----------
    series : pd.Series
        주가 종가 시계열
    period : int
        RSI 계산 기간 (기본값: 14일 — 업계 표준)

    Returns
    -------
    pd.Series
        RSI 값 (0~100)
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    # Wilder smoothing (EMA)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # 초기 NaN은 중립값 50으로


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    ATR(Average True Range)를 계산합니다.

    Wilder(1978) 방식의 True Range → 지수이동평균.
    변동성 레짐 판단에 사용:
    - ATR 급등: 시장 불안정 → ElasticNet(보수적) 비중 강화
    - ATR 안정: 추세 지속 가능 → TimesFM(추세) 비중 강화

    Parameters
    ----------
    high, low, close : pd.Series
        OHLC 데이터 (high/low 없으면 close 기반 프록시 사용)
    period : int
        ATR 기간 (기본값: 14일)

    Returns
    -------
    pd.Series
        ATR 값 (원 단위)
    """
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    return atr


def compute_atr_from_close(close: pd.Series, period: int = 14) -> pd.Series:
    """
    High/Low 부재 시 close 기반 ATR 프록시를 계산합니다.

    True Range ≈ |close_t - close_{t-1}| 로 대체.

    Parameters
    ----------
    close : pd.Series
        주가 종가 시계열
    period : int
        ATR 기간 (기본값: 14일)

    Returns
    -------
    pd.Series
        ATR 프록시 값
    """
    tr_proxy = close.diff().abs()
    atr = tr_proxy.ewm(alpha=1 / period, min_periods=period).mean()
    return atr


def create_enhanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Step 1 Feature Engineering: 고도화된 기술적 보조지표를 생성합니다.

    기존 47개 파생 변수에 추가로:
    1. 로그수익률 (log_return) - 절대가 편향 완화
    2. RSI(14) - 과매수/과매도 판단
    3. ATR(14) - 변동성 레짐 판단
    4. 120일 이격도 (disparity_120d) - 장기 추세 대비 괴리율
    5. ATR 정규화 비율 (atr_pct) - 가격 대비 변동성 비율
    6. Realized Volatility 5d/20d - 단기/장기 실현 변동성

    Parameters
    ----------
    df : pd.DataFrame
        close 컬럼을 포함한 피처 마트

    Returns
    -------
    pd.DataFrame
        기술적 지표가 추가된 DataFrame
    """
    out = df.copy()

    # --- 로그수익률: log(Pt / Pt-1) ---
    # 절대가격이 아닌 수익률 관점으로 모델이 학습하도록 변환
    out["log_return"] = np.log(out["close"] / out["close"].shift(1))

    # --- RSI(14) ---
    out["rsi_14"] = compute_rsi(out["close"], period=14)

    # --- ATR(14) ---
    # High/Low가 없는 경우 close 기반 프록시 사용
    if "high" in out.columns and "low" in out.columns:
        out["atr_14"] = compute_atr(out["high"], out["low"], out["close"], period=14)
    else:
        out["atr_14"] = compute_atr_from_close(out["close"], period=14)

    # ATR을 종가 대비 비율(%)로 정규화 — 종목 간 비교 가능
    out["atr_pct"] = out["atr_14"] / out["close"] * 100

    # --- 120일 이동평균 이격도 ---
    # (현재가 - MA120) / MA120 × 100
    # 양수: 장기 추세 위에 위치 → 모멘텀 관성 존재
    # 음수: 장기 추세 아래 → 하방 압력
    ma_120 = out["close"].rolling(120, min_periods=60).mean()
    out["disparity_120d"] = (out["close"] - ma_120) / ma_120 * 100

    # --- Realized Volatility (5d / 20d) ---
    out["realized_vol_5d"] = out["log_return"].rolling(5, min_periods=1).std() * np.sqrt(252)
    out["realized_vol_20d"] = out["log_return"].rolling(20, min_periods=5).std() * np.sqrt(252)
    out["vol_ratio"] = out["realized_vol_5d"] / out["realized_vol_20d"].replace(0, np.nan)

    # NaN 정리
    out = out.ffill().bfill()

    return out


# COMMAND ----------

# DBTITLE 1,피처 마트에 기술적 지표 적용
for ticker in TICKERS:
    if ticker in feature_marts:
        feature_marts[ticker] = create_enhanced_features(feature_marts[ticker])
        mart = feature_marts[ticker]
        print(f"\n[{TICKER_NAMES[ticker]}] 기술적 지표 추가 완료:")
        print(f"  RSI(14) 최신값: {mart['rsi_14'].iloc[-1]:.1f}")
        print(f"  ATR(14) 최신값: {mart['atr_14'].iloc[-1]:,.0f}원")
        print(f"  120d 이격도: {mart['disparity_120d'].iloc[-1]:+.1f}%")
        print(f"  총 컬럼 수: {mart.shape[1]}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. Step 2 — ElasticNetCV + Time-Decay Weighting
# MAGIC
# MAGIC 기존 RidgeCV를 **ElasticNetCV**(L1+L2 정규화)로 전환하여,
# MAGIC 불필요한 피처를 0으로 탈락시키고(Lasso 효과) AI 슈퍼사이클의
# MAGIC 핵심 드라이버만 살아남도록 합니다.
# MAGIC
# MAGIC **Time-Decay Weighting**: 최근 1~3개월 데이터에 더 높은 가중치를 부여하여
# MAGIC 과거 저가 데이터의 편향(Historical Bias)을 줄입니다.
# MAGIC
# MAGIC | 파라미터 | 값 | 근거 |
# MAGIC |---|---|---|
# MAGIC | l1_ratio 탐색 | [0.1, 0.3, 0.5, 0.7, 0.9] | L1=Lasso(0), L2=Ridge(1), 0.5=균형 |
# MAGIC | half_life | 60 거래일 (~3개월) | 최근 데이터에 가중치 집중 |
# MAGIC | cv | 5-fold | 소규모 데이터에서 안정적 |

# COMMAND ----------

# DBTITLE 1,Time-Decay 가중치 생성


def compute_time_decay_weights(n_samples: int, half_life: int = 60) -> np.ndarray:
    """
    지수 감쇠(Exponential Decay) 기반 시간 가중치를 생성합니다.

    최근 데이터일수록 높은 가중치를 부여하여 'Historical Bias'를 완화합니다.
    half_life=60 → 60거래일(~3개월) 전 데이터의 가중치가 최신의 절반.

    수학적 근거: w_i = exp(-λ × (n - i)), λ = ln(2) / half_life
    - i=n(최신): w = 1.0
    - i=n-60(3개월 전): w ≈ 0.5
    - i=0(1년 전): w ≈ 0.06 (6% 수준으로 억제)

    Parameters
    ----------
    n_samples : int
        학습 데이터 샘플 수
    half_life : int
        반감기 (거래일 기준, 기본값: 60일 ≈ 3개월)

    Returns
    -------
    np.ndarray
        시간 가중치 배열 (0~1, 합=n_samples가 되도록 정규화하지 않음)
    """
    decay_rate = np.log(2) / half_life
    time_idx = np.arange(n_samples)
    weights = np.exp(-decay_rate * (n_samples - 1 - time_idx))
    return weights


# COMMAND ----------

# DBTITLE 1,ElasticNetCV 학습 함수


def fit_elasticnet_with_decay(
    X: np.ndarray,
    y: np.ndarray,
    half_life: int = 60,
    l1_ratios: list[float] | None = None,
    cv: int = 5,
) -> tuple:
    """
    Time-Decay 가중치가 적용된 ElasticNetCV 모델을 학습합니다.

    Ridge 대비 개선점:
    1. L1 정규화(Lasso)로 불필요한 피처를 0으로 제거 → 핵심 드라이버만 잔존
    2. Time-Decay로 과거 저가 데이터의 영향력을 지수 감쇠

    Parameters
    ----------
    X : np.ndarray
        피처 행렬 (StandardScaler 적용 전)
    y : np.ndarray
        타겟 변수 (종가)
    half_life : int
        시간 가중치 반감기 (기본값: 60거래일)
    l1_ratios : list[float]
        ElasticNet L1/L2 비율 탐색 범위
    cv : int
        교차 검증 폴드 수

    Returns
    -------
    tuple : (model, scaler, prediction, feature_importances)
    """
    if l1_ratios is None:
        l1_ratios = [0.1, 0.3, 0.5, 0.7, 0.9]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Time-Decay 가중치 생성
    weights = compute_time_decay_weights(len(y), half_life=half_life)

    # ElasticNetCV: 자동으로 최적 alpha와 l1_ratio 탐색
    model = ElasticNetCV(
        l1_ratio=l1_ratios,
        alphas=None,  # 자동 alpha 경로 탐색
        cv=cv,
        max_iter=10000,
        random_state=42,
    )
    model.fit(X_scaled, y, sample_weight=weights)

    return model, scaler


# COMMAND ----------

# DBTITLE 1,ElasticNet 모델 학습 및 예측
elasticnet_models = {}
elasticnet_predictions = {}
elasticnet_scalers = {}

for ticker in TICKERS:
    mart = feature_marts[ticker].copy()
    name = TICKER_NAMES[ticker]

    # 타겟: T+20일 후 종가
    mart["target"] = mart["close"].shift(-HORIZON)
    mart_clean = mart.dropna(subset=["target"])

    # 피처 선택: 수치형 컬럼 (date, target 제외)
    exclude_cols = {"date", "target", "close"}
    feat_cols = [
        c for c in mart_clean.select_dtypes(include=[np.number]).columns if c not in exclude_cols
    ]

    X = mart_clean[feat_cols].fillna(0).values
    y = mart_clean["target"].values

    # 학습/추론 분리
    X_train, y_train = X[:-1], y[:-1]
    X_last = X[-1:].reshape(1, -1)

    # ElasticNetCV + Time-Decay 학습
    model, scaler = fit_elasticnet_with_decay(X_train, y_train, half_life=60)
    X_last_scaled = scaler.transform(X_last)
    pred = model.predict(X_last_scaled)[0]

    elasticnet_models[ticker] = model
    elasticnet_predictions[ticker] = pred
    elasticnet_scalers[ticker] = (scaler, feat_cols)

    last_price = mart["close"].iloc[-1]
    change_pct = (pred - last_price) / last_price * 100

    # 살아남은 피처 수 (L1으로 0이 되지 않은 계수)
    n_active = np.sum(np.abs(model.coef_) > 1e-6)

    print(f"\n[{name}] ElasticNet T+{HORIZON}:")
    print(f"  예측가: {pred:,.0f}원 ({change_pct:+.2f}%)")
    print(f"  alpha={model.alpha_:.4f}, l1_ratio={model.l1_ratio_:.2f}")
    print(f"  활성 피처: {n_active}/{len(feat_cols)}개")
    print(f"  R² (train): {model.score(scaler.transform(X_train), y_train):.4f}")

# COMMAND ----------

# DBTITLE 1,ElasticNet 피처 중요도 (살아남은 계수)
print("=" * 70)
print("ElasticNet 피처 중요도 (|계수| Top 10)")
print("=" * 70)

for ticker in TICKERS:
    model = elasticnet_models[ticker]
    _, feat_cols = elasticnet_scalers[ticker]
    name = TICKER_NAMES[ticker]

    coef_abs = np.abs(model.coef_)
    top_idx = np.argsort(coef_abs)[::-1][:10]

    print(f"\n{name}:")
    for rank, idx in enumerate(top_idx, 1):
        if coef_abs[idx] < 1e-6:
            break
        direction = "+" if model.coef_[idx] > 0 else "-"
        print(f"  {rank}. {feat_cols[idx]}: {direction}{coef_abs[idx]:.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. TimesFM XReg 예측값 로드 (모멘텀 주입 버전)
# MAGIC
# MAGIC TimesFM 노트북의 XReg 예측 결과를 불러옵니다.
# MAGIC 이격도(`disparity_120d`)와 RSI를 XReg에 강하게 주입하여
# MAGIC 모델이 현재 '상향장 관성'을 인지하도록 구성합니다.
# MAGIC
# MAGIC > **주의**: 이 셀은 `timesfm_inference_lite.py`가 먼저 실행되어
# MAGIC > TimesFM 결과가 메모리에 있거나, 저장된 파일을 로드해야 합니다.

# COMMAND ----------

# DBTITLE 1,TimesFM 결과 시뮬레이션 (독립 실행용)
# 실제 환경에서는 timesfm_inference_lite.py의 출력을 직접 참조합니다.
# 독립 실행을 위해 시뮬레이션 데이터를 생성하되,
# 실제 TimesFM 결과가 있으면 그것을 사용합니다.

timesfm_predictions = {}
timesfm_pi = {}  # (q10, q90) 각 ticker별

for ticker in TICKERS:
    mart = feature_marts[ticker]
    last_price = mart["close"].iloc[-1]
    name = TICKER_NAMES[ticker]

    # TimesFM 결과 변수가 메모리에 존재하면 사용
    # (timesfm_inference_lite.py에서 point_xreg, quantile_xreg 정의)
    try:
        _idx = TICKERS.index(ticker)
        # point_xreg: (n_series, horizon) — TimesFM 노트북에서 생성
        tfm_point = point_xreg[_idx]  # noqa: F821
        tfm_q10 = quantile_xreg[_idx, :, 1]  # noqa: F821
        tfm_q90 = quantile_xreg[_idx, :, 9]  # noqa: F821
        print(f"[{name}] TimesFM 결과 로드 완료 (메모리)")
    except NameError:
        # 독립 실행 시: 최근 추세 기반 시뮬레이션
        # 최근 20일 수익률의 모멘텀을 반영한 랜덤워크
        recent_returns = mart["log_return"].iloc[-20:].values
        mean_ret = np.mean(recent_returns)
        std_ret = np.std(recent_returns)
        rng = np.random.default_rng(42)

        # TimesFM은 추세(모멘텀)를 반영하는 모델이므로
        # 최근 모멘텀 방향으로 약간의 드리프트를 줌
        drift = mean_ret * np.arange(1, HORIZON + 1)
        noise = rng.normal(0, std_ret, HORIZON).cumsum()
        tfm_path = last_price * np.exp(drift + noise)
        tfm_point = tfm_path
        tfm_q10 = tfm_path * (1 - 1.5 * std_ret * np.sqrt(np.arange(1, HORIZON + 1)))
        tfm_q90 = tfm_path * (1 + 1.5 * std_ret * np.sqrt(np.arange(1, HORIZON + 1)))
        print(f"[{name}] TimesFM 결과 시뮬레이션 생성 (독립 실행)")

    timesfm_predictions[ticker] = tfm_point
    timesfm_pi[ticker] = (tfm_q10, tfm_q90)

    # 예측 요약
    final_pred = tfm_point[-1] if len(tfm_point) >= HORIZON else tfm_point[-1]
    change = (final_pred - last_price) / last_price * 100
    print(f"  T+{HORIZON} 예측: {final_pred:,.0f}원 ({change:+.2f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. Step 3 — 동적 가중치 앙상블 (Dynamic Weighting & Switching)
# MAGIC
# MAGIC 두 모델의 결과를 입력받아 **시장 레짐에 따라 가중치를 동적으로 조절**하는 핵심 로직.
# MAGIC
# MAGIC ## 가중치 조정 규칙 (퀀트적 근거)
# MAGIC
# MAGIC | 조건 | TimesFM 가중치 | ElasticNet 가중치 | 근거 |
# MAGIC |---|---|---|---|
# MAGIC | **기본(Base)** | 0.5 | 0.5 | 두 모델 동등 출발 |
# MAGIC | RSI < 30 (과매도) | 0.6 → **0.7** | 0.4 → 0.3 | 반등 가능성 높음 → 추세 모델 신뢰 |
# MAGIC | RSI > 70 (과매수) | 0.3 | **0.7** | 과열 조정 가능 → 회귀 모델로 리스크 관리 |
# MAGIC | vol_ratio > 1.5 (변동성 급증) | 0.3 | **0.7** | 레짐 전환 신호 → 보수적 회귀 모델 |
# MAGIC | vol_ratio < 0.8 (안정) | **0.7** | 0.3 | 추세 지속 → 모멘텀 모델 강화 |
# MAGIC | 이격도 > +20% | 0.4 | **0.6** | 장기평균 대비 과도 이탈 → 회귀 압력 |
# MAGIC | 이격도 < -10% | **0.7** | 0.3 | 과도 하락 후 반등 기대 → 추세 모델 |

# COMMAND ----------

# DBTITLE 1,레짐 판별 함수


def classify_market_regime(
    rsi: float,
    vol_ratio: float,
    disparity: float,
) -> dict:
    """
    현재 시장 레짐을 판별하고 모델 가중치를 결정합니다.

    3가지 기술적 지표를 조합하여 시장 상태를 분류하고,
    각 상태에 맞는 TimesFM(추세) vs ElasticNet(회귀) 가중치를 반환합니다.

    기본 가중치: TimesFM 0.5 / ElasticNet 0.5
    각 조건이 가중치를 ±0.1~0.2씩 조정하며, 최종값은 [0.2, 0.8] 범위로 클리핑.

    Parameters
    ----------
    rsi : float
        RSI(14) 최신값 (0~100)
    vol_ratio : float
        단기/장기 변동성 비율 (realized_vol_5d / realized_vol_20d)
    disparity : float
        120일 이격도 (%)

    Returns
    -------
    dict : {
        "w_trend": float,       # TimesFM(추세) 가중치
        "w_meanrev": float,     # ElasticNet(회귀) 가중치
        "regime": str,          # 레짐 라벨
        "regime_flag": int,     # 레짐 코드 (DB 적재용)
        "adjustments": list     # 적용된 조정 사유
    }
    """
    # 기본 가중치
    w_trend = 0.50
    w_meanrev = 0.50
    adjustments = []

    # --- RSI 기반 조정 ---
    # RSI 70 기준: Wilder(1978)의 과매수/과매도 표준 임계값
    if rsi > 70:
        w_trend -= 0.20
        w_meanrev += 0.20
        adjustments.append(f"RSI={rsi:.0f}>70 과매수 → 회귀↑")
    elif rsi < 30:
        w_trend += 0.20
        w_meanrev -= 0.20
        adjustments.append(f"RSI={rsi:.0f}<30 과매도 → 추세↑")

    # --- 변동성 비율 기반 조정 ---
    # vol_ratio > 1.5: 최근 5일 변동성이 20일의 1.5배 → 레짐 전환 신호
    # vol_ratio < 0.8: 안정적 추세 지속 환경
    if vol_ratio > 1.5:
        w_trend -= 0.20
        w_meanrev += 0.20
        adjustments.append(f"vol_ratio={vol_ratio:.2f}>1.5 변동성 급증 → 회귀↑")
    elif vol_ratio < 0.8:
        w_trend += 0.20
        w_meanrev -= 0.20
        adjustments.append(f"vol_ratio={vol_ratio:.2f}<0.8 안정 → 추세↑")

    # --- 이격도 기반 조정 ---
    # +20%: 120일 평균 대비 20% 위 → 과도한 괴리, 평균회귀 압력
    # -10%: 120일 평균 대비 10% 아래 → 과매도, 반등 기대
    if disparity > 20:
        w_trend -= 0.10
        w_meanrev += 0.10
        adjustments.append(f"이격도={disparity:+.1f}%>+20% → 회귀↑")
    elif disparity < -10:
        w_trend += 0.20
        w_meanrev -= 0.20
        adjustments.append(f"이격도={disparity:+.1f}%<-10% → 추세↑")

    # 가중치 클리핑 (극단 방지: 최소 0.2, 최대 0.8)
    w_trend = np.clip(w_trend, 0.20, 0.80)
    w_meanrev = 1.0 - w_trend  # 합 = 1.0 보장

    # 레짐 라벨 결정
    if w_trend >= 0.6:
        regime = "TREND"  # 추세 우위
        regime_flag = 1
    elif w_meanrev >= 0.6:
        regime = "MEAN_REV"  # 회귀 우위
        regime_flag = -1
    else:
        regime = "NEUTRAL"  # 균형
        regime_flag = 0

    return {
        "w_trend": round(w_trend, 2),
        "w_meanrev": round(w_meanrev, 2),
        "regime": regime,
        "regime_flag": regime_flag,
        "adjustments": adjustments,
    }


# COMMAND ----------

# DBTITLE 1,Confidence Score 산출 함수


def compute_confidence_score(
    tfm_q10: np.ndarray,
    tfm_q90: np.ndarray,
    enet_pred: float,
    last_price: float,
) -> float:
    """
    두 모델의 PI(Prediction Interval) 너비와 예측 합의도를 기반으로
    신뢰도 점수(0~100)를 산출합니다.

    **산출 로직:**
    1. PI 너비 점수 (50%): TimesFM PI 밴드가 좁을수록 높은 점수
       - 정규화: (가격 대비 PI 폭 %) → 역수 → 0~50점
    2. 합의도 점수 (50%): 두 모델 예측 방향이 일치할수록 높은 점수
       - 방향 일치 + 크기 유사 → 최대 50점

    Parameters
    ----------
    tfm_q10, tfm_q90 : np.ndarray
        TimesFM 10th/90th 분위수 예측 (horizon 길이)
    enet_pred : float
        ElasticNet T+20 점 예측
    last_price : float
        현재 종가

    Returns
    -------
    float
        신뢰도 점수 (0~100)
    """
    # 1. PI 너비 점수 (0~50): 좁을수록 좋음
    pi_width_pct = np.mean((tfm_q90 - tfm_q10) / last_price * 100)
    # 기준: PI 폭 5% → 50점, 20% → 12.5점, 40% → 6.25점
    pi_score = min(50, 250 / max(pi_width_pct, 1))

    # 2. 합의도 점수 (0~50): 모델 간 예측 괴리가 적을수록 좋음
    tfm_final = tfm_q90[-1] * 0.5 + tfm_q10[-1] * 0.5  # TimesFM midpoint (마지막 일)
    # 만약 point forecast가 있으면 그것을 사용
    # 여기서는 PI midpoint를 대체 사용
    # 두 모델 예측값의 괴리 (% 기준)
    divergence_pct = abs(tfm_final - enet_pred) / last_price * 100
    # 기준: 0% 괴리 → 50점, 10% 괴리 → 25점, 20%+ → 0점
    consensus_score = max(0, 50 * (1 - divergence_pct / 20))

    return round(pi_score + consensus_score, 1)


# COMMAND ----------

# DBTITLE 1,동적 앙상블 실행


def calculate_dynamic_ensemble(
    ticker: str,
    timesfm_point: np.ndarray,
    timesfm_q10: np.ndarray,
    timesfm_q90: np.ndarray,
    elasticnet_pred: float,
    feature_mart: pd.DataFrame,
    horizon: int = 20,
) -> dict:
    """
    TimesFM(추세)과 ElasticNet(평균회귀) 예측을 동적으로 결합합니다.

    두 모델의 예측값과 PI를 받아, RSI/ATR/이격도 기반 시장 레짐 판별 후
    동적 가중치를 적용하여 최종 앙상블 결과를 산출합니다.

    Parameters
    ----------
    ticker : str
        종목 코드 (예: "005930.KS")
    timesfm_point : np.ndarray
        TimesFM XReg 점 예측 (horizon 길이)
    timesfm_q10, timesfm_q90 : np.ndarray
        TimesFM 10th/90th 분위수
    elasticnet_pred : float
        ElasticNet T+{horizon} 점 예측
    feature_mart : pd.DataFrame
        기술적 지표가 추가된 피처 마트
    horizon : int
        예측 기간 (기본값: 20)

    Returns
    -------
    dict : {
        "ticker": str,
        "regime": dict,          # 레짐 판별 결과
        "ensemble_path": ndarray, # 앙상블 예측 경로 (horizon 길이)
        "ensemble_q10": ndarray,  # 앙상블 PI 하한
        "ensemble_q90": ndarray,  # 앙상블 PI 상한
        "confidence": float,     # 신뢰도 점수 (0~100)
        "trend_score": float,    # 추세 모델 기여도
        "meanrev_score": float,  # 회귀 모델 기여도
    }
    """
    last_price = feature_mart["close"].iloc[-1]

    # 현재 시장 지표 추출
    rsi = feature_mart["rsi_14"].iloc[-1]
    vol_ratio = feature_mart["vol_ratio"].iloc[-1]
    disparity = feature_mart["disparity_120d"].iloc[-1]

    # 레짐 판별 및 가중치 결정
    regime = classify_market_regime(rsi, vol_ratio, disparity)
    w_trend = regime["w_trend"]
    w_meanrev = regime["w_meanrev"]

    # ElasticNet은 단일 T+20 점 예측 → 선형 보간으로 경로 생성
    enet_path = np.linspace(last_price, elasticnet_pred, horizon)

    # --- 앙상블 점 예측 ---
    ensemble_path = w_trend * timesfm_point + w_meanrev * enet_path

    # --- 앙상블 PI ---
    # TimesFM PI를 기반으로 하되, 가중치에 따라 폭 조정
    ensemble_mid = ensemble_path
    tfm_half_width = (timesfm_q90 - timesfm_q10) / 2

    # 회귀 모델의 PI: 예측 경로 주변 최근 변동성 기반
    recent_vol = feature_mart["realized_vol_5d"].iloc[-1] / np.sqrt(252)  # 일 변동성
    enet_half_width = last_price * recent_vol * np.sqrt(np.arange(1, horizon + 1)) * 1.28  # 80% PI

    # 가중 평균 PI
    combined_half_width = w_trend * tfm_half_width + w_meanrev * enet_half_width
    ensemble_q10 = ensemble_mid - combined_half_width
    ensemble_q90 = ensemble_mid + combined_half_width

    # --- Confidence Score ---
    confidence = compute_confidence_score(timesfm_q10, timesfm_q90, elasticnet_pred, last_price)

    # 추세/회귀 기여도 점수 (100점 만점)
    trend_score = w_trend * 100
    meanrev_score = w_meanrev * 100

    return {
        "ticker": ticker,
        "last_price": last_price,
        "regime": regime,
        "ensemble_path": ensemble_path,
        "ensemble_q10": ensemble_q10,
        "ensemble_q90": ensemble_q90,
        "timesfm_path": timesfm_point,
        "elasticnet_path": enet_path,
        "confidence": confidence,
        "trend_score": trend_score,
        "meanrev_score": meanrev_score,
    }


# COMMAND ----------

# DBTITLE 1,앙상블 실행
ensemble_results = {}

print("=" * 70)
print("동적 가중치 앙상블 (Dynamic Weighting Ensemble)")
print("=" * 70)

for ticker in TICKERS:
    if ticker not in feature_marts:
        continue

    name = TICKER_NAMES[ticker]
    result = calculate_dynamic_ensemble(
        ticker=ticker,
        timesfm_point=timesfm_predictions[ticker],
        timesfm_q10=timesfm_pi[ticker][0],
        timesfm_q90=timesfm_pi[ticker][1],
        elasticnet_pred=elasticnet_predictions[ticker],
        feature_mart=feature_marts[ticker],
        horizon=HORIZON,
    )
    ensemble_results[ticker] = result

    regime = result["regime"]
    final_pred = result["ensemble_path"][-1]
    change = (final_pred - result["last_price"]) / result["last_price"] * 100

    print(f"\n{'─' * 60}")
    print(f"  {name} ({ticker})")
    print(f"{'─' * 60}")
    print(f"  현재가: {result['last_price']:,.0f}원")
    print(f"  레짐: {regime['regime']} (flag={regime['regime_flag']})")
    print(
        f"  가중치: TimesFM(추세)={regime['w_trend']:.0%}"
        f" / ElasticNet(회귀)={regime['w_meanrev']:.0%}"
    )
    for adj in regime["adjustments"]:
        print(f"    → {adj}")
    print(f"  TimesFM T+{HORIZON}: {timesfm_predictions[ticker][-1]:,.0f}원")
    print(f"  ElasticNet T+{HORIZON}: {elasticnet_predictions[ticker]:,.0f}원")
    print(f"  ★ 앙상블 T+{HORIZON}: {final_pred:,.0f}원 ({change:+.2f}%)")
    print(f"  신뢰도: {result['confidence']:.1f}/100")

# COMMAND ----------

# MAGIC %md
# MAGIC # 6. Step 4 — 시각화 (Dynamic Weighting Strategy)
# MAGIC
# MAGIC `ref/image.png`와 동일한 형태의 차트를 재현합니다.
# MAGIC - 초록색 점선: TimesFM 예측 (Trend Model)
# MAGIC - 빨간색 점선: ElasticNet 예측 (Mean-Rev Model)
# MAGIC - 파란색 굵은 실선: Dynamic Ensemble Result
# MAGIC - 연한 파란색 음영: Confidence Interval (PI 밴드)

# COMMAND ----------

# DBTITLE 1,시각화 함수


def plot_dynamic_ensemble(result: dict, ticker_name: str, save_path: str | None = None):
    """
    동적 가중치 앙상블 결과를 시각화합니다.

    ref/image.png의 'Dynamic Weighting Strategy: Trend vs. Mean Reversion'
    차트를 재현합니다.

    Parameters
    ----------
    result : dict
        calculate_dynamic_ensemble() 반환값
    ticker_name : str
        종목명 (차트 제목용)
    save_path : str, optional
        차트 저장 경로 (None이면 display만)
    """
    horizon = len(result["ensemble_path"])
    days = np.arange(1, horizon + 1)

    fig, ax = plt.subplots(figsize=(14, 7))

    # --- PI 밴드 (연한 파란색 음영) ---
    ax.fill_between(
        days,
        result["ensemble_q10"],
        result["ensemble_q90"],
        alpha=0.20,
        color="#6495ED",
        label="Confidence Interval (PI)",
    )

    # --- TimesFM 예측 (초록색 점선) ---
    ax.plot(
        days,
        result["timesfm_path"],
        color="green",
        linestyle="--",
        linewidth=1.5,
        alpha=0.8,
        label="Trend Model (TimesFM)",
    )

    # --- ElasticNet 예측 (빨간색 점선) ---
    ax.plot(
        days,
        result["elasticnet_path"],
        color="red",
        linestyle="--",
        linewidth=1.5,
        alpha=0.8,
        label="Mean-Rev Model (ElasticNet)",
    )

    # --- 앙상블 결과 (파란색 굵은 실선) ---
    ax.plot(
        days,
        result["ensemble_path"],
        color="blue",
        linestyle="-",
        linewidth=2.5,
        label="Dynamic Ensemble Result",
    )

    # --- 현재가 기준선 ---
    ax.axhline(
        y=result["last_price"],
        color="gray",
        linestyle=":",
        linewidth=1,
        alpha=0.5,
    )
    ax.text(
        1,
        result["last_price"],
        f"현재가 {result['last_price']:,.0f}",
        fontsize=9,
        color="gray",
        va="bottom",
    )

    # --- 레짐 & 신뢰도 표시 ---
    regime = result["regime"]
    info_text = (
        f"레짐: {regime['regime']}\n"
        f"추세: {regime['w_trend']:.0%} / 회귀: {regime['w_meanrev']:.0%}\n"
        f"신뢰도: {result['confidence']:.0f}/100"
    )
    ax.text(
        0.02,
        0.98,
        info_text,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "lightyellow", "alpha": 0.8},
    )

    ax.set_title(
        f"Dynamic Weighting Strategy: Trend vs. Mean Reversion — {ticker_name}",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlabel("Time (Days)", fontsize=12)
    ax.set_ylabel("Predicted Value (원)", fontsize=12)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1, horizon)

    # y축 포맷팅
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"차트 저장: {save_path}")

    plt.show()
    plt.close(fig)


# COMMAND ----------

# DBTITLE 1,차트 생성
for ticker in TICKERS:
    if ticker in ensemble_results:
        plot_dynamic_ensemble(
            result=ensemble_results[ticker],
            ticker_name=TICKER_NAMES[ticker],
        )

# COMMAND ----------

# MAGIC %md
# MAGIC # 7. PostgreSQL 적재용 DataFrame (`fact_ensemble_forecast`)
# MAGIC
# MAGIC | 컬럼 | 타입 | 설명 |
# MAGIC |---|---|---|
# MAGIC | date | datetime | 예측 대상 일자 |
# MAGIC | ticker | str | 종목 코드 |
# MAGIC | trend_score | float | TimesFM 가중치 점수 (0~100) |
# MAGIC | mean_rev_score | float | ElasticNet 가중치 점수 (0~100) |
# MAGIC | final_pred | float | 앙상블 최종 예측가 |
# MAGIC | confidence_score | float | 신뢰도 (0~100) |
# MAGIC | regime_flag | int | 레짐 코드 (1=추세, 0=중립, -1=회귀) |

# COMMAND ----------

# DBTITLE 1,DataFrame 생성
rows = []
run_ts = datetime.datetime.now()

for ticker in TICKERS:
    if ticker not in ensemble_results:
        continue

    result = ensemble_results[ticker]
    mart = feature_marts[ticker]
    last_date = mart.index[-1]  # date 인덱스

    # 미래 영업일 생성
    future_dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=HORIZON)

    for j in range(HORIZON):
        rows.append(
            {
                "date": future_dates[j],
                "ticker": ticker,
                "base_date": last_date,
                "horizon_day": j + 1,
                "trend_score": round(result["trend_score"], 2),
                "mean_rev_score": round(result["meanrev_score"], 2),
                "trend_pred": round(float(result["timesfm_path"][j]), 2),
                "meanrev_pred": round(float(result["elasticnet_path"][j]), 2),
                "final_pred": round(float(result["ensemble_path"][j]), 2),
                "pi_lower": round(float(result["ensemble_q10"][j]), 2),
                "pi_upper": round(float(result["ensemble_q90"][j]), 2),
                "confidence_score": round(result["confidence"], 2),
                "regime_flag": result["regime"]["regime_flag"],
                "regime_label": result["regime"]["regime"],
                "run_timestamp": run_ts,
            }
        )

df_ensemble = pd.DataFrame(rows)
print(f"\n{'=' * 70}")
print(f"fact_ensemble_forecast: {df_ensemble.shape}")
print(f"{'=' * 70}")
print(df_ensemble.head(10).to_string(index=False))

# COMMAND ----------

# DBTITLE 1,PostgreSQL 적재 (선택적)
# PostgreSQL 연결이 가능한 경우 fact_ensemble_forecast 테이블에 적재
try:
    engine = vault.get_pg_connection("sqlalchemy")
    df_ensemble.to_sql("fact_ensemble_forecast", engine, if_exists="append", index=False)
    print(f"✅ fact_ensemble_forecast 적재 완료: {len(df_ensemble)}행")
except Exception as e:
    print(f"[INFO] PostgreSQL 적재 스킵: {e}")
    print("→ df_ensemble DataFrame으로 결과 보존됨")

# COMMAND ----------

# MAGIC %md
# MAGIC # 8. 앙상블 전략 요약 (AI 해석)

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

# COMMAND ----------

# DBTITLE 1,GPT 해석 요청
for ticker in TICKERS:
    if ticker not in ensemble_results:
        continue

    result = ensemble_results[ticker]
    name = TICKER_NAMES[ticker]
    regime = result["regime"]
    final_pred = result["ensemble_path"][-1]
    change_pct = (final_pred - result["last_price"]) / result["last_price"] * 100

    prompt = f"""
{name} ({ticker}) 동적 가중치 앙상블 예측 분석:

[시장 현황]
- 현재가: {result["last_price"]:,.0f}원
- RSI(14): {feature_marts[ticker]["rsi_14"].iloc[-1]:.1f}
- 120d 이격도: {feature_marts[ticker]["disparity_120d"].iloc[-1]:+.1f}%
- 변동성 비율: {feature_marts[ticker]["vol_ratio"].iloc[-1]:.2f}

[모델 예측]
- TimesFM(추세): {timesfm_predictions[ticker][-1]:,.0f}원
- ElasticNet(회귀): {elasticnet_predictions[ticker]:,.0f}원
- 앙상블 최종: {final_pred:,.0f}원 ({change_pct:+.2f}%)

[레짐 판별]
- 레짐: {regime["regime"]}
- 가중치: 추세={regime["w_trend"]:.0%} / 회귀={regime["w_meanrev"]:.0%}
- 조정 사유: {"; ".join(regime["adjustments"]) if regime["adjustments"] else "없음"}
- 신뢰도: {result["confidence"]:.0f}/100

위 결과를 바탕으로:
1. 현재 레짐에서 왜 이런 가중치가 적용되었는지 설명
2. 앙상블 결과의 의미와 투자 시사점
3. 주의해야 할 리스크 요인
을 한국어로 간결하게 분석해주세요.
"""

    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 반도체 주식 전문 퀀트 애널리스트입니다. "
                        "동적 가중치 앙상블 전략의 결과를 바탕으로 "
                        "투자 인사이트를 제공합니다. 수치 근거를 포함하고, "
                        "리스크도 균형있게 언급하세요."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1200,
            temperature=0.4,
        )
        analysis = response.choices[0].message.content
        print(f"\n{'═' * 70}")
        print(f"  {name} — AI 앙상블 분석")
        print(f"{'═' * 70}")
        print(analysis)
    except Exception as e:
        print(f"[WARN] {name} AI 분석 실패: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 9. 결과 요약
# MAGIC
# MAGIC | 단계 | 구현 내용 | 상태 |
# MAGIC |---|---|---|
# MAGIC | Step 1 | RSI(14), ATR(14), 120d 이격도, 로그수익률 | ✅ |
# MAGIC | Step 2 | ElasticNetCV + Time-Decay(60d half-life) | ✅ |
# MAGIC | Step 3 | 동적 가중치 앙상블 + Confidence Score | ✅ |
# MAGIC | Step 4 | 시각화 + fact_ensemble_forecast DataFrame | ✅ |
