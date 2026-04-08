"""
yahoo_finance_crawler.py
===============
반도체 종목 주가 데이터 수집 및 ADLS Gen2 업로드 모듈

설명:
    yfinance를 사용하여 반도체 관련 종목의 1년치 주가 데이터를 수집하고
    Azure Data Lake Storage Gen2 raw 컨테이너에 직접 업로드합니다.

업로드 경로:
    raw 컨테이너 / yfinance/year={Y}/month={M}/day={D}/yahoo_finance_raw_{YYYYMMDD}.csv

의존성:
    - yfinance
    - pandas
    - azure-storage-file-datalake (vault_manager 경유)

Author: 김원비 (1조)
"""

import io
import logging
from datetime import datetime, timezone

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
# 수집 함수
# ---------------------------------------------------------------------------


def fetch_stock_data(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """
    yfinance를 사용하여 주가 데이터를 다운로드합니다.

    Args:
        tickers (list[str]): 수집할 종목 코드 리스트 (예: ['NVDA', 'TSM'])
        period (str): 수집 기간 (기본값: '1y' = 1년)
                      '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y'

    Returns:
        pd.DataFrame: 수집된 OHLCV 데이터프레임

    Raises:
        RuntimeError: 데이터 수집 실패 시
    """
    logger.info("데이터 다운로드 시작: %s (기간: %s)", tickers, period)
    df = yf.download(tickers, period=period, group_by="ticker")
    logger.info("데이터 다운로드 완료. shape=%s", df.shape)
    return df


# ---------------------------------------------------------------------------
# 업로드 함수
# ---------------------------------------------------------------------------


def upload_to_adls(df: pd.DataFrame, date: datetime) -> None:
    """
    데이터프레임을 CSV로 변환하여 ADLS Gen2 raw 컨테이너에 업로드합니다.

    업로드 경로:
        raw 컨테이너 / yfinance/year={Y}/month={M}/day={D}/yahoo_finance_raw_{YYYYMMDD}.csv

    Args:
        df (pd.DataFrame): 업로드할 주가 데이터프레임
        date (datetime): 업로드 기준 날짜 (UTC)

    Raises:
        RuntimeError: 업로드 실패 시
    """
    try:
        date_str = date.strftime("%Y%m%d")
        directory = f"yfinance/year={date.year}/month={date.month:02d}/day={date.day:02d}"
        file_name = f"yahoo_finance_raw_{date_str}.csv"

        # DataFrame → CSV 바이트 변환 (메모리 내)
        buffer = io.BytesIO()
        df.to_csv(buffer, encoding="utf-8-sig")
        buffer.seek(0)

        # ADLS Gen2 업로드
        storage_client = vault.get_storage_client()
        fs_client = storage_client.get_file_system_client("raw")
        dir_client = fs_client.get_directory_client(directory)
        file_client = dir_client.get_file_client(file_name)
        file_client.upload_data(buffer.read(), overwrite=True)

        adls_path = f"raw/{directory}/{file_name}"
        logger.info("ADLS Gen2 업로드 완료: %s (%d rows)", adls_path, len(df))

    except Exception as e:
        logger.error("ADLS Gen2 업로드 실패: %s", e)
        raise RuntimeError(f"ADLS Gen2 업로드 중 문제가 발생했습니다: {e}") from e


# ---------------------------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------------------------


def main():
    """
    반도체 종목 주가 데이터 수집 및 ADLS Gen2 업로드 메인 함수.

    실행 흐름:
        1. 반도체 관련 종목 1년치 주가 데이터 수집
        2. ADLS Gen2 raw 컨테이너에 직접 업로드
    """
    semiconductor_tickers = ["NVDA", "TSM", "AMD", "INTC", "ASML"]

    # 1. 데이터 수집
    stock_df = fetch_stock_data(tickers=semiconductor_tickers, period="1y")

    # UTC 기준 날짜 사용 — 팀원 간 날짜 기준 통일
    now_utc = datetime.now(tz=timezone.utc)

    # 2. ADLS Gen2 업로드
    upload_to_adls(stock_df, now_utc)


if __name__ == "__main__":
    main()
