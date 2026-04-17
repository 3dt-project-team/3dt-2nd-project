# Databricks notebook source
# ruff: noqa: E402, F821, E501
# MAGIC %md
# MAGIC ### 환경 설정
# MAGIC

# COMMAND ----------

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from openai import AzureOpenAI
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, FloatType, StringType, StructField, StructType

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"
sys.path.insert(0, "/Workspace/Repos/3dt030@msacademy.msai.kr/3dt-2nd-project/src")

import utils.vault_manager

utils.vault_manager._instance = None
from utils.vault_manager import get_vault_manager

vault = get_vault_manager()
vault.get_storage_client("3dtteam1adls")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ADF 파라미터 주입

# COMMAND ----------

dbutils.widgets.text("target_date", "")
target_date = dbutils.widgets.get("target_date")

from datetime import datetime, timedelta

if not target_date:
    now_kst = datetime.utcnow() + timedelta(hours=9)
    target_date = now_kst.strftime("%Y-%m-%d")

year_month = target_date[:7]
print(f"[INFO] 처리 대상: {target_date} (year_month: {year_month})")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 경로 설정

# COMMAND ----------

BRONZE_BASE_NAVER = "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/naver/preprocessed/"
BRONZE_BASE_FOREIGN = (
    "abfss://silver@3dtteam1adls.dfs.core.windows.net/news/google_bing/preprocessed_google&bing/"
)
OUTPUT_PATH = "abfss://silver@3dtteam1adls.dfs.core.windows.net/news/feature/"

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1. 데이터 로드 및 합치기

# COMMAND ----------

df_naver = spark.read.parquet(BRONZE_BASE_NAVER)
df_foreign = spark.read.parquet(BRONZE_BASE_FOREIGN)

# 네이버 year_month 파티션 컬럼 제거
df_naver = df_naver.drop("year_month")

# target_date 기준 필터링
df_naver = df_naver.filter(F.col("pub_date") == target_date)
df_foreign = df_foreign.filter(F.col("pub_date") == target_date)

print(f"[INFO] 네이버 신규: {df_naver.count():,}건")
print(f"[INFO] 해외 신규:   {df_foreign.count():,}건")

# 합치기
df = df_naver.unionByName(df_foreign, allowMissingColumns=True)
print(f"[INFO] 합친 데이터: {df.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2. 이미 처리된 URL 제외

# COMMAND ----------

try:
    df_existing = spark.read.parquet(f"{OUTPUT_PATH}year_month={year_month}/")
    existing_urls = df_existing.select("url")

    before = df.count()
    df = df.join(existing_urls, on="url", how="left_anti")  # 기존에 없는 것만
    after = df.count()
    print(f"[INFO] 기존 처리 제외: {before - after:,}건 → 신규 {after:,}건")

except Exception:
    print(f"[INFO] {year_month} feature 데이터 없음 - 전체 처리")
    print(f"[INFO] 처리 대상: {df.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3. description null 확인 및 제거

# COMMAND ----------

null_count = df.filter(F.col("description").isNull() | (F.col("description") == "")).count()
print(f"[INFO] description null/빈값: {null_count:,}건")

df = df.filter(F.col("description").isNotNull() & (F.col("description") != ""))
print(f"[INFO] 처리 대상: {df.count():,}건")

if df.count() == 0:
    print("[INFO] 처리할 신규 데이터 없음 - 종료")
    dbutils.notebook.exit("NO_NEW_DATA")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4. Azure OpenAI 클라이언트 설정

# COMMAND ----------

openai_key = vault.get_secret("azure-openai-key")  # gpt-4.1-mini용
openai_embedding_key = vault.get_secret("azure-openai-embedding-key")  # text-embedding-3-small용
openai_endpoint = vault.get_secret("azure-openai-endpoint")  # 공통 엔드포인트

print("[INFO] Azure OpenAI 클라이언트 설정 완료 (chat / embed 분리)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5. 임베딩 처리 (text-embedding-3-small)

# COMMAND ----------


def get_embeddings_bulk(texts: list):
    """100건씩 묶어서 임베딩 호출 - 워커마다 클라이언트 새로 생성 (pickle 오류 방지)"""
    if not texts:
        return []
    _client = AzureOpenAI(
        api_key=openai_embedding_key,
        api_version="2024-12-01-preview",
        azure_endpoint=openai_endpoint,
    )
    response = _client.embeddings.create(model="text-embedding-3-small", input=texts)
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]


def embed_batch(texts: pd.Series) -> pd.Series:
    batch_size = 100
    all_embeddings = []
    text_list = texts.tolist()

    for i in range(0, len(text_list), batch_size):
        batch = text_list[i : i + batch_size]
        try:
            embeddings = get_embeddings_bulk(batch)
        except Exception as e:
            print(f"[WARN] 임베딩 실패: {e}")
            embeddings = [None] * len(batch)
        all_embeddings.extend(embeddings)

    return pd.Series(all_embeddings)


embed_udf = F.pandas_udf(embed_batch, ArrayType(FloatType()))

print("[INFO] 임베딩 UDF 설정 완료")

# COMMAND ----------

print("[INFO] 임베딩 시작...")
df = df.withColumn("summary_vector", embed_udf(F.col("description")))
print(f"[INFO] 임베딩 완료: {df.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6. gpt-4.1-mini - absa_aspect + absa_score + dynamic_keywords 동시 추출

# COMMAND ----------

ASPECT_CATEGORIES = """
- 실적: 매출, 영업이익, EPS, 분기 실적, 연간 실적
- 공급망: 부품, 소재, 협력사, 재고, 수급
- 양산일정: 수율, 출시일, 생산라인, 공정
- 제조원가: 원가, 비용절감, 마진, 감가상각
- 거시경제: 금리, 환율, 관세, 정책, 규제
- 인사/경영: CEO, 조직개편, M&A, 합병, 인수
- 기타: 위 카테고리에 해당하지 않는 내용
"""

SYSTEM_PROMPT = (
    "뉴스 기사를 분석해서 아래 JSON만 반환하세요. 다른 텍스트 금지.\n\n"
    "카테고리 목록:\n" + ASPECT_CATEGORIES + "\n반환 형식:\n"
    '{"absa_aspect": "카테고리명", "absa_score": 감성점수, "dynamic_keywords": ["키워드1", "키워드2", "키워드3"]}\n\n'
    "규칙:\n"
    "- absa_score: -1.0(매우 부정) ~ 0.0(중립) ~ 1.0(매우 긍정)\n"
    "- dynamic_keywords: 기사의 핵심 명사 키워드 3~5개, 언더바(_)로 연결 (예: 삼성전자, HBM_수율, 트럼프_관세)"
)

print("[INFO] gpt-4.1-mini 프롬프트 설정 완료")

# COMMAND ----------


def get_absa_single(text: str):
    """gpt-4.1-mini로 absa_aspect + absa_score + dynamic_keywords 동시 추출
    워커마다 클라이언트 새로 생성 (pickle 오류 방지)"""
    if not text or len(text.strip()) < 10:
        return ("기타", 0.0, [])

    _client = AzureOpenAI(
        api_key=openai_key, api_version="2024-12-01-preview", azure_endpoint=openai_endpoint
    )

    try:
        response = _client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:1000]},
            ],
            max_tokens=100,
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        aspect = parsed.get("absa_aspect", "기타")
        score = float(parsed.get("absa_score", 0.0))
        score = max(-1.0, min(1.0, score))
        keywords = parsed.get("dynamic_keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        return (aspect, score, keywords)
    except Exception as e:
        print(f"[WARN] 분석 실패: {e}")
        return ("기타", 0.0, [])


absa_schema = StructType(
    [
        StructField("absa_aspect", StringType()),
        StructField("absa_score", FloatType()),
        StructField("dynamic_keywords", ArrayType(StringType())),
    ]
)


def absa_batch(texts: pd.Series) -> pd.DataFrame:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_absa_single, texts))
    return pd.DataFrame(results, columns=["absa_aspect", "absa_score", "dynamic_keywords"])


absa_udf = F.pandas_udf(absa_batch, absa_schema)

print("[INFO] gpt-4.1-mini UDF 설정 완료")

# COMMAND ----------

print("[INFO] gpt-4.1-mini 분석 시작...")
df = df.withColumn("absa", absa_udf(F.col("description")))
df = (
    df.withColumn("absa_aspect", F.col("absa.absa_aspect"))
    .withColumn("absa_score", F.col("absa.absa_score"))
    .withColumn("dynamic_keywords", F.col("absa.dynamic_keywords"))
    .drop("absa")
)
print(f"[INFO] gpt-4.1-mini 분석 완료: {df.count():,}건")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 7. 저장 (append 모드 - 월별 파티션)

# COMMAND ----------

print(f"[INFO] 최종 건수: {df.count():,}건")
print(f"[INFO] 컬럼: {df.columns}")

df_save = df.withColumn("year_month", F.date_format(F.col("pub_date"), "yyyy-MM"))

df_save.write.mode("append").partitionBy("year_month").parquet(OUTPUT_PATH)

print(f"[OK] 저장 완료 → {OUTPUT_PATH}year_month={year_month}/")
dbutils.notebook.exit("SUCCESS")
