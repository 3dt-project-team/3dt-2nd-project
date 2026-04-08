"""
yahoo_finance_crawler.py
===============
반도체 종목 주가 데이터 수집 및 ADLS Gen2 업로드 모듈

설명:
    yfinance를 사용하여 반도체 관련 종목의 1년치 주가 데이터를 수집하고
    Azure Data Lake Storage Gen2 raw 컨테이너에 직접 업로드합니다.

    수집 종목:
        - 미국 증시: NVDA, TSM, AMD, INTC, ASML, ^SOX (반도체 지수)
        - 한국 증시: 005930.KS (삼성전자), 000660.KS (SK하이닉스)

    데이터 형태:
        멀티인덱스(Wide) → Long 형태로 변환하여 저장합니다.
        각 행이 (날짜 + 종목) 단위로 구성됩니다.

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
# 수집 종목 정의
# ---------------------------------------------------------------------------

SEMICONDUCTOR_TICKERS = {
    # 미국 증시 — 퀀트 선행 지표
    "NVDA":     "NVDA",        # 엔비디아 (AI 수요 선행 지표)
    "TSM":      "TSM",         # TSMC
    "AMD":      "AMD",         # AMD
    "INTC":     "INTC",        # 인텔
    "ASML":     "ASML",        # ASML
    "MU":       "MU",          # 마이크론 (메모리 Proxy)
    "WDC":      "WDC",         # WDC (메모리 Proxy)
    "^SOX":     "^SOX",        # 필라델피아 반도체 지수 (SOX 스필오버 핵심 지표)
    # 한국 증시 — 예측 타겟 변수
    "삼성전자":  "005930.KS",   # 삼성전자
    "SK하이닉스": "000660.KS",  # SK하이닉스
}


# ---------------------------------------------------------------------------
# 수집 함수
# ---------------------------------------------------------------------------


def fetch_stock_data(tickers: dict[str, str], period: str = "1y") -> pd.DataFrame:
    """
    yfinance를 사용하여 주가 데이터를 다운로드하고 Long 형태로 변환합니다.

    yfinance는 기본적으로 멀티인덱스(Wide) 형태로 데이터를 반환합니다.
    Databricks에서 쉽게 읽을 수 있도록 각 행이 (날짜 + 종목) 단위인
    Long 형태로 변환합니다.

    [Wide 형태 - 변환 전]
               NVDA              TSM
               Open  Close  ...  Open  Close  ...
    Date
    2025-01-02  ...   ...        ...   ...

    [Long 형태 - 변환 후]
    Date        Ticker  Open    High    Low     Close   Volume
    2025-01-02  NVDA    138.5   140.2   137.1   139.8   123456789
    2025-01-02  TSM     180.3   182.1   179.5   181.2   45678900
    ...

    Args:
        tickers (dict[str, str]): {종목명: 티커코드} 딕셔너리
        period (str): 수집 기간 (기본값: '1y' = 1년)
                      '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y'

    Returns:
        pd.DataFrame: Long 형태로 변환된 OHLCV 데이터프레임

    Raises:
        RuntimeError: 데이터 수집 실패 시
    """
    ticker_codes = list(tickers.values())
    logger.info("데이터 다운로드 시작: %s (기간: %s)", ticker_codes, period)

    # yfinance 다운로드 (Wide 멀티인덱스 형태)
    raw_df = yf.download(ticker_codes, period=period, group_by="ticker")
    logger.info("데이터 다운로드 완료. shape=%s", raw_df.shape)

    # -----------------------------------------------------------------------
    # Wide → Long 변환
    # -----------------------------------------------------------------------
    long_records = []

    # 티커코드 → 종목명 역방향 매핑 (로그용)
    code_to_name = {v: k for k, v in tickers.items()}

    for ticker_code in ticker_codes:
        try:
            # 멀티인덱스에서 해당 종목 컬럼만 추출
            ticker_df = raw_df[ticker_code].copy()

            # 필요한 컬럼만 선택 (존재하는 것만)
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in ticker_df.columns]
            ticker_df = ticker_df[cols]

            # 결측치 행 제거 (휴장일 등)
            ticker_df = ticker_df.dropna(how="all")

            # 종목 정보 컬럼 추가
            ticker_df["Ticker"] = ticker_code
            ticker_df["Name"]   = code_to_name.get(ticker_code, ticker_code)

            long_records.append(ticker_df)
            logger.info("  [%s] %d행 변환 완료", ticker_code, len(ticker_df))

        except KeyError:
            logger.warning("  [%s] 데이터 없음 — 건너뜁니다.", ticker_code)
            continue

    if not long_records:
        raise RuntimeError("수집된 데이터가 없습니다. 티커 코드 및 네트워크 상태를 확인하세요.")

    # 전체 종목 합치기
    final_df = pd.concat(long_records)

    # 타임존 제거 (한국/미국 혼용 시 충돌 방지)
    final_df.index = final_df.index.tz_localize(None)

    # 컬럼 순서 정리: Ticker, Name 을 앞으로
    col_order = ["Ticker", "Name", "Open", "High", "Low", "Close", "Volume"]
    col_order = [c for c in col_order if c in final_df.columns]
    final_df = final_df[col_order]

    # 날짜 오름차순 정렬
    final_df = final_df.sort_index()

    logger.info("Long 변환 완료. 최종 shape=%s", final_df.shape)
    logger.info("수집 기간: %s ~ %s", final_df.index.min(), final_df.index.max())
    logger.info("수집 종목 수: %d개", final_df["Ticker"].nunique())

    return final_df


# ---------------------------------------------------------------------------
# 업로드 함수
# ---------------------------------------------------------------------------


def upload_to_adls(df: pd.DataFrame, date: datetime) -> None:
    """
    데이터프레임을 CSV로 변환하여 ADLS Gen2 raw 컨테이너에 업로드합니다.

    업로드 경로:
        raw 컨테이너 / yfinance/year={Y}/month={M}/day={D}/yahoo_finance_raw_{YYYYMMDD}.csv

    Args:
        df (pd.DataFrame): 업로드할 주가 데이터프레임 (Long 형태)
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
        1. 반도체 관련 종목 1년치 주가 데이터 수집 (미국 + 한국)
        2. Wide → Long 형태 변환
        3. ADLS Gen2 raw 컨테이너에 직접 업로드
    """
    # 1. 데이터 수집 및 Long 변환
    stock_df = fetch_stock_data(tickers=SEMICONDUCTOR_TICKERS, period="1y")

    # UTC 기준 날짜 사용 — 팀원 간 날짜 기준 통일
    now_utc = datetime.now(tz=timezone.utc)

    # 2. ADLS Gen2 업로드
    upload_to_adls(stock_df, now_utc)


if __name__ == "__main__":
    main()