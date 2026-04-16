import importlib
import sys

from werkzeug.middleware.proxy_fix import ProxyFix


def _load_app_module(monkeypatch):
    monkeypatch.setenv("KEY_VAULT_URL", "")
    monkeypatch.setenv("PG_CONNECTION_STRING", "dbname=postgres host=localhost")

    for module_name in ("app", "src.service.web.routes", "src.service.web", "src.utils.database"):
        sys.modules.pop(module_name, None)

    return importlib.import_module("app")


def test_api_chat_route_proxies_to_chat_service(monkeypatch):
    app_module = _load_app_module(monkeypatch)
    routes = importlib.import_module("src.service.web.routes")

    captured = {}

    def fake_handle_chat_request_payload(payload):
        captured["payload"] = payload
        return (
            {
                "status": "ok",
                "question": payload["question"],
                "route": "hybrid",
                "answer": "Summary response",
                "filters": {"stock_keyword": "SK HYNIX"},
                "sources": [],
                "snapshots": {},
            },
            200,
        )

    monkeypatch.setattr(routes, "handle_chat_request_payload", fake_handle_chat_request_payload)

    client = app_module.create_app().test_client()
    response = client.post("/api/chat", json={"question": "Summarize chip news"})

    assert response.status_code == 200
    assert response.get_json()["answer"] == "Summary response"
    assert captured["payload"] == {"question": "Summarize chip news"}


def test_api_chat_route_returns_400_for_invalid_payload(monkeypatch):
    app_module = _load_app_module(monkeypatch)

    client = app_module.create_app().test_client()
    response = client.post("/api/chat", json={})

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"
    assert "question" in response.get_json()["error"]


def test_healthz_route_returns_ok(monkeypatch):
    app_module = _load_app_module(monkeypatch)

    client = app_module.create_app().test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "sense-web"}


def test_app_module_exposes_wsgi_app(monkeypatch):
    app_module = _load_app_module(monkeypatch)

    assert app_module.app is not None
    assert isinstance(app_module.app.wsgi_app, ProxyFix)
