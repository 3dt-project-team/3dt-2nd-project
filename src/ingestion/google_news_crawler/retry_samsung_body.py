"""
Samsung Electronics 본문 재수집 스크립트
- 빈 본문 또는 Google News 보일러플레이트가 들어간 기사만 재시도
- wait_for_url 타임아웃을 15000ms로 늘려서 JS 리다이렉트 실패 최소화
"""

import asyncio
import json
import logging
import random
from pathlib import Path

from config import (
    MAX_RETRIES,
    PAGE_LOAD_TIMEOUT,
    RETRY_BACKOFF,
)
from crawling_google_news import _extract_body_from_html, create_stealth_page
from playwright.async_api import TimeoutError as PwTimeout
from playwright.async_api import async_playwright

from utils import save_final, setup_logging

logger = logging.getLogger("retry_samsung")

# Google News가 meta description으로 삽입하는 보일러플레이트 텍스트
BOILERPLATE = (
    "Comprehensive up-to-date news coverage, aggregated from sources all over the world"
    " by Google News."
)

REDIRECT_TIMEOUT = 15_000  # ms — SK하이닉스 대비 2배 여유
PAGE_SETTLE_DELAY = (0.5, 1.5)  # 리다이렉트 후 페이지 안정화 대기


def is_boilerplate(body: str) -> bool:
    return BOILERPLATE.lower() in body.lower()


async def retry_bodies(page, records: list[dict], label: str) -> int:
    """본문이 없거나 보일러플레이트인 기사만 재시도. 성공 건수 반환."""
    to_retry = [
        (i, r)
        for i, r in enumerate(records)
        if not r.get("body") or is_boilerplate(r.get("body", ""))
    ]
    total = len(to_retry)
    logger.info("[%s] 재수집 대상: %d건 (전체 %d건)", label, total, len(records))

    success = 0
    for seq, (idx, rec) in enumerate(to_retry):
        url = rec.get("url", "")
        if not url:
            continue

        for attempt in range(MAX_RETRIES):
            try:
                is_google_url = "news.google.com" in url

                await page.goto(url, wait_until="commit", timeout=PAGE_LOAD_TIMEOUT)

                if is_google_url:
                    try:
                        await page.wait_for_url(
                            lambda u: "news.google.com" not in u,
                            timeout=REDIRECT_TIMEOUT,
                        )
                    except PwTimeout:
                        logger.debug("리다이렉트 타임아웃: %s", url[:80])
                        break

                await page.wait_for_load_state("domcontentloaded")

                # 페이지 안정화 대기 (JS 렌더링 여유)
                await asyncio.sleep(random.uniform(*PAGE_SETTLE_DELAY))

                final_url = page.url
                if final_url and final_url != url and "news.google.com" not in final_url:
                    records[idx]["url"] = final_url

                html = await page.content()
                body = _extract_body_from_html(html)

                if body and not is_boilerplate(body):
                    records[idx]["body"] = body
                    success += 1
                    break
                else:
                    logger.debug("본문 미흡 (attempt %d): %s", attempt + 1, url[:60])

            except PwTimeout:
                logger.debug("페이지 타임아웃: %s", url[:80])
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF**attempt)
                else:
                    logger.debug("수집 실패: %s — %s", url[:60], e)

        # 딜레이 (일반 수집보다 조금 더 여유있게)
        await asyncio.sleep(random.uniform(0.5, 1.2))

        if (seq + 1) % 20 == 0:
            logger.info("[%s] 진행: %d/%d건 완료 (성공 %d건)", label, seq + 1, total, success)

    logger.info("[%s] 재수집 완료: %d/%d건 성공", label, success, total)
    return success


async def main():
    setup_logging()
    logger.info("=" * 60)
    logger.info("Samsung Electronics 본문 재수집 시작")
    logger.info("=" * 60)

    output_path = Path("data/output/Samsung_Electronics_news.json")
    if not output_path.exists():
        logger.error("파일 없음: %s", output_path)
        return

    # JSON 로드
    records = []
    with open(output_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    logger.info("로드 완료: %d건", len(records))

    before_empty = sum(1 for r in records if not r.get("body"))
    before_boiler = sum(1 for r in records if r.get("body") and is_boilerplate(r["body"]))
    logger.info("재수집 대상 — 빈 본문: %d건, 보일러플레이트: %d건", before_empty, before_boiler)

    async with async_playwright() as pw:
        context, page = await create_stealth_page(pw)
        try:
            await retry_bodies(page, records, "Samsung_Electronics")
        finally:
            await context.close()

    # 결과 저장
    save_final(records, "Samsung_Electronics")

    after_no_body = sum(
        1 for r in records if not r.get("body") or is_boilerplate(r.get("body", ""))
    )
    after_ok = len(records) - after_no_body
    logger.info(
        "최종 본문 보유: %d/%d건 (%.0f%%)", after_ok, len(records), after_ok / len(records) * 100
    )
    logger.info("저장 완료: data/output/Samsung_Electronics_news.json")


if __name__ == "__main__":
    asyncio.run(main())
