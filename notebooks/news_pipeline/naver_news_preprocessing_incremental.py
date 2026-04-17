# Databricks notebook source
# MAGIC %md
# MAGIC ## 네이버 뉴스 증분 전처리 파이프라인
# MAGIC - Bronze → Silver 증분 처리
# MAGIC - ADF에서 매시간 호출
# MAGIC - 수집된 데이터 중 미처리 데이터만 전처리

# COMMAND ----------

# MAGIC %md
# MAGIC ### 환경 설정

# COMMAND ----------
# ruff: noqa: E402, F821, E501

import os
import re
import sys
from datetime import datetime, timedelta

import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

# ADF에서 파라미터 주입 (없으면 KST 현재 시간 기준 자동 설정)
dbutils.widgets.text("target_date", "")
dbutils.widgets.text("target_hour", "")

target_date = dbutils.widgets.get("target_date")
target_hour = dbutils.widgets.get("target_hour")

# ✅ KST 기준으로 자동 설정 (함수앱과 동일한 기준)
if not target_date:
    now_kst = datetime.utcnow() + timedelta(hours=9)
    target_date = now_kst.strftime("%Y-%m-%d")
    target_hour = now_kst.strftime("%H")

print(f"[INFO] 처리 대상: {target_date} {target_hour}시 (KST)")

# Key Vault 설정
os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"
sys.path.insert(0, "/Workspace/Repos/3dt030@msacademy.msai.kr/3dt-2nd-project/src")

import utils.vault_manager

utils.vault_manager._instance = None
from utils.vault_manager import get_vault_manager

vault = get_vault_manager()
vault.get_storage_client("3dtteam1adls")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 경로 설정

# COMMAND ----------

BRONZE_BASE = "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/naver/"
SILVER_PATH = "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/naver/preprocessed/"

year_month = target_date[:7]
print(f"[INFO] Bronze 경로: {BRONZE_BASE}source=*/month={year_month}/")
print(f"[INFO] Silver 경로: {SILVER_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 데이터 로드

# COMMAND ----------

paths = [
    f"{BRONZE_BASE}source=samsung/month={year_month}/",
    f"{BRONZE_BASE}source=skhynix/month={year_month}/",
]

df_raw = spark.read.option("mergeSchema", "true").option("multiLine", "true").json(paths)

df = (
    df_raw.withColumnRenamed("newsId", "news_id")
    .withColumnRenamed("pubDate", "pub_date_raw")
    .withColumnRenamed("adjustedDate", "adjusted_date")
    .withColumnRenamed("fetchedAt", "published_time")
    .withColumnRenamed("source", "stock_keyword")
    .withColumn(
        "pub_date",
        F.coalesce(
            F.to_date("pub_date_raw", "yyyy-MM-dd"), F.to_date("adjusted_date", "yyyy-MM-dd")
        ),
    )
    .withColumn("news_source", F.lit("naver"))
    .withColumn(
        "stock_keyword",
        F.when(F.col("stock_keyword") == "삼성전자", "samsung")
        .when(F.col("stock_keyword") == "SK하이닉스", "skhynix")
        .otherwise(F.col("stock_keyword")),
    )
    .filter(F.col("pub_date") == target_date)
    .drop("naverUrl", "pub_date_raw", "adjusted_date")
)

# ✅ 즉시 메모리에 올려서 파일 연결 끊기
df_pandas = df.toPandas()
df = spark.createDataFrame(df_pandas)
df = df.cache()

print(f"[INFO] Bronze 로드: {df.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 이미 처리된 URL 제외

# COMMAND ----------

try:
    df_existing = spark.read.parquet(
        f"{SILVER_PATH}year_month={year_month}/"  # ✅ pub_date → year_month
    )

    latest_time = df_existing.agg(F.max("published_time")).collect()[0][0]

    print(f"[INFO] Silver 최신 수집 시간: {latest_time}")

    before = df.count()
    df = df.filter(F.col("published_time") > latest_time)
    after = df.count()
    print(f"[INFO] 신규 데이터: {before - after:,}건 제외 → {after:,}건 처리 예정")

except Exception:
    print(f"[INFO] {target_date} Silver 데이터 없음 - 전체 처리")
    print(f"[INFO] 전체 처리 대상: {df.count():,}건")

if df.count() == 0:
    print("[INFO] 처리할 신규 데이터 없음 - 종료")
    dbutils.notebook.exit("NO_NEW_DATA")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 중복 제거 + 본문 없는 기사 제거

# COMMAND ----------

before_count = df.count()

df_merged = (
    df.groupBy("url")
    .agg(
        F.first("news_id").alias("news_id"),
        F.first("pub_date").alias("pub_date"),
        F.first("published_time").alias("published_time"),
        F.first("news_source").alias("news_source"),
        F.first("press").alias("press"),
        F.first("headline").alias("headline"),
        F.first("body").alias("body"),
        F.concat_ws(",", F.collect_set("stock_keyword")).alias("stock_keyword"),
    )
    .filter(F.col("body").isNotNull() & (F.col("body") != "") & (F.length(F.col("body")) >= 50))
    .withColumn("description", F.lit(None).cast("string"))
)  # ✅ description None으로 추가

after_count = df_merged.count()
print(f"[INFO] 중복/본문없는 기사 제거: {before_count:,}건 → {after_count:,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### HTML 정리

# COMMAND ----------


def clean_text(text):
    if text is None:
        return None
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-zA-Z]+;", "", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


clean_udf = F.udf(clean_text)

df_cleaned = (
    df_merged.withColumn("body", clean_udf(F.col("body")))
    .withColumn("headline", clean_udf(F.col("headline")))
    .withColumn("description", clean_udf(F.col("description")))
)

print("[INFO] HTML 정리 완료")

# COMMAND ----------

display(df_cleaned.limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 본문 요약 (description 전처리)

# COMMAND ----------

from concurrent.futures import ThreadPoolExecutor

from openai import AzureOpenAI

openai_key = vault.get_secret("azure-openai-key")
openai_endpoint = vault.get_secret("azure-openai-endpoint")


def summarize_single(text):
    if not text or len(text.strip()) < 50:
        return None
    client = AzureOpenAI(
        api_key=openai_key, api_version="2024-12-01-preview", azure_endpoint=openai_endpoint
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "뉴스 기사를 3줄로 요약해주세요. 핵심 내용만 간결하게 작성하세요.",
                },
                {"role": "user", "content": text[:3000]},
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[WARN] 요약 실패: {e}")
        return None


def summarize_batch(texts: pd.Series) -> pd.Series:
    # ✅ 10개씩 병렬 호출
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(summarize_single, texts))
    return pd.Series(results)


summary_udf = F.pandas_udf(summarize_batch, StringType())

df_final = df_cleaned.withColumn(
    "description",
    F.when(
        F.col("description").isNull() | (F.col("description") == ""), summary_udf(F.col("body"))
    ).otherwise(F.col("description")),
)

print(f"[INFO] 요약 처리 완료: {df_final.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC #### 본문 요약 실패한 기사 제외

# COMMAND ----------

df_final = df_final.filter(F.col("description").isNotNull() & (F.col("description") != ""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### silver layer 데이터 저장

# COMMAND ----------


def remove_numbering(text):
    if text is None:
        return None
    text = re.sub(r"^\d+\.\s*", "", text)
    text = re.sub(r"\s*\d+\.\s*", " ", text)
    return text.strip()


remove_numbering_udf = F.udf(remove_numbering, StringType())

# 번호 제거
df_final = df_final.withColumn("description", remove_numbering_udf(F.col("description")))

# ✅ VOID 타입 컬럼 string으로 변환
df_final = df_final.withColumn("press", F.col("press").cast("string"))

# 캐시
df_final = df_final.cache()
print(f"[INFO] 캐시 완료: {df_final.count():,}건")

# Silver 저장
df_final.withColumn("year_month", F.date_format(F.col("pub_date"), "yyyy-MM")).write.mode(
    "append"
).partitionBy("year_month").parquet(SILVER_PATH)

print(f"[OK] Silver parquet 저장 완료: {df_final.count():,}건")
print(f"[OK] 처리 완료: {target_date} {target_hour}시")
dbutils.notebook.exit("SUCCESS")

# COMMAND ----------

display(df_final.limit(20))
