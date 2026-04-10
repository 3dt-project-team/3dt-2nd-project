"""
function_app.py — Azure Functions v2 진입점
===========================================
반도체 종목 주가 데이터 수집 HTTP 트리거 Azure Function (증분수집)

HTTP 트리거 호출 예시:
    POST https://<function-app>.azurewebsites.net/api/yahoo_finance_crawler
    Body: 없음 (증분수집 자동 판단)

    GET  https://<function-app>.azurewebsites.net/api/yahoo_finance_crawler
"""

import json
import logging

import azure.functions as func

from yahoo_finance_crawler import run_incremental

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="yahoo_finance_crawler")
def yahoo_finance_crawler(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP 트리거 진입점.

    Watermark 기반 증분수집을 자동으로 판단하여 실행합니다.
        - 최초 실행: 1년치 전체 수집
        - 이후 실행: 마지막 수집일 다음날부터 오늘까지만 수집
        - 오늘 이미 수집한 경우: 스킵

    Returns:
        200: 수집 결과 메시지 (JSON)
        500: 오류 메시지 (JSON)
    """
    logger.info("yahoo_finance_crawler HTTP 트리거 호출됨")

    try:
        result = run_incremental()
        logger.info("실행 완료: %s", result)
        return func.HttpResponse(
            body=json.dumps(result, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logger.error("처리 중 오류 발생: %s", e)
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json",
        )