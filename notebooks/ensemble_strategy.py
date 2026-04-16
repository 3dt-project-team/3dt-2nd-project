# Databricks notebook source
# MAGIC %md
# MAGIC # SENSE 프로젝트 — 동적 가중치 앙상블 전략 (v0418)
# MAGIC
# MAGIC > **역할**: TimesFM(추세)과 RF+ElasticNet(평균회귀) 예측을
# MAGIC > 뉴스 감성 데이터와 결합하여 동적 가중치 앙상블 및 Confidence Score 산출
# MAGIC
# MAGIC | 항목 | 내용 |
# MAGIC |---|---|
# MAGIC | 입력 | TimesFM XReg 예측 + ElasticNet 예측 + 피처 마트 + **뉴스 감성** |
# MAGIC | 핵심 로직 | Soft Switching + **뉴스 감성 가중치** + Interaction Term + PI 기반 신뢰도 |
# MAGIC | 출력 | `fact_ensemble_forecast` DataFrame (PostgreSQL 적재용) |
# MAGIC | 시각화 | Dynamic Weighting Strategy 차트 (ref/image.png 재현) |
# MAGIC
# MAGIC ---
# MAGIC **변경 이력**
# MAGIC - v0418 (2025-04-18): **AI 모델 전환 + ElasticNet 시나리오 + Date 인덱스 수정**
# MAGIC   - Section 8 AI 최종 분석 모델: gpt-4.1-mini → **gpt-5.4-mini** (Responses API)
# MAGIC   - 회귀 컴포넌트 `use_elasticnet` 플래그 추가 (RF-only 시나리오 지원)
# MAGIC   - Date 인덱스-컬럼 동시 존재 시 `reset_index(drop=True)` 충돌 수정
# MAGIC - v0417 (2025-04-17): **AutoML RandomForest 통합 + SQLAlchemy 2.x 호환**
# MAGIC   - Databricks AutoML 검증 결과 반영: RF R²=0.72(삼성)/0.86(SK) vs EN R²=0.05/-1.19
# MAGIC   - RandomForest 회귀 모델 추가 (AutoML 하이퍼파라미터: max_depth=8, n_estimators=400)
# MAGIC   - 회귀 컴포넌트 블렌딩: `regression_pred = 0.7*RF + 0.3*EN`
# MAGIC   - SQLAlchemy 2.x 호환성 수정 (`engine.connect()` + `conn.commit()`)
# MAGIC - v0416 (2025-04-16): **키워드 파생변수 + 멀티모델 비교**
# MAGIC   - `daily_keywords` JSONB → 6종 파생변수 (diversity, delta, concentration)
# MAGIC   - 교호작용 4종: surge×RSI, diversity×vol, sentiment×surge 등
# MAGIC   - Spearman/Pearson 교차검증 상관관계 분석 셀 추가
# MAGIC   - AI 중간 해석 셀 3개 추가 (키워드 상관, ElasticNet 결과, 앙상블 레짐)
# MAGIC   - 멀티모델 비교 (gpt-4.1-mini / gpt-5.4-mini / gpt-5.4 / gpt-5.4-pro)
# MAGIC   - `plt.show()` → `display(fig)` Databricks 호환 전환
# MAGIC - v0415 (2025-04-15): **뉴스 감성 통합** (News Sentiment Integration)
# MAGIC   - PostgreSQL Gold 레이어 (`gold_news.agg_market_sentiment_daily`) 연동
# MAGIC   - 감성 파생 피처: `sentiment_momentum`, `news_vol_surge`, `sentiment_vol_7d`
# MAGIC   - ElasticNet 피처에 감성 지표 자동 포함 (L1 자연 선택)
# MAGIC   - Soft Switching에 `_sentiment_weight_adjustment()` 추가
# MAGIC   - Interaction Term에 감성 × RSI 복합 규칙 추가
# MAGIC   - GPT 해석 프롬프트에 감성 컨텍스트 주입
# MAGIC - v0414 (2025-04-13): Soft Switching + 스케일링 고도화
# MAGIC   - ElasticNet 타겟을 절대가 → **로그수익률** 전환 (스케일 불변)
# MAGIC   - Alpha 검색 범위 0.001~1.0으로 축소 (과잉 정규화 방지)
# MAGIC   - Hard Threshold → **Soft Switching(선형/비선형 보간)** 전환
# MAGIC   - Interaction Term(RSI × vol_ratio 복합 신호 중첩) 추가
# MAGIC   - Confidence Score 산출 로직 개선
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
import json
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
SENTIMENT_STOCK_MAP = {"005930.KS": "SAMSUNG", "000660.KS": "SK HYNIX"}
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
# ---------------------------------------------------------------------------
# Gold Layer 데이터 로드 (feature 컨테이너) — 학습 노트북과 동일 소스
# ---------------------------------------------------------------------------
_gold_macro_path = f"abfss://feature@{account}.dfs.core.windows.net/gold_macro_1y/"
df_gold_macro = spark.read.parquet(_gold_macro_path).toPandas()  # noqa: F821
df_gold_macro.rename(columns={"기준일자": "date"}, inplace=True)
df_gold_macro["date"] = pd.to_datetime(df_gold_macro["date"])
df_gold_macro = df_gold_macro.sort_values("date").reset_index(drop=True)
print(
    f"Gold Macro 로드: {df_gold_macro.shape}, "
    f"기간: {df_gold_macro['date'].min().date()} ~ {df_gold_macro['date'].max().date()}"
)

# COMMAND ----------

# DBTITLE 1,반도체 수출입 데이터 (Silver)
# ---------------------------------------------------------------------------
# 반도체 수출입 (Gold Layer: macro_semiconductor)
# HS코드별 → 월별 집계 (학습 노트북과 동일)
# ---------------------------------------------------------------------------
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
    print(f"반도체 수출입 (monthly): {df_semi_monthly.shape}")
except Exception as e:  # noqa: BLE001
    print(f"[WARN] 반도체 데이터 로드 실패: {e}")
    df_semi_monthly = pd.DataFrame()

# COMMAND ----------

# DBTITLE 1,KFinance 데이터 (Silver)
# ---------------------------------------------------------------------------
# sense_macro: 파생 리스크 시그널 (23개 변수)
# — 학습 노트북(AutoML Stock Prediction)과 동일한 파생변수 선택
# ---------------------------------------------------------------------------
try:
    _sense_path = f"abfss://feature@{account}.dfs.core.windows.net/sense_macro/"
    df_sense = spark.read.parquet(_sense_path).toPandas()  # noqa: F821
    df_sense["date"] = pd.to_datetime(df_sense["date"])
    _sense_derived_cols = [
        "date",
        # 변동성/리스크
        "NVDA_log_return",
        "NVDA_volatility_gk",
        "NVDA_volatility_5d",
        "SOX_log_return",
        "SOX_volatility_5d",
        # 금리
        "yield_spread",
        "yield_spread_change",
        "stagnation_pressure",
        # 환율
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
        "semi_export_yoy",
        "semi_export_mom",
        # 공급 압력
        "dram_supply_pressure",
        "nand_supply_pressure",
    ]
    _available = [c for c in _sense_derived_cols if c in df_sense.columns]
    df_sense_derived = df_sense[_available].copy()
    print(f"sense_macro 파생변수: {df_sense_derived.shape}")
except Exception as e:  # noqa: BLE001
    print(f"[WARN] sense_macro 로드 실패: {e}")
    df_sense_derived = pd.DataFrame()

# COMMAND ----------

# DBTITLE 1,피처 마트 구성 (종목별)
# ---------------------------------------------------------------------------
# 종목별 피처 마트 구성 — Gold Layer 기반 (학습 노트북과 동일)
# ---------------------------------------------------------------------------
TICKER_COL_MAP = {
    "005930.KS": "yfinance_samsung_close",
    "000660.KS": "yfinance_skhynix_close",
}

feature_marts = {}
for ticker in TICKERS:
    name = TICKER_NAMES[ticker]
    close_col = TICKER_COL_MAP.get(ticker)

    if close_col is None or close_col not in df_gold_macro.columns:
        print(f"[WARN] {name}: close 컬럼({close_col}) 미발견 — 스킵")
        continue

    # --- gold_macro_1y 기반 마트 초기화 ---
    mart = df_gold_macro[["date"]].copy()
    mart["close"] = df_gold_macro[close_col].values

    # 매크로/해외주가 컬럼 병합 (date, close, 메타/비수치 컬럼 제외)
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

    # --- 반도체 수출입 병합 (monthly → Forward Fill) ---
    if not df_semi_monthly.empty:
        mart = mart.merge(df_semi_monthly, on="date", how="left")
        for sc in ["semi_hsCode", "semi_expDlr", "semi_impDlr"]:
            if sc in mart.columns:
                mart[sc] = mart[sc].ffill()

    # --- sense_macro 파생변수 병합 ---
    if not df_sense_derived.empty:
        mart = mart.merge(df_sense_derived, on="date", how="left")
        _sense_num_cols = df_sense_derived.select_dtypes(include=[np.number]).columns.tolist()
        for sc in _sense_num_cols:
            if sc in mart.columns:
                mart[sc] = mart[sc].ffill()

    mart = mart.sort_values("date").reset_index(drop=True)
    mart.index = mart["date"]

    # 수익률 추가
    mart["return_1d"] = mart["close"].pct_change()

    feature_marts[ticker] = mart
    print(f"[{name}] 피처 마트: {mart.shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 1.5. 뉴스 감성 데이터 로드 (PostgreSQL Gold Layer)
# MAGIC
# MAGIC Gold 레이어의 `gold_news.v_news_sentiment_trend` 뷰에서
# MAGIC 삼성전자/SK하이닉스의 **일별 뉴스 감성 데이터**를 로드합니다.
# MAGIC
# MAGIC > "시장은 뉴스에 선행하지만, 뉴스의 **극단적 감성**과 **급증 패턴**은
# MAGIC > 레짐 전환의 전조 신호다."
# MAGIC
# MAGIC | 컬럼 | 설명 | 앙상블 활용 |
# MAGIC |---|---|---|
# MAGIC | `avg_sentiment` | 당일 ABSA 평균 점수 (-1~+1) | Soft Switching 가중치 조정 |
# MAGIC | `news_vol` | 당일 뉴스 건수 | 뉴스량 급증 변곡점 감지 |
# MAGIC | `sentiment_ma7` | 7일 감성 이동평균 | 감성 모멘텀 추출 |
# MAGIC | `main_aspect` | 주요 뉴스 측면 카테고리 | 레짐 맥락 보조 정보 |
# MAGIC | `daily_keywords` JSONB | TOP 10 키워드 | 급증 키워드(300%↑) 카운트 |

# COMMAND ----------

# DBTITLE 1,PostgreSQL 뉴스 감성 로드
from sqlalchemy import text as sa_text  # noqa: E402

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

    # -----------------------------------------------------------------------
    # 같은 날 여러 stock_code 매칭 시 일별 집계 (공동 기사 포함)
    # -----------------------------------------------------------------------
    def _merge_daily_keywords(kw_series):
        """같은 날 여러 행의 daily_keywords JSONB를 하나로 합칩니다."""
        merged = []
        seen_kw = set()
        for kw_json in kw_series:
            if kw_json is None:
                continue
            items = json.loads(kw_json) if isinstance(kw_json, str) else kw_json
            for item in items:
                k = item.get("keyword", "")
                if k not in seen_kw:
                    seen_kw.add(k)
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

    # -----------------------------------------------------------------------
    # daily_keywords JSONB → 동적 키워드 파생변수 추출
    # -----------------------------------------------------------------------
    def _extract_keyword_features(kw_json):
        """daily_keywords JSONB에서 다차원 파생변수를 추출합니다."""
        if kw_json is None:
            return pd.Series(
                {
                    "keyword_surge_count": 0,
                    "keyword_diversity": 0,
                    "keyword_avg_delta_pct": 0.0,
                    "keyword_max_delta_pct": 0.0,
                    "keyword_positive_ratio": 0.0,
                    "keyword_concentration": 0.0,
                }
            )
        if isinstance(kw_json, str):
            kw_json = json.loads(kw_json)
        if not kw_json:
            return pd.Series(
                {
                    "keyword_surge_count": 0,
                    "keyword_diversity": 0,
                    "keyword_avg_delta_pct": 0.0,
                    "keyword_max_delta_pct": 0.0,
                    "keyword_positive_ratio": 0.0,
                    "keyword_concentration": 0.0,
                }
            )

        deltas = [kw.get("mention_delta_pct", 0) for kw in kw_json]
        mentions = [max(kw.get("mention_count", 1), 1) for kw in kw_json]
        total_mentions = sum(mentions)

        # 급증 키워드(300%↑) 카운트 (기존)
        surge_count = sum(1 for d in deltas if d >= 300)
        # 키워드 다양성: 고유 키워드 수
        diversity = len(kw_json)
        # 평균/최대 언급 변화율
        avg_delta = np.mean(deltas) if deltas else 0.0
        max_delta = max(deltas) if deltas else 0.0
        # 긍정적 변화율 비율 (언급 증가 키워드 비율)
        positive_ratio = sum(1 for d in deltas if d > 0) / len(deltas) if deltas else 0.0
        # 허핀달 집중도 지수 (1개 키워드 독점 → 1.0, 고르게 분산 → 0)
        hhi = sum((m / total_mentions) ** 2 for m in mentions) if total_mentions > 0 else 0.0

        return pd.Series(
            {
                "keyword_surge_count": surge_count,
                "keyword_diversity": diversity,
                "keyword_avg_delta_pct": avg_delta,
                "keyword_max_delta_pct": max_delta,
                "keyword_positive_ratio": positive_ratio,
                "keyword_concentration": hhi,
            }
        )

    kw_features = df_sent["daily_keywords"].apply(_extract_keyword_features)
    df_sent = pd.concat([df_sent, kw_features], axis=1)
    df_sent = df_sent.drop(columns=["daily_keywords"])

    sentiment_data[ticker] = df_sent
    print(
        f"[{name}] 뉴스 감성 로드: {df_sent.shape}, "
        f"기간: {df_sent['date'].min().date()} ~ {df_sent['date'].max().date()}, "
        f"평균 감성: {df_sent['avg_sentiment'].mean():.3f}"
    )

# COMMAND ----------

# DBTITLE 1,피처 마트에 감성 데이터 병합
for ticker in TICKERS:
    if ticker in feature_marts and ticker in sentiment_data:
        mart = feature_marts[ticker]
        sent = sentiment_data[ticker]

        # date가 인덱스이면 컬럼으로 꺼내서 merge 후 다시 인덱스 설정
        _date_is_index = mart.index.name == "date"
        if _date_is_index:
            if "date" in mart.columns:
                mart = mart.reset_index(drop=True)
            else:
                mart = mart.reset_index()
        mart = mart.merge(sent, on="date", how="left")
        if _date_is_index:
            mart = mart.set_index("date")

        # 감성 데이터 NaN 처리: 뉴스 없는 날은 중립(0) / 0건
        mart["avg_sentiment"] = mart["avg_sentiment"].fillna(0.0)
        mart["news_vol"] = mart["news_vol"].fillna(0).astype(int)
        mart["sentiment_ma7"] = mart["sentiment_ma7"].fillna(0.0)
        mart["keyword_surge_count"] = mart["keyword_surge_count"].fillna(0).astype(int)
        mart["keyword_diversity"] = mart["keyword_diversity"].fillna(0).astype(int)
        mart["keyword_avg_delta_pct"] = mart["keyword_avg_delta_pct"].fillna(0.0)
        mart["keyword_max_delta_pct"] = mart["keyword_max_delta_pct"].fillna(0.0)
        mart["keyword_positive_ratio"] = mart["keyword_positive_ratio"].fillna(0.0)
        mart["keyword_concentration"] = mart["keyword_concentration"].fillna(0.0)

        feature_marts[ticker] = mart
        name = TICKER_NAMES[ticker]
        _sent_coverage = (mart["avg_sentiment"] != 0.0).sum()
        print(
            f"[{name}] 감성 병합 완료: {mart.shape}, "
            f"감성 데이터 커버리지: {_sent_coverage}/{len(mart)}일"
        )

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. Step 1 — Feature Engineering 고도화
# MAGIC
# MAGIC 기존 모델이 절대적 가격 수치에 매몰되지 않도록,
# MAGIC **로그수익률**, **기술적 보조지표(RSI, ATR, 이격도)**, **뉴스 감성 파생 지표**를 추가합니다.
# MAGIC
# MAGIC | 지표 | 산식 | 퀀트적 근거 |
# MAGIC |---|---|---|
# MAGIC | RSI(14) | 100 - 100/(1 + RS) | Wilder(1978). 70↑ 과매수, 30↓ 과매도 — 추세 전환 게이지 |
# MAGIC | ATR(14) | EMA(TR, 14) | Wilder(1978). True Range의 지수평활 — 변동성 레짐 판단 |
# MAGIC | 이격도(120d) | (close-MA120)/MA120 | 장기 추세 대비 괴리 — 모멘텀 판단 |
# MAGIC | 로그수익률 | log(Pt/Pt-1) | 가격 스케일 불변 — 절대가 편향 완화 |
# MAGIC | 감성모멘텀 | sentiment - sentiment_ma7 | 감성 방향 변화 감지 — 심리 전환 포착 |
# MAGIC | 뉴스량급증비 | news_vol / news_vol_ma7 | 뉴스 폭증 = 변곡점 전조 신호 |
# MAGIC | 감성변동성 | std(sentiment, 7d) | 심리 불안정도 — 레짐 불확실성 |

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

    # --- 뉴스 감성 파생 피처 (Section 1.5에서 병합된 경우) ---
    if "avg_sentiment" in out.columns:
        # 감성 모멘텀: 당일 감성 - 7일 MA (양수=호전, 음수=악화)
        out["sentiment_momentum"] = out["avg_sentiment"] - out["sentiment_ma7"]

        # 뉴스량 7일 이동평균
        out["news_vol_ma7"] = out["news_vol"].rolling(7, min_periods=1).mean()

        # 뉴스량 급증 비율: 당일/7일평균 (1.0=평균, 2.0+=급증)
        out["news_vol_surge"] = out["news_vol"] / out["news_vol_ma7"].replace(0, 1)

        # 감성 변동성 (7일): 심리 불안정도
        out["sentiment_vol_7d"] = out["avg_sentiment"].rolling(7, min_periods=1).std()

        # 감성-가격 디커플링: 감성은 긍정인데 가격 하락 (또는 반대)
        if "log_return" in out.columns:
            _price_dir = np.sign(out["log_return"].rolling(5).mean())
            _sent_dir = np.sign(out["avg_sentiment"])
            out["sent_price_decouple"] = (_price_dir != _sent_dir).astype(float)

    # --- 동적 키워드 파생 피처 (교호작용 + 교차검증용) ---
    if "keyword_diversity" in out.columns:
        # 키워드 다양성 7일 이동평균 (안정적 신호)
        out["keyword_diversity_ma7"] = out["keyword_diversity"].rolling(7, min_periods=1).mean()

        # 키워드 변화율 모멘텀: 당일 avg_delta - 7일 MA
        _kw_delta_ma7 = out["keyword_avg_delta_pct"].rolling(7, min_periods=1).mean()
        out["keyword_delta_momentum"] = out["keyword_avg_delta_pct"] - _kw_delta_ma7

        # 키워드 집중도 변화: 집중 → 분산 전환 감지
        out["concentration_change"] = out["keyword_concentration"].diff()

    # --- 교호작용(Interaction) 파생변수 ---
    if "keyword_surge_count" in out.columns and "rsi_14" in out.columns:
        # 키워드 급증 × RSI: 뉴스 폭증 + 과매수 = 고위험 과열
        out["keyword_surge_x_rsi"] = out["keyword_surge_count"] * (out["rsi_14"] / 100)

    if "keyword_diversity" in out.columns and "vol_ratio" in out.columns:
        # 키워드 다양성 × 변동성비: 다양한 뉴스 + 변동성 확대 = 불확실성
        out["keyword_div_x_vol"] = out["keyword_diversity"] * out["vol_ratio"]

    if "avg_sentiment" in out.columns and "keyword_surge_count" in out.columns:
        # 감성 × 키워드 급증: 긍정 감성 + 급증 = 강한 호재 신호
        out["sentiment_x_surge"] = out["avg_sentiment"] * out["keyword_surge_count"]

    if "keyword_positive_ratio" in out.columns and "disparity_120d" in out.columns:
        # 긍정 키워드 비율 × 이격도: 낙관 + 고이격 = 과열 경고
        out["kw_positive_x_disparity"] = out["keyword_positive_ratio"] * out["disparity_120d"]

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
# MAGIC ## 2-1. 동적 키워드 파생변수 상관관계 분석
# MAGIC
# MAGIC > 키워드 파생변수 + 교호작용 변수들이 close와 얼마나 상관관계가 있는지 확인
# MAGIC > Spearman(순위) + Pearson(선형) 상관계수로 교차 검증

# COMMAND ----------

# DBTITLE 1,키워드 파생변수 상관관계 (Spearman / Pearson 교차검증)
_keyword_derived_cols = [
    "keyword_surge_count",
    "keyword_diversity",
    "keyword_avg_delta_pct",
    "keyword_max_delta_pct",
    "keyword_positive_ratio",
    "keyword_concentration",
    "keyword_diversity_ma7",
    "keyword_delta_momentum",
    "concentration_change",
    "keyword_surge_x_rsi",
    "keyword_div_x_vol",
    "sentiment_x_surge",
    "kw_positive_x_disparity",
    "sentiment_momentum",
    "news_vol_surge",
    "sentiment_vol_7d",
    "sent_price_decouple",
]

for ticker in TICKERS:
    mart = feature_marts[ticker]
    avail_kw = [c for c in _keyword_derived_cols if c in mart.columns]
    if not avail_kw:
        continue

    sub = mart[avail_kw + ["close"]].dropna()
    spearman = (
        sub.corr(method="spearman")["close"]
        .drop("close")
        .sort_values(key=lambda x: x.abs(), ascending=False)
    )
    pearson = sub.corr(method="pearson")["close"].drop("close").reindex(spearman.index)

    name = TICKER_NAMES[ticker]
    print(f"\n{'═' * 70}")
    print(f"  {name} — 키워드 파생변수 vs close 상관관계 (교차검증)")
    print(f"{'═' * 70}")
    print(f"  {'변수':<30} {'Spearman':>10} {'Pearson':>10}  {'일관성':>6}")
    print(f"  {'─' * 62}")
    for col in spearman.index:
        sp_val = spearman[col]
        pe_val = pearson[col]
        # 부호 일치하면 ✅, 불일치면 ⚠️
        consistent = "✅" if (sp_val * pe_val > 0 or abs(sp_val) < 0.01) else "⚠️"
        print(f"  {col:<30} {sp_val:>+10.4f} {pe_val:>+10.4f}  {consistent:>4}")

    # 요약 메트릭
    strong = [c for c in spearman.index if abs(spearman[c]) >= 0.1]
    print(f"\n  |Spearman| ≥ 0.1 인 변수: {len(strong)}개 / {len(avail_kw)}개")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2-2. AI 해석 — 키워드 파생변수 상관관계

# COMMAND ----------

# DBTITLE 1,GPT 해석: 키워드 파생변수 vs 주가 상관관계
from openai import AzureOpenAI  # noqa: E402

OPENAI_DEPLOYMENT = "gpt-4.1-mini"
OPENAI_API_VERSION = "2025-03-01-preview"
_openai_endpoint = vault.get_secret("azure-openai-endpoint")
_openai_key = vault.get_secret("azure-openai-key")

_ens_openai_client = AzureOpenAI(
    azure_endpoint=_openai_endpoint, api_key=_openai_key, api_version=OPENAI_API_VERSION
)

_corr_lines = ["[동적 키워드 파생변수 vs 주가 상관관계 분석 결과]\n"]
for ticker in TICKERS:
    mart = feature_marts[ticker]
    avail_kw = [c for c in _keyword_derived_cols if c in mart.columns]
    if not avail_kw:
        continue
    sub = mart[avail_kw + ["close"]].dropna()
    spearman = (
        sub.corr(method="spearman")["close"]
        .drop("close")
        .sort_values(key=lambda x: x.abs(), ascending=False)
    )
    _corr_lines.append(f"\n{TICKER_NAMES[ticker]} Spearman 상관 Top 5:")
    for rank, (col, val) in enumerate(spearman.head(5).items(), 1):
        _corr_lines.append(f"  {rank}. {col}: {val:+.4f}")

_corr_prompt = "\n".join(_corr_lines) + (
    "\n\n위 상관관계 결과를 바탕으로:\n"
    "1. 키워드 파생변수 중 주가 예측에 유용한 변수와 그 이유\n"
    "2. 교호작용 변수(keyword_surge_x_rsi 등)의 유효성 평가\n"
    "3. Spearman/Pearson 부호 불일치 변수의 비선형성 해석\n"
    "4. 모델에 포함할 변수 추천 (ElasticNet L1이 자동 선택하지만 사전 지식 기반 의견)\n"
    "을 한국어로 간결하게 분석해주세요."
)

try:
    _corr_resp = _ens_openai_client.chat.completions.create(
        model=OPENAI_DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 반도체 주식 NLP 기반 퀀트 분석가입니다. "
                    "뉴스 키워드 파생변수의 주가 예측력을 평가합니다."
                ),
            },
            {"role": "user", "content": _corr_prompt},
        ],
        max_tokens=800,
        temperature=0.3,
    )
    print(_corr_resp.choices[0].message.content)
except Exception as e:
    print(f"[WARN] AI 분석 실패: {e}")

# COMMAND ----------

# DBTITLE 1,AutoML UC 모델 설명
# MAGIC %md
# MAGIC # 3. Step 2 — AutoML UC 모델 (Unity Catalog 등록 모델)
# MAGIC
# MAGIC 기존 ElasticNetCV(R²≈0.05)를 **Databricks AutoML 에서 학습된
# MAGIC Unity Catalog 모델**로 교체합니다.
# MAGIC Gold Layer 동일 데이터로 학습된 모델이 sklearn 1.8.0 네이티브로 등록되어
# MAGIC 호환성 패치가 불필요합니다.
# MAGIC
# MAGIC | 모델 | UC 경로 | R² |
# MAGIC |---|---|---|
# MAGIC | 삼성전자 | `sense_databricks.models.automl_삼성전자_t20` v1 | 0.817 |
# MAGIC | SK하이닉스 | `sense_databricks.models.automl_SK하이닉스_t20` v1 | 0.770 |
# MAGIC
# MAGIC ### v0419 핵심 변경
# MAGIC 1. **ElasticNet 제거**: R²≈0.05(삼성)/−1.19(SK) → 예측력 부족
# MAGIC 2. **RandomForest 수동 학습 제거**: AutoML 파이프라인이 최적 모델을 자동 선택
# MAGIC 3. **UC 모델 직접 로드**: `mlflow.sklearn.load_model("models:/.../1")` → 예측
# MAGIC 4. **피처 100% 정렬**: 학습/추론 동일 Gold Layer 피처 69개

# COMMAND ----------

# DBTITLE 1,ElasticNet 모델 학습 및 예측
# ---------------------------------------------------------------------------
# Unity Catalog AutoML 모델 로드 + T+20 예측
# ---------------------------------------------------------------------------
# sklearn 1.4.2 → 1.8.0 역직렬화 호환성 패치
# 원인: __sklearn_is_fitted__ 메서드가 없는 구버전 Pipeline → NotFittedError
# 해결: 모든 하위 estimator에 __sklearn_is_fitted__ 재귀적 설정
# ---------------------------------------------------------------------------
from sklearn.impute import SimpleImputer  # noqa: E402


def _deep_mark_fitted(obj, _visited=None):
    """역직렬화된 sklearn 파이프라인의 모든 하위 estimator를 fitted로 마킹."""
    if _visited is None:
        _visited = set()
    if id(obj) in _visited:
        return
    _visited.add(id(obj))

    # sklearn estimator이면 fitted 마킹
    if hasattr(obj, "get_params"):
        obj.__sklearn_is_fitted__ = lambda: True

    # SimpleImputer._fill_dtype 누락 복원 (1.4.2 → 1.8.0)
    if isinstance(obj, SimpleImputer) and not hasattr(obj, "_fill_dtype"):
        obj._fill_dtype = obj.statistics_.dtype if hasattr(obj, "statistics_") else np.float64

    # 모든 속성을 순회하며 하위 estimator 재귀 탐색
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


print("[OK] sklearn 호환성 패치 준비 완료")

# ---------------------------------------------------------------------------
import mlflow  # noqa: E402
from mlflow import MlflowClient  # noqa: E402

mlflow.set_registry_uri("databricks-uc")
client = MlflowClient(registry_uri="databricks-uc")

UC_MODELS = {
    "005930.KS": "sense_databricks.models.automl_삼성전자_t20",
    "000660.KS": "sense_databricks.models.automl_SK하이닉스_t20",
}

automl_models = {}
automl_predictions = {}

print("=" * 70)
print("  Unity Catalog AutoML 모델 로드 + 추론")
print("=" * 70)

for ticker in TICKERS:
    if ticker not in feature_marts:
        continue
    name = TICKER_NAMES[ticker]
    model_name = UC_MODELS[ticker]

    # --- 최신 버전 조회 ---
    versions = client.search_model_versions(f"name='{model_name}'")
    latest_ver = max(int(v.version) for v in versions)
    model_uri = f"models:/{model_name}/{latest_ver}"

    # --- 모델 로드 + 호환성 패치 ---
    model = mlflow.sklearn.load_model(model_uri)
    _deep_mark_fitted(model)
    automl_models[ticker] = model
    print(f"\n  [{name}] {model_name} v{latest_ver} 로드 완료")
    print(f"    모델 타입: {type(model).__name__}")

    # --- 피처 준비 ---
    mart = feature_marts[ticker].copy()
    _drop_cols = ["date", "target"]
    _str_cols = mart.select_dtypes(include=["object", "datetime64"]).columns.tolist()
    _all_drop = list(set(_drop_cols + _str_cols))
    X_latest = mart.drop(columns=[c for c in _all_drop if c in mart.columns]).iloc[[-1]]

    # --- 예측 ---
    log_return_pred = model.predict(X_latest)[0]
    last_price = mart["close"].iloc[-1]
    price_pred = last_price * np.exp(log_return_pred)
    automl_predictions[ticker] = price_pred

    change_pct = (price_pred - last_price) / last_price * 100
    print(f"    로그수익률 예측: {log_return_pred:+.4f}")
    print(f"    T+20 예측가: {price_pred:,.0f}원 ({change_pct:+.2f}%)")
    print(f"    현재가: {last_price:,.0f}원")

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
# ---------------------------------------------------------------------------
# TimesFM 2.5 XReg 예측 결과 로드
# 우선순위: ADLS 실제 결과 > 메모리 변수 > 랜덤워크 시뮬레이션
# ---------------------------------------------------------------------------
timesfm_predictions = {}
timesfm_pi = {}  # (q10, q90) 각 ticker별
_tfm_source = "UNKNOWN"

# --- 1순위: ADLS에서 실제 TimesFM 2.5 결과 로드 ---
_tfm_path = f"abfss://feature@{account}.dfs.core.windows.net/timesfm_forecast/"
try:
    df_tfm = spark.read.parquet(_tfm_path).toPandas()  # noqa: F821
    df_tfm["forecast_date"] = pd.to_datetime(df_tfm["forecast_date"])
    df_tfm["base_date"] = pd.to_datetime(df_tfm["base_date"])

    # base_date 최신 기준으로 필터
    latest_base = df_tfm["base_date"].max()
    df_tfm = df_tfm[df_tfm["base_date"] == latest_base].sort_values(["ticker", "horizon_day"])

    print("=" * 70)
    print(f"✅ TimesFM 2.5 XReg 예측 로드 (ADLS) — base_date: {latest_base.date()}")
    print("=" * 70)

    _loaded_count = 0
    for ticker in TICKERS:
        name = TICKER_NAMES[ticker]
        df_t = df_tfm[df_tfm["ticker"] == ticker]

        if len(df_t) == 0:
            print(f"  [{name}] TimesFM 예측 없음 — 시뮬레이션으로 대체")
            continue

        tfm_point = df_t["xreg_point"].values
        tfm_q10 = df_t["xreg_q10"].values
        tfm_q90 = df_t["xreg_q90"].values

        timesfm_predictions[ticker] = tfm_point
        timesfm_pi[ticker] = (tfm_q10, tfm_q90)

        last_price = feature_marts[ticker]["close"].iloc[-1]
        final_pred = tfm_point[-1]
        change = (final_pred - last_price) / last_price * 100

        print(f"  [{name}] T+{HORIZON} 예측: {final_pred:,.0f}원 ({change:+.2f}%)")
        print(f"    PI(80%): [{tfm_q10[-1]:,.0f}, {tfm_q90[-1]:,.0f}]")
        print(f"    Macro Impact: {df_t['macro_impact'].sum():+,.0f}원 (누적)")
        _loaded_count += 1

    if _loaded_count == len(TICKERS):
        _tfm_source = "ADLS_REAL"
        print(f"\n✅ 실제 TimesFM 2.5 XReg 결과 로드 완료 ({len(df_tfm)} rows)")
    else:
        print(f"\n⚠️ 일부 종목만 로드됨 ({_loaded_count}/{len(TICKERS)})")
        _tfm_source = "ADLS_PARTIAL"

except Exception as e:  # noqa: BLE001
    print(f"[INFO] ADLS TimesFM 로드 실패: {e}")

# --- 2순위: 메모리 변수 (timesfm_inference와 동일 세션) ---
for ticker in TICKERS:
    if ticker in timesfm_predictions:
        continue  # 이미 ADLS에서 로드됨
    name = TICKER_NAMES[ticker]
    try:
        _idx = TICKERS.index(ticker)
        tfm_point = point_xreg[_idx]  # noqa: F821
        tfm_q10 = quantile_xreg[_idx, :, 1]  # noqa: F821
        tfm_q90 = quantile_xreg[_idx, :, 9]  # noqa: F821
        timesfm_predictions[ticker] = tfm_point
        timesfm_pi[ticker] = (tfm_q10, tfm_q90)
        print(f"  [{name}] TimesFM 결과 로드 완료 (메모리)")
        _tfm_source = "MEMORY" if _tfm_source == "UNKNOWN" else _tfm_source
    except NameError:
        pass

# --- 3순위: 시뮬레이션 (fallback) ---
for ticker in TICKERS:
    if ticker in timesfm_predictions:
        continue
    name = TICKER_NAMES[ticker]
    mart = feature_marts[ticker]
    last_price = mart["close"].iloc[-1]

    recent_returns = mart["log_return"].iloc[-20:].values
    mean_ret = np.mean(recent_returns)
    std_ret = np.std(recent_returns)
    rng = np.random.default_rng(42)

    drift = mean_ret * np.arange(1, HORIZON + 1)
    noise = rng.normal(0, std_ret, HORIZON).cumsum()
    tfm_path = last_price * np.exp(drift + noise)

    timesfm_predictions[ticker] = tfm_path
    timesfm_pi[ticker] = (
        tfm_path * (1 - 1.5 * std_ret * np.sqrt(np.arange(1, HORIZON + 1))),
        tfm_path * (1 + 1.5 * std_ret * np.sqrt(np.arange(1, HORIZON + 1))),
    )
    _tfm_source = "SIMULATION" if _tfm_source == "UNKNOWN" else _tfm_source

    final_pred = tfm_path[-1]
    change = (final_pred - last_price) / last_price * 100
    print(f"  ⚠️ [{name}] 시뮬레이션 생성: {final_pred:,.0f}원 ({change:+.2f}%)")
    print("    → timesfm_inference 노트북을 먼저 실행하면 실제 결과가 사용됩니다.")

print(f"\nTimesFM 데이터 소스: {_tfm_source}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. Step 3 — 동적 가중치 앙상블 (Soft Switching & Dynamic Weight Interpolation)
# MAGIC
# MAGIC 두 모델의 결과를 입력받아 **시장 레짐에 따라 가중치를 동적으로 조절**하는 핵심 로직.
# MAGIC
# MAGIC ### v0414 — Soft Switching 도입
# MAGIC > 고정 임계값(Hard Threshold)에 의한 예측값의 불연속성을 방지하고,
# MAGIC > 지표의 극단값(Extreme Values)이 갖는 통계적 유의미성을 가중치에
# MAGIC > 비례적으로 반영하기 위해 **선형/비선형 가중치 보간법**
# MAGIC > **(Dynamic Weight Interpolation)**을 적용함.
# MAGIC
# MAGIC ### v0415 — 뉴스 감성 가중치 통합
# MAGIC > **"AI 슈퍼사이클"** 서사에서 뉴스 감성은 펀더멘탈보다 빠르게
# MAGIC > 시장 심리를 반영한다. 극단적 감성(호재/악재)과 뉴스량 급증은
# MAGIC > 레짐 전환의 전조 신호로 활용되며, 기존 Soft Switching에
# MAGIC > `_sentiment_weight_adjustment()`를 추가하여 5번째 조정분을 반영.
# MAGIC
# MAGIC #### 감성 가중치 설계
# MAGIC | 조건 | 조정 | 근거 |
# MAGIC |---|---|---|
# MAGIC | avg_sentiment > 0.3 | TimesFM +0.10 | 강한 호재 → 모멘텀 지속 기대 |
# MAGIC | avg_sentiment < -0.3 | ElasticNet +0.10 | 강한 악재 → 평균회귀 기대 |
# MAGIC | news_vol_surge > 2.0 | ElasticNet +0.05 | 뉴스 폭증 → 변곡점 전조 |
# MAGIC | sentiment ↔ RSI 동조 | ±0.08 | 복합 신호 = 확신의 크기 ↑ |
# MAGIC
# MAGIC #### 가중치 함수 설계 원칙
# MAGIC | 지표 | 구간 | 보간 방식 | 근거 |
# MAGIC |---|---|---|---|
# MAGIC | RSI | 30~50~70 | 선형 보간 (-0.01/pt) | Wilder 과매수/매도 연속 판단 |
# MAGIC | RSI | <30, >70 | 가속 (1.5배 기울기) | 극단값은 경계보다 더 강한 신호 |
# MAGIC | 이격도 | ±10%~±20% | 1.5제곱 가속 | 평균 괴리 커질수록 회귀 인력 ↑ |
# MAGIC | vol_ratio | 0.8~1.2 | 선형 보간 | 0.8 이하 안정, 1.5 이상 급변 |
# MAGIC | Interaction | RSI×vol 중첩 | 곱셈 가중 | 복합 신호 = 확신의 크기 ↑ |
# MAGIC
# MAGIC #### 수식
# MAGIC - RSI 50~70: $w_{adj} = -0.01 \times (RSI - 50)$
# MAGIC - RSI >70 가속: $w_{adj} = -0.20 - 0.015 \times (RSI - 70)$
# MAGIC - 이격도: $w_{adj} = \pm 0.15 \times \min\left(\left(\frac{|d|}{20}\right)^{1.5}, 1\right)$

# COMMAND ----------

# DBTITLE 1,Soft Switching 가중치 보간 함수


def _rsi_weight_adjustment(rsi: float) -> float:
    """
    RSI 기반 TimesFM 가중치 조정분 (Soft Switching).

    v0416: 실제 TimesFM + UC BestTrial 조합으로 조정분 축소 (±0.30 → ±0.20)
    양쪽 모델 모두 검증된 실제 모델이므로 극단적 전환 불필요.

    가중치 변화 곡선:
        RSI 0 ─── +0.20 ──► RSI 30 ─── +0.13 ──► RSI 50 ─── 0.00
                   (가속)              (선형)
        RSI 50 ── 0.00 ──► RSI 70 ─── -0.13 ──► RSI 100 ── -0.20
                             (선형)              (가속)
    """
    if rsi <= 30:
        base = 0.13
        accel = 0.07 * min((30 - rsi) / 30, 1.0)
        return base + accel
    elif rsi <= 50:
        return 0.13 * (50 - rsi) / 20
    elif rsi <= 70:
        return -0.0065 * (rsi - 50)
    else:
        base = -0.13
        accel = -0.07 * min((rsi - 70) / 30, 1.0)
        return base + accel


def _vol_weight_adjustment(vol_ratio: float) -> float:
    """
    변동성 비율 기반 가중치 조정분.

    v0416: ±0.20 → ±0.15 스케일 조정.

    - vol_ratio < 0.8: 안정적 추세 지속 → TimesFM 강화
    - 0.8~1.2: 정상 범위 → 무조정
    - vol_ratio > 1.2: 변동성 급증 → UC(회귀) 강화
    """
    if vol_ratio <= 0.8:
        return 0.12 * min((0.8 - vol_ratio) / 0.8, 1.0)
    elif vol_ratio <= 1.2:
        return 0.0
    else:
        return -0.15 * min((vol_ratio - 1.2) / 0.8, 1.0)


def _disparity_weight_adjustment(disparity: float) -> float:
    """
    120일 이격도 기반 가중치 조정분 (가속화).

    "평균에서 멀어질수록 회귀하려는 인력은 제곱으로 강해진다"
    → 이격도가 커질수록 1.5제곱으로 가속하여 조정분을 키움.

    - 양수 이격 (+): 장기평균 위 → 회귀 압력 (UC ↑)
    - 음수 이격 (-): 장기평균 아래 → 반등 기대 (TimesFM ↑)
    """
    if disparity > 0:
        norm = min(disparity / 20, 1.0)
        return -0.15 * (norm**1.5)
    elif disparity < 0:
        norm = min(abs(disparity) / 10, 1.0)
        return 0.15 * (norm**1.5)
    return 0.0


def _sentiment_weight_adjustment(avg_sentiment: float, news_vol_surge: float) -> float:
    """
    뉴스 감성 기반 TimesFM 가중치 조정분.

    v0416: UC BestTrial이 이미 감성 피처 내재 → 조정분 축소 (±0.15 → ±0.10)

    - 강한 호재(>0.3): 모멘텀 지속 기대 → TimesFM 강화 (+0.07)
    - 강한 악재(<-0.3): 과도한 비관 → 평균회귀 기대 → UC 강화 (-0.07)
    - 뉴스량 급증(>2.0): 변곡점 전조 → 보수적 UC 강화 (-0.03)
    """
    adj = 0.0

    if avg_sentiment > 0.3:
        adj += 0.07 * min((avg_sentiment - 0.3) / 0.4, 1.0)
    elif avg_sentiment < -0.3:
        adj -= 0.07 * min((abs(avg_sentiment) - 0.3) / 0.4, 1.0)

    if news_vol_surge > 2.0:
        adj -= 0.03 * min((news_vol_surge - 2.0) / 3.0, 1.0)

    return np.clip(adj, -0.10, 0.10)


def _interaction_weight(
    rsi: float,
    vol_ratio: float,
    disparity: float,
    avg_sentiment: float = 0.0,
) -> float:
    """
    복합 지표 가중치 (Interaction Term).

    "신호들의 중첩은 확신의 크기를 키운다"
    단일 지표보다 복수 지표가 동시에 같은 방향을 가리킬 때
    가중치 조정을 추가로 부여합니다.
    """
    adj = 0.0

    # 규칙 1: 과매수 + 변동성 급증 = 하락 신호 중첩
    if rsi > 60 and vol_ratio > 1.2:
        overbought_strength = min((rsi - 60) / 40, 1.0)
        vol_strength = min((vol_ratio - 1.2) / 0.8, 1.0)
        adj -= 0.08 * overbought_strength * vol_strength

    # 규칙 2: 과매도 + 변동성 급증 = 패닉 매도 후 반등 기대
    if rsi < 40 and vol_ratio > 1.2:
        oversold_strength = min((40 - rsi) / 40, 1.0)
        vol_strength = min((vol_ratio - 1.2) / 0.8, 1.0)
        adj += 0.08 * oversold_strength * vol_strength

    # 규칙 3: 이격도 과열 + RSI 과매수 = 이중 회귀 압력
    if disparity > 15 and rsi > 65:
        disp_strength = min((disparity - 15) / 15, 1.0)
        rsi_strength = min((rsi - 65) / 35, 1.0)
        adj -= 0.08 * disp_strength * rsi_strength

    # 규칙 4: 호재 감성 + RSI 과매수 = 모멘텀 과열 경고
    if avg_sentiment > 0.3 and rsi > 60:
        sent_strength = min((avg_sentiment - 0.3) / 0.4, 1.0)
        rsi_strength = min((rsi - 60) / 40, 1.0)
        adj -= 0.08 * sent_strength * rsi_strength

    # 규칙 5: 악재 감성 + RSI 과매도 = 패닉 → 역발상 반등
    if avg_sentiment < -0.3 and rsi < 40:
        sent_strength = min((abs(avg_sentiment) - 0.3) / 0.4, 1.0)
        rsi_strength = min((40 - rsi) / 40, 1.0)
        adj += 0.08 * sent_strength * rsi_strength

    return adj


def compute_dynamic_weights(
    rsi: float,
    vol_ratio: float,
    disparity: float,
    avg_sentiment: float = 0.0,
    news_vol_surge: float = 1.0,
) -> dict:
    """
    Soft Switching 기반 동적 가중치를 산출합니다.

    v0416: 실제 TimesFM 2.5 + UC BestTrial(R²=0.93) 조합 최적화.
    - 기본 가중치: TimesFM 0.45 / UC 0.55 (UC R² 우위 반영)
    - 조정 범위: [0.25, 0.75] (양쪽 모델 모두 검증되어 극단 편중 방지)
    - 조정분 스케일: RSI ±0.20, vol ±0.15, 이격도 ±0.15, 감성 ±0.10

    Parameters
    ----------
    rsi : float
        RSI(14) 최신값 (0~100)
    vol_ratio : float
        단기/장기 변동성 비율
    disparity : float
        120일 이격도 (%)
    avg_sentiment : float
        당일 뉴스 ABSA 평균 감성
    news_vol_surge : float
        뉴스량 급증 비율

    Returns
    -------
    dict
    """
    # --- 각 지표별 연속 조정분 산출 ---
    rsi_adj = _rsi_weight_adjustment(rsi)
    vol_adj = _vol_weight_adjustment(vol_ratio)
    disp_adj = _disparity_weight_adjustment(disparity)
    inter_adj = _interaction_weight(rsi, vol_ratio, disparity, avg_sentiment)
    sent_adj = _sentiment_weight_adjustment(avg_sentiment, news_vol_surge)

    # --- 기본 가중치 + 조정분 합산 (v0416: 0.45 기반) ---
    w_trend = 0.45 + rsi_adj + vol_adj + disp_adj + inter_adj + sent_adj
    w_trend = np.clip(w_trend, 0.25, 0.75)
    w_meanrev = round(1.0 - w_trend, 4)

    # --- 조정 사유 기록 ---
    adjustments = []
    if abs(rsi_adj) > 0.01:
        adjustments.append(f"RSI={rsi:.1f} → adj={rsi_adj:+.3f}")
    if abs(vol_adj) > 0.01:
        adjustments.append(f"vol_ratio={vol_ratio:.2f} → adj={vol_adj:+.3f}")
    if abs(disp_adj) > 0.01:
        adjustments.append(f"이격도={disparity:+.1f}% → adj={disp_adj:+.3f}")
    if abs(inter_adj) > 0.01:
        adjustments.append(f"Interaction → adj={inter_adj:+.3f}")
    if abs(sent_adj) > 0.01:
        adjustments.append(
            f"감성={avg_sentiment:+.3f}, 뉴스급증={news_vol_surge:.1f}x → adj={sent_adj:+.3f}"
        )

    # --- 레짐 라벨 결정 ---
    if w_trend >= 0.55:
        regime = "TREND"
        regime_flag = 1
    elif w_meanrev >= 0.55:
        regime = "MEAN_REV"
        regime_flag = -1
    else:
        regime = "NEUTRAL"
        regime_flag = 0

    return {
        "w_trend": round(w_trend, 4),
        "w_meanrev": round(w_meanrev, 4),
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
    automl_pred: float,
    feature_mart: pd.DataFrame,
    horizon: int = 20,
) -> dict:
    """
    TimesFM(추세)과 AutoML UC 모델(평균회귀) 예측을 동적으로 결합합니다.

    v0419: ElasticNet/RF 블렌딩 제거, AutoML UC 모델 단독 회귀 컴포넌트 사용.
    - 삼성전자: sense_databricks.models.automl_삼성전자_t20 (R²=0.817)
    - SK하이닉스: sense_databricks.models.automl_SK하이닉스_t20 (R²=0.770)

    Parameters
    ----------
    ticker : str
        종목 코드
    timesfm_point : np.ndarray
        TimesFM XReg 점 예측 (horizon 길이)
    timesfm_q10, timesfm_q90 : np.ndarray
        TimesFM 10th/90th 분위수
    automl_pred : float
        AutoML UC 모델 T+{horizon} 절대가 예측
    feature_mart : pd.DataFrame
        기술적 지표가 추가된 피처 마트
    horizon : int
        예측 기간 (기본값: 20)

    Returns
    -------
    dict
    """
    last_price = feature_mart["close"].iloc[-1]

    # 현재 시장 지표 추출
    rsi = feature_mart["rsi_14"].iloc[-1]
    vol_ratio = feature_mart["vol_ratio"].iloc[-1]
    disparity = feature_mart["disparity_120d"].iloc[-1]

    # 뉴스 감성 지표 (v0415)
    avg_sentiment = (
        feature_mart["avg_sentiment"].iloc[-1] if "avg_sentiment" in feature_mart.columns else 0.0
    )
    news_vol_surge = (
        feature_mart["news_vol_surge"].iloc[-1] if "news_vol_surge" in feature_mart.columns else 1.0
    )

    # 레짐 판별 및 가중치 결정
    regime = compute_dynamic_weights(
        rsi,
        vol_ratio,
        disparity,
        avg_sentiment=avg_sentiment,
        news_vol_surge=news_vol_surge,
    )
    w_trend = regime["w_trend"]
    w_meanrev = regime["w_meanrev"]

    # AutoML 회귀 컴포넌트: T+20 점 예측 → 선형 보간 경로
    automl_path = np.linspace(last_price, automl_pred, horizon)

    # --- 앙상블 점 예측 ---
    ensemble_path = w_trend * timesfm_point + w_meanrev * automl_path

    # --- 앙상블 PI ---
    ensemble_mid = ensemble_path
    tfm_half_width = (timesfm_q90 - timesfm_q10) / 2

    recent_vol = feature_mart["realized_vol_5d"].iloc[-1] / np.sqrt(252)
    automl_half_width = last_price * recent_vol * np.sqrt(np.arange(1, horizon + 1)) * 1.28

    combined_half_width = w_trend * tfm_half_width + w_meanrev * automl_half_width
    ensemble_q10 = ensemble_mid - combined_half_width
    ensemble_q90 = ensemble_mid + combined_half_width

    # --- Confidence Score ---
    confidence = compute_confidence_score(timesfm_q10, timesfm_q90, automl_pred, last_price)

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
        "automl_path": automl_path,
        "confidence": confidence,
        "trend_score": trend_score,
        "meanrev_score": meanrev_score,
        "avg_sentiment": avg_sentiment,
        "news_vol_surge": news_vol_surge,
    }


# COMMAND ----------

# DBTITLE 1,앙상블 실행
ensemble_results = {}

print("=" * 70)
print("동적 가중치 앙상블 (Dynamic Weighting Ensemble) — v0419 AutoML UC")
print("=" * 70)

for ticker in TICKERS:
    if ticker not in feature_marts or ticker not in automl_predictions:
        continue

    name = TICKER_NAMES[ticker]
    result = calculate_dynamic_ensemble(
        ticker=ticker,
        timesfm_point=timesfm_predictions[ticker],
        timesfm_q10=timesfm_pi[ticker][0],
        timesfm_q90=timesfm_pi[ticker][1],
        automl_pred=automl_predictions[ticker],
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
        f"  가중치: TimesFM(추세)={regime['w_trend']:.2%} / AutoML(회귀)={regime['w_meanrev']:.2%}"
    )
    for adj in regime["adjustments"]:
        print(f"    → {adj}")
    print(f"  TimesFM T+{HORIZON}: {timesfm_predictions[ticker][-1]:,.0f}원")
    print(f"  AutoML  T+{HORIZON}: {automl_predictions[ticker]:,.0f}원")
    print(f"  ★ 앙상블 T+{HORIZON}: {final_pred:,.0f}원 ({change:+.2f}%)")
    print(f"  신뢰도: {result['confidence']:.1f}/100")
    print(
        f"  뉴스 감성: avg={result['avg_sentiment']:+.3f}, 뉴스급증={result['news_vol_surge']:.1f}x"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5-1. AI 해석 — 앙상블 레짐 판별 및 가중치 근거

# COMMAND ----------

# DBTITLE 1,GPT 해석: 앙상블 결과 중간 해석
_regime_lines = ["[동적 가중치 앙상블 결과 요약]\n"]
for ticker in TICKERS:
    if ticker not in ensemble_results:
        continue
    result = ensemble_results[ticker]
    regime = result["regime"]
    final_pred = result["ensemble_path"][-1]
    change = (final_pred - result["last_price"]) / result["last_price"] * 100
    _regime_lines.append(
        f"\n{TICKER_NAMES[ticker]}:"
        f"\n  레짐={regime['regime']}, "
        f"TimesFM={regime['w_trend']:.0%}/AutoML(회귀)={regime['w_meanrev']:.0%}"
        f"\n  앙상블={final_pred:,.0f}원({change:+.2f}%), 신뢰도={result['confidence']:.0f}/100"
        f"\n  감성={result['avg_sentiment']:+.3f}, 뉴스급증={result['news_vol_surge']:.1f}x"
        f"\n  조정: {'; '.join(regime['adjustments']) if regime['adjustments'] else '없음'}"
    )

_regime_prompt = "\n".join(_regime_lines) + (
    "\n\n위 앙상블 결과를 바탕으로:\n"
    "1. 레짐 판별이 왜 이렇게 되었는지 (RSI, 이격도, 감성 기반)\n"
    "2. 두 종목의 가중치 차이가 의미하는 바\n"
    "3. AutoML UC 모델(R²>0.77)이 기존 ElasticNet(R²≈0.05) 대비 개선된 점\n"
    "4. 현 시점 투자 시그널 (매수/관망/매도 강도)\n"
    "을 2~3문장으로 요약하세요."
)
try:
    _regime_resp = _ens_openai_client.chat.completions.create(
        model=OPENAI_DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": "반도체 퀀트 애널리스트. 앙상블 투자 시사점 해석.",
            },
            {"role": "user", "content": _regime_prompt},
        ],
        max_tokens=600,
        temperature=0.3,
    )
    print(_regime_resp.choices[0].message.content)
except Exception as e:
    print(f"[WARN] AI 분석 실패: {e}")

# COMMAND ----------

# DBTITLE 1,Step 4 시각화 설명
# MAGIC %md
# MAGIC # 6. Step 4 — 시각화 (Dynamic Weighting Strategy)
# MAGIC
# MAGIC `ref/image.png`와 동일한 형태의 차트를 재현합니다.
# MAGIC - 초록색 점선: TimesFM 예측 (Trend Model)
# MAGIC - 주황색 점선: AutoML UC 모델 예측 (Mean-Rev Model)
# MAGIC - 파란색 굵은 실선: Dynamic Ensemble Result
# MAGIC - 연한 파란색 음영: Confidence Interval (PI 밴드)

# COMMAND ----------

# DBTITLE 1,시각화 함수


def plot_dynamic_ensemble(result: dict, ticker_name: str, save_path: str | None = None):
    """
    동적 가중치 앙상블 결과 시각화 (v0419: AutoML UC 모델).
    """
    horizon = len(result["ensemble_path"])
    days = np.arange(1, horizon + 1)

    fig, ax = plt.subplots(figsize=(14, 7))

    # --- PI 밴드 ---
    ax.fill_between(
        days,
        result["ensemble_q10"],
        result["ensemble_q90"],
        alpha=0.20,
        color="#6495ED",
        label="Confidence Interval (PI)",
    )

    # --- TimesFM ---
    ax.plot(
        days,
        result["timesfm_path"],
        color="green",
        linestyle="--",
        linewidth=1.5,
        alpha=0.8,
        label="Trend Model (TimesFM)",
    )

    # --- AutoML UC 모델 ---
    ax.plot(
        days,
        result["automl_path"],
        color="darkorange",
        linestyle="--",
        linewidth=1.5,
        alpha=0.8,
        label="Mean-Rev Model (AutoML UC)",
    )

    # --- 앙상블 ---
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

    # --- 레짐 & 신뢰도 & 감성 ---
    regime = result["regime"]
    _sent_val = result.get("avg_sentiment", 0.0)
    _sent_label = "호재" if _sent_val > 0.3 else ("악재" if _sent_val < -0.3 else "중립")
    _surge_val = result.get("news_vol_surge", 1.0)
    info_text = (
        f"레짐: {regime['regime']}\n"
        f"추세: {regime['w_trend']:.2%} / 회귀: {regime['w_meanrev']:.2%}\n"
        f"신뢰도: {result['confidence']:.0f}/100\n"
        f"뉴스 감성: {_sent_val:+.3f} ({_sent_label})\n"
        f"뉴스량 급증: {_surge_val:.1f}x"
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

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"차트 저장: {save_path}")

    display(fig)  # noqa: F821
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
# MAGIC | mean_rev_score | float | 회귀(RF+EN) 가중치 점수 (0~100) |
# MAGIC | final_pred | float | 앙상블 최종 예측가 |
# MAGIC | confidence_score | float | 신뢰도 (0~100) |
# MAGIC | regime_flag | int | 레짐 코드 (1=추세, 0=중립, -1=회귀) |
# MAGIC | avg_sentiment | float | 당일 뉴스 ABSA 평균 감성 (-1~+1) |
# MAGIC | news_vol_surge | float | 뉴스량 급증 비율 (당일/7일평균) |

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
                "meanrev_pred": round(float(result["automl_path"][j]), 2),
                "final_pred": round(float(result["ensemble_path"][j]), 2),
                "pi_lower": round(float(result["ensemble_q10"][j]), 2),
                "pi_upper": round(float(result["ensemble_q90"][j]), 2),
                "confidence_score": round(result["confidence"], 2),
                "regime_flag": result["regime"]["regime_flag"],
                "regime_label": result["regime"]["regime"],
                "avg_sentiment": round(result.get("avg_sentiment", 0.0), 4),
                "news_vol_surge": round(result.get("news_vol_surge", 1.0), 2),
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
    with engine.connect() as conn:
        df_ensemble.to_sql("fact_ensemble_forecast", conn, if_exists="append", index=False)
        conn.commit()
    print(f"✅ fact_ensemble_forecast 적재 완료: {len(df_ensemble)}행")
except Exception as e:
    print(f"[INFO] PostgreSQL 적재 스킵: {e}")
    print("→ df_ensemble DataFrame으로 결과 보존됨")

# COMMAND ----------

# MAGIC %md
# MAGIC # 8. 앙상블 전략 요약 (AI 해석)

# COMMAND ----------

# DBTITLE 1,Azure OpenAI 클라이언트 (gpt-5.4-mini — Responses API)
from openai import OpenAI  # noqa: E402

_openai_key = vault.get_secret("azure-openai-key")
openai_client = OpenAI(
    api_key=_openai_key,
    base_url="https://aoai-3dt-team1.openai.azure.com/openai/v1/",
)
OPENAI_FINAL_MODEL = "gpt-5.4-mini"

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

[뉴스 감성 (Gold Layer)]
- 당일 평균 감성: {result.get("avg_sentiment", 0.0):+.3f} (-1=극악재 ~ +1=극호재)
- 뉴스량 급증 비율: {result.get("news_vol_surge", 1.0):.1f}x (1.0=평균, 2.0+=급증)

[모델 예측]
- TimesFM(추세): {timesfm_predictions[ticker][-1]:,.0f}원
- AutoML UC(회귀): {automl_predictions[ticker]:,.0f}원
  (R²={0.817 if "005930" in ticker else 0.770:.3f})
- 앙상블 최종: {final_pred:,.0f}원 ({change_pct:+.2f}%)

[레짐 판별]
- 레짐: {regime["regime"]}
- 가중치: 추세={regime["w_trend"]:.0%} / 회귀={regime["w_meanrev"]:.0%}
- 조정 사유: {"; ".join(regime["adjustments"]) if regime["adjustments"] else "없음"}
- 신뢰도: {result["confidence"]:.0f}/100

위 결과를 바탕으로:
1. 뉴스 감성이 레짐 판별과 가중치에 어떤 영향을 미쳤는지 설명
2. "AI 슈퍼사이클 → 반도체 수요 → 뉴스 감성 → 주가 예측" 스토리라인으로 해석
3. AutoML UC 모델(R²>0.77) 도입으로 앙상블 품질이 어떻게 개선되었는지
4. 뉴스 감성 변화 시 주의해야 할 리스크 요인
을 한국어로 간결하게 분석해주세요.
"""

    try:
        response = openai_client.responses.create(
            model=OPENAI_FINAL_MODEL,
            instructions=(
                "당신은 반도체 주식 전문 퀀트 애널리스트입니다. "
                "동적 가중치 앙상블 전략의 결과를 바탕으로 "
                "투자 인사이트를 제공합니다. AutoML UC 모델의 "
                "도입 배경(ElasticNet R²≈0.05 → AutoML R²>0.77)을 "
                "포함해 해석하세요."
            ),
            input=prompt,
            max_output_tokens=1200,
            temperature=0.4,
        )
        analysis = response.output_text
        print(f"\n{'═' * 70}")
        print(f"  {name} — AI 앙상블 분석")
        print(f"{'═' * 70}")
        print(analysis)
    except Exception as e:
        print(f"[WARN] {name} AI 분석 실패: {e}")

# COMMAND ----------

# DBTITLE 1,Silver vs Gold 가격 시계열 비교 실험
# ---------------------------------------------------------------------------
# Silver Layer vs Gold Layer — TimesFM 입력 가격 시계열 비교
# ---------------------------------------------------------------------------
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# --- 1. Silver Layer 로드 ---
try:
    _silver_path = f"abfss://curated@{account}.dfs.core.windows.net/pre_macro_1y_adf.parquet"
    df_silver = spark.read.parquet(_silver_path).toPandas()  # noqa: F821
    # 날짜 컨럼 자동 감지
    _date_col = "기준일자" if "기준일자" in df_silver.columns else "date"
    df_silver[_date_col] = pd.to_datetime(df_silver[_date_col])
    df_silver = df_silver.sort_values(_date_col).rename(columns={_date_col: "s_date"})
    print(
        f"[OK] Silver: {df_silver.shape}, "
        f"{df_silver['s_date'].min().date()} ~ {df_silver['s_date'].max().date()}"
    )
    _silver_loaded = True
except Exception as e:
    print(f"[WARN] Silver 로드 실패: {e}")
    _silver_loaded = False

print(
    f"[OK] Gold:   {df_gold_macro.shape}, "
    f"{df_gold_macro['date'].min().date()} ~ {df_gold_macro['date'].max().date()}"
)

if _silver_loaded:
    _s_col = "yfinance_samsung_close"
    _h_col = "yfinance_skhynix_close"

    for col_name, ticker_name in [(_s_col, "삼성전자"), (_h_col, "SK하이닉스")]:
        if col_name not in df_silver.columns:
            print(f"  [SKIP] Silver에 {col_name} 없음")
            continue

        # Silver 가격 시계열
        s_close = df_silver[["s_date", col_name]].dropna(subset=[col_name]).copy()
        s_close.columns = ["date", "close"]
        s_close = s_close.sort_values("date").reset_index(drop=True)

        # Gold 가격 시계열
        g_close = df_gold_macro[["date", col_name]].dropna(subset=[col_name]).copy()
        g_close.columns = ["date", "close"]
        g_close = g_close.sort_values("date").reset_index(drop=True)

        print(f"\n{'=' * 70}")
        print(f"  {ticker_name} — Silver vs Gold 비교")
        print(f"{'=' * 70}")
        print(
            f"  Silver: {len(s_close)}일, "
            f"{s_close['date'].iloc[0].date()} ~ {s_close['date'].iloc[-1].date()}"
        )
        print(
            f"  Gold:   {len(g_close)}일, "
            f"{g_close['date'].iloc[0].date()} ~ {g_close['date'].iloc[-1].date()}"
        )
        _s_ret = (s_close["close"].iloc[-1] / s_close["close"].iloc[0] - 1) * 100
        print(
            f"  Silver: {s_close['close'].iloc[0]:,.0f} → "
            f"{s_close['close'].iloc[-1]:,.0f} ({_s_ret:+.1f}%)"
        )
        _g_ret = (g_close["close"].iloc[-1] / g_close["close"].iloc[0] - 1) * 100
        print(
            f"  Gold:   {g_close['close'].iloc[0]:,.0f} → "
            f"{g_close['close'].iloc[-1]:,.0f} ({_g_ret:+.1f}%)"
        )

        # 날짜 차이
        s_end = s_close["date"].iloc[-1]
        g_end = g_close["date"].iloc[-1]
        date_diff = (g_end - s_end).days
        print(f"\n  ★ Silver 마지막 날짜: {s_end.date()}")
        print(f"  ★ Gold   마지막 날짜: {g_end.date()}")
        if date_diff != 0:
            print(f"  ★ 날짜 차이: {date_diff}일 — Gold가 {abs(date_diff)}일 더 최신!")
        print(f"  ★ 데이터 길이 차이: Silver {len(s_close)}일 vs Gold {len(g_close)}일")

        # 공통 날짜 merge
        merged = pd.merge(s_close, g_close, on="date", suffixes=("_silver", "_gold"), how="inner")
        if len(merged) > 0:
            diff = (
                (merged["close_silver"] - merged["close_gold"]).abs() / merged["close_gold"] * 100
            )
            print(f"  공통 기간 가격 차이: 평균 {diff.mean():.3f}%, 최대 {diff.max():.3f}%")
            if diff.mean() < 0.01:
                print("  → 동일 yfinance 데이터 — 가격 자체는 같음")

        # Silver 최근 60일 vs Gold 최근 60일 곡선 형태
        for label, df_p in [("Silver", s_close), ("Gold", g_close)]:
            last60 = df_p.tail(60)
            ret = (last60["close"].iloc[-1] / last60["close"].iloc[0] - 1) * 100
            slope = np.polyfit(np.arange(len(last60)), last60["close"].values, 1)[0]
            std = last60["close"].pct_change().dropna().std() * 100
            up = (last60["close"].pct_change() > 0).sum()
            down = (last60["close"].pct_change() < 0).sum()
            print(
                f"\n  {label} 최근 60일 "
                f"({last60['date'].iloc[0].date()} ~ {last60['date'].iloc[-1].date()}):"
            )
            print(
                f"    {last60['close'].iloc[0]:,.0f} → "
                f"{last60['close'].iloc[-1]:,.0f} ({ret:+.1f}%)"
            )
            print(f"    기울기: {slope:+,.1f}원/일, 변동성: {std:.2f}%/일, 상승/하락: {up}/{down}")

        # --- 시각화 ---
        fig, axes = plt.subplots(1, 2, figsize=(16, 5))
        s_plot = s_close.tail(120)
        g_plot = g_close.tail(120)
        axes[0].plot(s_plot["date"], s_plot["close"], "b-", lw=1.5)
        axes[0].set_title(f"{ticker_name} Silver (최근 {len(s_plot)}일)")
        axes[0].set_ylabel("원")
        axes[0].grid(alpha=0.3)
        axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

        axes[1].plot(g_plot["date"], g_plot["close"], "r-", lw=1.5)
        axes[1].set_title(f"{ticker_name} Gold (최근 {len(g_plot)}일)")
        axes[1].set_ylabel("원")
        axes[1].grid(alpha=0.3)
        axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

        plt.suptitle(
            f"{ticker_name}: Silver vs Gold — TimesFM context 비교",
            fontsize=13,
            fontweight="bold",
        )
        plt.tight_layout()
        display(fig)  # noqa: F821
        plt.close(fig)

    print(f"\n{'=' * 70}")
    print("  ★ 최종 결론")
    print(f"{'=' * 70}")
    print(
        f"  Silver 마지막: {df_silver['s_date'].max().date()}, "
        f"Gold 마지막: {df_gold_macro['date'].max().date()}"
    )
    _days_gap = (df_gold_macro["date"].max() - df_silver["s_date"].max()).days
    if _days_gap > 0:
        print(
            f"  Gold가 {_days_gap}일 더 최신 — "
            "이 기간에 V자 급락+반등 발생 시 TimesFM context 완전히 다름"
        )
    print("  → 데이터 소스 차이가 아닌 ‘시점 차이’가 TimesFM 예측 변화의 근본 원인")


# COMMAND ----------

# DBTITLE 1,v0419 결과 요약
# MAGIC %md
# MAGIC # 9. 결과 요약
# MAGIC
# MAGIC | 단계 | 구현 내용 | 상태 |
# MAGIC |---|---|---|
# MAGIC | Step 0 | 환경설정 + 한글 폰트 | ✅ |
# MAGIC | Step 1 | RSI, ATR, 이격도, 로그수익률 + **감성·키워드 파생 피처** | ✅ v0416 |
# MAGIC | Step 1.5 | **뉴스 감성 + 동적 키워드 파생변수** (6종 + 교호작용 4종) | ✅ v0416 |
# MAGIC | Step 2 | **AutoML UC 모델** (삼성전자 R²=0.817, SK하이닉스 R²=0.770) | ✅ v0419 |
# MAGIC | Step 2-1 | **키워드 파생변수 상관관계 분석** (Spearman/Pearson 교차검증) | ✅ v0416 |
# MAGIC | Step 3 | **Soft Switching** + 감성 가중치 + Interaction + Confidence | ✅ v0415 |
# MAGIC | Step 4 | 시각화 + fact_ensemble_forecast DataFrame | ✅ v0419 |
# MAGIC | Step 5-1 | **AI 중간 해석** (앙상블 레짐, 키워드 상관) | ✅ v0416 |
# MAGIC | Step 8 | AI 앙상블 전략 요약 (**gpt-5.4-mini** Responses API) | ✅ v0418 |
