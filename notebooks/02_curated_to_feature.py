# Databricks notebook source
# SENSE 프로젝트 — Databricks 피처 엔지니어링 노트북 (curated → feature)
# SENSE: Semiconductor Economic News & Sentiment Engine
#
# 목적: curated/ 의 클렌징 데이터에서 ML용 피처를 추출해 feature/ 에 저장
# 실행: 01_raw_to_curated.py 완료 후 실행

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
vault.get_storage_client()  # Spark OAuth 설정

account = vault.get_secret("adls-account-name")

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. curated 데이터 로드

# COMMAND ----------

# curated_path = f"abfss://curated@{account}.dfs.core.windows.net/news/"
# df = spark.read.parquet(curated_path)  # noqa: F821
# display(df.limit(5))  # noqa: F821

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. 피처 엔지니어링
# MAGIC
# MAGIC > TODO: 실제 피처 추출 로직 구현
# MAGIC > - 제목 + 본문 합산 텍스트 컬럼 생성 (`text_for_model`)
# MAGIC > - 감성 라벨 컬럼 (positive/negative/neutral) — 초기엔 규칙 기반
# MAGIC > - 반도체 키워드 포함 여부 플래그
# MAGIC > - 발행 날짜 → 연/월/주 파티션 컬럼

# COMMAND ----------

# from pyspark.sql import functions as F
#
# SEMI_KEYWORDS = ["반도체", "삼성", "SK하이닉스", "TSMC", "엔비디아", "메모리", "파운드리"]
# keyword_pattern = "|".join(SEMI_KEYWORDS)
#
# df_feature = (
#     df
#     .withColumn("text_for_model", F.concat_ws(" ", F.col("title"), F.col("content")))
#     .withColumn("has_semi_keyword", F.col("text_for_model").rlike(keyword_pattern).cast("int"))
#     .withColumn("pub_year", F.year("published_at"))
#     .withColumn("pub_month", F.month("published_at"))
# )

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. feature/ 저장

# COMMAND ----------

# feature_path = f"abfss://feature@{account}.dfs.core.windows.net/sense/"
# df_feature.write.mode("overwrite").partitionBy(  # noqa: F821
#     "pub_year", "pub_month"
# ).parquet(feature_path)
# print(f"[OK] {df_feature.count()}건 저장 완료: {feature_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. (선택) PostgreSQL에 요약 통계 적재

# COMMAND ----------

# import pandas as pd
# engine = vault.get_pg_connection(engine="sqlalchemy")
# summary = df_feature.groupBy("pub_year", "pub_month").count().toPandas()  # noqa: F821
# summary.to_sql("feature_stats", engine, if_exists="replace", index=False)
# print("[OK] PostgreSQL feature_stats 테이블 적재 완료")
