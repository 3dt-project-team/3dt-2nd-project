"""Azure ML Studio v2 SDK — uv + vault_manager 연계 학습 잡 제출 예시.

로컬 또는 Compute Instance 터미널에서 실행합니다.

사전 요구 사항:
  # uv 설치 (최초 1회)
  curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
  # irm https://astral.sh/uv/install.ps1 | iex      # Windows PowerShell

  uv sync --extra ml   # azure-ai-ml, mlflow 설치
  az login             # 로컬 개발 시 인증
"""

from azure.ai.ml import MLClient, command
from azure.identity import DefaultAzureCredential

# ── 접속 정보 (환경 변수나 Key Vault에서 읽도록 수정 권장) ──────────────────
SUBSCRIPTION_ID = ""   # Azure 구독 ID
RESOURCE_GROUP  = ""   # 리소스 그룹 이름
WORKSPACE_NAME  = ""   # ML Studio 워크스페이스 이름
COMPUTE_NAME    = "cpu-cluster"  # 사전 생성된 컴퓨팅 클러스터 이름

ml_client = MLClient(
    credential=DefaultAzureCredential(),
    subscription_id=SUBSCRIPTION_ID,
    resource_group_name=RESOURCE_GROUP,
    workspace_name=WORKSPACE_NAME,
)

# ── 학습 잡 정의 ─────────────────────────────────────────────────────────────
# uv pip install 후 train.py 실행 — 환경 구성 시간을 pip 대비 대폭 단축
job = command(
    code="./src",
    command=(
        "uv pip install --system "
        "azure-identity azure-keyvault-secrets azure-storage-file-datalake "
        "python-dotenv sqlalchemy && "
        "python models/train.py"
    ),
    # ML Studio 기본 Python 환경 사용 (커스텀 Docker 이미지로 교체 가능)
    environment="azureml://registries/azureml/environments/python-sdk-v2/versions/1",
    compute=COMPUTE_NAME,
    # Key Vault URL 주입 — Managed Identity 로 자동 인증
    environment_variables={
        "KEY_VAULT_URL": "https://{your-keyvault-name}.vault.azure.net/",
    },
    display_name="3dt-train-with-uv",
)

returned_job = ml_client.jobs.create_or_update(job)
print(f"[OK] 학습 잡 제출 완료: {returned_job.studio_url}")

# ── train.py 내 MLflow + Git commit hash 태깅 예시 ──────────────────────────
# import mlflow, subprocess
# commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
# mlflow.set_tag("git_commit", commit)
# mlflow.log_params({"learning_rate": 0.01, "epochs": 10})
# mlflow.log_metric("accuracy", 0.95)
