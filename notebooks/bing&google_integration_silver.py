# Databricks notebook source
# SENSE 프로젝트 — Databricks 전처리 노트북 (raw → curated)
# SENSE: Semiconductor Economic News & Sentiment Engine
#
# 목적: ADLS Gen2 raw/ 에서 뉴스 원문 데이터를 읽어 텍스트 클렌징 후 통합
# 실행: 셀 순서대로 진행

# COMMAND ----------

# MAGIC %md
# MAGIC ## 환경설정
# MAGIC

# COMMAND ----------

# MAGIC %sh
# MAGIC # 필수 Azure SDK 패키지 설치
# MAGIC uv pip install azure-identity azure-keyvault-secrets azure-storage-file-datalake

# COMMAND ----------

import sys
import os

# 1. 경로 설정 (사용자님 계정으로 변경)
os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"
repo_path = "/Workspace/Repos/3dt020@msacademy.msai.kr/3dt-2nd-project/src"

if repo_path not in sys.path:
    sys.path.insert(0, repo_path)

# 2. Vault 매니저 초기화 및 시크릿 가져오기
import utils.vault_manager
utils.vault_manager._instance = None
from utils.vault_manager import get_vault_manager

vault = get_vault_manager()

# 3. 변수에 시크릿 저장
client_id = vault.get_secret("adls-client-id")
client_secret = vault.get_secret("adls-client-secret")
tenant_id = vault.get_secret("adls-tenant-id")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 데이터 불러오기
# MAGIC

# COMMAND ----------

# DBTITLE 1,데이터 읽기 - Bing & Google 뉴스
# 1. 데이터 읽기

# Spark에 ADLS Gen2 OAuth 인증 설정 (Cell 4에서 가져온 서비스 프린시펄 사용)
storage_account = "3dtteam1adls"
spark.conf.set(f"fs.azure.account.auth.type.{storage_account}.dfs.core.windows.net", "OAuth")
spark.conf.set(f"fs.azure.account.oauth.provider.type.{storage_account}.dfs.core.windows.net",
               "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider")
spark.conf.set(f"fs.azure.account.oauth2.client.id.{storage_account}.dfs.core.windows.net", client_id)
spark.conf.set(f"fs.azure.account.oauth2.client.secret.{storage_account}.dfs.core.windows.net", client_secret)
spark.conf.set(f"fs.azure.account.oauth2.client.endpoint.{storage_account}.dfs.core.windows.net",
               f"https://login.microsoftonline.com/{tenant_id}/oauth2/token")

# Bing 뉴스: 하위 날짜별 폴더를 와일드카드로 모두 포함
bing_df = spark.read.parquet(
    "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/bing/*/*.parquet"
)

# Google 뉴스: SK_Hynix_news.parquet, Samsung_Electronics_news.parquet
google_df = spark.read.parquet(
    "abfss://raw@3dtteam1adls.dfs.core.windows.net/news/google/*.parquet"
)

print("=== Bing News ===")
bing_df.printSchema()
print(f"Bing rows: {bing_df.count()}")

print("\n=== Google News ===")
google_df.printSchema()
print(f"Google rows: {google_df.count()}")

# COMMAND ----------

# DBTITLE 1,데이터 미리보기 - Bing & Google 각 5건
print("=== Bing News (5건) ===")
display(bing_df.limit(5))

print("\n=== Google News (5건) ===")
display(google_df.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 정규화

# COMMAND ----------

# DBTITLE 1,source 칼럼 대문자 정규화
from pyspark.sql.functions import upper

# source 칼럼 대문자 통일 (SK hynix / SK Hynix → SK HYNIX, Samsung → SAMSUNG)
bing_df = bing_df.withColumn("source", upper("source"))
google_df = google_df.withColumn("source", upper("source"))

# 변환 결과 확인
print("=== Bing source 값 ===")
bing_df.select("source").distinct().show()

print("=== Google source 값 ===")
google_df.select("source").distinct().show()

# COMMAND ----------

# DBTITLE 1,Bing+Google 통합 및 URL 중복 제거
from pyspark.sql.functions import lit

# 출처 태깅 (news_source 칼럼 추가)
bing_tagged = bing_df.withColumn("news_source", lit("bing"))
google_tagged = google_df.withColumn("news_source", lit("google"))

# Bing + Google 통합
merged_df = bing_tagged.unionByName(google_tagged)
print(f"통합 전: Bing {bing_df.count()}건 + Google {google_df.count()}건 = {merged_df.count()}건")

# URL 기준 중복 제거
deduped_df = merged_df.dropDuplicates(["url"])
print(f"중복 제거 후: {deduped_df.count()}건 (제거된 중복: {merged_df.count() - deduped_df.count()}건)")

# COMMAND ----------

# DBTITLE 1,통합 데이터 칼럼 목록 확인
from pyspark.sql.functions import col, to_date

# 칼럼명 변경 + 타입 변환 + 순서 정리
silver_df = deduped_df.select(
    col("url"),
    col("newsId").alias("news_id"),
    col("source").alias("stock_keyword"),
    col("news_source"),
    to_date(col("pubDate")).alias("pub_date"),
    col("fetchedAt").alias("published_time"),
    col("press"),
    col("headline"),
    col("body"),
    col("description")
)

silver_df.printSchema()
print(f"\n총 {silver_df.count()}건")
display(silver_df.limit(5))

# COMMAND ----------

# DBTITLE 1,silver 컨테이너로 parquet 저장
from pyspark.sql.functions import current_timestamp

# silver 저장 경로
silver_path = "abfss://silver@3dtteam1adls.dfs.core.windows.net/news/google_bing/preprocessed_google&bing/"

# 자동화 고려: overwrite 모드로 매번 재실행 시 최신 데이터로 교체
# coalesce(1): 소규모 데이터(~3K건)이므로 단일 파일로 출력
silver_df \
    .coalesce(1) \
    .write \
    .mode("overwrite") \
    .parquet(silver_path)

print(f"[OK] silver 저장 완료: {silver_path}")
print(f"저장 건수: {silver_df.count()}건")

# 저장 결과 확인
for f in dbutils.fs.ls(silver_path):
    print(f"  {f.name}  ({f.size:,} bytes)")