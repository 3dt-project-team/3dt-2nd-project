# crawler_core.py — 공통 크롤링 로직
import asyncio
import hashlib
import html
import json
import logging
import os
import re
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── 설정 ──
KEYWORD_MAP = {"삼성전자": "samsung", "SK하이닉스": "skhynix"}
ADLS_CONTAINER = "raw"
MAX_DISPLAY = 100
MAX_START = 1000
MAX_CONCURRENT = 5
GARBAGE_KEYWORDS = ["로그인", "회원가입", "기사제보", "지면보기", "구독하기", "전체기사"]


# ────────────────────────────────────────
# 유틸 함수
# ────────────────────────────────────────
def clean_text(text):
    """HTML 태그 및 엔티티 제거"""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


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
            for kw in ["article", "body", "content", "news", "text", "view", "story"]
        ):
            if not is_garbage(text):
                candidates.append((len(text), text))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def parse_body(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
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
    return body_text


# ────────────────────────────────────────
# Key Vault 시크릿 로드
# ────────────────────────────────────────
def load_secrets():
    """환경변수에서 시크릿 로드"""
    secrets = {
        "NAVER_CLIENT_ID": os.environ["NAVER_CLIENT_ID"],
        "NAVER_CLIENT_SECRET": os.environ["NAVER_CLIENT_SECRET"],
        "ADLS_CONNECTION_STRING": os.environ["ADLS_CONNECTION_STRING"],
    }
    logger.info("✅ 환경변수 로드 완료")
    return secrets


# ────────────────────────────────────────
# ADLS 기존 newsId 로드
# ────────────────────────────────────────
def get_existing_ids(keyword_en, date_str, secrets):
    """ADLS에서 오늘 저장된 newsId 목록 로드"""
    month_str = date_str[:7]
    try:
        from azure.storage.filedatalake import DataLakeServiceClient

        service_client = DataLakeServiceClient.from_connection_string(
            secrets["ADLS_CONNECTION_STRING"]
        )
        fs_client = service_client.get_file_system_client(ADLS_CONTAINER)
        file_path = (
            f"news/naver/source={keyword_en}/month={month_str}/"
            f"news_{keyword_en}_{date_str.replace('-', '')}.json"
        )
        file_client = fs_client.get_file_client(file_path)
        data = file_client.download_file().readall()
        records = json.loads(data.decode("utf-8"))
        existing = set(r["newsId"] for r in records)
        logger.info(f"[{keyword_en}] 기존 저장 건수: {len(existing)}건")
        return existing
    except Exception:
        logger.info(f"[{keyword_en}] 기존 파일 없음 — 새로 수집 시작")
        return set()


# ────────────────────────────────────────
# 네이버 뉴스 API
# ────────────────────────────────────────
async def fetch_naver_news(session, keyword, date_str, secrets, existing_ids=None):
    if existing_ids is None:
        existing_ids = set()

    headers = {
        "X-Naver-Client-Id": secrets["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": secrets["NAVER_CLIENT_SECRET"],
    }
    items_all = []
    start = 1

    while True:
        params = {"query": keyword, "display": MAX_DISPLAY, "start": start, "sort": "date"}
        try:
            async with session.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as res:
                data = await res.json()

            items = data.get("items", [])
            if not items:
                break

            stop = False
            for item in items:
                pub_raw = item.get("pubDate", "")
                try:
                    pub_dt = datetime.strptime(pub_raw, "%a, %d %b %Y %H:%M:%S %z")
                    pub_date_only = pub_dt.strftime("%Y-%m-%d")
                except Exception:
                    pub_date_only = ""

                # 오늘 날짜 아니면 건너뜀
                if pub_date_only != date_str:
                    if pub_date_only < date_str:
                        stop = True
                        break
                    continue

                link = item.get("originallink") or item.get("link", "")
                news_id = extract_news_id(link)

                # 이미 저장된 newsId면 수집 종료
                if news_id in existing_ids:
                    logger.info(f"[{keyword}] 중복 newsId 감지 — 수집 종료")
                    stop = True
                    break

                items_all.append(
                    {
                        "title": clean_text(item.get("title", "")),
                        "link": link,
                        "naverLink": item.get("link", ""),
                        "description": clean_text(item.get("description", "")),
                        "pubDate": pub_raw,
                        "pubDateKST": pub_date_only,
                    }
                )

            if stop or len(items) < MAX_DISPLAY or start + MAX_DISPLAY > MAX_START:
                break

            start += MAX_DISPLAY
            await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"[{keyword}] Naver API 오류 (start={start}): {e}")
            break

    return items_all


# ────────────────────────────────────────
# 본문 수집
# ────────────────────────────────────────
async def fetch_body(session, url, semaphore):
    async with semaphore:
        try:
            async with session.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/146.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "ko-KR,ko;q=0.9",
                    "Referer": "https://search.naver.com/",
                },
                timeout=aiohttp.ClientTimeout(total=5),
                ssl=False,  # SSL 인증서 오류 해결
            ) as res:
                raw = await res.read()  # text() → read() 로 변경
                try:
                    html_content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        html_content = raw.decode("euc-kr")  # EUC-KR 폴백
                    except UnicodeDecodeError:
                        html_content = raw.decode("utf-8", errors="ignore")

                body_text = parse_body(html_content)
                return body_text or ""

        except asyncio.TimeoutError:
            logger.warning(f"본문 수집 타임아웃 ({url})")
            return ""
        except aiohttp.ClientConnectorError:
            logger.warning(f"본문 수집 연결 실패 ({url})")
            return ""
        except aiohttp.ServerDisconnectedError:
            logger.warning(f"본문 수집 서버 연결 끊김 ({url})")
            return ""
        except Exception as e:
            logger.warning(f"본문 수집 실패 ({url}): {e}")
            return ""


# ────────────────────────────────────────
# ADLS 저장 (append)
# ────────────────────────────────────────
def save_to_adls(records, keyword_en, date_str, secrets):
    """기존 파일에 새 기사 append 저장"""
    month_str = date_str[:7]

    try:
        from azure.storage.filedatalake import DataLakeServiceClient

        service_client = DataLakeServiceClient.from_connection_string(
            secrets["ADLS_CONNECTION_STRING"]
        )
        fs_client = service_client.get_file_system_client(ADLS_CONTAINER)
        file_path = (
            f"news/naver/source={keyword_en}/month={month_str}/"
            f"news_{keyword_en}_{date_str.replace('-', '')}.json"
        )
        file_client = fs_client.get_file_client(file_path)

        # 기존 데이터 로드
        existing = []
        try:
            data = file_client.download_file().readall()
            existing = json.loads(data.decode("utf-8"))
        except Exception:
            pass

        existing.extend(records)
        content = json.dumps(existing, ensure_ascii=False, indent=2).encode("utf-8")
        file_client.upload_data(content, overwrite=True)

        logger.info(
            f"✅ ADLS 저장 완료: {ADLS_CONTAINER}/{file_path} "
            f"({len(records)}건 추가 / 총 {len(existing)}건)"
        )
        return True

    except Exception as e:
        logger.error(f"❌ ADLS 저장 실패 ({keyword_en}): {e}")
        return False


# ────────────────────────────────────────
# 메인 크롤링
# ────────────────────────────────────────
async def crawl_today(date_str):
    """당일 뉴스 수집 메인 로직"""
    secrets = load_secrets()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    summary = []

    async with aiohttp.ClientSession() as session:
        for keyword in KEYWORD_MAP:
            keyword_en = KEYWORD_MAP[keyword]
            logger.info(f"[{keyword_en}] {date_str} 수집 시작")

            # 기존 저장된 newsId 로드
            existing_ids = get_existing_ids(keyword_en, date_str, secrets)

            # 신규 기사만 수집 (중복 체크 포함)
            items = await fetch_naver_news(session, keyword, date_str, secrets, existing_ids)
            logger.info(f"[{keyword_en}] 신규 수집: {len(items)}건")

            if not items:
                logger.info(f"[{keyword_en}] 신규 기사 없음 — 건너뜀")
                continue

            # 본문 병렬 수집
            tasks = [fetch_body(session, item["link"], semaphore) for item in items]
            bodies = await asyncio.gather(*tasks)

            # 레코드 조합
            records = []
            for item, body in zip(items, bodies):
                records.append(
                    {
                        "source": keyword_en,
                        "newsId": extract_news_id(item["link"]),
                        "url": item["link"],
                        "naverUrl": item["naverLink"],
                        "pubDate": item["pubDateKST"],
                        "adjustedDate": date_str,
                        "headline": item["title"],
                        "description": item["description"],
                        "body": body,
                        "fetchedAt": datetime.utcnow().isoformat() + "+00:00",
                    }
                )

            # append 저장
            save_to_adls(records, keyword_en, date_str, secrets)

            has_body = sum(1 for r in records if r["body"])
            summary.append(
                f"{keyword_en}: 신규 {len(records)}건 "
                f"(본문 {has_body}건 / 누적 {len(existing_ids) + len(records)}건)"
            )
            logger.info(f"[{keyword_en}] 완료")
            await asyncio.sleep(1)

    return summary
