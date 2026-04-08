"""pytest 공통 픽스처."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def set_env():
    """테스트 시 Key Vault 없이도 동작하도록 환경 변수 기본값 설정."""
    os.environ.setdefault("KEY_VAULT_URL", "")
