from __future__ import annotations

import os
import shutil
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

try:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some environments
    DefaultAzureCredential = None  # type: ignore[assignment]
    SecretClient = None  # type: ignore[assignment]

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parents[2]
WORKSPACE_AZURE_CONFIG_DIR = PROJECT_ROOT / ".azure-config"
USER_AZURE_CONFIG_DIR = Path.home() / ".azure"


def _normalize_proxy_env() -> None:
    broken_proxy_markers = ("127.0.0.1:9", "localhost:9")
    proxy_keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "GIT_HTTP_PROXY",
        "GIT_HTTPS_PROXY",
    )

    for key in proxy_keys:
        value = os.getenv(key, "")
        if value and any(marker in value for marker in broken_proxy_markers):
            os.environ.pop(key, None)


def _ensure_workspace_azure_cli_cache() -> None:
    WORKSPACE_AZURE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("AZURE_CONFIG_DIR", str(WORKSPACE_AZURE_CONFIG_DIR))

    if not USER_AZURE_CONFIG_DIR.exists():
        return

    for name in (
        "azureProfile.json",
        "msal_token_cache.bin",
        "msal_http_cache.bin",
        "config",
        "clouds.config",
    ):
        src = USER_AZURE_CONFIG_DIR / name
        dst = WORKSPACE_AZURE_CONFIG_DIR / name
        if src.exists() and not dst.exists():
            with suppress(Exception):
                shutil.copy2(src, dst)


_normalize_proxy_env()
_ensure_workspace_azure_cli_cache()

load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(APP_DIR / ".env", override=True)


@dataclass(frozen=True)
class Settings:
    key_vault_url: str
    db_connection_string: str
    db_host: str
    db_port: str
    db_name: str
    db_user: str
    db_password: str
    db_sslmode: str
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    default_stock_keyword: str
    default_stock_code: str
    default_ticker: str
    default_news_limit: int
    default_history_days: int
    rerank_pool_multiplier: int
    answer_temperature: float
    default_horizon_day: int

    @property
    def is_database_configured(self) -> bool:
        return bool(self.db_connection_string) or all(
            [self.db_host, self.db_name, self.db_user, self.db_password]
        )

    @property
    def is_llm_configured(self) -> bool:
        return all(
            [
                self.azure_openai_api_key,
                self.azure_openai_endpoint,
                self.azure_openai_chat_deployment,
                self.azure_openai_embedding_deployment,
            ]
        )

    def require_database(self) -> None:
        if self.is_database_configured:
            return
        raise RuntimeError(
            "DB 연결 정보가 충분하지 않습니다. "
            "DB_HOST, DB_NAME, DB_USER, DB_PASSWORD 또는 PG_CONNECTION_STRING"
            "(또는 Key Vault 'pg-connection-string')을 확인해 주세요."
        )

    def require_llm(self) -> None:
        if self.is_llm_configured:
            return
        raise RuntimeError(
            "Azure OpenAI 설정이 충분하지 않습니다. "
            "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_CHAT_DEPLOYMENT, AZURE_OPENAI_EMBEDDING_DEPLOYMENT를 확인해 주세요. "
            "Key Vault를 사용하는 경우 KEY_VAULT_URL 및 관련 시크릿도 확인해 주세요."
        )


@lru_cache(maxsize=1)
def _get_secret_client(vault_url: str):
    if not vault_url or DefaultAzureCredential is None or SecretClient is None:
        return None

    with suppress(Exception):
        credential = DefaultAzureCredential()
        return SecretClient(vault_url=vault_url, credential=credential)
    return None


def _get_kv_secret(vault_url: str, secret_name: str) -> str:
    if not vault_url or not secret_name:
        return ""

    client = _get_secret_client(vault_url)
    if client is None:
        return ""

    with suppress(Exception):
        value = client.get_secret(secret_name).value
        return value or ""
    return ""


def _env_or_kv(
    env_key: str,
    vault_url: str,
    secret_name: str,
    default: str = "",
) -> str:
    env_value = os.getenv(env_key, "")
    if env_value:
        return env_value

    kv_value = _get_kv_secret(vault_url, secret_name)
    if kv_value:
        return kv_value

    return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    key_vault_url = os.getenv("KEY_VAULT_URL", "")

    pg_connection_secret_name = os.getenv(
        "SENSE_KV_PG_CONNECTION_SECRET_NAME", "pg-connection-string"
    )
    db_host_secret_name = os.getenv("SENSE_KV_DB_HOST_SECRET_NAME", "db-host")
    db_port_secret_name = os.getenv("SENSE_KV_DB_PORT_SECRET_NAME", "db-port")
    db_name_secret_name = os.getenv("SENSE_KV_DB_NAME_SECRET_NAME", "db-name")
    db_user_secret_name = os.getenv("SENSE_KV_DB_USER_SECRET_NAME", "db-user")
    db_password_secret_name = os.getenv("SENSE_KV_DB_PASSWORD_SECRET_NAME", "db-password")
    db_sslmode_secret_name = os.getenv("SENSE_KV_DB_SSLMODE_SECRET_NAME", "db-sslmode")

    aoai_api_key_secret_name = os.getenv("SENSE_KV_AOAI_API_KEY_SECRET_NAME", "azure-openai-key")
    aoai_endpoint_secret_name = os.getenv(
        "SENSE_KV_AOAI_ENDPOINT_SECRET_NAME", "azure-openai-endpoint"
    )
    aoai_api_version_secret_name = os.getenv(
        "SENSE_KV_AOAI_API_VERSION_SECRET_NAME", "azure-openai-api-version"
    )
    aoai_chat_deployment_secret_name = os.getenv(
        "SENSE_KV_AOAI_CHAT_DEPLOYMENT_SECRET_NAME", "azure-openai-chat-deployment"
    )
    aoai_embedding_deployment_secret_name = os.getenv(
        "SENSE_KV_AOAI_EMBEDDING_DEPLOYMENT_SECRET_NAME",
        "azure-openai-embedding-deployment",
    )

    return Settings(
        key_vault_url=key_vault_url,
        db_connection_string=_env_or_kv(
            "PG_CONNECTION_STRING",
            key_vault_url,
            pg_connection_secret_name,
            "",
        ),
        db_host=_env_or_kv("DB_HOST", key_vault_url, db_host_secret_name, ""),
        db_port=_env_or_kv("DB_PORT", key_vault_url, db_port_secret_name, "5432"),
        db_name=_env_or_kv("DB_NAME", key_vault_url, db_name_secret_name, ""),
        db_user=_env_or_kv("DB_USER", key_vault_url, db_user_secret_name, ""),
        db_password=_env_or_kv("DB_PASSWORD", key_vault_url, db_password_secret_name, ""),
        db_sslmode=_env_or_kv("DB_SSLMODE", key_vault_url, db_sslmode_secret_name, "require"),
        azure_openai_api_key=_env_or_kv(
            "AZURE_OPENAI_API_KEY", key_vault_url, aoai_api_key_secret_name, ""
        ),
        azure_openai_endpoint=_env_or_kv(
            "AZURE_OPENAI_ENDPOINT", key_vault_url, aoai_endpoint_secret_name, ""
        ),
        azure_openai_api_version=_env_or_kv(
            "AZURE_OPENAI_API_VERSION",
            key_vault_url,
            aoai_api_version_secret_name,
            "2025-03-01-preview",
        ),
        azure_openai_chat_deployment=_env_or_kv(
            "AZURE_OPENAI_CHAT_DEPLOYMENT",
            key_vault_url,
            aoai_chat_deployment_secret_name,
            "gpt-4.1-mini",
        ),
        azure_openai_embedding_deployment=_env_or_kv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            key_vault_url,
            aoai_embedding_deployment_secret_name,
            "text-embedding-3-small",
        ),
        default_stock_keyword=os.getenv("SENSE_DEFAULT_STOCK_KEYWORD", "SK HYNIX"),
        default_stock_code=os.getenv("SENSE_DEFAULT_STOCK_CODE", "SK HYNIX"),
        default_ticker=os.getenv("SENSE_DEFAULT_TICKER", "000660.KS"),
        default_news_limit=int(os.getenv("SENSE_DEFAULT_NEWS_LIMIT", "6")),
        default_history_days=int(os.getenv("SENSE_DEFAULT_HISTORY_DAYS", "7")),
        rerank_pool_multiplier=int(os.getenv("SENSE_RERANK_POOL_MULTIPLIER", "4")),
        answer_temperature=float(os.getenv("SENSE_ANSWER_TEMPERATURE", "0.2")),
        default_horizon_day=int(os.getenv("SENSE_DEFAULT_HORIZON_DAY", "5")),
    )
