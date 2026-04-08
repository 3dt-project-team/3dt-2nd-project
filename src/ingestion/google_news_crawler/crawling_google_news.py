"""
Google News 해외 뉴스 크롤러
1차 메타데이터: Google News RSS 피드 (aiohttp — CAPTCHA 없음)
2차 본문 수집: Playwright + tf-playwright-stealth (원문 링크 방문)

수집 대상: Google News 영문판 — SK Hynix, Samsung Electronics
영문 기사만 수집 (비영문 기사 자동 필터링)
"""

import asyncio
import hashlib
import logging
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import aiohttp
from config import (
    BODY_MAX_DELAY,
    BODY_MIN_DELAY,
    DATE_END,
    DATE_START,
    GOOGLE_NEWS_RSS_BASE,
    HEADLESS,
    KEYWORDS,
    LOCALE,
    MAX_RETRIES,
    PAGE_LOAD_TIMEOUT,
    RETRY_BACKOFF,
    RSS_CEID,
    RSS_COUNTRY,
    RSS_DELAY_MAX,
    RSS_DELAY_MIN,
    RSS_LANG,
    TIMEZONE,
    USER_AGENT,
    VIEWPORT,
)
from playwright.async_api import (
    BrowserContext,
    Page,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PwTimeout,
)
from playwright_stealth import StealthConfig, stealth_async
from scrapling import Selector

from utils import (
    clean_text,
    generate_monthly_ranges,
    load_checkpoint,
    save_checkpoint,
    save_final,
    setup_logging,
)

logger = logging.getLogger("google_news")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  영문 판별
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ASCII + 기본 라틴 확장 비율로 판별 (숫자/공백/구두점 포함)
_LATIN_RE = re.compile(r"[A-Za-z0-9\s\.,;:!?\-'\"()\[\]{}/@#$%^&*+=<>~`]")


def is_english(text: str, threshold: float = 0.70) -> bool:
    """텍스트의 70% 이상이 ASCII 문자이면 영문으로 판별한다."""
    if not text:
        return False
    latin_count = sum(1 for ch in text if _LATIN_RE.match(ch))
    return (latin_count / len(text)) >= threshold


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  유틸
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def make_news_id(url: str) -> str:
    """URL에서 고유 ID를 생성한다."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def build_rss_url(keyword: str, start_date: str, end_date: str) -> str:
    """Google News RSS 검색 URL을 생성한다.

    날짜 필터: after:YYYY-MM-DD before:YYYY-MM-DD
    """
    query = f"{keyword} after:{start_date} before:{end_date}"
    return (
        f"{GOOGLE_NEWS_RSS_BASE}"
        f"?q={quote_plus(query)}"
        f"&hl={RSS_LANG}&gl={RSS_COUNTRY}&ceid={RSS_CEID}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  1차: RSS 피드에서 메타데이터 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def fetch_rss(
    session: aiohttp.ClientSession,
    keyword: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """한 달치 Google News RSS 피드를 가져와 파싱한다."""
    month_label = start_date[:7]
    url = build_rss_url(keyword, start_date, end_date)
    now = datetime.now(timezone.utc).isoformat()

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "RSS HTTP %d (시도 %d/%d): %s %s",
                        resp.status,
                        attempt + 1,
                        MAX_RETRIES,
                        keyword,
                        month_label,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BACKOFF**attempt)
                    continue
                text = await resp.text()
        except Exception as e:
            logger.warning(
                "RSS 요청 실패 (시도 %d/%d): %s — %s", attempt + 1, MAX_RETRIES, keyword, e
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF**attempt)
            continue

        # XML 파싱
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            logger.error("RSS XML 파싱 오류: %s — %s", keyword, e)
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        items = channel.findall("item")
        records: list[dict] = []
        skipped_lang = 0

        for item in items:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date_raw = item.findtext("pubDate", "").strip()
            description_raw = item.findtext("description", "").strip()

            # <source> 태그에서 언론사명
            source_el = item.find("source")
            press = source_el.text.strip() if source_el is not None and source_el.text else ""

            # 영문 기사만 수집
            if not is_english(title):
                skipped_lang += 1
                continue

            # 날짜 파싱 (RFC 2822 → YYYY-MM-DD)
            pub_date = ""
            if pub_date_raw:
                try:
                    dt = parsedate_to_datetime(pub_date_raw)
                    pub_date = dt.strftime("%Y-%m-%d")
                except Exception:
                    pub_date = pub_date_raw[:10]

            # description에서 HTML 태그 제거
            description = clean_text(re.sub(r"<[^>]+>", "", description_raw))

            news_id = make_news_id(link)

            records.append(
                {
                    "source": keyword,
                    "newsId": news_id,
                    "url": link,
                    "pubDate": pub_date,
                    "adjustedDate": month_label,
                    "headline": clean_text(title),
                    "press": press,
                    "description": description,
                    "body": "",
                    "fetchedAt": now,
                }
            )

        if skipped_lang:
            logger.info("[%s] %s — 비영문 기사 %d건 제외", keyword, month_label, skipped_lang)
        logger.info("[%s] %s — RSS에서 %d건 수집", keyword, month_label, len(records))
        return records

    return []


async def collect_month_rss(
    session: aiohttp.ClientSession,
    keyword: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """한 달치 메타데이터를 RSS로 수집한다."""
    records = await fetch_rss(session, keyword, start_date, end_date)
    # RSS 내 URL 중복 제거
    seen: set[str] = set()
    unique: list[dict] = []
    for r in records:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2차: 본문 수집 (Playwright + stealth)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def create_stealth_page(playwright) -> tuple[BrowserContext, Page]:
    browser = await playwright.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    context = await browser.new_context(
        viewport=VIEWPORT,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        user_agent=USER_AGENT,
    )
    page = await context.new_page()

    stealth_cfg = StealthConfig(
        webdriver=True,
        chrome_app=True,
        chrome_csi=True,
        chrome_load_times=True,
        chrome_runtime=True,
        navigator_languages=True,
        navigator_permissions=True,
        navigator_plugins=True,
        navigator_user_agent=True,
        navigator_vendor=True,
        webgl_vendor=True,
        navigator_hardware_concurrency=True,
        media_codecs=True,
    )
    await stealth_async(page, config=stealth_cfg)

    return context, page


def _extract_body_from_html(html: str) -> str:
    """원문 페이지 HTML에서 본문을 추출한다."""
    doc = Selector(content=html)

    # 전략 1: <article> 태그 내 텍스트
    article = doc.css("article")
    if article:
        paragraphs = article[0].css("p")
        if paragraphs:
            texts = [clean_text(p.get_all_text(strip=True)) for p in paragraphs]
            body = " ".join(t for t in texts if len(t) > 20)
            if len(body) > 100:
                return body

    # 전략 2: 모든 <p> 중 긴 것들
    all_p = doc.css("p")
    if all_p:
        texts = [clean_text(p.get_all_text(strip=True)) for p in all_p]
        long_texts = [t for t in texts if len(t) > 40]
        if long_texts:
            return " ".join(long_texts)

    # 전략 3: meta description 폴백
    meta_desc = doc.css('meta[property="og:description"]')
    if meta_desc:
        content = meta_desc[0].attrib.get("content", "")
        if content:
            return clean_text(content)
    meta_desc2 = doc.css('meta[name="description"]')
    if meta_desc2:
        content = meta_desc2[0].attrib.get("content", "")
        if content:
            return clean_text(content)

    return ""


async def collect_bodies(page: Page, records: list[dict]) -> list[dict]:
    """각 기사의 원문 링크를 방문하여 본문을 수집한다."""
    total = len(records)
    logger.info("본문 수집 시작: %d건", total)
    success = 0

    for i, rec in enumerate(records):
        url = rec.get("url", "")
        if not url or rec.get("body"):
            continue

        for attempt in range(MAX_RETRIES):
            try:
                # Google News 프록시 URL → 실제 기사로 JS 리디렉트 대기
                is_google_url = "news.google.com" in url
                resp = await page.goto(url, wait_until="commit", timeout=PAGE_LOAD_TIMEOUT)

                if is_google_url:
                    try:
                        await page.wait_for_url(
                            lambda u: "news.google.com" not in u,
                            timeout=8000,
                        )
                    except PwTimeout:
                        logger.debug("Google 리디렉트 타임아웃: %s", url[:80])
                        break

                await page.wait_for_load_state("domcontentloaded")

                # 리디렉트된 실제 URL로 업데이트
                final_url = page.url
                if final_url and final_url != url and "news.google.com" not in final_url:
                    rec["url"] = final_url

                if resp and resp.status >= 400:
                    logger.debug("HTTP %d — %s", resp.status, url[:80])
                    break

                await asyncio.sleep(random.uniform(0.2, 0.5))

                html = await page.content()
                body = _extract_body_from_html(html)
                if body:
                    rec["body"] = body
                    success += 1
                break

            except PwTimeout:
                logger.debug("본문 타임아웃: %s", url[:80])
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF**attempt)
                else:
                    logger.debug("본문 수집 실패 (%s): %s", url[:60], e)

        if (i + 1) % 20 == 0:
            logger.info("본문 수집 진행: %d/%d건 (성공 %d건)", i + 1, total, success)

        await asyncio.sleep(random.uniform(BODY_MIN_DELAY, BODY_MAX_DELAY))

    logger.info("본문 수집 완료: %d/%d건 성공", success, total)
    return records


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  메인 오케스트레이션
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def crawl_keyword(keyword: str, date_start: str, date_end: str) -> list[dict]:
    """특정 키워드의 뉴스를 한 달씩 끊어서 전체 수집한다.

    Phase 1: RSS로 메타데이터 수집 (전체 월)
    Phase 2: Playwright로 본문 수집
    """
    monthly_ranges = generate_monthly_ranges(date_start, date_end)
    all_records: list[dict] = []

    # ── Phase 1: RSS 메타데이터 ──
    logger.info("[%s] Phase 1 — RSS 메타데이터 수집 시작 (%d개월)", keyword, len(monthly_ranges))

    async with aiohttp.ClientSession() as session:
        for start_date, end_date in monthly_ranges:
            month_label = start_date[:7]

            # 체크포인트 확인
            cached = load_checkpoint(keyword, start_date)
            if cached:
                all_records.extend(cached)
                logger.info(
                    "[%s] %s — 체크포인트에서 로드 (%d건)", keyword, month_label, len(cached)
                )
                continue

            records = await collect_month_rss(session, keyword, start_date, end_date)
            save_checkpoint(records, keyword, start_date)
            all_records.extend(records)

            await asyncio.sleep(random.uniform(RSS_DELAY_MIN, RSS_DELAY_MAX))

    logger.info("[%s] Phase 1 완료 — 총 %d건 메타데이터 수집", keyword, len(all_records))

    if not all_records:
        return []

    # ── Phase 2: Playwright 본문 수집 ──
    logger.info("[%s] Phase 2 — 본문 수집 시작 (%d건)", keyword, len(all_records))

    async with async_playwright() as pw:
        context, page = await create_stealth_page(pw)
        try:
            all_records = await collect_bodies(page, all_records)
        finally:
            await context.close()

    logger.info("[%s] Phase 2 완료", keyword)
    return all_records


async def main() -> None:
    setup_logging()
    logger.info("=" * 60)
    logger.info("Google News 해외 뉴스 크롤러 시작")
    logger.info("키워드: %s", KEYWORDS)
    logger.info("기간: %s ~ %s", DATE_START, DATE_END)
    logger.info("모드: RSS 메타데이터 + Playwright 본문")
    logger.info("필터: 영문 기사만 수집")
    logger.info("=" * 60)

    for keyword in KEYWORDS:
        logger.info("━" * 40)
        logger.info("키워드 수집 시작: %s", keyword)
        logger.info("━" * 40)

        records = await crawl_keyword(keyword, DATE_START, DATE_END)

        if records:
            adls_path = save_final(records, keyword)
            logger.info("최종 저장 완료: %s", adls_path)
        else:
            logger.warning("수집된 데이터 없음: %s", keyword)

    logger.info("=" * 60)
    logger.info("전체 크롤링 완료")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
