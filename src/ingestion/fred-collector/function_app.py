import datetime
import logging
import os

import azure.functions as func
import pandas as pd
from azure.storage.blob import BlobServiceClient, ContentSettings
from fredapi import Fred

# Azure Function App 초기화
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# 컨테이너 이름 내재화
RAW_CONTAINER = "raw"

@app.route(route="collect/fred")
def fred_to_blob_fetcher(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("FRED data fetcher function (HTTP Trigger) started.")

    fred_api_key = os.environ.get("FRED_API_KEY")
    storage_conn_str = os.environ.get("TARGET_STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")

    if not all([fred_api_key, storage_conn_str]):
        return func.HttpResponse("Environment variables missing", status_code=500)

    try:
        fred = Fred(api_key=fred_api_key)
        tickers = ["DGS10", "DGS2", "T10Y2Y", "BAMLH0A0HYM2", "DFF", "DFII10"]
        
        end_date = datetime.datetime.today()
        start_date = end_date - datetime.timedelta(days=7)
        crawled_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        records = []
        for ticker in tickers:
            data = fred.get_series(ticker, observation_start=start_date, observation_end=end_date)
            for date_idx, value in data.dropna().items():
                records.append((date_idx.strftime("%Y-%m-%d"), ticker, float(value), crawled_at))

        if not records:
            return func.HttpResponse("No new data", status_code=200)

        df = pd.DataFrame(records, columns=["관측일자", "지표코드", "금리값", "수집일시"])
        
        # [수정] pandas를 이용해 직접 바이트로 변환
        parquet_bytes = df.to_parquet(index=False, engine='pyarrow')

        blob_service_client = BlobServiceClient.from_connection_string(storage_conn_str)
        container_client = blob_service_client.get_container_client(RAW_CONTAINER)

        today_str = end_date.strftime("%Y-%m-%d")
        blob_name = f"fred_macro_data/{today_str}/rates_data_{datetime.datetime.now().strftime('%H%M%S')}.parquet"
        
        container_client.upload_blob(
            name=blob_name,
            data=parquet_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/octet-stream")
        )

        return func.HttpResponse(f"Success: {blob_name}", status_code=200)

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)