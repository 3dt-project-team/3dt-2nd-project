"""vault_manager 단위 테스트."""

import os
from unittest.mock import MagicMock, patch

import pytest

from utils.vault_manager import KeyVaultManager


def test_vault_manager_no_url():
    """KEY_VAULT_URL 미설정 시 환경 변수 fallback 동작 확인."""
    os.environ["KEY_VAULT_URL"] = ""
    vault = KeyVaultManager()
    assert vault.client is None


def test_get_secret_env_fallback():
    """Key Vault 없을 때 환경 변수에서 시크릿 fallback."""
    os.environ["KEY_VAULT_URL"] = ""
    os.environ["TEST_SECRET_VALUE"] = "hello"
    vault = KeyVaultManager()
    result = vault.get_secret("test-secret-value")
    assert result == "hello"


# ---------------------------------------------------------------------------
# get_pg_connection() 테스트
# ---------------------------------------------------------------------------

URL_WITH_DRIVER = "postgresql+psycopg://user:pass@host:5432/db?sslmode=require"
URL_PLAIN = "postgresql://user:pass@host:5432/db?sslmode=require"
LIBPQ = "host=host port=5432 dbname=db user=user password=pass sslmode=require"


def _make_vault(pg_conn_str: str) -> KeyVaultManager:
    """Key Vault 없이 환경 변수에서 pg-connection-string 을 읽는 Vault 인스턴스."""
    os.environ["KEY_VAULT_URL"] = ""
    os.environ["PG_CONNECTION_STRING"] = pg_conn_str
    return KeyVaultManager()


@pytest.mark.parametrize(
    "conn_str",
    [URL_WITH_DRIVER, URL_PLAIN],
    ids=["url_with_driver", "url_plain"],
)
def test_get_pg_connection_sqlalchemy_url(conn_str):
    """URL 형식: creator 함수가 postgresql:// URI 로 psycopg.connect 를 호출해야 한다."""
    vault = _make_vault(conn_str)

    mock_raw_conn = MagicMock()

    with patch("psycopg.connect", return_value=mock_raw_conn) as mock_connect:
        engine = vault.get_pg_connection(engine="sqlalchemy")

        # creator 방식이므로 아직 connect 는 호출되지 않음 — engine 생성 시점 확인
        assert engine is not None

        # pool_pre_ping 으로 인해 creator 가 즉시 호출되지 않으므로
        # creator 함수를 직접 꺼내 실행하여 psycopg.connect 호출 여부를 검증
        creator = engine.pool._creator
        creator()

        called_uri = mock_connect.call_args[0][0]
        # "+psycopg" 드라이버 접두사가 제거된 URI 여야 한다
        assert called_uri.startswith("postgresql://"), (
            f"psycopg3 에 전달된 URI 에 드라이버 접두사가 남아 있음: {called_uri}"
        )
        assert "+psycopg" not in called_uri


def test_get_pg_connection_sqlalchemy_libpq():
    """libpq key=value 형식: creator 함수가 그대로 psycopg.connect 를 호출해야 한다."""
    vault = _make_vault(LIBPQ)

    mock_raw_conn = MagicMock()

    with patch("psycopg.connect", return_value=mock_raw_conn) as mock_connect:
        engine = vault.get_pg_connection(engine="sqlalchemy")
        assert engine is not None

        creator = engine.pool._creator
        creator()

        called_arg = mock_connect.call_args[0][0]
        assert called_arg == LIBPQ


@pytest.mark.parametrize(
    "conn_str",
    [URL_WITH_DRIVER, URL_PLAIN],
    ids=["url_with_driver", "url_plain"],
)
def test_get_pg_connection_psycopg_url(conn_str):
    """psycopg 모드 URL 형식: postgresql:// 로 변환 후 psycopg.connect 호출."""
    vault = _make_vault(conn_str)

    with patch("psycopg.connect") as mock_connect:
        vault.get_pg_connection(engine="psycopg")
        called_uri = mock_connect.call_args[0][0]
        assert called_uri.startswith("postgresql://")
        assert "+psycopg" not in called_uri


def test_get_pg_connection_psycopg_libpq():
    """psycopg 모드 libpq 형식: 그대로 psycopg.connect 에 전달."""
    vault = _make_vault(LIBPQ)

    with patch("psycopg.connect") as mock_connect:
        vault.get_pg_connection(engine="psycopg")
        called_arg = mock_connect.call_args[0][0]
        assert called_arg == LIBPQ


def test_get_pg_connection_missing_secret():
    """pg-connection-string 시크릿 없을 때 ValueError 발생."""
    os.environ["KEY_VAULT_URL"] = ""
    os.environ.pop("PG_CONNECTION_STRING", None)
    vault = KeyVaultManager()

    with pytest.raises(ValueError, match="pg-connection-string"):
        vault.get_pg_connection()
