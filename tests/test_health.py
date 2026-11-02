from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_is_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_unknown_route_uses_error_shape():
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_cors_allows_only_configured_origin():
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    blocked = client.get("/health", headers={"Origin": "https://evil.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_oversized_body_is_rejected():
    response = client.post(
        "/health", content=b"x" * (65 * 1024), headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 413
