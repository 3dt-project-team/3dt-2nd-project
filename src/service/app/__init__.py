"""SENSE RAG service package."""

__all__ = [
    "build_chat_response",
    "create_chat_http_response",
    "handle_chat_request_payload",
]


def build_chat_response(*args, **kwargs):
    from .chatbot import build_chat_response as _build_chat_response

    return _build_chat_response(*args, **kwargs)


def create_chat_http_response(*args, **kwargs):
    from .flask_adapter import create_chat_http_response as _create_chat_http_response

    return _create_chat_http_response(*args, **kwargs)


def handle_chat_request_payload(*args, **kwargs):
    from .flask_adapter import handle_chat_request_payload as _handle_chat_request_payload

    return _handle_chat_request_payload(*args, **kwargs)
