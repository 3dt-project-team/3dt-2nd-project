# Databricks notebook source
# MAGIC %md
# MAGIC # bronze 전체 네이버 뉴스 데이터 전처리

# COMMAND ----------

# MAGIC %md
# MAGIC ## 환경설정

# COMMAND ----------

# MAGIC %sh
# MAGIC # 필수 Azure SDK 패키지 설치
# MAGIC uv pip install azure-identity azure-keyvault-secrets azure-storage-file-datalake

# COMMAND ----------
# ruff: noqa: E402, F821, E501

import os
import sys

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"

sys.path.insert(0, "/Workspace/Repos/3dt030@msacademy.msai.kr/3dt-2nd-project/src")

# ✅ import 전에 싱글톤 초기화
import utils.vault_manager

utils.vault_manager._instance = None

# ✅ 그 다음 vault 새로 가져오기
from utils.vault_manager import get_vault_manager

vault = get_vault_manager()

print("client_id:", vault.get_secret("adls-client-id"))
print("client_secret:", vault.get_secret("adls-client-secret"))
print("tenant_id:", vault.get_secret("adls-tenant-id"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 데이터 로드

# COMMAND ----------

vault.get_storage_client("3dtteam1adls")

from pyspark.sql import functions as F
from pyspark.sql.types import StringType

BRONZE_BASE = "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/naver/"

# 와일드카드로 JSON 파일 직접 읽기
df_raw = (
    spark.read.option("mergeSchema", "true")
    .option("multiLine", "true")  # ← 이거 추가!
    .json(f"{BRONZE_BASE}source=*/month=*/*.json")
)

print(f"총 로드: {df_raw.count():,}건")
print(f"컬럼: {df_raw.columns}")
df_raw.printSchema()


# COMMAND ----------

# 경로 자동 생성 (파일명 신경 안 써도 됨)
sources = ["samsung", "skhynix"]
months = (
    [f"2025-{m:02d}" for m in range(4, 13)]  # 2025-04 ~ 2025-12
    + [f"2026-{m:02d}" for m in range(1, 5)]  # 2026-01 ~ 2026-04
)

paths = [f"{BRONZE_BASE}source={s}/month={m}/" for s in sources for m in months]

print(f"총 경로 수: {len(paths)}개")

df_raw = spark.read.option("mergeSchema", "true").option("multiLine", "true").json(paths)

print(f"총 로드: {df_raw.count():,}건")
print(f"컬럼: {df_raw.columns}")


# COMMAND ----------

# MAGIC %md
# MAGIC ### 컬럼 표준화 + pubDate 처리

# COMMAND ----------

df = (
    df_raw.withColumnRenamed("newsId", "news_id")
    .withColumnRenamed("pubDate", "pub_date_raw")
    .withColumnRenamed("adjustedDate", "adjusted_date")
    .withColumnRenamed("fetchedAt", "fetched_at")
    .withColumnRenamed("source", "stock_keyword")  # samsung/skhynix
)

# pubDate 전체 null → adjustedDate 대체
df = df.withColumn(
    "pub_date",
    F.coalesce(F.to_date("pub_date_raw", "yyyy-MM-dd"), F.to_date("adjusted_date", "yyyy-MM-dd")),
)

# news_source는 항상 naver
df = df.withColumn("news_source", F.lit("naver"))

print(f"컬럼: {df.columns}")
display(df.limit(10))

# COMMAND ----------

df = df.drop("naverUrl", "pub_date_raw", "adjusted_date")

df = df.withColumnRenamed("fetched_at", "published_time")

print(f"최종 컬럼: {df.columns}")
display(df.limit(10))

# COMMAND ----------

# 컬럼 순서 정리
df = df.select(
    "news_id",  # PK
    "stock_keyword",  # samsung/skhynix
    "news_source",  # naver
    "pub_date",  # 발행 날짜
    "published_time",  # 발행 시각
    "press",  # 언론사
    "headline",  # 기사 제목
    "body",  # 원문 본문
    "description",  # 3줄 요약 (LLM 예정)
    "url",  # 원문 URL
)

print(f"컬럼 순서: {df.columns}")
display(df.limit(10))


# COMMAND ----------

# MAGIC %md
# MAGIC ### samsung, skhynix 중복 기사 전처리
# MAGIC - url 기준으로 중복 처리
# MAGIC - 겹치는 기사를 stock_keyword->samsung,skhynix 설정 후 중복된 기사 제거

# COMMAND ----------

# 1. 한글 → 영어 표준화
df = df.withColumn(
    "stock_keyword",
    F.when(F.col("stock_keyword") == "삼성전자", "samsung")
    .when(F.col("stock_keyword") == "SK하이닉스", "skhynix")
    .otherwise(F.col("stock_keyword")),
)

# 2. URL 기준으로 머지
# - news_id는 버리고 (samsung용/skhynix용 각각 다르게 생성됐으므로)
# - URL이 같으면 stock_keyword만 합치고 나머지는 첫 번째 값 사용
df_merged = df.groupBy("url").agg(
    F.first("pub_date").alias("pub_date"),
    F.first("published_time").alias("published_time"),
    F.first("news_source").alias("news_source"),
    F.first("press").alias("press"),
    F.first("headline").alias("headline"),
    F.first("body").alias("body"),
    F.first("description").alias("description"),
    F.concat_ws(",", F.collect_set("stock_keyword")).alias("stock_keyword"),
)

# 3. 결과 확인
print(f"머지 전: {df.count():,}건")
print(f"머지 후: {df_merged.count():,}건")
print(f"중복 제거: {df.count() - df_merged.count():,}건")

display(df_merged.groupBy("stock_keyword").count().orderBy("count", ascending=False))


# COMMAND ----------

# MAGIC %md
# MAGIC ### 본문 NULL 값 열 제거

# COMMAND ----------

# 본문 없는 기사 제거
before_count = df_merged.count()

df_merged = df_merged.filter(
    F.col("body").isNotNull()
    & (F.col("body") != "")
    & (F.length(F.col("body")) >= 50)  # 50자 미만도 제거
)

after_count = df_merged.count()
print(f"[INFO] 본문 없는 기사 제거 전: {before_count:,}건")
print(f"[INFO] 본문 없는 기사 제거 후: {after_count:,}건")
print(f"[INFO] 제거된 기사: {before_count - after_count:,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 본문 html, 특수문자 등 정리

# COMMAND ----------

import re

from pyspark.sql import functions as F


# 1. HTML 및 불필요한 텍스트 제거 UDF
def clean_text(text):
    if text is None:
        return None
    # HTML 태그 제거
    text = re.sub(r"<[^>]+>", "", text)
    # HTML 엔티티 제거 (&amp; &lt; 등)
    text = re.sub(r"&[a-zA-Z]+;", "", text)
    # 특수문자 정리 (문장부호 제외)
    text = re.sub(r"[\r\n\t]+", " ", text)
    # 연속 공백 정리
    text = re.sub(r" +", " ", text)
    return text.strip()


clean_udf = F.udf(clean_text)

# 2. body, headline, description 컬럼 클렌징
df_cleaned = (
    df_merged.withColumn("body", clean_udf(F.col("body")))
    .withColumn("headline", clean_udf(F.col("headline")))
    .withColumn("description", clean_udf(F.col("description")))
)

# 3. 키워드별 10개씩 샘플 출력
keywords = ["samsung", "skhynix", "skhynix,samsung"]

for kw in keywords:
    print(f"\n{'=' * 60}")
    print(f"📰 stock_keyword = '{kw}' 샘플 10건")
    print(f"{'=' * 60}")
    df_cleaned.filter(F.col("stock_keyword") == kw).select(
        "stock_keyword", "headline", "body"
    ).limit(10).show(truncate=100)

# COMMAND ----------

# MAGIC %md
# MAGIC ### description 전처리
# MAGIC - **Azure OpenAI GPT-4.1 mini** 를 사용하여 본문(`body`)을 3줄 요약
# MAGIC - `description`이 없는 기사만 요약 처리 (있는 건 그대로 유지)
# MAGIC - **Batch API** 방식으로 제출 (최대 24시간 대기, 비용 50% 절감)
# MAGIC - 50,000건씩 분할하여 `.jsonl` 파일로 제출
# MAGIC - 1회차 전체 처리 후 이후 증분 데이터는 실시간 API로 처리

# COMMAND ----------

# MAGIC %md
# MAGIC #### 셀 1 - Batch 요청 파일 생성

# COMMAND ----------

import json

from pyspark.sql import functions as F

df_need_summary = (
    df_cleaned.filter(F.col("description").isNull() | (F.col("description") == ""))
    .select("url", "body")
    .toPandas()
)  # ✅  url

print(f"[INFO] 요약 필요 건수: {len(df_need_summary)}건")

batch_size = 50000
chunks = [df_need_summary[i : i + batch_size] for i in range(0, len(df_need_summary), batch_size)]

for idx, chunk in enumerate(chunks):
    output_file = f"/tmp/batch_request_{idx + 1}.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for _, row in chunk.iterrows():
            request = {
                "custom_id": str(row["url"]),  # ✅  url
                "method": "POST",
                "url": "/chat/completions",
                "body": {
                    "model": "gpt-4.1-mini-batch",  # ✅ 모델명
                    "messages": [
                        {
                            "role": "system",
                            "content": "뉴스 기사를 3줄로 요약해주세요. 핵심 내용만 간결하게 작성하세요.",
                        },
                        {"role": "user", "content": str(row["body"])[:3000]},
                    ],
                    "max_tokens": 300,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
    print(f"[OK] 파일 생성: {output_file} ({len(chunk)}건)")

# COMMAND ----------

# MAGIC %md
# MAGIC #### 셀 2 - Batch 파일 업로드 및 작업 제출

# COMMAND ----------

from openai import AzureOpenAI

# Azure OpenAI 클라이언트
client = AzureOpenAI(
    # api_key=vault.get_secret("azure-openai-key"),      # Key Vault에서 가져오기
    api_key="",
    api_version="2024-12-01-preview",
    azure_endpoint=vault.get_secret("azure-openai-endpoint"),
)

batch_job_ids = []

for idx in range(len(chunks)):
    file_path = f"/tmp/batch_request_{idx + 1}.jsonl"

    # 파일 업로드
    with open(file_path, "rb") as f:
        uploaded_file = client.files.create(file=f, purpose="batch")
    print(f"[OK] 파일 업로드: {uploaded_file.id}")

    # Batch 작업 제출
    batch_job = client.batches.create(
        input_file_id=uploaded_file.id, endpoint="/chat/completions", completion_window="24h"
    )
    batch_job_ids.append(batch_job.id)
    print(f"[OK] Batch 제출: {batch_job.id}")

print(f"\n[INFO] 전체 Batch Job IDs: {batch_job_ids}")

# COMMAND ----------

# MAGIC %md
# MAGIC #### 셀 3 - 상태 확인 (나중에 실행)

# COMMAND ----------

import time

batch_job_ids = [
    "batch_f6da50db-5a9d-4915-8228-f48dee79ee34",
    "batch_357a34f0-6e9b-4226-a537-994f7419a537",
    "batch_b59bec80-4a0d-4541-a4d6-a0f9b3d07596",
]

while True:
    all_done = True
    for job_id in batch_job_ids:
        job = client.batches.retrieve(job_id)
        print(
            f"{job_id[:20]}... | 상태: {job.status} | 완료: {job.request_counts.completed}/{job.request_counts.total}"
        )
        if job.status not in ["completed", "failed", "cancelled"]:
            all_done = False

    if all_done:
        print("\n[완료] 모든 Batch 작업 완료!")
        break

    print("---")
    time.sleep(300)  # 5분마다 확인

# COMMAND ----------

import json
from datetime import datetime

import pandas as pd

all_summaries = {}

for job_id in batch_job_ids:
    job = client.batches.retrieve(job_id)

    if job.status != "completed":
        print(f"[WARN] {job_id} 아직 미완료: {job.status}")
        continue

    result_content = client.files.content(job.output_file_id).text

    for line in result_content.strip().split("\n"):
        result = json.loads(line)
        url = result["custom_id"]
        summary = result["response"]["body"]["choices"][0]["message"]["content"]
        all_summaries[url] = summary

print(f"[OK] 요약 수집 완료: {len(all_summaries)}건")

summary_df = spark.createDataFrame(
    pd.DataFrame(list(all_summaries.items()), columns=["url", "description_new"])
)

# ✅ 오늘 날짜 제외하고 경로 재설정
today = datetime.now().strftime("%Y-%m-%d")
year_month_today = today[:7]  # 2026-04

# 오늘 날짜가 포함된 월 제외하고 경로 재구성
sources = ["samsung", "skhynix"]
months = (
    [f"2025-{m:02d}" for m in range(4, 13)]
    + [f"2026-{m:02d}" for m in range(1, 4)]  # ✅ 2026-04 제외
)

BRONZE_BASE = "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/naver/"
paths = [f"{BRONZE_BASE}source={s}/month={m}/" for s in sources for m in months]

print(f"[INFO] 오늘({today}) 포함 월 제외 → {len(paths)}개 경로 로드")

df_raw_filtered = spark.read.option("mergeSchema", "true").option("multiLine", "true").json(paths)

# 컬럼 표준화 다시 처리
from pyspark.sql import functions as F

df_filtered = (
    df_raw_filtered.withColumnRenamed("newsId", "news_id")
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
    .drop("naverUrl", "pub_date_raw", "adjusted_date")
)

# 중복 제거 + 본문 없는 기사 제거
df_merged_filtered = (
    df_filtered.groupBy("url")
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
)  # ✅ description 추가


# HTML 정리
def clean_text(text):
    if text is None:
        return None
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-zA-Z]+;", "", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


clean_udf = F.udf(clean_text)
df_cleaned_filtered = (
    df_merged_filtered.withColumn("body", clean_udf(F.col("body")))
    .withColumn("headline", clean_udf(F.col("headline")))
    .withColumn("description", clean_udf(F.col("description")))
)

print(f"[INFO] 재로드 완료: {df_cleaned_filtered.count():,}건")

# df_final 생성
df_has_summary = df_cleaned_filtered.filter(
    F.col("description").isNotNull() & (F.col("description") != "")
)
df_need_summary_spark = (
    df_cleaned_filtered.filter(F.col("description").isNull() | (F.col("description") == ""))
    .drop("description")
    .join(summary_df, on="url", how="left")
    .withColumnRenamed("description_new", "description")
)

df_final = df_has_summary.union(df_need_summary_spark)
print(f"[OK] 최종 데이터: {df_final.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC #### 셀 4 - 결과 수집 및 df_final 생성

# COMMAND ----------

import json
from datetime import datetime

import pandas as pd

all_summaries = {}

for job_id in batch_job_ids:
    job = client.batches.retrieve(job_id)

    if job.status != "completed":
        print(f"[WARN] {job_id} 아직 미완료: {job.status}")
        continue

    result_content = client.files.content(job.output_file_id).text

    for line in result_content.strip().split("\n"):
        result = json.loads(line)
        url = result["custom_id"]
        summary = result["response"]["body"]["choices"][0]["message"]["content"]
        all_summaries[url] = summary

print(f"[OK] 요약 수집 완료: {len(all_summaries)}건")

summary_df = spark.createDataFrame(
    pd.DataFrame(list(all_summaries.items()), columns=["url", "description_new"])
)

# ✅ 오늘 날짜 제외
today = datetime.now().strftime("%Y-%m-%d")
df_cleaned_filtered = df_cleaned.filter(F.col("pub_date") < today)
print(f"[INFO] 오늘({today}) 제외 후: {df_cleaned_filtered.count():,}건")

df_has_summary = df_cleaned_filtered.filter(
    F.col("description").isNotNull() & (F.col("description") != "")
)
df_need_summary_spark = (
    df_cleaned_filtered.filter(F.col("description").isNull() | (F.col("description") == ""))
    .drop("description")
    .join(summary_df, on="url", how="left")
    .withColumnRenamed("description_new", "description")
)

df_final = df_has_summary.union(df_need_summary_spark)
print(f"[OK] 최종 데이터: {df_final.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 요약 실패 기사 제거

# COMMAND ----------

before = df_final.count()

df_final = df_final.filter(F.col("description").isNotNull() & (F.col("description") != ""))

after = df_final.count()
print(f"[INFO] 요약 실패 제거: {before - after:,}건 제거 → {after:,}건 남음")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 칼럼 정리 및 결과 저장

# COMMAND ----------


def remove_numbering(text):
    if text is None:
        return None
    # "1. " "2. " "3. " 형식 제거
    text = re.sub(r"^\d+\.\s*", "", text)
    text = re.sub(r"\s*\d+\.\s*", " ", text)
    return text.strip()


remove_numbering_udf = F.udf(remove_numbering, StringType())

df_final = df_final.withColumn("description", remove_numbering_udf(F.col("description")))
print("[OK] description 번호 제거 완료")

# COMMAND ----------

df_final = df_final.select(
    "url",
    "news_id",
    "stock_keyword",
    "news_source",
    "pub_date",
    "published_time",
    "press",
    "headline",
    "body",
    "description",
)

SILVER_PATH = "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/naver/preprocessed/"

df_final.withColumn("year_month", F.date_format(F.col("pub_date"), "yyyy-MM")).write.mode(
    "overwrite"
).partitionBy("year_month").parquet(SILVER_PATH)

print(f"[OK] Silver parquet 저장 완료: {df_final.count():,}건")
print(f"[OK] 경로: {SILVER_PATH}")

# COMMAND ----------

display(df_final.limit(20))
