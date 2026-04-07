"""
yahoo_finance_crawler.py
===============
반도체 종목 주가 데이터 수집 및 CSV 저장 모듈

설명:
    yfinance를 사용하여 반도체 관련 종목의 1년치 주가 데이터를 수집하고
    로컬 CSV 파일로 저장합니다.

    저장된 CSV 파일은 Azure Portal에서 ADLS Gen2 컨테이너에 직접 업로드합니다.
    (GUI 업로드: Azure Portal → 스토리지 계정 → 컨테이너 → 업로드)

저장 경로:
    C:/Users/EL42/Downloads/yahoo_finance_raw_{YYYYMMDD}.csv

의존성:
    - yfinance
    - pandas

Author: 김원비 (1조)
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

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
# 저장 함수
# ---------------------------------------------------------------------------

def save_to_csv(df: pd.DataFrame, output_path: str) -> None:
    """
    데이터프레임을 CSV 파일로 저장합니다.

    저장 후 Azure Portal GUI를 통해 ADLS Gen2 컨테이너에 수동 업로드합니다.
    업로드 경로: raw/bronze/stock/year={Y}/month={M}/day={D}/

    Args:
        df (pd.DataFrame): 저장할 주가 데이터프레임
        output_path (str): 저장할 로컬 파일 경로
                           (예: 'output/stock/yahoo_finance_raw_20260407.csv')

    Raises:
        RuntimeError: 파일 저장 실패 시
    """
    try:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)  # 디렉토리 없으면 자동 생성

        df.to_csv(path, encoding="utf-8-sig")  # utf-8-sig: 한글 환경 Excel 호환

        logger.info("CSV 저장 완료: %s (%d rows)", path, len(df))
        logger.info("다음 단계: Azure Portal에서 해당 파일을 ADLS 컨테이너에 업로드하세요.")

    except Exception as e:
        logger.error("CSV 저장 실패: %s", e)
        raise RuntimeError(f"CSV 저장 중 문제가 발생했습니다: {e}") from e


# ---------------------------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------------------------

def main():
    """
    반도체 종목 주가 데이터 수집 및 CSV 저장 메인 함수.

    실행 흐름:
        1. 반도체 관련 종목 1년치 주가 데이터 수집
        2. 로컬 CSV 파일로 저장
        3. (수동) Azure Portal에서 ADLS Gen2 컨테이너에 업로드
    """
    semiconductor_tickers = ["NVDA", "TSM", "AMD", "INTC", "ASML"]

    # 1. 데이터 수집
    stock_df = fetch_stock_data(tickers=semiconductor_tickers, period="1y")

    # UTC 기준 날짜 사용 — 팀원 간 날짜 기준 통일
    today_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")

    # 2. CSV 저장
    output_path = f"C:/Users/EL42/Downloads/yahoo_finance_raw_{today_str}.csv"
    save_to_csv(stock_df, output_path)


if __name__ == "__main__":
    main()