import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO

import pandas as pd
import requests
from azure.storage.filedatalake import DataLakeServiceClient
from dotenv import load_dotenv


def fetch_customs_data(api_key: str, start_date: str, end_date: str, hs_code: str) -> pd.DataFrame:
    """관세청 API 호출 및 데이터프레임 변환"""
    url = (
        f"https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
        f"?serviceKey={api_key}"
        f"&strtYymm={start_date}"
        f"&endYymm={end_date}"
        f"&hsSgn={hs_code}"
        f"&pageNo=1"
        f"&numOfRows=1000"
    )

    print(f"📡 API 호출: {start_date} ~ {end_date}")
    response = requests.get(url)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    if root.findtext(".//resultCode") != "00":
        raise Exception(f"API 에러: {root.findtext('.//resultMsg')}")

    items = root.findall(".//item")
    data_list = [{child.tag: child.text for child in item} for item in items]
    df = pd.DataFrame(data_list)

    if not df.empty:
        # '총계' 행 제외 및 숫자 변환
        for col in ["year", "statMm"]:
            if col in df.columns:
                df = df[df[col] != "총계"].reset_index(drop=True)

        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
    return df


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
    print(f"✅ ADLS 적재 완료: {file_path}")


if __name__ == "__main__":
    load_dotenv()
    API_KEY = os.getenv("CUSTOMS_API_KEY")
    ADLS_CONN_STR = os.getenv("ADLS_CONNECTION_STRING")

    # 1. 날짜 설정 (자동화)
    now = datetime.now()
    current_year = now.year
    current_month = now.strftime("%m")

    # 2024년부터 현재 연도까지의 루프 생성
    periods = []
    for year in range(2024, current_year + 1):
        start_m = f"{year}01"
        # 현재 연도라면 전달(last month)까지만, 과거 연도라면 12월까지
        if year == current_year:
            # 1월인 경우 작년 12월까지로 처리되는 로직 등이 필요할 수 있으나
            # 단순화를 위해 현재 달까지 시도 (데이터가 없으면 빈 DF 반환됨)
            end_m = f"{year}{current_month}"
        else:
            end_m = f"{year}12"
        periods.append((start_m, end_m))

    # 2. 설정값
    CONTAINER_NAME = "raw"
    HS_CODE = "8542"  # 반도체
    FILE_NAME = f"semiconductor_trade_2024_to_{current_year}.parquet"
    ADLS_FILE_PATH = f"public_data/semiconductor/source=data_go_kr/{FILE_NAME}"

    all_dfs = []
    print(f"🚀 {current_year}년 {current_month}월 기준 최신화 작업 시작...")

    try:
        for start, end in periods:
            df = fetch_customs_data(API_KEY, start, end, HS_CODE)
            if not df.empty:
                all_dfs.append(df)
            time.sleep(1)

        if all_dfs:
            final_df = pd.concat(all_dfs, ignore_index=True)
            print(f"\n📊 총 {len(final_df)}건의 데이터 병합 완료")

            # ADLS 업로드
            upload_to_adls_gen2(final_df, ADLS_CONN_STR, CONTAINER_NAME, ADLS_FILE_PATH)
        else:
            print("데이터를 찾을 수 없습니다.")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
