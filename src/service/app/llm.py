from __future__ import annotations

from functools import lru_cache
from typing import Any

try:
    from openai import AzureOpenAI
except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
    AzureOpenAI = Any  # type: ignore[assignment]
    OPENAI_IMPORT_ERROR = exc
else:  # pragma: no cover - environment-dependent
    OPENAI_IMPORT_ERROR = None

from .config import get_settings
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import RetrievalBundle


class LLMConfigurationError(RuntimeError):
    """Raised when Azure OpenAI configuration is incomplete."""


@lru_cache(maxsize=1)
def get_client() -> AzureOpenAI:
    settings = get_settings()
    settings.require_llm()
    if OPENAI_IMPORT_ERROR is not None:
        raise LLMConfigurationError(
            "openai 패키지가 설치되어 있지 않습니다. requirements 설치 후 다시 시도해 주세요."
        ) from OPENAI_IMPORT_ERROR
    return AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
    )


def generate_embedding(text: str) -> list[float]:
    settings = get_settings()
    if not settings.azure_openai_embedding_deployment:
        raise LLMConfigurationError("임베딩 배포명이 비어 있습니다.")

    response = get_client().embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=text,
    )
    return response.data[0].embedding


def generate_answer(bundle: RetrievalBundle) -> str:
    settings = get_settings()
    response = get_client().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(bundle)},
        ],
        temperature=settings.answer_temperature,
    )

    message = response.choices[0].message.content
    return (message or "").strip()
