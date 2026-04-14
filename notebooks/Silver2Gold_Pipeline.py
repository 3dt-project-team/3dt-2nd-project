# Databricks notebook source
# MAGIC %md
# MAGIC # 🥇 SENSE Project: Gold Layer ETL Pipeline
# MAGIC 이 노트북은 **Silver Layer(Delta Table)**의 증분 데이터를 읽어와서, 목적별로 최적화된 **Gold Layer(PostgreSQL)**로 적재하는 프로세스를 수행합니다.
# MAGIC
# MAGIC ### **적재 대상 테이블**
# MAGIC 1. `dim_news_display`: Web App 및 Power BI 리스트 서빙용
# MAGIC 2. `agg_market_sentiment_daily`: 일별 감성 지표 집계 및 EDA용
# MAGIC 3. `fact_feature_vector_store`: RAG 서비스 및 ML 모델 피처용

# COMMAND ----------

# MAGIC %md
# MAGIC ##환경 설정 및 DB 연결 정보

# COMMAND ----------

# MAGIC %sh
# MAGIC # 필수 Azure SDK 및 패키지 설치
# MAGIC uv pip install azure-identity azure-keyvault-secrets azure-storage-file-datalake

# COMMAND ----------

import os
import sys
from pyspark.sql import functions as F
from pyspark.sql.types import *

# 1. 환경 변수 및 경로 설정
os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"
sys.path.insert(0, "/Workspace/Repos/3dt030@msacademy.msai.kr/3dt-2nd-project/src")

# 2. Vault Manager 로드 (연결 유지를 위해 일단 실행)
import utils.vault_manager
utils.vault_manager._instance = None
from utils.vault_manager import get_vault_manager
vault = get_vault_manager()

# 3. PostgreSQL 접속 정보 설정 (제공해주신 정보 반영)
db_host = "sense-pg-server.postgres.database.azure.com" 
db_user = "senseadmin"
db_password = "Sense2026!Secure"
db_name = "postgres"

# 4. 최종 연결 객체 생성
db_url = f"jdbc:postgresql://{db_host}:5432/{db_name}"
db_properties = {
    "user": db_user,
    "password": db_password,
    "driver": "org.postgresql.Driver",
    "stringtype": "unspecified"  # PostgreSQL이 string→UUID 자동 캐스팅 허용
}

print("✅ 제공된 정보를 바탕으로 DB 접속 정보 설정 완료!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🥈 1. Silver Layer 데이터 로드
# MAGIC 분석이 완료된 실버 데이터를 캐싱하여 로드합니다.

# COMMAND ----------

# [Cell] 실버 데이터 로드 (서비스 주체 인증 방식)
storage_account_name = vault.get_secret("adls-account-name") 
client_id = vault.get_secret("adls-client-id")
client_secret = vault.get_secret("adls-client-secret")
tenant_id = vault.get_secret("adls-tenant-id")

# Spark 세션에 통행증(OAuth) 설정
spark.conf.set(f"fs.azure.account.auth.type.{storage_account_name}.dfs.core.windows.net", "OAuth")
spark.conf.set(f"fs.azure.account.oauth.provider.type.{storage_account_name}.dfs.core.windows.net", "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider")
spark.conf.set(f"fs.azure.account.oauth2.client.id.{storage_account_name}.dfs.core.windows.net", client_id)
spark.conf.set(f"fs.azure.account.oauth2.client.secret.{storage_account_name}.dfs.core.windows.net", client_secret)
spark.conf.set(f"fs.azure.account.oauth2.client.endpoint.{storage_account_name}.dfs.core.windows.net", f"https://login.microsoftonline.com/{tenant_id}/oauth2/token")

# 데이터 로드 시도
SILVER_PATH = f"abfss://silver@{storage_account_name}.dfs.core.windows.net/news/feature/"
silver_df = spark.read.format("parquet").load(SILVER_PATH)

print(f"✅ 드디어 실버 데이터 접속 성공! 총 {silver_df.count()}건 확인")
display(silver_df.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🎯 2. Gold: `dim_news_display` 적재
# MAGIC - `absa_score` 기반 감성 등급 매핑 (-1 ~ 1 -> 호재/악재)

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql import Window

# [Step 1] Silver 전체 데이터 캐싱
gold_df = silver_df.cache()
print(f"📦 Gold 적재 대상: 총 {gold_df.count()}건")

# ============================================================
# 공통 헬퍼
# ============================================================
def to_uuid(col_name):
    """news_id → md5 기반 UUID 형식 변환 (stringtype=unspecified로 PG 자동 캐스팅)"""
    md5 = F.md5(F.col(col_name))
    return F.concat_ws("-",
        F.substring(md5, 1, 8),  F.substring(md5, 9, 4),
        F.substring(md5, 13, 4), F.substring(md5, 17, 4),
        F.substring(md5, 21, 12)
    ).alias(col_name)

def compute_keyword_stats(df):
    """
    Window 함수 활용: 키워드 전일 대비 언급량 증감(delta) 및 급증률(mention_delta_pct%) 계산
    Returns: (top10_keywords_df, article_momentum_df, article_surge_df)
    """
    # 1) 키워드 explode
    kw_exploded = df.select(
        "news_id", "pub_date", "stock_keyword", "absa_score",
        F.explode_outer("dynamic_keywords").alias("keyword")
    ).filter(F.col("keyword").isNotNull() & (F.col("keyword") != ""))

    # 2) 일별/종목별/키워드별 집계
    daily_kw = kw_exploded.groupBy("pub_date", "stock_keyword", "keyword").agg(
        F.count("*").alias("mention_count"),
        F.round(F.avg("absa_score"), 2).alias("avg_sentiment")
    )

    # 3) Window: 전일 대비 delta / mention_delta_pct 계산
    w = Window.partitionBy("stock_keyword", "keyword").orderBy("pub_date")
    daily_kw = daily_kw \
        .withColumn("prev_mention", F.lag("mention_count").over(w)) \
        .withColumn("prev_sentiment", F.lag("avg_sentiment").over(w)) \
        .withColumn("mention_delta",
            F.col("mention_count") - F.coalesce(F.col("prev_mention"), F.lit(0))) \
        .withColumn("mention_delta_pct",
            F.when(F.col("prev_mention") > 0,
                   F.round((F.col("mention_count") - F.col("prev_mention"))
                           / F.col("prev_mention") * 100, 1))
            .otherwise(F.lit(0.0))) \
        .withColumn("sentiment_delta",
            F.round(F.col("avg_sentiment") - F.coalesce(F.col("prev_sentiment"), F.lit(0.0)), 2)) \
        .withColumn("sentiment_label",
            F.when(F.col("avg_sentiment") >= 0.3, "positive")
             .when(F.col("avg_sentiment") <= -0.3, "negative")
             .otherwise("neutral"))

    # 4) TOP 10 키워드 (agg 테이블용) → 8개 필드 JSONB 배열
    w_rank = Window.partitionBy("pub_date", "stock_keyword").orderBy(F.desc("mention_count"))
    top10 = daily_kw.withColumn("rank", F.row_number().over(w_rank)).filter(F.col("rank") <= 10)
    top10_json = top10.groupBy("pub_date", "stock_keyword").agg(
        F.to_json(
            F.collect_list(
                F.struct(
                    "rank", "keyword", "mention_count", "avg_sentiment",
                    "sentiment_label", "mention_delta", "mention_delta_pct",
                    "sentiment_delta"
                )
            )
        ).alias("daily_keywords_json")
    )

    # 5) 기사별 키워드 모멘텀 (vector 테이블용) → {"키워드": 급증률} JSONB
    article_kw = kw_exploded.join(
        daily_kw.select("pub_date", "stock_keyword", "keyword", "mention_delta_pct"),
        on=["pub_date", "stock_keyword", "keyword"], how="left"
    )
    article_momentum = article_kw.groupBy("news_id").agg(
        F.to_json(
            F.map_from_arrays(
                F.collect_list("keyword"),
                F.collect_list(F.coalesce(F.col("mention_delta_pct"), F.lit(0.0)))
            )
        ).alias("keyword_momentum_json")
    )

    # 6) is_surge 판별: 키워드 중 하나라도 mention_delta_pct >= 300 이면 True
    article_surge = article_kw.groupBy("news_id").agg(
        (F.max(F.coalesce(F.col("mention_delta_pct"), F.lit(0.0))) >= 300).alias("is_surge")
    )

    return top10_json, article_momentum, article_surge

# ============================================================
# [Track 1] dim_news_display (⭐ is_surge 칼럼 추가)
# ============================================================
def load_display_table(df, article_surge):
    base = df.join(article_surge, on="news_id", how="left")
    display_df = base.select(
        to_uuid("news_id"),
        F.col("headline").alias("display_title"),
        F.col("description").alias("core_summary"),
        F.when(F.col("absa_score") >= 0.3, "호재")
         .when(F.col("absa_score") <= -0.3, "악재")
         .otherwise("중립").alias("sentiment_class"),
        F.col("absa_aspect").alias("category"),
        F.col("press"),
        F.col("url").alias("original_url"),
        F.col("stock_keyword"),
        F.to_date(F.col("pub_date")).alias("pub_date"),
        F.coalesce(F.col("is_surge"), F.lit(False)).alias("is_surge")
    )
    display_df.write.jdbc(url=db_url, table="gold_news.dim_news_display",
                          mode="append", properties=db_properties)
    surge_cnt = base.filter(F.col("is_surge") == True).count()
    print(f"✅ 1. dim_news_display 적재 완료 (is_surge=True: {surge_cnt}건)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 📊 3. Gold: `agg_market_sentiment_daily` 적재
# MAGIC - Power BI 대시보드 및 통계 분석용

# COMMAND ----------

# ============================================================
# [Track 2] agg_market_sentiment_daily
# - 당일 종목별 TOP 10 키워드 (rank, mention_delta, sentiment_delta) JSONB
# ============================================================
def load_agg_table(df, top10_json):
    base_agg = df.groupBy("pub_date", "stock_keyword").agg(
        F.avg("absa_score").alias("avg_sentiment"),
        F.count("news_id").cast("int").alias("news_vol"),
        F.mode("absa_aspect").alias("main_aspect")
    )

    agg_df = base_agg.join(
        top10_json, on=["pub_date", "stock_keyword"], how="left"
    ).select(
        F.to_date(F.col("pub_date")).alias("base_date"),
        F.col("stock_keyword").alias("stock_code"),
        "avg_sentiment",
        "news_vol",
        "main_aspect",
        F.coalesce(F.col("daily_keywords_json"), F.lit("[]")).alias("daily_keywords")
    )

    agg_df.write.jdbc(url=db_url, table="gold_news.agg_market_sentiment_daily",
                      mode="append", properties=db_properties)
    print("✅ 2. agg_market_sentiment_daily (통계용) 적재 완료")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🧠 4. Gold: `fact_feature_vector_store` 적재
# MAGIC - `pgvector`를 위한 벡터 문자열 변환 처리

# COMMAND ----------

# ============================================================
# [Track 3] fact_feature_vector_store
# - 기사별 {"키워드": 급증률} JSONB → keyword_momentum
# ============================================================
def load_vector_table(df, article_momentum):
    vector_df = df.join(
        article_momentum, on="news_id", how="left"
    ).select(
        to_uuid("news_id"),
        F.col("summary_vector").cast("string").alias("summary_vec"),
        F.col("body").alias("search_context"),
        F.col("absa_score").cast("float").alias("feature_score"),
        F.col("absa_aspect").alias("aspect_tag"),
        F.coalesce(F.col("keyword_momentum_json"), F.lit("{}")).alias("keyword_momentum")
    )
    vector_df.write.jdbc(url=db_url, table="gold_news.fact_feature_vector_store",
                         mode="append", properties=db_properties)
    print("✅ 3. fact_feature_vector_store (ML/RAG용) 적재 완료")

# ============================================================
# 스마트 샘플링 테스트 (100건)
# - 04-13 + 04-14 데이터로 전일 대비 로직 검증
# ============================================================
import psycopg2

def truncate_gold_tables():
    conn = psycopg2.connect(host=db_host, port=5432, dbname=db_name,
                            user=db_user, password=db_password)
    conn.autocommit = True
    cur = conn.cursor()
    for tbl in ["gold_news.fact_feature_vector_store",
                "gold_news.agg_market_sentiment_daily",
                "gold_news.dim_news_display"]:
        cur.execute(f"TRUNCATE TABLE {tbl} CASCADE")
        print(f"🗑️ {tbl} TRUNCATE 완료")
    cur.close()
    conn.close()

# 1) TRUNCATE
truncate_gold_tables()

# 2) 스마트 샘플링: 04-13 + 04-14 데이터 우선 확보 (100건)
gold_deduped = gold_df.dropDuplicates(["news_id"])

# 날짜 분포 확인
target_dates = ["2026-04-13", "2026-04-14"]
two_day_df = gold_deduped.filter(F.col("pub_date").isin(target_dates))
two_day_count = two_day_df.count()

if two_day_count >= 20:
    test_sample = two_day_df.limit(100).cache()
    print(f"\n🧪 스마트 샘플링: 04-13 + 04-14 데이터 {two_day_count}건 중 {test_sample.count()}건 샘플")
else:
    # 최신 날짜 2일치 데이터로 fallback
    latest_dates = gold_deduped.select("pub_date").distinct() \
        .orderBy(F.desc("pub_date")).limit(2).collect()
    fallback_dates = [row["pub_date"] for row in latest_dates]
    test_sample = gold_deduped.filter(F.col("pub_date").isin(fallback_dates)).limit(100).cache()
    print(f"\n🧪 Fallback 샘플링: {fallback_dates} 데이터 {test_sample.count()}건")

# 날짜 분포 확인
print("\n📅 샘플 날짜 분포:")
test_sample.groupBy("pub_date").count().orderBy("pub_date").show()

# 3) 키워드 모멘텀 통계 계산 (Window 함수)
print("🔄 키워드 모멘텀 계산 중...")
top10_kw, article_mom, article_surge = compute_keyword_stats(test_sample)
print("✅ 키워드 모멘텀 계산 완료")

# 4) 테스트 적재 (is_surge 포함)
success = 0
for name, func, args in [
    ("dim_news_display",           load_display_table, (test_sample, article_surge)),
    ("agg_market_sentiment_daily", load_agg_table,     (test_sample, top10_kw)),
    ("fact_feature_vector_store",  load_vector_table,  (test_sample, article_mom))
]:
    try:
        func(*args)
        success += 1
    except Exception as e:
        print(f"❌ {name}: {str(e)[:500]}")

print(f"\n🎉 테스트 결과: {success}/3 테이블 성공")
if success == 3:
    print("➡️ 테스트 성공! 아래 전체 적재 셀을 실행하세요.")

# COMMAND ----------

# DBTITLE 1,전체 데이터 Gold 적재
# ============================================================
# 전체 데이터 적재
# ============================================================

# 1) 테스트 데이터 정리
truncate_gold_tables()

# 2) 전체 데이터 중복 제거
total = gold_df.count()
gold_deduped = gold_df.dropDuplicates(["news_id"])
deduped_count = gold_deduped.count()
print(f"\n📦 전체 적재: {total}건 → 중복 제거 후 {deduped_count}건")

# 3) 키워드 모멘텀 통계 계산 (Window 함수)
print("🔄 키워드 모멘텀 계산 중...")
top10_kw, article_mom, article_surge = compute_keyword_stats(gold_deduped)
print("✅ 키워드 모멘텀 계산 완료")

# 4) 전체 적재 실행
success = 0
for name, func, args in [
    ("dim_news_display",           load_display_table, (gold_deduped, article_surge)),
    ("agg_market_sentiment_daily", load_agg_table,     (gold_deduped, top10_kw)),
    ("fact_feature_vector_store",  load_vector_table,  (gold_deduped, article_mom))
]:
    try:
        func(*args)
        success += 1
    except Exception as e:
        print(f"❌ {name}: {str(e)[:500]}")

print(f"\n🎉 전체 적재 결과: {success}/3 테이블 성공 ({deduped_count}건)")