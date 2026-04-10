import datetime
import json
import os
import re
import time
import types

from azure.storage.blob import BlobServiceClient

import function_app

STORAGE_CONNECTION_STRING = os.environ.get("STORAGE_CONNECTION_STRING", "").strip()
CONTAINER = os.environ.get("RAW_CONTAINER", "raw").strip() or "raw"
PREFIX = os.environ.get("FOLDER_PATH", "news/bing/").strip() or "news/bing/"
if not PREFIX.endswith("/"):
    PREFIX += "/"
TARGET_MIN = 50
SLEEP_SECONDS = 30
CHUNK_SIZE = 3

HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
ALPHA_RE = re.compile(r"[A-Za-z\uac00-\ud7a3]")
ENG_RE = re.compile(r"[A-Za-z]")


def iter_target_months():
    y, m = 2026, 4
    while y > 2025 or (y == 2025 and m >= 4):
        yield f"{y}-{m:02d}"
        m -= 1
        if m == 0:
            y -= 1
            m = 12


def monthly_target(month: str) -> int:
    if month == "2026-04":
        return 50
    if month in {"2026-03", "2026-02"}:
        return 100
    if month in {"2026-01", "2025-12", "2025-11", "2025-10"}:
        return 30
    return 20


def eng_ratio(text: str) -> float:
    alpha = ALPHA_RE.findall(text or "")
    if not alpha:
        return 0.0
    eng = ENG_RE.findall(text or "")
    return len(eng) / len(alpha)


def is_english_row(row: dict) -> bool:
    text = " ".join(
        [
            str(row.get("headline", "")),
            str(row.get("description", "")),
            str(row.get("body", "")),
        ]
    )
    if HANGUL_RE.search(text):
        return False
    return eng_ratio(text) >= 0.85


def load_month_count(container_client, month):
    yy, mm = month.split("-")
    path = f"{PREFIX}{month}/bing_news_{yy}_{mm}.json"
    blob = container_client.get_blob_client(path)
    if not blob.exists():
        return 0

    try:
        rows = json.loads(blob.download_blob().readall())
    except Exception:
        return 0

    if not isinstance(rows, list):
        return 0

    valid = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        pub_date = str(row.get("pubDate", "")).strip()
        if not pub_date.startswith(month):
            continue
        if not is_english_row(row):
            continue
        valid += 1
    return valid


def get_counts():
    if not STORAGE_CONNECTION_STRING:
        raise RuntimeError("STORAGE_CONNECTION_STRING is required")
    container = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING).get_container_client(CONTAINER)
    result = {}
    for month in iter_target_months():
        result[month] = load_month_count(container, month)
    return result


def deficits(counts):
    return {k: v for k, v in counts.items() if v < monthly_target(k)}


def top_n_deficits(need_map: dict, n: int) -> list:
    ordered = sorted(need_map.items(), key=lambda kv: (monthly_target(kv[0]) - kv[1]), reverse=True)
    return [month for month, _ in ordered[:n]]


def run_once(chunk_months: list[str]):
    os.environ["BACKFILL_MODE"] = "1"
    os.environ["MAX_CHUNK_COUNT"] = str(CHUNK_SIZE)
    os.environ["TARGET_MONTHS"] = ",".join(chunk_months)
    function_app.semiconductor_news_fetcher(types.SimpleNamespace(past_due=False))


def main():
    round_idx = 1
    while True:
        now = datetime.datetime.now().isoformat()
        before = get_counts()
        need_before = deficits(before)
        print(f"[{now}] ROUND {round_idx} START | deficit_months={len(need_before)}")
        for month, count in need_before.items():
            print(f"  - {month}: {count}/{monthly_target(month)}")

        if not need_before:
            print("All target months reached quality targets. Loop ends.")
            break

        chunk_months = top_n_deficits(need_before, CHUNK_SIZE)
        print("Processing chunk:", ", ".join(chunk_months))

        run_once(chunk_months)

        after = get_counts()
        need_after = deficits(after)
        print(f"ROUND {round_idx} END | deficit_months={len(need_after)}")
        for month in iter_target_months():
            b = before[month]
            a = after[month]
            marker = "*" if a != b else " "
            print(f"{marker} {month}: {b} -> {a} (target={monthly_target(month)})")

        round_idx += 1
        if need_after:
            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
