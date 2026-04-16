from __future__ import annotations

from typing import Any, Mapping

from .chatbot import build_chat_response


class ChatRequestError(ValueError):
    """Raised when the inbound chat payload is invalid."""


def parse_chat_request(payload: Mapping[str, Any] | None) -> tuple[str, bool]:
    if payload is None:
        raise ChatRequestError("요청 본문이 비어 있습니다.")

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ChatRequestError("question 필드는 비어 있지 않은 문자열이어야 합니다.")

    include_debug = bool(payload.get("include_debug", False))
    return question.strip(), include_debug


def _compact_sources(news_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for doc in news_docs:
        sources.append(
            {
                "news_id": doc.get("news_id"),
                "title": doc.get("display_title"),
                "summary": doc.get("core_summary"),
                "press": doc.get("press"),
                "pub_date": doc.get("pub_date"),
                "url": doc.get("original_url"),
                "sentiment_class": doc.get("sentiment_class"),
                "category": doc.get("category"),
                "stock_keyword": doc.get("stock_keyword"),
                "hybrid_score": doc.get("hybrid_score"),
            }
        )
    return sources


def _compact_snapshots(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "forecast": bundle.get("forecast_rows", [])[:1],
        "macro": bundle.get("macro_snapshot", [])[:1],
        "ml_feature": bundle.get("ml_feature_snapshot", [])[:1],
        "quant": bundle.get("quant_signal_rows", [])[:1],
        "sentiment": bundle.get("sentiment_snapshot", [])[:1],
    }


def create_chat_http_response(question: str, include_debug: bool = False) -> dict[str, Any]:
    result = build_chat_response(question)
    bundle = result["bundle"]

    response = {
        "status": "ok",
        "question": result["question"],
        "route": result["route"],
        "answer": result["answer"],
        "filters": result["filters"],
        "sources": _compact_sources(bundle.get("news_docs", [])),
        "snapshots": _compact_snapshots(bundle),
    }

    if include_debug:
        response["debug"] = {
            "bundle": bundle,
            "errors": result["errors"],
        }

    return response


def handle_chat_request_payload(payload: Mapping[str, Any] | None) -> tuple[dict[str, Any], int]:
    try:
        question, include_debug = parse_chat_request(payload)
    except ChatRequestError as exc:
        return {
            "status": "error",
            "error": str(exc),
        }, 400

    try:
        return create_chat_http_response(question, include_debug=include_debug), 200
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error": str(exc),
        }, 500
