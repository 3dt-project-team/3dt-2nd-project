import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

load_dotenv()

_instance = None


def _is_databricks() -> bool:
    """현재 실행 환경이 Azure Databricks인지 감지합니다."""
    return "DATABRICKS_RUNTIME_VERSION" in os.environ


def get_vault_manager():
    global _instance
    if _instance is None:
        _instance = KeyVaultManager()
    return _instance


class KeyVaultManager:
    def __init__(self):
        self.vault_url = os.getenv("KEY_VAULT_URL")
        self.client = None
        self.credential = None

        if self.vault_url:
            try:
                # 로컬: az login, 클라우드: Managed Identity 자동 사용
                self.credential = DefaultAzureCredential()
                self.client = SecretClient(vault_url=self.vault_url, credential=self.credential)
                print(f"[OK] Key Vault 클라이언트 연결 완료: {self.vault_url}")
            except Exception as e:
                print(f"[WARN] Key Vault 연결 실패 - 환경 변수 fallback 전환: {e}")
        else:
            print("[INFO] KEY_VAULT_URL 미설정 - 환경 변수에서 시크릿을 로드합니다")

    def get_secret(self, secret_name: str) -> str | None:
        """Key Vault에서 시크릿을 가져옵니다.

        조회 실패 시 환경 변수(대문자 + 하이픈→언더스코어)에서 fallback합니다.
        예: 'azure-openai-key' → AZURE_OPENAI_KEY
        """
        if self.client:
            try:
                return self.client.get_secret(secret_name).value
            except ResourceNotFoundError:
                print(f"[WARN] Key Vault에 '{secret_name}' 시크릿이 존재하지 않습니다.")
            except HttpResponseError as e:
                print(f"[WARN] Key Vault 접근 오류 (권한 문제일 수 있습니다): {e}")

        env_key = secret_name.upper().replace("-", "_")
        return os.getenv(env_key)

    def list_secret_names(self) -> list[str]:
        """Key Vault에 저장된 모든 시크릿 이름 목록을 반환합니다."""
        if not self.client:
            return []
        try:
            return [p.name for p in self.client.list_properties_of_secrets() if p.name is not None]
        except HttpResponseError as e:
            print(f"[WARN] 시크릿 목록 조회 오류: {e}")
            return []

    def get_all_secrets(self) -> dict[str, str]:
        """Key Vault의 모든 시크릿을 {이름: 값} 딕셔너리로 반환합니다. 결과는 캐시됩니다."""
        if hasattr(self, "_cache"):
            return self._cache

        secrets: dict[str, str] = {}
        failed: list[str] = []

        for name in self.list_secret_names():
            value = self.get_secret(name)
            if value is not None:
                print(f"  [OK] [{name}] 로드 성공")
                secrets[name] = value
            else:
                print(f"  [FAIL] [{name}] 로드 실패")
                failed.append(name)

        print(f"\n[결과] 성공 {len(secrets)}개 / 실패 {len(failed)}개")
        if failed:
            print(f"   실패 목록: {failed}")

        self._cache = secrets
        return secrets

    def get_storage_client(self, account_name: str | None = None):
        """ADLS Gen2 DataLakeServiceClient를 반환합니다.

        - 일반 환경(ADF, ML Studio 등): DefaultAzureCredential로 인증된
          DataLakeServiceClient를 반환합니다.
        - Databricks 환경: Service Principal 자격 증명으로 현재 SparkSession에
          OAuth conf를 설정하고 None을 반환합니다.
          설정 후 abfss://container@account.dfs.core.windows.net/path 형식으로 접근하세요.

        Key Vault 시크릿:
          adls-account-name  : ADLS 스토리지 계정 이름
          adls-client-id     : (Databricks 전용) Service Principal 클라이언트 ID
          adls-client-secret : (Databricks 전용) Service Principal 클라이언트 시크릿
          adls-tenant-id     : (Databricks 전용) Azure AD 테넌트 ID
        """
        acct = account_name or self.get_secret("adls-account-name") or os.getenv("ADLS_ACCOUNT_NAME")
        if not acct:
            raise ValueError(
                "ADLS 계정 이름을 확인할 수 없습니다. "
                "KV 시크릿 'adls-account-name' 또는 환경 변수 ADLS_ACCOUNT_NAME을 설정하세요."
            )

        if _is_databricks():
            return self._configure_spark_for_adls(acct)

        from azure.storage.filedatalake import DataLakeServiceClient

        if self.credential is None:
            self.credential = DefaultAzureCredential()

        return DataLakeServiceClient(
            account_url=f"https://{acct}.dfs.core.windows.net",
            credential=self.credential,
        )

    def _configure_spark_for_adls(self, account_name: str) -> None:
        """Databricks 환경에서 활성 SparkSession에 Service Principal OAuth 설정을 적용합니다."""
        try:
            from pyspark.sql import SparkSession
            spark = SparkSession.getActiveSession()
            if spark is None:
                raise RuntimeError("활성화된 Spark 세션이 없습니다.")
        except ImportError as exc:
            raise RuntimeError(
                "PySpark를 찾을 수 없습니다. Databricks 환경인지 확인하세요."
            ) from exc

        client_id = self.get_secret("adls-client-id")
        client_secret = self.get_secret("adls-client-secret")
        tenant_id = self.get_secret("adls-tenant-id")

        if not all([client_id, client_secret, tenant_id]):
            raise ValueError(
                "Databricks Spark 설정에 필요한 시크릿이 누락되었습니다. "
                "Key Vault에 adls-client-id / adls-client-secret / adls-tenant-id를 등록하세요."
            )

        base = "fs.azure.account"
        endpoint = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"

        spark.conf.set(f"{base}.auth.type.{account_name}.dfs.core.windows.net", "OAuth")
        spark.conf.set(
            f"{base}.oauth.provider.type.{account_name}.dfs.core.windows.net",
            "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
        )
        spark.conf.set(f"{base}.oauth2.client.id.{account_name}.dfs.core.windows.net", client_id)
        spark.conf.set(
            f"{base}.oauth2.client.secret.{account_name}.dfs.core.windows.net", client_secret
        )
        spark.conf.set(
            f"{base}.oauth2.client.endpoint.{account_name}.dfs.core.windows.net", endpoint
        )
        print(f"[OK] Spark conf ADLS Gen2 OAuth 설정 완료: {account_name}")
        return None

    def get_pg_connection(self, engine: str = "psycopg"):
        """Azure Database for PostgreSQL 연결 객체를 반환합니다.

        Key Vault 시크릿 'pg-connection-string' 에서 연결 문자열을 읽어 인증합니다.

        Args:
            engine: "psycopg" (기본값) | "sqlalchemy"
              - "psycopg"   → psycopg.Connection. 컨텍스트 매니저(with 구문)로 사용하세요.
              - "sqlalchemy" → sqlalchemy.Engine. pd.read_sql / Session과 함께 사용하세요.

        Key Vault 시크릿:
          pg-connection-string : PostgreSQL 연결 문자열 (libpq 형식)

        연결 문자열 예시:
          "host={server}.postgres.database.azure.com dbname={db}
           user={user} password={pass} sslmode=require"
        """
        connection_string = self.get_secret("pg-connection-string")
        if not connection_string:
            raise ValueError(
                "PostgreSQL 연결 문자열을 찾을 수 없습니다. "
                "KV 시크릿 'pg-connection-string' 또는 환경 변수 PG_CONNECTION_STRING을 설정하세요."
            )

        if engine == "sqlalchemy":
            from sqlalchemy import create_engine

            return create_engine(
                f"postgresql+psycopg:///?{connection_string}",
                pool_pre_ping=True,
            )

        import psycopg

        return psycopg.connect(connection_string)


# 모듈 레벨 싱글톤 — 다른 모듈에서 바로 import해서 사용
vault = get_vault_manager()


def main():
    print("데이터 파이프라인 설정을 초기화합니다...")
    vault.get_all_secrets()


if __name__ == "__main__":
    main()