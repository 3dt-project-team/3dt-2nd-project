import logging

import azure.functions as func

# 파일에서 함수 가져오기
from kr_public_data_customs import collect_customs_data
from kr_public_data_finance import collect_options_data

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# 관세청 수집 트리거
@app.route(route="collect")
def http_trigger_customs(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("관세청 데이터 수집 요청")
    try:
        collect_customs_data()
        return func.HttpResponse("관세청 데이터 수집 완료!", status_code=200)
    except Exception as e:
        return func.HttpResponse(f"실패: {str(e)}", status_code=500)


# 금융위 옵션 수집 트리거
@app.route(route="collect-options")
def http_trigger_options(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("금융위 옵션 데이터 수집 요청")
    try:
        # 월별 루프 로직 실행
        result_message = collect_options_data()
        return func.HttpResponse(result_message, status_code=200)
    except Exception as e:
        logging.error(f"에러: {str(e)}")
        return func.HttpResponse(f"실패: {str(e)}", status_code=500)
