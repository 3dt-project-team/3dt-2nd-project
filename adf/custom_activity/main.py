"""ADF Custom Activity 진입점 예시.

ADF가 이 컨테이너를 실행할 때:
  1. Key Vault에서 자격 증명을 자동 획득 (Managed Identity)
  2. ADLS Gen2 또는 Azure SQL 작업 수행
  3. 처리 결과를 저장소에 기록

로컬 테스트: KEY_VAULT_URL 환경 변수 설정 후 python main.py
"""

import os
import sys

# 컨테이너 내 경로 기준으로 src 모듈 등록
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from utils.vault_manager import vault  # noqa: E402


def run():
    print("[ADF Custom Activity] 시작")

    # ── ADLS Gen2 연결 ─────────────────────────────────────────────────────
    # Key Vault 시크릿 'adls-account-name' 에서 계정명을 읽어 클라이언트 반환
    adls_client = vault.get_storage_client()
    print(f"[OK] ADLS Gen2 연결: {adls_client.url}")

    # 예: 특정 컨테이너의 파일 목록 조회
    # file_system = adls_client.get_file_system_client("raw")
    # paths = list(file_system.get_paths("/input"))
    # print(f"[OK] 파일 수: {len(paths)}")

    # ── Azure SQL 연결 ─────────────────────────────────────────────────────
    # Key Vault 시크릿 'sql-connection-string' 을 읽어 pyodbc.Connection 반환
    # with vault.get_sql_connection() as conn:
    #     cursor = conn.cursor()
    #     cursor.execute("SELECT TOP 5 * FROM dbo.your_table")
    #     for row in cursor.fetchall():
    #         print(row)

    print("[ADF Custom Activity] 완료")


if __name__ == "__main__":
    run()
