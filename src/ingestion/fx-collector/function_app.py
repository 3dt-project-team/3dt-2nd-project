import datetime as dt
import json
import logging
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import azure.functions as func
import pyarrow as pa
import pyarrow.parquet as pq
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings

app = func.FunctionApp()

OXR_APP_ID = os.environ["OXR_APP_ID"]
RAW_CONTAINER = os.getenv("RAW_CONTAINER", "raw")
OXR_BASE_URL = "https://openexchangerates.org/api/latest.json"

BASE_CURRENCY = "USD"
QUOTE_CURRENCY = "KRW"


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "fx-collector/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_blob_service_client() -> BlobServiceClient:
    conn_str = os.getenv("TARGET_STORAGE_CONNECTION_STRING") or os.environ["AzureWebJobsStorage"]
    return BlobServiceClient.from_connection_string(conn_str)


def ensure_container(container_client) -> None:
    try:
        container_client.create_container()
    except ResourceExistsError:
        pass


def build_parquet_bytes(row: dict) -> bytes:
    schema = pa.schema(
        [
            pa.field("provider", pa.string()),
            pa.field("base_currency", pa.string()),
            pa.field("quote_currency", pa.string()),
            pa.field("rate", pa.float64()),
            pa.field("provider_timestamp_utc", pa.timestamp("us", tz="UTC")),
            pa.field("collected_at_utc", pa.timestamp("us", tz="UTC")),
            pa.field("collected_at_kst", pa.timestamp("us", tz="Asia/Seoul")),
            pa.field("provider_timestamp_unix", pa.int64()),
            pa.field("raw_payload_json", pa.string()),
        ]
    )

    table = pa.Table.from_pylist([row], schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="snappy")
    return sink.getvalue().to_pybytes()


@app.function_name(name="CollectUsdKrwHourly")
@app.timer_trigger(
    schedule="0 3 * * * *",  # 매시 03분
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=True,
)
def collect_usd_krw_hourly(mytimer: func.TimerRequest) -> None:
    if mytimer.past_due:
        logging.warning("Timer trigger is running late.")

    now_utc = dt.datetime.now(dt.timezone.utc)
    now_kst = now_utc.astimezone(ZoneInfo("Asia/Seoul"))

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
        raise ValueError(f"Unexpected response: {payload}")

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

    blob_service = get_blob_service_client()
    container_client = blob_service.get_container_client(RAW_CONTAINER)
    ensure_container(container_client)

    blob_name = (
        "fx/"
        "usd_krw/"
        "source=openexchangerates/"
        f"dt={now_kst:%Y-%m-%d}/"
        f"hour={now_kst:%H}/"
        f"part-{now_kst:%Y%m%dT%H%M%S%z}.parquet"
    )

    parquet_bytes = build_parquet_bytes(row)

    container_client.upload_blob(
        name=blob_name,
        data=parquet_bytes,
        overwrite=False,
        content_settings=ContentSettings(content_type="application/octet-stream"),
    )

    logging.info("Saved parquet to raw/%s", blob_name)
