"""vault_manager 단위 테스트."""

import os

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
