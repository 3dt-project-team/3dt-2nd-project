# function_app.py — Azure Functions v2
import asyncio
import json
import logging
from datetime import datetime, timedelta

import azure.functions as func
from crawler_core import crawl_today

logger = logging.getLogger(__name__)
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ── 타이머 트리거 1 — 매시간 정각 (KST 01:00 ~ 23:00) ──
@app.timer_trigger(arg_name="mytimer_hourly", schedule="0 0 16-13 * * *", run_on_startup=False)
def daily_crawl_hourly(mytimer_hourly: func.TimerRequest) -> None:  # ← async 제거
    today_kst = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d")
    logger.info(f"[시간별] 수집 시작: {today_kst}")

    if mytimer_hourly.past_due:
        logger.warning("⚠️ 타이머 지연 실행됨")

    asyncio.run(crawl_today(today_kst))  # ← asyncio.run으로 호출
    logger.info(f"[시간별] 수집 완료: {today_kst}")


# ── 타이머 트리거 2 — 매일 KST 23:55 마지막 수집 ──
@app.timer_trigger(arg_name="mytimer_last", schedule="0 55 14 * * *", run_on_startup=False)
def daily_crawl_last(mytimer_last: func.TimerRequest) -> None:  # ← async 제거
    today_kst = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d")
    logger.info(f"[마지막] 수집 시작: {today_kst} (KST 23:55)")

    if mytimer_last.past_due:
        logger.warning("⚠️ 타이머 지연 실행됨")

    asyncio.run(crawl_today(today_kst))  # ← asyncio.run으로 호출
    logger.info(f"[마지막] 수집 완료: {today_kst}")


# ── HTTP 트리거 — ADF Function Activity 또는 수동 실행 ──
@app.route(route="crawl")
def crawl(req: func.HttpRequest) -> func.HttpResponse:  # ← async 제거
    date_str = None
    try:
        body = req.get_json()
        date_str = body.get("date")
    except Exception:
        pass

    if not date_str:
        date_str = req.params.get("date")

    if not date_str:
        date_str = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d")

    logger.info(f"[HTTP] 수집 시작: {date_str}")

    try:
        summary = asyncio.run(crawl_today(date_str))  # ← asyncio.run으로 호출
        result = {"status": "success", "date": date_str, "summary": summary}
        logger.info(f"[HTTP] 수집 완료: {date_str}")
        return func.HttpResponse(
            body=json.dumps(result, ensure_ascii=False),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        logger.error(f"[HTTP] 수집 실패: {e}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)}),
            mimetype="application/json",
            status_code=500,
        )
