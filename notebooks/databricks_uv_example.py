# Databricks 노트북 — uv + vault_manager + ADLS Gen2 연동 예시
# 각 셀 구분은 주석으로 표시되어 있습니다. Databricks에서 셀별로 분리해서 사용하세요.

# ==============================================================================
# [셀 1] 패키지 즉석 설치 (Init Script 없이 빠르게 테스트할 때)
# Init Script(init_script_install_uv.sh)가 등록된 클러스터라면 이 셀은 생략 가능
# ==============================================================================

# %sh
# pip install uv -q
# uv pip install --system \
#   azure-identity azure-keyvault-secrets azure-storage-file-datalake python-dotenv -q

# ==============================================================================
# [셀 2] 경로 설정 및 vault_manager import
# Repos 경로는 실제 이메일/저장소 이름으로 교체하세요.
# ==============================================================================

import os
import sys

REPO_PATH = "/Workspace/Repos/{your-email}/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

# KEY_VAULT_URL 환경 변수 설정
# 보안 강화: dbutils.secrets.get() 으로 Key Vault URL 자체도 숨길 수 있습니다 (셀 5 참고)
os.environ["KEY_VAULT_URL"] = "https://{your-keyvault-name}.vault.azure.net/"

from utils.vault_manager import vault  # noqa: E402

# ==============================================================================
# [셀 3] ADLS Gen2 Spark 설정
# vault.get_storage_client()가 Databricks 환경을 감지하면:
#   - KV에서 adls-client-id / adls-client-secret / adls-tenant-id 를 읽어
#   - 현재 SparkSession에 OAuth Spark conf 를 자동으로 적용합니다.
# ==============================================================================

vault.get_storage_client()  # Spark conf 설정 완료 → None 반환 (정상)

# 설정 후 abfss:// URI 로 데이터 접근
# container = "raw"
# account   = dbutils.secrets.get(scope="kv-scope", key="adls-account-name")
# df = spark.read.parquet(f"abfss://{container}@{account}.dfs.core.windows.net/input/")
# display(df)

# ==============================================================================
# [셀 4] PostgreSQL 연결 (pandas로 결과 조회 예시)
# ==============================================================================

# import pandas as pd
# conn = vault.get_pg_connection(engine="sqlalchemy")
# df_result = pd.read_sql("SELECT * FROM results LIMIT 100", conn)
# display(df_result)

# ==============================================================================
# [셀 5] 보안 강화 — Databricks Secret Scope 로 Key Vault URL 숨기기
# Key Vault 연동 Secret Scope 등록 방법:
#   databricks secrets create-scope --scope kv-scope \
#     --scope-backend-type AZURE_KEYVAULT \
#     --resource-id /subscriptions/{sub}/resourceGroups/{rg}/providers/ \
#       Microsoft.KeyVault/vaults/{kv}
# ==============================================================================

# KEY_VAULT_URL = dbutils.secrets.get(scope="kv-scope", key="KEY-VAULT-URL")
# os.environ["KEY_VAULT_URL"] = KEY_VAULT_URL
# from importlib import reload
# import utils.vault_manager as vm_module
# reload(vm_module)
# vault = vm_module.KeyVaultManager()
