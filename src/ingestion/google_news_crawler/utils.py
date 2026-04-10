"""
Google News 해외 뉴스 크롤러 유틸리티
"""

import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

# vault_manager: 컨테이너(/app/flat)와 로컈(src/utils/) 모두 지원
try:
    from vault_manager import get_vault_manager
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "utils"))
    from vault_manager import get_vault_manager

logger = logging.getLogger("google_news")

# ── ADLS 경로 상수 ───────────────────────────────────────────────────────
_ADLS_CONTAINER = "raw"
_CHECKPOINT_PREFIX = "news/google/checkpoints"
_OUTPUT_PREFIX = "news/google"


# ── 로깅 설정 ────────────────────────────────────────────────
def setup_logging(level: int = logging.INFO) -> None:
    fmt = "[%(asctime)s] %(levelname)-7s %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S")


# ── 날짜 유틸 ────────────────────────────────────────────────
def generate_monthly_ranges(start: str, end: str) -> list[tuple[str, str]]:
    """start~end 기간을 월별로 분할하여 (시작일, 종료일) 리스트를 반환한다.

    예: ('2025-04-01', '2025-06-15')
        → [('2025-04-01', '2025-04-30'), ('2025-05-01', '2025-05-31'), ('2025-06-01', '2025-06-15')]
    """
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    ranges: list[tuple[str, str]] = []

    current = s
    while current <= e:
        month_end = (current + pd.offsets.MonthEnd(0)).normalize()
        period_end = min(month_end, e)
        ranges.append((current.strftime("%Y-%m-%d"), period_end.strftime("%Y-%m-%d")))
        current = period_end + pd.Timedelta(days=1)

    return ranges


# ── ADLS 클라이언트 팩토리 ────────────────────────────────────
def _get_adls_client():
    return get_vault_manager().get_storage_client()


# ── 체크포인트 (월별 중간 저장) ───────────────────────────────
def _checkpoint_blob(keyword: str, month_start: str) -> str:
    safe_name = re.sub(r"[^\w가-힣]", "_", keyword)
    month_tag = month_start[:7]  # YYYY-MM
    return f"{_CHECKPOINT_PREFIX}/{safe_name}_{month_tag}.json"


def save_checkpoint(records: list[dict], keyword: str, month_start: str) -> str:
    blob_path = _checkpoint_blob(keyword, month_start)
    try:
        fs = _get_adls_client().get_file_system_client(_ADLS_CONTAINER)
        fc = fs.get_file_client(blob_path)
        data = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
        fc.upload_data(data, overwrite=True, length=len(data))
        logger.info("체크포인트 저장: %s (%d건)", blob_path, len(records))
    except Exception as e:
        logger.warning("체크포인트 ADLS 저장 실패 (스킵): %s", e)
    return blob_path


def load_checkpoint(keyword: str, month_start: str) -> list[dict] | None:
    blob_path = _checkpoint_blob(keyword, month_start)
    try:
        fs = _get_adls_client().get_file_system_client(_ADLS_CONTAINER)
        fc = fs.get_file_client(blob_path)
        raw = fc.download_file().readall()
        data = json.loads(raw.decode("utf-8"))
        logger.info("체크포인트 로드: %s (%d건)", blob_path, len(data))
        return data
    except Exception:
        return None


# ── 최종 저장 (Parquet → ADLS) ───────────────────────────────
def save_final(records: list[dict], keyword: str) -> str:
    """Parquet으로 변환 후 ADLS에 업로드하고 ADLS 경로를 반환한다."""
    safe_name = re.sub(r"[^\w가-힣]", "_", keyword)

    df = pd.DataFrame(records)
    if "newsId" in df.columns:
        df = df.drop_duplicates(subset="newsId")

    now = datetime.now()
    blob_path = (
        f"{_OUTPUT_PREFIX}/keyword={safe_name}"
        f"/year={now.year}/month={now.month:02d}/articles.parquet"
    )

    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf_bytes = buf.getvalue()

    fs = _get_adls_client().get_file_system_client(_ADLS_CONTAINER)
    fc = fs.get_file_client(blob_path)
    fc.upload_data(buf_bytes, overwrite=True, length=len(buf_bytes))
    logger.info("Parquet ADLS 저장: %s (%d건)", blob_path, len(df))
    return blob_path


# ── 진행률 ────────────────────────────────────────────────────
def log_progress(keyword: str, month: str, page: int, total_pages: int, articles: int) -> None:
    logger.info(
        "[%s] %s — 페이지 %d/%d (누적 %d건)",
        keyword,
        month,
        page,
        total_pages,
        articles,
    )


# ── 텍스트 정리 ──────────────────────────────────────────────
def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_date(date_str: str) -> str:
    """다양한 날짜 형식을 YYYY-MM-DD로 정규화한다.

    Google News의 상대 시간 표현(2 hours ago, 3 days ago 등)도 처리.
    """
    date_str = date_str.strip()

    # 상대 시간 처리 (Google News: "2 hours ago", "3 days ago" 등)
    relative = re.match(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", date_str, re.IGNORECASE)
    if relative:
        num, unit = int(relative.group(1)), relative.group(2).lower()
        delta_map = {"minute": 1, "hour": 60, "day": 1440, "week": 10080, "month": 43200}
        from datetime import timedelta

        dt = datetime.now() - timedelta(minutes=num * delta_map.get(unit, 1))
        return dt.strftime("%Y-%m-%d")

    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str
