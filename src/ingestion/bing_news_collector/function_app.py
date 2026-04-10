import azure.functions as func
import datetime
import hashlib
import json
import logging
import os
import re
from html import unescape
from urllib.parse import quote_plus, urlparse

import feedparser
import pandas as pd
import requests
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

app = func.FunctionApp()

KEYWORDS = ["Samsung", "SK hynix"]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUIRED_ENV_KEYS = [
    "PROJECT_CONNECTION_STRING",
    "PROJECT_ENDPOINT",
    "STORAGE_CONNECTION_STRING",
    "RAW_CONTAINER",
    "FOLDER_PATH",
]


def clean_text(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def contains_hangul(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text or ""))


def english_alpha_ratio(text: str) -> float:
    value = text or ""
    letters = re.findall(r"[A-Za-z]", value)
    alpha = re.findall(r"[A-Za-z\uac00-\ud7a3]", value)
    if not alpha:
        return 0.0
    return len(letters) / len(alpha)


def is_english_article(headline: str, description: str, body: str) -> bool:
    merged = " ".join([headline or "", description or "", body or ""]).strip()
    if not merged:
        return False
    if contains_hangul(merged):
        return False
    return english_alpha_ratio(merged) >= 0.85


def normalize_pub_date(raw_value: str, parsed_struct=None) -> str:
    if parsed_struct:
        try:
            dt = datetime.datetime(*parsed_struct[:6], tzinfo=datetime.timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    raw = (raw_value or "").strip()
    if not raw:
        return ""

    for fmt in [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%b %d, %Y",
        "%B %d, %Y",
    ]:
        try:
            return datetime.datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


def in_target_range(pub_date: str, start_date: datetime.date, end_date: datetime.date) -> bool:
    try:
        dt = datetime.datetime.strptime(pub_date, "%Y-%m-%d").date()
        return start_date <= dt <= end_date
    except ValueError:
        return False


def parse_adjusted_month(adjusted_date: str) -> tuple[datetime.date, datetime.date]:
    year, month = adjusted_date.split("-")
    year_i = int(year)
    month_i = int(month)
    start_date = datetime.date(year_i, month_i, 1)
    if month_i == 12:
        end_date = datetime.date(year_i + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        end_date = datetime.date(year_i, month_i + 1, 1) - datetime.timedelta(days=1)
    return start_date, end_date


def get_monthly_target(adjusted_date: str) -> int:
    override_key = f"TARGET_{adjusted_date.replace('-', '_')}"
    override_raw = os.environ.get(override_key, "").strip()
    if override_raw:
        try:
            override_value = int(override_raw)
            if override_value > 0:
                return override_value
        except ValueError:
            pass

    # Recommended target profile:
    # - 2026-04: 50
    # - 2026-03, 2026-02: 100
    # - 2026-01 to 2025-10: 30
    # - 2025-09 to 2025-04: 20
    if adjusted_date == "2026-04":
        return 50
    if adjusted_date in {"2026-03", "2026-02"}:
        return 100
    if adjusted_date in {"2026-01", "2025-12", "2025-11", "2025-10"}:
        return 30
    return 20


def build_bing_news_rss_url(query: str) -> str:
    return f"https://www.bing.com/news/search?q={quote_plus(query)}&format=RSS"


def resolve_final_url(raw_url: str) -> str:
    try:
        resp = requests.get(
            raw_url,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
            timeout=10,
        )
        final_url = (resp.url or "").strip()
    except requests.RequestException:
        return ""

    if not final_url:
        return ""
    if not re.match(r"^https?://", final_url, re.IGNORECASE):
        return ""
    return final_url


def build_search_queries(start_date_str: str, query_end_date_str: str) -> dict:
    del start_date_str, query_end_date_str

    event_terms = [
        "earnings",
        "guidance",
        "forecast",
        "outlook",
        "capex",
        "investment",
        "expansion",
        "production",
        "output",
        "shipment",
        "supply",
        "contract",
        "order",
        "demand",
        "pricing",
        "market share",
        "utilization",
        "inventory",
        "margin",
        "profit",
        "guidance cut",
        "guidance raise",
        "price hike",
        "price decline",
        "demand recovery",
        "weak demand",
        "oversupply",
        "undersupply",
        "downturn",
        "upcycle",
    ]
    segment_terms = [
        "semiconductor",
        "memory",
        "memory chip",
        "DRAM",
        "NAND",
        "HBM",
        "HBM3E",
        "AI memory",
        "server memory",
        "chip",
        "foundry",
        "advanced packaging",
        "2.5D packaging",
        "TSV",
        "CXL",
        "wafer",
        "fab",
        "semiconductor industry",
        "chip industry",
        "memory industry",
        "OSAT",
        "assembly test",
        "back-end process",
        "front-end process",
        "process node",
        "EUV",
        "clean room",
        "yield rate",
        "wafer starts",
    ]
    ecosystem_terms = [
        "NVIDIA",
        "AMD",
        "Intel",
        "hyperscaler",
        "AI server",
        "data center",
        "cloud",
        "automotive",
        "smartphone",
        "TSMC",
        "Micron",
        "Qualcomm",
        "Broadcom",
        "Marvell",
        "Google",
        "Microsoft",
        "Meta",
        "Amazon",
        "OpenAI",
    ]
    supply_chain_terms = [
        "equipment",
        "materials",
        "substrate",
        "photoresist",
        "etching",
        "deposition",
        "packaging substrate",
        "co-packaged optics",
        "HPC",
        "AI accelerator",
        "server OEM",
    ]
    market_terms = [
        "semiconductor market",
        "memory market",
        "chip market",
        "industry report",
        "analyst note",
        "broker report",
        "earnings call",
        "investor day",
        "supply chain update",
        "production plan",
    ]

    base_aliases = {
        "Samsung": ["Samsung", "Samsung Electronics"],
        "SK hynix": ["SK hynix", "SK Hynix"],
    }

    queries_by_keyword = {}
    for keyword, aliases in base_aliases.items():
        query_set = set()
        for alias in aliases:
            query_set.add(alias)
            for segment in segment_terms:
                query_set.add(f"{alias} {segment}")
            for event in event_terms:
                query_set.add(f"{alias} {event}")
            for segment in segment_terms:
                for event in event_terms:
                    query_set.add(f"{alias} {segment} {event}")
            for eco in ecosystem_terms:
                query_set.add(f"{alias} {eco}")
                query_set.add(f"{alias} semiconductor {eco}")
                query_set.add(f"{alias} memory {eco}")
            for supply in supply_chain_terms:
                query_set.add(f"{alias} semiconductor {supply}")
                query_set.add(f"{alias} memory {supply}")
                query_set.add(f"{alias} chip {supply}")
            for market in market_terms:
                query_set.add(f"{alias} {market}")
                query_set.add(f"{alias} semiconductor {market}")

            # Broader templates to fetch indirectly-related semiconductor coverage.
            for segment in segment_terms:
                for market in market_terms:
                    query_set.add(f"{alias} {segment} {market}")
            for eco in ecosystem_terms:
                for event in event_terms:
                    query_set.add(f"{alias} {eco} {event}")
                    query_set.add(f"{alias} semiconductor {eco} {event}")
            for supply in supply_chain_terms:
                for event in event_terms:
                    query_set.add(f"{alias} {supply} {event}")
                    query_set.add(f"{alias} semiconductor {supply} {event}")

            # Include a few high-recall boolean-like expressions for Bing RSS.
            query_set.add(f"{alias} semiconductor OR memory OR foundry")
            query_set.add(f"{alias} HBM OR DRAM OR NAND")
            query_set.add(f"{alias} chip OR semiconductor industry")

        # Keep deterministic order to make repeated runs reproducible.
        queries_by_keyword[keyword] = sorted(query_set)

    return queries_by_keyword


def collect_rss_candidates(
    keyword: str,
    query_list: list,
    start_date: datetime.date,
    end_date: datetime.date,
    max_candidates: int,
    strict_date_filter: bool = True,
) -> list:
    seen_links = set()
    candidates = []

    for query in query_list:
        rss_url = build_bing_news_rss_url(query)
        try:
            rss_resp = requests.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=15)
            rss_resp.raise_for_status()
            feed = feedparser.parse(rss_resp.content)
        except requests.RequestException as ex:
            logging.warning("[%s] RSS fetch 실패 | query=%s | err=%s", keyword, query, ex)
            continue

        for entry in feed.entries:
            raw_link = str(entry.get("link", "")).strip()
            if not raw_link:
                continue

            if raw_link in seen_links:
                continue

            headline = clean_text(str(entry.get("title", "")))
            description = clean_text(str(entry.get("summary", "")))
            press = clean_text(str(getattr(entry.get("source", {}), "title", "")))
            pub_date = normalize_pub_date(
                str(entry.get("published", entry.get("updated", ""))),
                parsed_struct=entry.get("published_parsed", entry.get("updated_parsed", None)),
            )

            if not headline or not pub_date:
                continue
            if strict_date_filter and not in_target_range(pub_date, start_date, end_date):
                continue

            seen_links.add(raw_link)
            candidates.append(
                {
                    "source": keyword,
                    "headline": headline,
                    "url": raw_link,
                    "pubDate": pub_date,
                    "press": press,
                    "description": description,
                }
            )

            if len(candidates) >= max_candidates:
                break

        if len(candidates) >= max_candidates:
            break

    return candidates


def build_ai_prompt(keyword: str, candidates: list, start_str: str, end_str: str, max_items: int) -> str:
    facts = []
    for idx, row in enumerate(candidates, start=1):
        facts.append(
            {
                "id": idx,
                "headline": row["headline"],
                "url": row["url"],
                "press": row.get("press", ""),
                "pubDate": row["pubDate"],
                "description": row.get("description", ""),
            }
        )

    facts_json = json.dumps(facts, ensure_ascii=False, indent=2)

    return f"""
You are a semiconductor business analyst.

You are given a factual RSS article list for keyword '{keyword}' from {start_str} to {end_str}.

Hard constraints:
1) Never invent, modify, or replace any URL or headline.
2) Use only URL/headline pairs exactly as listed in RSS_FACT_LIST.
3) Return as many items as possible from RSS_FACT_LIST, up to {max_items}. Do not stop early.
4) Keep items related to semiconductor business signals: HBM, DRAM/NAND, foundry, yield, earnings, guidance, supply contracts, capex, AI server memory demand, stock price, market outlook, investor response, and major partnership news involving Samsung or SK hynix.
    Also keep broader semiconductor-industry items if they are clearly related to Samsung or SK hynix ecosystem, customers, suppliers, or peer competition.
5) Select ENGLISH articles only. Exclude Korean-language articles.
6) For each selected item, write a body of at least 60 characters containing concrete proper nouns and meaningful business context in English.
6) Return only a valid JSON array.

Output schema:
[
  {{
    "headline": "...",
    "url": "...",
    "press": "...",
    "pubDate": "YYYY-MM-DD",
    "description": "...",
    "body": "..."
  }}
]

RSS_FACT_LIST:
{facts_json}
""".strip()


def parse_json_array(text: str) -> list:
    clean = re.sub(r"```(?:json)?", "", text or "").replace("```", "").strip()
    match = re.search(r"\[.*\]", clean, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group())
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def chunked_list(items: list, chunk_size: int) -> list:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def validate_ai_items(
    keyword: str,
    ai_items: list,
    candidate_map_by_url: dict,
    adjusted_date: str,
    fetched_at: str,
    max_items: int,
) -> list:
    selected = []
    seen_news_ids = set()

    for item in ai_items:
        if len(selected) >= max_items:
            break
        if not isinstance(item, dict):
            continue

        url = str(item.get("url", "")).strip()
        if not url:
            continue

        src = candidate_map_by_url.get(url)
        if not src:
            continue

        canonical_url = resolve_final_url(src.get("url", ""))
        if not canonical_url:
            continue

        # Preserve canonical headline/url from RSS facts exactly.
        headline = src["headline"]
        press = src.get("press", "")
        pub_date = src.get("pubDate", "")
        description = src.get("description", "")
        body = clean_text(str(item.get("body", "")))

        if len(body) < 60:
            continue
        if not is_english_article(headline, description, body):
            continue

        news_id = "bing_" + hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
        if news_id in seen_news_ids:
            continue

        selected.append(
            {
                "source": keyword,
                "newsId": news_id,
                "url": canonical_url,
                "pubDate": pub_date,
                "adjustedDate": adjusted_date,
                "headline": headline,
                "press": press,
                "description": description,
                "body": body,
                "fetchedAt": fetched_at,
            }
        )
        seen_news_ids.add(news_id)

    return selected


def iter_month_windows(start_year: int, start_month: int, end_year: int, end_month: int) -> list:
    windows = []
    cursor = datetime.date(start_year, start_month, 1)
    end_cursor = datetime.date(end_year, end_month, 1)

    while cursor <= end_cursor:
        if cursor.month == 12:
            next_month = datetime.date(cursor.year + 1, 1, 1)
        else:
            next_month = datetime.date(cursor.year, cursor.month + 1, 1)

        last_day = next_month - datetime.timedelta(days=1)
        windows.append(
            {
                "start_date": cursor,
                "end_date": last_day,
                "adjusted_date": cursor.strftime("%Y-%m"),
            }
        )
        cursor = next_month

    return windows


def build_backfill_template_windows() -> list:
    # Backfill execution range: 2025-03 to 2026-03 monthly loop
    windows = iter_month_windows(2025, 3, 2026, 3)
    windows.reverse()
    return windows


def build_current_month_window(now_utc_date: datetime.date) -> list:
    return [
        {
            "start_date": datetime.date(2026, 4, 1),
            "end_date": now_utc_date,
            "adjusted_date": "2026-04",
        }
    ]


def upload_month_records(storage_conn_str: str, container_name: str, folder_path: str, adjusted_date: str, records: list) -> None:
    if not records:
        logging.info("[%s] 업로드할 데이터가 없습니다.", adjusted_date)
        return

    df = pd.DataFrame(
        records,
        columns=[
            "source",
            "newsId",
            "url",
            "pubDate",
            "adjustedDate",
            "headline",
            "press",
            "description",
            "body",
            "fetchedAt",
        ],
    )
    before = len(df)
    df = df.drop_duplicates(subset=["newsId"])
    after = len(df)
    logging.info("[%s] 중복 제거: %d -> %d", adjusted_date, before, after)

    year, month = adjusted_date.split("-")
    prefix = f"{folder_path}{adjusted_date}/"
    json_blob_name = f"{prefix}bing_news_{year}_{month}.json"
    parquet_blob_name = f"{prefix}bing_news_{year}_{month}.parquet"

    blob_service = BlobServiceClient.from_connection_string(storage_conn_str)
    container = blob_service.get_container_client(container_name)

    json_bytes = json.dumps(df.to_dict(orient="records"), ensure_ascii=False, indent=2).encode("utf-8")
    container.get_blob_client(json_blob_name).upload_blob(json_bytes, overwrite=True)

    parquet_bytes = df.to_parquet(engine="pyarrow", index=False)
    container.get_blob_client(parquet_blob_name).upload_blob(parquet_bytes, overwrite=True)

    logging.info("[%s] JSON 업로드 완료: [%s] %s", adjusted_date, container_name, json_blob_name)
    logging.info("[%s] Parquet 업로드 완료: [%s] %s", adjusted_date, container_name, parquet_blob_name)
    logging.info("[%s] 총 %d건 업로드", adjusted_date, len(df))


def enforce_quality_for_month(records: list, adjusted_date: str) -> list:
    month_start, month_end = parse_adjusted_month(adjusted_date)
    filtered = []
    seen = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        news_id = str(row.get("newsId", "")).strip()
        if not news_id or news_id in seen:
            continue

        headline = clean_text(str(row.get("headline", "")))
        description = clean_text(str(row.get("description", "")))
        body = clean_text(str(row.get("body", "")))
        pub_date = str(row.get("pubDate", "")).strip()

        if not is_english_article(headline, description, body):
            continue
        if not in_target_range(pub_date, month_start, month_end):
            continue

        row["headline"] = headline
        row["description"] = description
        row["body"] = body
        filtered.append(row)
        seen.add(news_id)

    return filtered


def month_blob_names(folder_path: str, adjusted_date: str) -> tuple[str, str]:
    year, month = adjusted_date.split("-")
    prefix = f"{folder_path}{adjusted_date}/"
    json_blob_name = f"{prefix}bing_news_{year}_{month}.json"
    parquet_blob_name = f"{prefix}bing_news_{year}_{month}.parquet"
    return json_blob_name, parquet_blob_name


def get_month_existing_records(storage_conn_str: str, container_name: str, folder_path: str, adjusted_date: str) -> list:
    json_blob_name, _ = month_blob_names(folder_path, adjusted_date)

    blob_service = BlobServiceClient.from_connection_string(storage_conn_str)
    container = blob_service.get_container_client(container_name)
    blob = container.get_blob_client(json_blob_name)
    if not blob.exists():
        return []

    try:
        rows = json.loads(blob.download_blob().readall())
    except Exception:
        return []

    if not isinstance(rows, list):
        return []

    month_start, month_end = parse_adjusted_month(adjusted_date)
    filtered = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        news_id = str(row.get("newsId", "")).strip()
        if not news_id or news_id in seen:
            continue
        if not is_english_article(
            clean_text(str(row.get("headline", ""))),
            clean_text(str(row.get("description", ""))),
            clean_text(str(row.get("body", ""))),
        ):
            continue
        pub_date = str(row.get("pubDate", "")).strip()
        if not in_target_range(pub_date, month_start, month_end):
            continue
        filtered.append(row)
        seen.add(news_id)

    return filtered


@app.timer_trigger(schedule="0 0 1 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def semiconductor_news_fetcher(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info("The timer is past due!")

    logging.info("반도체 뉴스 수집 파이프라인 시작 (Bing RSS + AI 하이브리드, Production Backfill)")

    project_connection_string = os.environ.get("PROJECT_CONNECTION_STRING", "").strip()
    project_endpoint = os.environ.get("PROJECT_ENDPOINT", "").strip()
    storage_conn_str = os.environ.get("STORAGE_CONNECTION_STRING", "").strip()
    container_name = os.environ.get("RAW_CONTAINER", "").strip()
    folder_path = os.environ.get("FOLDER_PATH", "").strip()
    if not folder_path.endswith("/"):
        folder_path += "/"

    missing = [key for key in REQUIRED_ENV_KEYS if not os.environ.get(key, "").strip()]
    if missing:
        logging.error("필수 환경 변수가 누락되었습니다: %s", ", ".join(missing))
        return

    now_utc_date = datetime.datetime.now(datetime.timezone.utc).date()
    if os.environ.get("BACKFILL_MODE", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}:
        execution_windows = build_backfill_template_windows()
    else:
        execution_windows = build_current_month_window(now_utc_date)

    target_months_raw = os.environ.get("TARGET_MONTHS", "").strip()
    if target_months_raw:
        target_months = {item.strip() for item in target_months_raw.split(",") if item.strip()}
        execution_windows = [w for w in execution_windows if w["adjusted_date"] in target_months]
        logging.info("TARGET_MONTHS 적용: %s", ", ".join(sorted(target_months, reverse=True)))

    max_per_keyword = 350
    max_queries_per_keyword = int(os.environ.get("MAX_QUERIES_PER_KEYWORD", "300").strip() or "300")
    if max_queries_per_keyword <= 0:
        max_queries_per_keyword = 300
    # Keep strict month filtering to preserve month consistency.
    force_fill_mode = False
    max_chunk_count = int(os.environ.get("MAX_CHUNK_COUNT", "0").strip() or "0")
    if max_chunk_count <= 0:
        max_chunk_count = len(execution_windows)
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        if hasattr(AIProjectClient, "from_connection_string"):
            try:
                project_client = AIProjectClient.from_connection_string(
                    conn_str=project_connection_string,
                    credential=DefaultAzureCredential(),
                )
            except Exception:
                project_client = AIProjectClient(
                    endpoint=project_endpoint,
                    credential=DefaultAzureCredential(),
                )
        else:
            project_client = AIProjectClient(
                endpoint=project_endpoint,
                credential=DefaultAzureCredential(),
            )

        with project_client:
            openai_client = project_client.get_openai_client()

            processed_windows = 0
            for window in execution_windows:
                if processed_windows >= max_chunk_count:
                    logging.info("청크 상한 도달: %d개월 처리 후 종료", max_chunk_count)
                    break

                start_date = window["start_date"]
                end_date = window["end_date"]
                adjusted_date = window["adjusted_date"]
                monthly_target = get_monthly_target(adjusted_date)
                min_monthly_target = monthly_target

                existing_rows = get_month_existing_records(storage_conn_str, container_name, folder_path, adjusted_date)
                month_records_by_id = {str(row.get("newsId")): row for row in existing_rows if str(row.get("newsId", "")).strip()}
                if len(month_records_by_id) >= monthly_target:
                    logging.info("[%s] 기존 영문 데이터 %d건으로 목표(%d건) 충족, 스킵", adjusted_date, len(month_records_by_id), monthly_target)
                    safe_existing = enforce_quality_for_month(list(month_records_by_id.values()), adjusted_date)
                    upload_month_records(
                        storage_conn_str=storage_conn_str,
                        container_name=container_name,
                        folder_path=folder_path,
                        adjusted_date=adjusted_date,
                        records=safe_existing,
                    )
                    processed_windows += 1
                    continue

                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                query_end_str = (end_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                year = adjusted_date[:4]
                month = adjusted_date[5:7]

                logging.info("[%s] 수집 윈도우 시작: %s ~ %s | 기존 영문 %d건", adjusted_date, start_str, end_str, len(month_records_by_id))

                queries_by_keyword = build_search_queries(start_str, query_end_str)

                for keyword in KEYWORDS:
                    if len(month_records_by_id) >= monthly_target:
                        break

                    keyword_queries_all = queries_by_keyword.get(keyword, [])
                    keyword_queries = keyword_queries_all[:max_queries_per_keyword]
                    logging.info(
                        "[%s][%s] 쿼리 사용량: %d개 (생성 총 %d개)",
                        adjusted_date,
                        keyword,
                        len(keyword_queries),
                        len(keyword_queries_all),
                    )
                    candidates = collect_rss_candidates(
                        keyword=keyword,
                        query_list=keyword_queries,
                        start_date=start_date,
                        end_date=end_date,
                        max_candidates=700,
                        strict_date_filter=not force_fill_mode,
                    )

                    logging.info("[%s][%s] RSS 후보 %d건", adjusted_date, keyword, len(candidates))
                    if not candidates:
                        continue

                    selected = []
                    for batch_index, batch in enumerate(chunked_list(candidates, 15), start=1):
                        if len(selected) >= max_per_keyword or len(month_records_by_id) >= monthly_target:
                            break

                        remaining_keyword = max_per_keyword - len(selected)
                        remaining_month = monthly_target - len(month_records_by_id)
                        remaining = min(remaining_keyword, remaining_month)
                        if remaining <= 0:
                            break

                        batch = batch[:remaining]
                        candidate_map_by_url = {c["url"]: c for c in batch}
                        prompt = build_ai_prompt(keyword, batch, start_str, end_str, len(batch))

                        response = openai_client.responses.create(
                            model="gpt-4o-mini",
                            input=prompt,
                        )

                        ai_items = parse_json_array(getattr(response, "output_text", "") or "")
                        logging.info("[%s][%s][batch %d] AI 반환 %d건", adjusted_date, keyword, batch_index, len(ai_items))

                        batch_selected = validate_ai_items(
                            keyword=keyword,
                            ai_items=ai_items,
                            candidate_map_by_url=candidate_map_by_url,
                            adjusted_date=adjusted_date,
                            fetched_at=fetched_at,
                            max_items=remaining,
                        )

                        logging.info("[%s][%s][batch %d] 최종 선별 %d건", adjusted_date, keyword, batch_index, len(batch_selected))
                        for row in batch_selected:
                            month_records_by_id[row["newsId"]] = row
                            selected.append(row)

                        logging.info(
                            "현재 %s년 %s월 수집 중... (%d/%d건 완료)",
                            year,
                            month,
                            len(month_records_by_id),
                            monthly_target,
                        )

                    logging.info("[%s][%s] 최종 선별 %d건", adjusted_date, keyword, len(selected))
                window_records = list(month_records_by_id.values())
                window_records = enforce_quality_for_month(window_records, adjusted_date)
                if len(window_records) < min_monthly_target:
                    logging.warning(
                        "[%s] 월 최소치(%d건) 미달: %d건 (가능한 최대치로 저장 후 다음 달 진행)",
                        adjusted_date,
                        min_monthly_target,
                        len(window_records),
                    )

                upload_month_records(
                    storage_conn_str=storage_conn_str,
                    container_name=container_name,
                    folder_path=folder_path,
                    adjusted_date=adjusted_date,
                    records=window_records,
                )
                processed_windows += 1

    except Exception as ex:
        logging.exception("반도체 뉴스 수집 파이프라인 오류: %s", ex)
