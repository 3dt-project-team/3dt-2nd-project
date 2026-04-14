import datetime as dt
import json
import logging
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import azure.functions as func
from azure.storage.blob import ContentSettings

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)  # 인증 레벨 설정

OXR_APP_ID = os.environ["OXR_APP_ID"]
# 수정 코드 (직접 할당)
RAW_CONTAINER = "raw"
OXR_BASE_URL = "https://openexchangerates.org/api/latest.json"

BASE_CURRENCY = "USD"
QUOTE_CURRENCY = "KRW"

# ... (기존 fetch_json, get_blob_service_client, ensure_container, build_parquet_bytes 함수는 동일) ...


@app.route(route="collect/fx")  # 호출 경로 설정 (예: /api/collect/fx)
def collect_usd_krw_manual(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")

    try:
        now_utc = dt.datetime.now(dt.timezone.utc)
        now_kst = now_utc.astimezone(ZoneInfo("Asia/Seoul"))

        # API 호출 및 데이터 가공 로직 (기존과 동일)
        query = urllib.parse.urlencode(
            {
                "app_id": OXR_APP_ID,
                "symbols": QUOTE_CURRENCY,
                "prettyprint": "false",
            }
        )
        url = f"{OXR_BASE_URL}?{query}"
        payload = fetch_json(url)

        rate = payload.get("rates", {}).get(QUOTE_CURRENCY)
        provider_ts_unix = payload.get("timestamp")

        if rate is None or provider_ts_unix is None:
            return func.HttpResponse("Unexpected API response", status_code=500)

        provider_dt_utc = dt.datetime.fromtimestamp(provider_ts_unix, tz=dt.timezone.utc)

        row = {
            "provider": "openexchangerates",
            "base_currency": BASE_CURRENCY,
            "quote_currency": QUOTE_CURRENCY,
            "rate": float(rate),
            "provider_timestamp_utc": provider_dt_utc,
            "collected_at_utc": now_utc,
            "collected_at_kst": now_kst,
            "provider_timestamp_unix": int(provider_ts_unix),
            "raw_payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        }

        # Blob Storage 저장 로직
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(RAW_CONTAINER)
        ensure_container(container_client)

        blob_name = (
            "fx/usd_krw/source=openexchangerates/"
            f"dt={now_kst:%Y-%m-%d}/hour={now_kst:%H}/"
            f"part-{now_kst:%Y%m%dT%H%M%S%z}.parquet"
        )

        parquet_bytes = build_parquet_bytes(row)
        container_client.upload_blob(
            name=blob_name,
            data=parquet_bytes,
            overwrite=False,
            content_settings=ContentSettings(content_type="application/octet-stream"),
        )

        return func.HttpResponse(f"Successfully saved to {blob_name}", status_code=200)

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return func.HttpResponse(f"Internal Error: {str(e)}", status_code=500)
