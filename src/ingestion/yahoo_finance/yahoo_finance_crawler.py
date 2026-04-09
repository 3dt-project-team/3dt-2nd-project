"""
yahoo_finance_crawler.py
========================
반도체 종목 주가 데이터 수집 및 ADLS Gen2 업로드 비즈니스 로직 (증분수집)

수집 종목:
    - 미국 증시: NVDA, TSM, AMD, INTC, ASML, MU, WDC, ^SOX (반도체 지수)
    - 한국 증시: 005930.KS (삼성전자), 000660.KS (SK하이닉스)

데이터 형태:
    멀티인덱스(Wide) → Long 형태로 변환하여 저장합니다.
    각 행이 (날짜 + 종목) 단위로 구성됩니다.

업로드 경로:
    raw 컨테이너 / yfinance/year={Y}/month={M}/day={D}/yahoo_finance_raw_{YYYYMMDD}.csv

Watermark 경로:
    raw 컨테이너 / yfinance/watermark.json

Author: 김원비 (1조)
"""

import io
import json
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from vault_manager import vault

# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수 정의
# ---------------------------------------------------------------------------
RAW_CONTAINER    = "raw"
WATERMARK_PATH   = "yfinance/watermark.json"
FULL_LOAD_PERIOD = "1y"  # 최초 실행 시 수집 기간


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
# Watermark 함수
# ---------------------------------------------------------------------------

def read_watermark() -> str | None:
    """
    ADLS Gen2 에서 watermark.json 을 읽어 마지막 수집일을 반환합니다.

    Returns:
        str | None: 마지막 수집일 (예: "2026-04-09") 또는 None (최초 실행)
    """
    try:
        storage_client = vault.get_storage_client()
        fs_client      = storage_client.get_file_system_client(RAW_CONTAINER)
        file_client    = fs_client.get_file_client(WATERMARK_PATH)

        download = file_client.download_file()
        content  = json.loads(download.readall().decode("utf-8"))
        last_date = content.get("last_collected_date")
        logger.info("Watermark 읽기 완료: last_collected_date=%s", last_date)
        return last_date

    except Exception:
        logger.info("Watermark 없음 → 최초 실행으로 판단, 전체 수집 진행")
        return None


def write_watermark(date: datetime) -> None:
    """
    ADLS Gen2 에 watermark.json 을 저장합니다.

    Args:
        date (datetime): 저장할 수집 기준일 (UTC)
    """
    try:
        content = {
            "last_collected_date": date.strftime("%Y-%m-%d"),
            "last_run_utc":        date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        buffer = io.BytesIO(json.dumps(content, ensure_ascii=False).encode("utf-8"))

        storage_client = vault.get_storage_client()
        fs_client      = storage_client.get_file_system_client(RAW_CONTAINER)
        file_client    = fs_client.get_file_client(WATERMARK_PATH)
        file_client.upload_data(buffer.getvalue(), overwrite=True)

        logger.info("Watermark 저장 완료: %s", content)

    except Exception as e:
        logger.error("Watermark 저장 실패: %s", e)
        raise RuntimeError(f"Watermark 저장 중 문제가 발생했습니다: {e}") from e


# ---------------------------------------------------------------------------
# 증분수집 진입 함수
# ---------------------------------------------------------------------------

def run_incremental() -> dict:
    """
    Watermark 기반 증분수집 실행 함수.

    실행 흐름:
        1. Watermark 읽기
        2. 수집 범위 결정 (최초 or 증분)
        3. 데이터 수집
        4. ADLS 업로드
        5. Watermark 업데이트

    Returns:
        dict: 수집 결과 요약
    """
    now_utc   = datetime.now(tz=timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    # 1. Watermark 읽기
    last_collected_date = read_watermark()

    # 2. 이미 오늘 수집한 경우 → 스킵
    if last_collected_date == today_str:
        logger.info("이미 오늘 날짜까지 수집 완료. 스킵합니다.")
        return {
            "status":              "skipped",
            "message":             "이미 오늘 날짜까지 수집 완료",
            "last_collected_date": last_collected_date,
        }

    # 3. 수집 범위 결정
    if last_collected_date is None:
        # 최초 실행 → 1년치 전체 수집
        mode       = "full"
        start_date = None
        end_date   = None
        logger.info("최초 실행 → 전체 수집 (period=%s)", FULL_LOAD_PERIOD)
    else:
        # 증분 수집 → 마지막 수집일 다음날부터 오늘까지
        mode       = "incremental"
        start_date = (
            datetime.strptime(last_collected_date, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        end_date   = today_str
        logger.info("증분 수집 → %s ~ %s", start_date, end_date)

    # 4. 데이터 수집
    stock_df = fetch_stock_data(
        tickers    = SEMICONDUCTOR_TICKERS,
        start_date = start_date,
        end_date   = end_date,
        period     = FULL_LOAD_PERIOD if mode == "full" else None,
    )

    if stock_df.empty:
        logger.info("신규 데이터 없음. 스킵합니다.")
        return {
            "status":  "skipped",
            "message": "수집할 신규 데이터 없음",
            "mode":    mode,
        }

    # 5. ADLS 업로드
    adls_path = upload_to_adls(stock_df, now_utc)

    # 6. Watermark 업데이트
    write_watermark(now_utc)

    return {
        "status":         "success",
        "mode":           mode,
        "collected_from": start_date or stock_df.index.min().strftime("%Y-%m-%d"),
        "collected_to":   today_str,
        "rows":           len(stock_df),
        "tickers":        int(stock_df["Ticker"].nunique()),
        "adls_path":      adls_path,
    }


# ---------------------------------------------------------------------------
# 수집 함수
# ---------------------------------------------------------------------------

def fetch_stock_data(
    tickers:    dict[str, str],
    start_date: str | None = None,
    end_date:   str | None = None,
    period:     str | None = None,
) -> pd.DataFrame:
    """
    yfinance를 사용하여 주가 데이터를 다운로드하고 Long 형태로 변환합니다.

    Args:
        tickers (dict[str, str]): {종목명: 티커코드} 딕셔너리
        start_date (str | None): 수집 시작일 (예: "2026-04-01") - 증분수집 시 사용
        end_date   (str | None): 수집 종료일 (예: "2026-04-09") - 증분수집 시 사용
        period     (str | None): 수집 기간 (예: "1y") - 최초 전체 수집 시 사용

    Returns:
        pd.DataFrame: Long 형태로 변환된 OHLCV 데이터프레임
    """
    ticker_codes = list(tickers.values())

    if period:
        logger.info("전체 수집 시작 (period=%s)", period)
        raw_df = yf.download(ticker_codes, period=period, group_by="ticker")
    else:
        logger.info("증분 수집 시작 (%s ~ %s)", start_date, end_date)
        raw_df = yf.download(
            ticker_codes,
            start=start_date,
            end=end_date,
            group_by="ticker",
        )

    logger.info("데이터 다운로드 완료. shape=%s", raw_df.shape)

    long_records = []
    code_to_name = {v: k for k, v in tickers.items()}

    for ticker_code in ticker_codes:
        try:
            ticker_df = raw_df[ticker_code].copy()
            cols      = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in ticker_df.columns]
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
        return pd.DataFrame()  # 빈 DataFrame 반환 (수집할 데이터 없음)

    final_df = pd.concat(long_records)
    final_df.index = final_df.index.tz_localize(None)

    col_order = ["Ticker", "Name", "Open", "High", "Low", "Close", "Volume"]
    col_order = [c for c in col_order if c in final_df.columns]
    final_df  = final_df[col_order]
    final_df  = final_df.sort_index()

    logger.info("Long 변환 완료. 최종 shape=%s", final_df.shape)
    logger.info("수집 기간: %s ~ %s", final_df.index.min(), final_df.index.max())
    logger.info("수집 종목 수: %d개", final_df["Ticker"].nunique())

    return final_df


# ---------------------------------------------------------------------------
# 업로드 함수
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
        fs_client      = storage_client.get_file_system_client(RAW_CONTAINER)
        dir_client     = fs_client.get_directory_client(directory)
        file_client    = dir_client.get_file_client(file_name)
        file_client.upload_data(buffer.read(), overwrite=True)

        adls_path = f"{RAW_CONTAINER}/{directory}/{file_name}"
        logger.info("ADLS Gen2 업로드 완료: %s (%d rows)", adls_path, len(df))
        return adls_path

    except Exception as e:
        logger.error("ADLS Gen2 업로드 실패: %s", e)
        raise RuntimeError(f"ADLS Gen2 업로드 중 문제가 발생했습니다: {e}") from e