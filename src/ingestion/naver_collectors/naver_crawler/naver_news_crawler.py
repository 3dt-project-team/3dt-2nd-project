import asyncio
import hashlib
import json
import os
import re
import warnings
from datetime import date, datetime
from itertools import groupby

import aiohttp
import pandas as pd

# Azure
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ──────────────────────────────────────────────
# 환경변수
# ──────────────────────────────────────────────
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL", "https://kv-3dt-team1.vault.azure.net/")
KEYWORDS_ENV = os.environ.get("KEYWORDS", "삼성전자,SK하이닉스")
DATE_START = os.environ.get("DATE_START", "2025-04-01")
DATE_END = os.environ.get("DATE_END", date.today().isoformat())
ADLS_ACCOUNT = os.environ.get("ADLS_ACCOUNT", "3dtteam1adls")
ADLS_CONTAINER = os.environ.get("ADLS_CONTAINER", "raw")

KEYWORDS = [k.strip() for k in KEYWORDS_ENV.split(",")]

# 한글 키워드 → 영어 디렉토리명 매핑
KEYWORD_EN_MAP = {
    "삼성전자": "samsung",
    "SK하이닉스": "skhynix",
}


def to_en(keyword):
    """한글 키워드를 영어 디렉토리명으로 변환 (매핑 없으면 그대로 소문자)"""
    return KEYWORD_EN_MAP.get(keyword, keyword.lower().replace(" ", "_"))


# ──────────────────────────────────────────────
# ADLS 클라이언트 (Managed Identity)
# ──────────────────────────────────────────────
def get_adls_client():
    credential = DefaultAzureCredential()
    return DataLakeServiceClient(
        account_url=f"https://{ADLS_ACCOUNT}.dfs.core.windows.net", credential=credential
    )


def upload_to_adls(adls_client, records, keyword, month_str):
    """JSON 레코드를 ADLS raw/news/naver/source={keyword_en}/month={month_str}/ 에 업로드"""
    keyword_en = to_en(keyword)
    file_path = (
        f"news/naver/source={keyword_en}/month={month_str}/"
        f"news_{keyword_en}_{month_str.replace('-', '')}.json"
    )

    fs_client = adls_client.get_file_system_client(ADLS_CONTAINER)
    file_client = fs_client.get_file_client(file_path)

    # 기존 파일 있으면 merge
    existing = []
    try:
        download = file_client.download_file()
        existing = json.loads(download.readall().decode("utf-8"))
    except Exception:
        pass

    existing.extend(records)
    data = json.dumps(existing, ensure_ascii=False, indent=2).encode("utf-8")
    file_client.upload_data(data, overwrite=True)
    print(f"      ☁️  ADLS 업로드: {file_path} ({len(existing)}건 누적)")


# ──────────────────────────────────────────────
# 크롤러 로직 (test.py 그대로)
# ──────────────────────────────────────────────
GARBAGE_KEYWORDS = ["로그인", "회원가입", "기사제보", "지면보기", "구독하기", "전체기사"]
MAX_CONCURRENT = 5


def is_garbage(text):
    if not text:
        return True
    return sum(1 for kw in GARBAGE_KEYWORDS if kw in text) >= 2


def extract_news_id(url):
    try:
        if "n.news.naver.com" in url:
            match = re.search(r"/article/(\d+)/(\d+)", url)
            if match:
                return f"naver_{match.group(1)}_{match.group(2)}"
        if "yna.co.kr" in url:
            match = re.search(r"/view/(AKR\w+)", url)
            if match:
                return f"yna_{match.group(1)}"
        if "hankyung.com" in url:
            match = re.search(r"/article/(\w+)", url)
            if match:
                return f"hankyung_{match.group(1)}"
        if "mk.co.kr" in url:
            match = re.search(r"/article/(\d+)", url)
            if match:
                return f"mk_{match.group(1)}"
        if "edaily.co.kr" in url:
            match = re.search(r"/view/(\w+)", url)
            if match:
                return f"edaily_{match.group(1)}"
        if "chosun.com" in url:
            match = re.search(r"/([A-Z0-9]{20,})", url)
            if match:
                return f"chosun_{match.group(1)}"
        if "newsis.com" in url:
            match = re.search(r"/(NISX\w+)", url)
            if match:
                return f"newsis_{match.group(1)}"
        return "hash_" + hashlib.md5(url.encode()).hexdigest()[:12]
    except Exception:
        return "hash_" + hashlib.md5(url.encode()).hexdigest()[:12]


def find_best_selector(soup):
    candidates = []
    for tag in soup.find_all(["div", "article", "section"]):
        text = tag.get_text(strip=True)
        if len(text) < 200:
            continue
        tag_id = tag.get("id", "")
        tag_cls = " ".join(tag.get("class", []))
        identifier = (tag_id + tag_cls).lower()
        if any(
            kw in identifier
            for kw in [
                "article",
                "body",
                "content",
                "news",
                "text",
                "view",
                "story",
            ]
        ):
            if not is_garbage(text):
                candidates.append((len(text), text))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def parse_body(html):
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", {"property": "og:article:published_time"})
    pub_date = meta["content"] if meta else None

    selectors = [
        "#newsct_article",
        "#articleBodyContents",
        "#article-view-content-div",
        ".article_txt",
        ".art_body",
        ".news_body",
        ".article-body__content",
        ".article_body",
        "#content-body",
        ".article-body",
        ".article-body-content",
        ".view-article",
        "#articleView",
        ".story-news-article",
        "#articlebody",
        ".art_txt",
        "#newsEndContents",
        "#content",
        ".news-article-content",
        ".view_text",
        "#textBody",
        "#articleText",
        ".article_view",
        ".text_area",
        "#newsContent",
        "#fusion-app",
        ".article_txt_area",
        ".article-content",
        "#article-body",
        "#articleBody",
        "div[class*='articleBody']",
        "div[class*='article_body']",
        "div[class*='article-body']",
        "div[id*='article']",
        "article",
    ]
    body_text = None
    for sel in selectors:
        tag = soup.select_one(sel)
        if not tag:
            continue
        text = tag.get_text(separator="\n", strip=True)
        if len(text) > 100 and not is_garbage(text):
            body_text = text
            break
    if not body_text:
        body_text = find_best_selector(soup)

    return pub_date, body_text


async def fetch_with_aiohttp(session, url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://search.naver.com/",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as res:
            html = await res.text()
            return html
    except Exception:
        return None


async def get_article_detail_async(url, semaphore, context, session):
    async with semaphore:
        html = await fetch_with_aiohttp(session, url)
        if html:
            pub_date, body_text = parse_body(html)
            if body_text:
                return pub_date, body_text
        try:
            page = await context.new_page()
            await stealth_async(page)
            await page.goto(url, timeout=10000, wait_until="domcontentloaded")
            await page.wait_for_timeout(800)
            html = await page.content()
            await page.close()
            pub_date, body_text = parse_body(html)
            return pub_date, body_text
        except Exception:
            return None, None


async def fetch_hits(page, keyword, ds, ymd):
    url = (
        f"https://search.naver.com/search.naver?where=news&query={keyword}"
        f"&sort=1&pd=3&ds={ds}&de={ds}"
        f"&nso=so:dd,p:from{ymd}to{ymd},a:all"
    )
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    prev_height = 0
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(100)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == prev_height:
            break
        prev_height = new_height

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    hits = []
    for span in soup.select("span[class*='headline']"):
        title = span.get_text(strip=True)
        a_tag = span.find_parent("a", href=True)
        if not title or not a_tag:
            continue
        link = a_tag["href"]
        press = ""
        body_span = span.find_next("span", class_=lambda v: v and "body2" in v)
        if body_span:
            press = body_span.get_text(strip=True)
        hits.append((title, link, press))

    return hits


def already_collected_adls(adls_client, keyword, date_str):
    """ADLS에서 해당 날짜 데이터가 이미 수집됐는지 확인"""
    month_str = date_str[:7]
    keyword_en = to_en(keyword)
    file_path = (
        f"news/naver/source={keyword_en}/month={month_str}/"
        f"news_{keyword_en}_{month_str.replace('-', '')}.json"
    )
    try:
        fs_client = adls_client.get_file_system_client(ADLS_CONTAINER)
        file_client = fs_client.get_file_client(file_path)
        download = file_client.download_file()
        existing = json.loads(download.readall().decode("utf-8"))
        return any(r["adjustedDate"] == date_str for r in existing)
    except Exception:
        return False


async def crawl_all(start, end):
    adls_client = get_adls_client()
    dates = list(pd.date_range(start, end))
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        search_page = await context.new_page()
        await stealth_async(search_page)

        async with aiohttp.ClientSession() as session:
            all_records = []

            for keyword in KEYWORDS:
                print(f"\n{'=' * 50}")
                print(f"🔍 키워드: {keyword}")
                print(f"{'=' * 50}")

                month_grouped = groupby(dates, key=lambda d: d.strftime("%Y-%m"))

                for month_str, month_dates in month_grouped:
                    print(f"\n  📅 [{keyword}] {month_str} 수집 시작")
                    month_records = []

                    for date_val in month_dates:
                        ds = date_val.strftime("%Y.%m.%d")
                        ymd = date_val.strftime("%Y%m%d")
                        date_str = date_val.strftime("%Y-%m-%d")

                        if already_collected_adls(adls_client, keyword, date_str):
                            print(f"    ⏭️  {ds} 이미 수집됨 — 건너뜀")
                            continue

                        print(f"\n    [{keyword}] {ds} 수집 중…")
                        hits = await fetch_hits(search_page, keyword, ds, ymd)
                        print(f"      → {len(hits)}건 수집")

                        tasks = [
                            get_article_detail_async(link, semaphore, context, session)
                            for _, link, _ in hits
                        ]
                        results = await asyncio.gather(*tasks)

                        daily_records = []
                        for (title, link, press), (pub, body_text) in zip(hits, results):
                            news_id = extract_news_id(link)
                            has_body = "✅" if body_text else "❌"
                            print(f"      • {has_body} {press or '언론사없음'} | {title[:45]}...")
                            daily_records.append(
                                {
                                    "source": keyword,
                                    "newsId": news_id,
                                    "url": link,
                                    "pubDate": pub,
                                    "adjustedDate": date_str,
                                    "headline": title,
                                    "press": press,
                                    "body": body_text if body_text else "",
                                    "fetchedAt": datetime.utcnow().isoformat() + "+00:00",
                                }
                            )

                        if daily_records:
                            day_body = sum(1 for r in daily_records if r["body"])
                            message = (
                                f"      💾 {date_str}: {len(daily_records)}건 (본문 {day_body}건)"
                            )
                            print(message)
                            month_records.extend(daily_records)

                        all_records.extend(daily_records)
                        await asyncio.sleep(0.5)

                    # 월 단위로 ADLS 업로드
                    if month_records:
                        upload_to_adls(adls_client, month_records, keyword, month_str)

        await browser.close()

    df = pd.DataFrame(all_records)
    if df.empty:
        print("\n✅ 수집 완료 — 새로운 데이터 없음")
        return df

    total = len(df)
    has_body = df["body"].apply(lambda x: bool(x)).sum()

    print(f"\n{'=' * 50}")
    print(f"✅ 수집 완료 — 총 {total}건")
    print(f"   본문 성공: {has_body}건 ({has_body / total * 100:.1f}%)")
    print(f"   본문 실패: {total - has_body}건 ({(total - has_body) / total * 100:.1f}%)")

    for kw in KEYWORDS:
        kw_df = df[df["source"] == kw]
        kw_body = kw_df["body"].apply(lambda x: bool(x)).sum()
        print(f"      {kw}: {len(kw_df)}건 (본문 {kw_body}건)")

    dedup_count = len(df.drop_duplicates("newsId"))
    print(f"\n   ℹ️  newsId 중복 제거 시: {total} → {dedup_count}건")
    return df


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    print("🚀 네이버 뉴스 크롤러 시작")
    print(f"   키워드: {KEYWORDS}")
    print(f"   기간: {DATE_START} ~ {DATE_END}")
    asyncio.run(crawl_all(DATE_START, DATE_END))
