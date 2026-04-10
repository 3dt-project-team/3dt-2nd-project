# Databricks notebook source
# SENSE 프로젝트 — Databricks 전처리 노트북 (raw → curated)
# SENSE: Semiconductor Economic News & Sentiment Engine
#
# 목적: ADLS Gen2 raw/ 에서 뉴스 원문 데이터를 읽어 텍스트 클렌징 후 curated/ 에 저장
# 실행: Databricks Repos에서 feature 브랜치 체크아웃 후 각 셀 순서대로 실행

# COMMAND ----------

# MAGIC %md
# MAGIC # 1. 경로 및 vault_manager 초기화

# COMMAND ----------

import os
import sys

REPO_PATH = "/Workspace/Repos/{your-email}/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"

from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. ADLS Gen2 Spark OAuth 설정
# MAGIC
# MAGIC `vault.get_storage_client()` → Databricks 환경 감지 시 SparkSession에 OAuth 자동 설정

# COMMAND ----------

vault.get_storage_client()

account = vault.get_secret("adls-account-name")  # "3dtteam1adls"

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. raw 데이터 로드
# MAGIC
# MAGIC > TODO: 실제 파일 경로로 교체 (예: news_raw_20260101.parquet)

# COMMAND ----------

# raw_path = f"abfss://raw@{account}.dfs.core.windows.net/news/"
# df_raw = spark.read.parquet(raw_path)  # noqa: F821
# display(df_raw)  # noqa: F821

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. 텍스트 클렌징
# MAGIC
# MAGIC > TODO: 실제 클렌징 로직 구현
# MAGIC > - HTML 태그 제거
# MAGIC > - 특수문자 정규화
# MAGIC > - 중복 기사 제거 (URL/제목 기준)
# MAGIC > - 날짜·분류 컬럼 파싱

# COMMAND ----------

# from pyspark.sql import functions as F
#
# df_curated = (
#     df_raw
#     .dropDuplicates(["url"])
#     .filter(F.col("content").isNotNull())
#     # TODO: UDF로 HTML 태그 제거
# )

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. curated/ 저장

# COMMAND ----------

# curated_path = f"abfss://curated@{account}.dfs.core.windows.net/news/"
# df_curated.write.mode("overwrite").parquet(curated_path)  # noqa: F821
# print(f"[OK] {df_curated.count()}건 저장 완료: {curated_path}")  # noqa: F821
