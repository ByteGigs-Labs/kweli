import httpx
import pytest

from api.config import Settings
from paypal.auth import PayPalAuthError, fetch_access_token


def settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://u:p@h/db",
        "paypal_client_id": "client-id",
        "paypal_client_secret": "client-secret",
    } | overrides
    return Settings(_env_file=None, **values)


def client_returning(status: int, body: dict, seen: list) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_token_is_fetched_from_sandbox_with_basic_auth():
    seen: list[httpx.Request] = []
    body = {
        "access_token": "A21AAtoken",
        "scope": "https://uri.paypal.com/services/invoicing openid",
        "app_id": "APP-123",
        "expires_in": 32400,
    }
    token = fetch_access_token(settings(), client_returning(200, body, seen))
    request = seen[0]
    assert str(request.url) == "https://api-m.sandbox.paypal.com/v1/oauth2/token"
    assert request.headers["Authorization"].startswith("Basic ")
    assert request.content == b"grant_type=client_credentials"
    assert token.value == "A21AAtoken"
    assert "https://uri.paypal.com/services/invoicing" in token.scopes
    assert token.is_fresh()


def test_rejected_credentials_raise_without_leaking_secret():
    seen: list[httpx.Request] = []
    with pytest.raises(PayPalAuthError) as error:
        fetch_access_token(settings(), client_returning(401, {"error": "invalid_client"}, seen))
    assert "client-secret" not in str(error.value)
    assert "401" in str(error.value)


def test_missing_credentials_fail_before_any_request():
    seen: list[httpx.Request] = []
    with pytest.raises(PayPalAuthError):
        fetch_access_token(settings(paypal_client_id=""), client_returning(200, {}, seen))
    assert seen == []
