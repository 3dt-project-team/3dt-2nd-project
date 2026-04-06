"""SENSE 프로젝트 — Azure ML Studio 학습 스크립트.

SENSE: Semiconductor Economic News & Sentiment Engine
반도체 경제 뉴스 텍스트 기반 감성 분석 모델 학습.

실행 방법 (로컬 또는 ML Studio Compute Instance):
    uv run python src/models/train.py

ML Studio CommandJob으로 실행 시:
    aml_train_example.py 의 job 정의를 사용하세요.
"""

import subprocess
import sys

import mlflow

# ── 경로 등록 (ML Studio Compute Instance 또는 로컬) ──────────────────────────
sys.path.insert(0, "src")

from utils.vault_manager import get_vault_manager  # noqa: E402

vault = get_vault_manager()


def get_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


def load_data():
    """ADLS Gen2 feature/ 컨테이너에서 학습 데이터 로드.

    TODO: 실제 데이터 경로로 교체
        account = vault.get_secret("adls-account-name")
        df = pd.read_parquet(f"abfs://feature@{account}.dfs.core.windows.net/sense/train.parquet")
    """
    raise NotImplementedError("데이터 로드 로직을 구현하세요.")


def train(df):
    """모델 학습 로직.

    TODO: 실제 모델(HuggingFace, sklearn 등)로 교체
    """
    raise NotImplementedError("학습 로직을 구현하세요.")


def main():
    mlflow.start_run()
    mlflow.set_tag("project", "SENSE")
    mlflow.set_tag("git_commit", get_git_commit())

    # 하이퍼파라미터 (추후 MLflow 파라미터로 관리)
    params = {
        "model_name": "klue/roberta-base",
        "max_length": 128,
        "batch_size": 32,
        "epochs": 3,
        "learning_rate": 2e-5,
    }
    mlflow.log_params(params)

    df = load_data()
    model = train(df)  # noqa: F841

    # TODO: mlflow.log_metric("accuracy", acc)
    # TODO: mlflow.sklearn.log_model(model, "sense-model")

    mlflow.end_run()


if __name__ == "__main__":
    main()
