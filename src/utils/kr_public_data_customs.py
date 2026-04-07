import os
import time
import xml.etree.ElementTree as ET
from io import BytesIO

import pandas as pd
import requests
from azure.storage.filedatalake import DataLakeServiceClient
from dotenv import load_dotenv


def fetch_customs_data(api_key: str, start_date: str, end_date: str, hs_code: str) -> pd.DataFrame:
    """
    관세청 품목별 API를 호출하여 XML 응답을 파싱하고 Pandas DataFrame으로 반환합니다.
    """
    url = (
        f"https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
        f"?serviceKey={api_key}"
        f"&strtYymm={start_date}"
        f"&endYymm={end_date}"
        f"&hsSgn={hs_code}"
        f"&pageNo=1"
        f"&numOfRows=1000"
    )

    print(f"API 호출 중... (기간: {start_date} ~ {end_date}, 품목: {hs_code})")

    response = requests.get(url)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    result_code = root.findtext(".//resultCode")
    if result_code != "00":
        result_msg = root.findtext(".//resultMsg")
        raise Exception(f"API 에러 발생: {result_msg}")

    items = root.findall(".//item")
    data_list = []

    for item in items:
        row = {child.tag: child.text for child in item}
        data_list.append(row)

    df = pd.DataFrame(data_list)

    if not df.empty:
        # '총계' 행 필터링
        if "year" in df.columns:
            df = df[df["year"] != "총계"].reset_index(drop=True)
        elif "statMm" in df.columns:
            df = df[df["statMm"] != "총계"].reset_index(drop=True)

        # ✨ FutureWarning 해결: 숫자형 변환 로직 개선
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass  # 숫자로 변환할 수 없는 컬럼(품목명 등)은 유지

    return df


def upload_to_adls_gen2(
    df: pd.DataFrame, connection_string: str, container_name: str, file_path: str
):
    """
    DataFrame을 Parquet 포맷으로 변환하여 ADLS Gen2에 업로드합니다.
    """
    if df.empty:
        print("업로드할 데이터가 없습니다.")
        return

    print(f"ADLS Gen2 업로드 시작... 대상 컨테이너: {container_name}, 경로: {file_path}")

    service_client = DataLakeServiceClient.from_connection_string(connection_string)
    file_system_client = service_client.get_file_system_client(container_name)
    file_client = file_system_client.get_file_client(file_path)

    parquet_buffer = BytesIO()
    df.to_parquet(parquet_buffer, index=False, engine="pyarrow")
    parquet_buffer.seek(0)

    file_client.upload_data(parquet_buffer.read(), overwrite=True)
    print("✅ ADLS 업로드 완료!")


if __name__ == "__main__":
    load_dotenv()

    API_KEY = os.getenv("CUSTOMS_API_KEY")
    ADLS_CONN_STR = os.getenv("ADLS_CONNECTION_STRING")

    if not API_KEY or not ADLS_CONN_STR:
        print("경고: .env 파일에서 API 키 또는 ADLS 연결 문자열을 찾을 수 없습니다.")
        exit(1)

    # ✨ 팀 컨벤션에 맞춘 설정 변경
    CONTAINER_NAME = "raw"  # 컨테이너명을 'raw'로 변경
    HS_CODE = "8542"

    periods = [("202401", "202412"), ("202501", "202512")]

    FILE_NAME = f"itemtrade_{HS_CODE}_2024_2025.parquet"

    # ✨ Hive 스타일 파티셔닝 및 공공데이터(public_data) 경로 적용
    ADLS_FILE_PATH = f"public_data/semiconductor/source=data_go_kr/{FILE_NAME}"

    all_dataframes = []

    try:
        print("\n--- [Step 1] 데이터 추출 및 병합 시작 ---")

        for start_m, end_m in periods:
            df = fetch_customs_data(API_KEY, start_m, end_m, HS_CODE)

            if not df.empty:
                all_dataframes.append(df)
                print(f"  -> {len(df)}건 수집 완료")
            else:
                print("  -> 데이터 없음")

            time.sleep(1)

        if all_dataframes:
            final_df = pd.concat(all_dataframes, ignore_index=True)
            print(f"\n✅ 전체 데이터 병합 완료! 총 {len(final_df)}건")

            # --- [Step 2] 로컬 저장 테스트 ---
            print("\n--- [Step 2] 로컬 Parquet 저장 테스트 ---")
            os.makedirs("temp_data", exist_ok=True)
            local_path = f"temp_data/{FILE_NAME}"
            final_df.to_parquet(local_path, index=False, engine="pyarrow")
            print(f"✅ 로컬 저장 완료: {local_path}")

            # --- [Step 3] ADLS Gen2 업로드 ---
            print("\n--- [Step 3] ADLS Gen2 업로드 시작 ---")
            upload_to_adls_gen2(final_df, ADLS_CONN_STR, CONTAINER_NAME, ADLS_FILE_PATH)
        else:
            print("\n❌ 수집된 데이터가 없습니다.")

    except Exception as e:
        print(f"\n❌ 작업 중 오류가 발생했습니다: {e}")
