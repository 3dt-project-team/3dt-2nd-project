import json
import logging

import azure.functions as func

# 1. 내가 만든 파일(kr_public_data_customs.py)에서 실행 함수를 가져옵니다.
# 주의: 파일명에서 .py는 떼고 적으세요!
from kr_public_data_customs import collect_customs_data

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# 2. HTTP 트리거 설정
@app.route(route="collect")  # 주소 뒤에 /api/collect 가 붙습니다.
def http_trigger_customs(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("관세청 데이터 수집 요청을 확인했습니다.")

    try:
        # 3. 질문자님이 만든 로직 실행!
        collect_customs_data()

        return func.HttpResponse(
            body=json.dumps({"message": "수집 완료!", "status": "success"}),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"에러 발생: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"message": "실패", "error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )
