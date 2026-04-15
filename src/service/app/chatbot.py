from __future__ import annotations

from typing import Any

from .llm import LLMConfigurationError, generate_answer, generate_embedding
from .prompts import render_context_snapshot
from .retriever import build_retrieval_bundle
from .router import classify_query, extract_filters


def _build_fallback_answer(bundle, reason: str | None = None) -> str:
    header = "[임시 요약]\nAzure OpenAI 응답이 없어도 현재 검색 결과를 기준으로 요약합니다."
    if reason:
        header += f"\n사유: {reason}"
    return f"{header}\n\n{render_context_snapshot(bundle)}"


def build_chat_response(question: str) -> dict[str, Any]:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("질문이 비어 있습니다.")

    route = classify_query(cleaned_question)
    filters = extract_filters(cleaned_question)

    embedding = None
    embedding_error = None
    try:
        embedding = generate_embedding(cleaned_question)
    except Exception as exc:  # noqa: BLE001
        embedding_error = str(exc)

    bundle = build_retrieval_bundle(
        question=cleaned_question,
        route=route,
        filters=filters,
        question_embedding=embedding,
    )

    llm_error = None
    try:
        answer = generate_answer(bundle)
    except (LLMConfigurationError, RuntimeError, ValueError) as exc:
        llm_error = str(exc)
        answer = _build_fallback_answer(bundle, llm_error)
    except Exception as exc:  # noqa: BLE001
        llm_error = str(exc)
        answer = _build_fallback_answer(bundle, llm_error)

    return {
        "question": cleaned_question,
        "route": route.value,
        "filters": filters.to_dict(),
        "answer": answer,
        "bundle": bundle.to_dict(),
        "errors": {
            "embedding_error": embedding_error,
            "llm_error": llm_error,
        },
    }


if __name__ == "__main__":
    sample = build_chat_response("SK하이닉스 하락 리스크 근거 기사와 매크로 신호를 요약해줘")
    print(sample["answer"])
