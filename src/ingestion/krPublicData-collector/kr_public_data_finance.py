import logging
import os
import time
from datetime import datetime
from io import BytesIO

import pandas as pd
import requests
from azure.storage.filedatalake import DataLakeServiceClient
from dotenv import load_dotenv


def fetch_options_data(api_key: str, begin_date: str, end_date: str) -> pd.DataFrame:
    """금융위원회 옵션시세 정보 API 호출"""
    url = (
        "http://apis.data.go.kr/1160100/service/GetDerivativeProductInfoService/getOptionsPriceInfo"
    )

    params = {
        "serviceKey": api_key,
        "numOfRows": "5000",  # 한 달 치 데이터가 많을 수 있으므로 넉넉히 설정
        "pageNo": "1",
        "resultType": "json",
        "beginBasDt": begin_date,
        "endBasDt": end_date,
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    res_data = response.json()
    items = res_data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

    return pd.DataFrame(items)


def upload_to_adls_gen2(
    df: pd.DataFrame, connection_string: str, container_name: str, file_path: str
):
    """ADLS Gen2에 Parquet 업로드"""
    service_client = DataLakeServiceClient.from_connection_string(connection_string)
    file_system_client = service_client.get_file_system_client(container_name)
    file_client = file_system_client.get_file_client(file_path)

    parquet_buffer = BytesIO()
    df.to_parquet(parquet_buffer, index=False, engine="pyarrow")
    parquet_buffer.seek(0)

    file_client.upload_data(parquet_buffer.read(), overwrite=True)


def collect_options_data():
    """2024년부터 현재까지 월 단위로 루프를 돌며 수집"""
    load_dotenv()
    API_KEY = os.getenv("PUBLIC_DATA_API_KEY")
    ADLS_CONN_STR = os.getenv("ADLS_CONNECTION_STRING")
    CONTAINER_NAME = "raw"

    # 2024년 1월부터 이번 달까지의 월 시작일 리스트 생성
    # 예: ['2024-01-01', '2024-02-01', ...]
    start_dates = pd.date_range(start="2024-01-01", end=datetime.now(), freq="MS")

    total_count = 0

    for start_date in start_dates:
        # 해당 월의 시작일과 종료일 계산 (YYYYMMDD 형식)
        begin_str = start_date.strftime("%Y%m%d")
        # 해당 월의 마지막 날 계산
        end_str = (start_date + pd.offsets.MonthEnd(0)).strftime("%Y%m%d")

        # 미래 날짜 수집 방지
        if begin_str > datetime.now().strftime("%Y%m%d"):
            break

        logging.info(f"수집 중: {begin_str} ~ {end_str}")

        try:
            df = fetch_options_data(API_KEY, begin_str, end_str)

            if not df.empty:
                file_name = f"fsc_options_{begin_str[:6]}.parquet"  # 월별 파일명 생성
                adls_path = f"public_data/finance/options/year_month={begin_str[:6]}/{file_name}"

                upload_to_adls_gen2(df, ADLS_CONN_STR, CONTAINER_NAME, adls_path)
                total_count += len(df)
                logging.info(f"성공: {begin_str[:6]} 데이터 {len(df)}건 적재")

                # API 서버 부하 방지를 위해 1초간 휴식 (매너 코딩)
                time.sleep(1)
            else:
                logging.info(f"데이터 없음: {begin_str[:6]}")

        except Exception as e:
            logging.error(f"오류 발생 ({begin_str[:6]}): {e}")
            continue  # 에러가 나도 다음 달로 넘어감

    return f"전체 수집 완료! 총 {total_count}건의 데이터가 월별로 분할 적재되었습니다."
