# Databricks notebook source
# Databricks notebook source
# COMMAND ----------
import os
import sys

import pandas as pd

# 1. 환경 설정 및 마스터 키(vault_manager) 불러오기
# 리포지토리 경로 설정 (본인의 환경에 맞게 확인 필요)
REPO_PATH = "/Workspace/Repos/3dt004@msacademy.msai.kr/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

# Azure Key Vault 진짜 주소 설정
os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"

from utils.vault_manager import get_vault_manager  # noqa: E402

# 2. 보안 인증 수행 (여기가 핵심!)
# 아까처럼 spark.conf.set(...)에 직접 키를 적지 않아도,
# 아래 두 줄이 뒤에서 안전하게 열쇠를 찾아 연결해줍니다.
vault = get_vault_manager()
vault.get_storage_client()

# 3. 데이터 로드: ADLS의 curated 폴더 경로 설정
base_path = "abfss://curated@3dtteam1adls.dfs.core.windows.net"

# 반도체(Silver) 데이터와 금융(Silver) 데이터를 읽어옵니다.
print("데이터를 불러오는 중...")
df_semi = spark.read.parquet(f"{base_path}/silver_semiconductor.parquet")  # noqa: F821
df_fin = spark.read.parquet(f"{base_path}/silver_kfinance.parquet")  # noqa: F821

# 4. 분석을 위해 Pandas DataFrame으로 변환
semi_pdf = df_semi.toPandas()
fin_pdf = df_fin.toPandas()

print(f"로드 완료! 반도체 데이터: {len(semi_pdf)}행, 금융 데이터: {len(fin_pdf)}행")

# COMMAND ----------

print("반도체 컬럼명:", semi_pdf.columns)
print("금융 컬럼명:", fin_pdf.columns)

# COMMAND ----------


# 1. 날짜 컬럼을 판다스 데이트타임 형식으로 변환
semi_pdf["date"] = pd.to_datetime(semi_pdf["date"])
fin_pdf["date"] = pd.to_datetime(fin_pdf["date"])

# 2. 분석에 사용할 수치 데이터들을 '숫자형(float)'으로 변환 (중요!)
# errors='coerce' 옵션은 숫자가 아닌 이상한 값이 있으면 에러 대신 NaN(빈값)으로 바꿔줍니다.
semi_pdf["expDlr"] = pd.to_numeric(semi_pdf["expDlr"], errors="coerce")
fin_pdf["close_price"] = pd.to_numeric(fin_pdf["close_price"], errors="coerce")

# 3. 금융 데이터(일별)를 월별 평균으로 집계
# numeric_only=True를 넣어주면 숫자 데이터만 계산하라고 명시하게 되어 경고 메시지도 사라집니다.
fin_monthly = fin_pdf.set_index("date").resample("MS").mean(numeric_only=True).reset_index()

# 4. 이제 'date' 컬럼을 기준으로 두 데이터를 합칩니다.
merged_df = semi_pdf.merge(fin_monthly, on="date", how="inner")

# 5. 상관분석 수행
# 결측치(NaN)가 있으면 계산이 안 될 수 있으므로 dropna()를 추가하여 안전하게 처리합니다.
final_data = merged_df[["expDlr", "close_price"]].dropna()
correlation = final_data["expDlr"].corr(final_data["close_price"])

print(f"데이터 결합 성공! 분석 대상 행 개수: {len(final_data)}")
print(f"반도체 수출액(expDlr)과 주가(close_price)의 상관계수: {correlation:.4f}")

# 결과 확인
display(merged_df.head())  # noqa: F821

# COMMAND ----------

# 3. 충격 분석 (Impulse Response Function)
import matplotlib.pyplot as plt  # noqa: E402
from statsmodels.tsa.api import VAR  # noqa: E402

# 분석할 컬럼 선택 (반도체 수출액과 주가)
# 날짜 순으로 정렬되어 있어야 정확한 분석이 가능합니다.
analysis_data = merged_df.sort_values("date")[["expDlr", "close_price"]].dropna()

# VAR 모델 학습
model = VAR(analysis_data)
results = model.fit(maxlags=2)  # 데이터 양에 따라 시차(Lag)를 조절 (보통 1~2)

# 충격 반응 함수(IRF) 산출
irf = results.irf(10)  # 향후 10기(10개월) 동안의 반응을 봅니다.

# 그래프 그리기
plt.figure(figsize=(10, 8))
irf.plot(orth=True)
plt.show()

# COMMAND ----------

# [해석 셀]
# 그래프에서 'Combined' 형태의 그림이 나올 겁니다.
# 우리가 주목해야 할 것은 [expDlr -> close_price] 그래프입니다.
# 만약 선이 위(0보다 위)로 솟구쳤다가 서서히 내려온다면:
# "반도체 수출이 늘어나는 '충격'이 발생하면, 주가도 즉각 상승하며 그 영향이 몇 달간 지속된다"고 해석합니다.  # noqa: E501

# COMMAND ----------

# MAGIC %sh
# MAGIC uv pip install mlflow>=3.0 --upgrade

# COMMAND ----------

import os  # noqa: E402
import sys  # noqa: E402
import warnings  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)

REPO_PATH = "/Workspace/Repos/3dt004@msacademy.msai.kr/3dt-2nd-project"
# REPO_PATH = "/Workspace/Repos/{your-email}/3dt-2nd-project"
sys.path.insert(0, f"{REPO_PATH}/src")

os.environ["KEY_VAULT_URL"] = "https://kv-3dt-team1.vault.azure.net/"
# os.environ["KEY_VAULT_URL"] = "https://{your-keyvault-name}.vault.azure.net/"

from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()
vault.get_storage_client()  # Spark OAuth conf 자동 설정
account = vault.get_secret("adls-account-name")  # "3dtteam1adls"

# COMMAND ----------

import os  # noqa: E402

from openai import AzureOpenAI  # noqa: E402

OPENAI_DEPLOYMENT = "gpt-4.1-mini"
OPENAI_API_VERSION = "2025-03-01-preview"

_openai_endpoint = vault.get_secret("azure-openai-endpoint")
_openai_key = vault.get_secret("azure-openai-key")

openai_client = AzureOpenAI(
    azure_endpoint=_openai_endpoint,
    api_key=_openai_key,
    api_version=OPENAI_API_VERSION,
)
# 3. 정형 데이터 분석 결과 입력 (아까 구한 수치들)
# 실제 프로젝트에서는 변수를 자동으로 할당하게 하면 됩니다.
struct_results = {
    "correlation_coefficient": 0.62,  # 예시 상관계수
    "peak_lag_months": 2,  # IRF에서 확인한 정점 시차
    "impact_duration": 10,  # 충격이 지속되는 기간
    "target_variable": "삼성전자 주가",
    "feature_variable": "반도체 수출액(expDlr)",
}

# 4. AI에게 전달할 프롬프트 구성
prompt = f"""
당신은 전문 금융 데이터 아키텍트이자 투자 전략가입니다. 
아래의 '정형 데이터 분석 결과'를 바탕으로 비즈니스 인사이트 리포트를 작성하세요.

[분석 결과]
- 분석 대상: {struct_results["feature_variable"]}와 {struct_results["target_variable"]}의 관계
- 상관계수: {struct_results["correlation_coefficient"]}
- 선행 시차(Peak Lag): {struct_results["peak_lag_months"]}개월
- 영향 지속성: {struct_results["impact_duration"]}개월 이상

[요구사항]
1. 두 지표 간의 관계를 정의하세요.
2. 선행 지표로서의 가치를 평가하세요.
3. 향후 투자 또는 비즈니스 의사결정에 어떻게 활용할지 제안하세요.
4. 말투는 '전문적이고 신뢰감 있는 보고서체'로 작성하세요.
"""

# 5. AI 실행 (GPT-4.1-mini)
response = openai_client.chat.completions.create(
    model="gpt-4.1-mini",  # 배포명 사용
    messages=[
        {"role": "system", "content": "당신은 정형 데이터 해석 전문 AI입니다."},
        {"role": "user", "content": prompt},
    ],
    temperature=0.3,  # 보고서이므로 일관성 있게 낮은 온도로 설정
)

# 6. 결과 출력
print("### 정형 데이터 AI 해석 결과 ###")
print(response.choices[0].message.content)
