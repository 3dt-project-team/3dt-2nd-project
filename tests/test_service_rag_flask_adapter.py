from src.service.rag.flask_adapter import (
    ChatRequestError,
    create_chat_http_response,
    handle_chat_request_payload,
    parse_chat_request,
)


def test_parse_chat_request_rejects_empty_payload():
    try:
        parse_chat_request({})
    except ChatRequestError as exc:
        assert "question" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ChatRequestError")


def test_create_chat_http_response_shapes_payload(monkeypatch):
    def fake_build_chat_response(question: str):
        return {
            "question": question,
            "route": "hybrid",
            "answer": "요약된 답변",
            "filters": {"stock_keyword": "SK HYNIX"},
            "bundle": {
                "news_docs": [
                    {
                        "news_id": "n1",
                        "display_title": "테스트 기사",
                        "core_summary": "기사 요약",
                        "press": "테스트언론",
                        "pub_date": "2026-04-15",
                        "original_url": "https://example.com",
                        "sentiment_class": "호재",
                        "category": "실적",
                        "stock_keyword": "SK HYNIX",
                        "hybrid_score": 0.9,
                    }
                ],
                "forecast_rows": [{"ticker": "000660.KS"}],
                "macro_snapshot": [{"trade_date": "2026-04-15"}],
                "ml_feature_snapshot": [{"base_date": "2026-04-15"}],
                "quant_signal_rows": [{"signal_date": "2026-04-15"}],
                "sentiment_snapshot": [{"base_date": "2026-04-15"}],
            },
            "errors": {"embedding_error": None, "llm_error": None},
        }

    monkeypatch.setattr(
        "src.service.rag.flask_adapter.build_chat_response",
        fake_build_chat_response,
    )

    response = create_chat_http_response("질문", include_debug=True)

    assert response["status"] == "ok"
    assert response["answer"] == "요약된 답변"
    assert response["sources"][0]["title"] == "테스트 기사"
    assert "debug" in response


def test_handle_chat_request_payload_returns_400_for_bad_request():
    body, status = handle_chat_request_payload({"question": ""})

    assert status == 400
    assert body["status"] == "error"
