import pytest

from api.config import get_settings
from tests.conftest import PASSWORD


def test_api_responses_carry_security_headers(client):
    response = client.get("/v1/auth/me")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


def test_hsts_is_sent_when_cookies_are_secure(client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    try:
        response = client.get("/health")
    finally:
        get_settings.cache_clear()
    assert response.headers["strict-transport-security"].startswith("max-age=31536000")


def test_the_session_cookie_is_http_only_and_strict(client, make_user):
    make_user()
    response = client.post(
        "/v1/auth/login", json={"email": "amina@kweli.test", "password": PASSWORD}
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie


@pytest.mark.parametrize("origin", ["https://evil.test", "null", "http://localhost:5173.evil.test"])
def test_cross_site_writes_are_refused(logged_in, origin):
    client = logged_in()
    response = client.post("/v1/auth/logout", headers={"Origin": origin})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "bad_origin"
    assert client.get("/v1/auth/me").status_code == 200


def test_same_site_and_server_to_server_writes_pass(logged_in):
    client = logged_in()
    assert (
        client.post("/v1/packs", json={}, headers={"Origin": "http://localhost:5173"}).status_code
        == 422
    )
    assert client.post("/v1/packs", json={}).status_code == 422
    assert client.get("/v1/ledger", headers={"Origin": "https://evil.test"}).status_code == 200


def test_api_docs_are_off_unless_asked_for(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_uploads_are_rate_limited(logged_in, monkeypatch):
    from tests.test_documents import upload

    monkeypatch.setenv("UPLOADS_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        client = logged_in()
        codes = [upload(client).status_code for _ in range(3)]
    finally:
        get_settings.cache_clear()
    assert codes == [201, 201, 429]
