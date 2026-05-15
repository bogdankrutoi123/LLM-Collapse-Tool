from __future__ import annotations

from fastapi.testclient import TestClient


def test_root_returns_app_info(client):
    real_client, _ = client
    resp = real_client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "name" in body
    assert "version" in body
    assert body["status"] == "running"


def test_health_endpoint_returns_healthy(client):
    real_client, _ = client
    resp = real_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def test_https_not_enforced_by_default(client):
    real_client, _ = client
    resp = real_client.get("/health")
    assert resp.status_code == 200


def test_https_middleware_rejects_http_when_enabled(app_with_db, monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "ENFORCE_HTTPS", True)

    tc = TestClient(app_with_db, raise_server_exceptions=False)
    resp = tc.get("/health")
    assert resp.status_code == 403
    assert "HTTPS" in resp.json().get("detail", "")


def test_https_middleware_allows_https_forwarded_proto(app_with_db, monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "ENFORCE_HTTPS", True)

    tc = TestClient(app_with_db, raise_server_exceptions=False)
    resp = tc.get("/health", headers={"x-forwarded-proto": "https"})
    assert resp.status_code == 200


def test_global_exception_handler_returns_500_with_detail(app_with_db):
    import app.main as main_module

    @main_module.app.get("/__test_boom")
    def _boom():
        raise RuntimeError("deliberate test boom")

    try:
        tc = TestClient(app_with_db, raise_server_exceptions=False)
        resp = tc.get("/__test_boom")
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" in body
        assert "RuntimeError" in body["detail"] or "boom" in body["detail"]
    finally:
        main_module.app.router.routes = [
            r for r in main_module.app.router.routes
            if getattr(r, "path", None) != "/__test_boom"
        ]
