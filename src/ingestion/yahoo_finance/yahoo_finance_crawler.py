"""
yahoo_finance_crawler.py -v3
===============
반도체 종목 주가 데이터 수집 및 ADLS Gen2 업로드 Azure Function 앱

설명:
    HTTP 트리거 기반 Azure Function으로, 호출 시 반도체 관련 종목의
    1년치 주가 데이터를 수집하고 ADLS Gen2 raw 컨테이너에 업로드합니다.

    수집 종목:
        - 미국 증시: NVDA, TSM, AMD, INTC, ASML, ^SOX (반도체 지수)
        - 한국 증시: 005930.KS (삼성전자), 000660.KS (SK하이닉스)

    데이터 형태:
        멀티인덱스(Wide) → Long 형태로 변환하여 저장합니다.
        각 행이 (날짜 + 종목) 단위로 구성됩니다.

업로드 경로:
    raw 컨테이너 / yfinance/year={Y}/month={M}/day={D}/yahoo_finance_raw_{YYYYMMDD}.csv

HTTP 트리거 호출 예시:
    POST https://<function-app>.azurewebsites.net/api/yahoo_finance_crawler
    Body (선택): { "period": "1y" }   ← 생략 시 기본값 "1y" 사용

    GET  https://<function-app>.azurewebsites.net/api/yahoo_finance_crawler?period=6mo

의존성:
    - azure-functions
    - yfinance
    - pandas
    - azure-storage-file-datalake (vault_manager 경유)
"""

import io
import json
import logging
from datetime import datetime, timezone

import azure.functions as func
import pandas as pd
import yfinance as yf

from src.utils.vault_manager import vault

# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 수집 종목 정의
# ---------------------------------------------------------------------------

SEMICONDUCTOR_TICKERS = {
    # 미국 증시 — 퀀트 선행 지표
    "NVDA":      "NVDA",       # 엔비디아 (AI 수요 선행 지표)
    "TSM":       "TSM",        # TSMC
    "AMD":       "AMD",        # AMD
    "INTC":      "INTC",       # 인텔
    "ASML":      "ASML",       # ASML
    "MU":        "MU",         # 마이크론 (메모리 Proxy)
    "WDC":       "WDC",        # WDC (메모리 Proxy)
    "^SOX":      "^SOX",       # 필라델피아 반도체 지수 (SOX 스필오버 핵심 지표)
    # 한국 증시 — 예측 타겟 변수
    "삼성전자":   "005930.KS",  # 삼성전자
    "SK하이닉스": "000660.KS",  # SK하이닉스
}


# ---------------------------------------------------------------------------
# Azure Function 앱 초기화 (function_app.py 기본 구조 유지)
# ---------------------------------------------------------------------------

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ---------------------------------------------------------------------------
# HTTP 트리거 진입점
# ---------------------------------------------------------------------------

@app.route(route="yahoo_finance_crawler")
def yahoo_finance_crawler(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP 트리거 진입점.

    요청 파라미터 (선택):
        period (str): 수집 기간 (기본값: "1y")
                      Body JSON 또는 Query String으로 전달 가능
                      예: POST Body → { "period": "6mo" }
                          GET  URL  → ?period=6mo

    Returns:
        200: 수집 및 업로드 성공 메시지 (JSON)
        500: 수집 또는 업로드 실패 메시지 (JSON)
    """
    logger.info("yahoo_finance_crawler HTTP 트리거 호출됨")

    # -----------------------------------------------------------------------
    # 요청에서 period 파라미터 추출
    # 우선순위: Body JSON > Query String > 기본값 "1y"
    # -----------------------------------------------------------------------
    period = "1y"

    # Query String 확인
    qs_period = req.params.get("period")
    if qs_period:
        period = qs_period

    # Body JSON 확인 (Query String보다 우선)
    try:
        body = req.get_json()
        if body.get("period"):
            period = body["period"]
    except ValueError:
        pass  # Body가 없거나 JSON이 아닌 경우 무시

    logger.info("수집 기간: %s", period)

    # -----------------------------------------------------------------------
    # 데이터 수집 및 업로드
    # -----------------------------------------------------------------------
    try:
        # 1. 데이터 수집 및 Long 변환
        stock_df = fetch_stock_data(tickers=SEMICONDUCTOR_TICKERS, period=period)

        # UTC 기준 날짜 사용 — 팀원 간 날짜 기준 통일
        now_utc = datetime.now(tz=timezone.utc)

        # 2. ADLS Gen2 업로드
        adls_path = upload_to_adls(stock_df, now_utc)

        # 성공 응답
        result = {
            "status":     "success",
            "period":     period,
            "rows":       len(stock_df),
            "tickers":    int(stock_df["Ticker"].nunique()),
            "date_range": {
                "start": str(stock_df.index.min()),
                "end":   str(stock_df.index.max()),
            },
            "adls_path":  adls_path,
        }
        logger.info("전체 완료: %s", result)
        return func.HttpResponse(
            body=json.dumps(result, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logger.error("처리 중 오류 발생: %s", e)
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json",
        )


# ---------------------------------------------------------------------------
# 수집 함수 (기존 yahoo_finance_crawler.py 로직 그대로 유지)
# ---------------------------------------------------------------------------

def fetch_stock_data(tickers: dict[str, str], period: str = "1y") -> pd.DataFrame:
    """
    yfinance를 사용하여 주가 데이터를 다운로드하고 Long 형태로 변환합니다.

    [Wide 형태 - 변환 전]
               NVDA              TSM
               Open  Close  ...  Open  Close  ...
    Date
    2025-01-02  ...   ...        ...   ...

    [Long 형태 - 변환 후]
    Date        Ticker  Open    High    Low     Close   Volume
    2025-01-02  NVDA    138.5   140.2   137.1   139.8   123456789
    2025-01-02  TSM     180.3   182.1   179.5   181.2   45678900

    Args:
        tickers (dict[str, str]): {종목명: 티커코드} 딕셔너리
        period (str): 수집 기간 (기본값: '1y')

    Returns:
        pd.DataFrame: Long 형태로 변환된 OHLCV 데이터프레임

    Raises:
        RuntimeError: 수집된 데이터가 없을 시
    """
    ticker_codes = list(tickers.values())
    logger.info("데이터 다운로드 시작: %s (기간: %s)", ticker_codes, period)

    raw_df = yf.download(ticker_codes, period=period, group_by="ticker")
    logger.info("데이터 다운로드 완료. shape=%s", raw_df.shape)

    long_records = []
    code_to_name = {v: k for k, v in tickers.items()}

    for ticker_code in ticker_codes:
        try:
            ticker_df = raw_df[ticker_code].copy()
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in ticker_df.columns]
            ticker_df = ticker_df[cols]
            ticker_df = ticker_df.dropna(how="all")
            ticker_df["Ticker"] = ticker_code
            ticker_df["Name"]   = code_to_name.get(ticker_code, ticker_code)
            long_records.append(ticker_df)
            logger.info("  [%s] %d행 변환 완료", ticker_code, len(ticker_df))

        except KeyError:
            logger.warning("  [%s] 데이터 없음 — 건너뜁니다.", ticker_code)
            continue

    if not long_records:
        raise RuntimeError("수집된 데이터가 없습니다. 티커 코드 및 네트워크 상태를 확인하세요.")

    final_df = pd.concat(long_records)
    final_df.index = final_df.index.tz_localize(None)

    col_order = ["Ticker", "Name", "Open", "High", "Low", "Close", "Volume"]
    col_order = [c for c in col_order if c in final_df.columns]
    final_df = final_df[col_order]
    final_df = final_df.sort_index()

    logger.info("Long 변환 완료. 최종 shape=%s", final_df.shape)
    logger.info("수집 기간: %s ~ %s", final_df.index.min(), final_df.index.max())
    logger.info("수집 종목 수: %d개", final_df["Ticker"].nunique())

    return final_df


# ---------------------------------------------------------------------------
# 업로드 함수 (기존 yahoo_finance_crawler.py 로직 그대로 유지)
# ---------------------------------------------------------------------------

def upload_to_adls(df: pd.DataFrame, date: datetime) -> str:
    """
    데이터프레임을 CSV로 변환하여 ADLS Gen2 raw 컨테이너에 업로드합니다.

    업로드 경로:
        raw 컨테이너 / yfinance/year={Y}/month={M}/day={D}/yahoo_finance_raw_{YYYYMMDD}.csv

    Args:
        df (pd.DataFrame): 업로드할 주가 데이터프레임 (Long 형태)
        date (datetime): 업로드 기준 날짜 (UTC)

    Returns:
        str: 업로드된 ADLS 경로

    Raises:
        RuntimeError: 업로드 실패 시
    """
    try:
        date_str  = date.strftime("%Y%m%d")
        directory = f"yfinance/year={date.year}/month={date.month:02d}/day={date.day:02d}"
        file_name = f"yahoo_finance_raw_{date_str}.csv"

        buffer = io.BytesIO()
        df.to_csv(buffer, encoding="utf-8-sig")
        buffer.seek(0)

        storage_client = vault.get_storage_client()
        fs_client   = storage_client.get_file_system_client("raw")
        dir_client  = fs_client.get_directory_client(directory)
        file_client = dir_client.get_file_client(file_name)
        file_client.upload_data(buffer.read(), overwrite=True)

        adls_path = f"raw/{directory}/{file_name}"
        logger.info("ADLS Gen2 업로드 완료: %s (%d rows)", adls_path, len(df))
        return adls_path

    except Exception as e:
        logger.error("ADLS Gen2 업로드 실패: %s", e)
        raise RuntimeError(f"ADLS Gen2 업로드 중 문제가 발생했습니다: {e}") from e