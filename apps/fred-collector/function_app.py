import datetime
import logging
import os

import azure.functions as func
import pandas as pd
from azure.storage.blob import BlobServiceClient
from fredapi import Fred

# ---------------------------------------------------------------------------
# Azure Function App 초기화
# ---------------------------------------------------------------------------
app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 0 1 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False
)
def fred_to_blob_fetcher(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info("The timer is past due!")

    logging.info("FRED data fetcher function started.")

    # =======================================================================
    # 1. 환경 변수 로드 및 검증
    # =======================================================================
    fred_api_key = os.environ.get("FRED_API_KEY")
    storage_conn_str = os.environ.get("TARGET_STORAGE_CONNECTION_STRING")
    container_name = os.environ.get("RAW_CONTAINER")

    if not all([fred_api_key, storage_conn_str, container_name]):
        logging.error(
            "Missing required environment variables. "
            "Please check local.settings.json or Azure App Settings."
        )
        return

    # =======================================================================
    # 2. API 클라이언트 세팅 및 수집 대상 정의
    # =======================================================================
    fred = Fred(api_key=fred_api_key)

    tickers = {
        "DGS10": "10-Year Treasury",
        "DGS2": "2-Year Treasury",
        "T10Y2Y": "10Y-2Y Spread",
        "BAMLH0A0HYM2": "High Yield Spread",
        "DFF": "Effective Federal Funds Rate",
        "DFII10": "10-Year Real Yield",
    }

    # =======================================================================
    # 3. 데이터 수집 기간 및 메타데이터 설정 (7일 롤링 윈도우)
    # =======================================================================
    end_date = datetime.datetime.today()
    start_date = end_date - datetime.timedelta(days=7)
    crawled_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    records = []

    # =======================================================================
    # 4. 데이터 수집 및 전처리 파이프라인
    # =======================================================================
    try:
        # [Step 4-1] FRED API 호출
        for ticker in tickers.keys():
            logging.info(f"Fetching FRED data for ticker: {ticker}")
            data = fred.get_series(ticker, observation_start=start_date, observation_end=end_date)

            # 결측치(주말, 공휴일 등 미발표일) 제외 후 리스트에 추가
            for date_idx, value in data.dropna().items():
                date_str = date_idx.strftime("%Y-%m-%d")
                records.append((date_str, ticker, float(value), crawled_at))

        if not records:
            logging.info("No new data to upload today.")
            return

        # [Step 4-2] Pandas 데이터프레임 변환 (한글 속성명 적용)
        df = pd.DataFrame(records, columns=["관측일자", "지표코드", "금리값", "수집일시"])

        # [Step 4-3] Azure Blob Storage 클라이언트 연결
        blob_service_client = BlobServiceClient.from_connection_string(storage_conn_str)
        container_client = blob_service_client.get_container_client(container_name)

        # [Step 4-4] 저장 경로(가상 폴더) 및 파일명 동적 생성
        today_str = end_date.strftime("%Y-%m-%d")
        blob_name = f"fred_macro_data/{today_str}/rates_data.parquet"
        blob_client = container_client.get_blob_client(blob_name)

        # [Step 4-5] Parquet 직렬화 및 스토리지 업로드
        parquet_data = df.to_parquet(engine="pyarrow", index=False)
        blob_client.upload_blob(parquet_data, overwrite=True)

        logging.info(f"Successfully uploaded {len(records)} records as Parquet.")
        logging.info(f"Storage Path: [{container_name}] {blob_name}")

    except Exception as e:
        logging.error(f"An error occurred during the FRED data pipeline: {str(e)}")
