import httpx
import pytest

from paypal.errors import PayPalError, PayPalUnavailable
from tests.paypal_fakes import FakePayPal


def test_token_is_cached_between_calls():
    fake = FakePayPal()
    fake.queue("GET", "/v2/invoicing/invoices/INV2-1", httpx.Response(200, json={"id": "INV2-1"}))
    client = fake.client()
    client.get("/v2/invoicing/invoices/INV2-1")
    client.get("/v2/invoicing/invoices/INV2-1")
    assert fake.token_calls == 1
    assert fake.requests[0].headers["Authorization"] == "Bearer A21AAfaketoken"


def test_expired_token_is_refreshed_once_on_401():
    fake = FakePayPal()
    fake.queue(
        "GET",
        "/v1/x",
        httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"}),
        httpx.Response(200, json={"ok": True}),
    )
    assert fake.client().get("/v1/x") == {"ok": True}
    assert fake.token_calls == 2


def test_post_gets_an_idempotency_key_that_survives_retries():
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v1/x",
        httpx.Response(503),
        httpx.Response(500),
        httpx.Response(201, json={"id": "1"}),
    )
    assert fake.client().post("/v1/x", json={}) == {"id": "1"}
    ids = {request.headers["PayPal-Request-Id"] for request in fake.requests}
    assert len(fake.requests) == 3
    assert len(ids) == 1


def test_explicit_request_id_is_used():
    fake = FakePayPal()
    fake.queue("POST", "/v1/x", httpx.Response(201, json={}))
    fake.client().post("/v1/x", json={}, request_id="send-inv-42")
    assert fake.requests[0].headers["PayPal-Request-Id"] == "send-inv-42"


def test_retry_after_header_is_respected():
    fake = FakePayPal()
    fake.queue(
        "GET",
        "/v1/x",
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200, json={}),
    )
    delays: list[float] = []
    client = fake.client()
    client._sleep = delays.append
    client.get("/v1/x")
    assert delays == [2.0]


def test_gives_up_after_max_retries():
    fake = FakePayPal()
    fake.queue("GET", "/v1/x", httpx.Response(503, json={"name": "SERVICE_UNAVAILABLE"}))
    with pytest.raises(PayPalUnavailable) as error:
        fake.client(max_retries=2).get("/v1/x")
    assert error.value.status == 503
    assert len(fake.requests) == 3


def test_network_errors_are_retried_then_reported():
    fake = FakePayPal()
    fake.queue("GET", "/v1/x", httpx.ConnectError("boom"))
    with pytest.raises(PayPalUnavailable) as error:
        fake.client(max_retries=1).get("/v1/x")
    assert error.value.name == "NETWORK_ERROR"
    assert len(fake.requests) == 2


def test_client_errors_are_not_retried_and_carry_details():
    fake = FakePayPal()
    body = {
        "name": "UNPROCESSABLE_ENTITY",
        "message": "The requested action could not be performed.",
        "debug_id": "abc123",
        "details": [{"issue": "INVALID_CURRENCY_CODE"}],
    }
    fake.queue("POST", "/v1/x", httpx.Response(422, json=body))
    with pytest.raises(PayPalError) as error:
        fake.client().post("/v1/x", json={})
    assert len(fake.requests) == 1
    assert error.value.debug_id == "abc123"
    assert error.value.issues == ["INVALID_CURRENCY_CODE"]
    assert "client-secret" not in str(error.value)


def test_requests_go_to_the_sandbox_host():
    fake = FakePayPal()
    fake.queue("GET", "/v1/x", httpx.Response(200, json={}))
    fake.client().get("/v1/x")
    assert fake.requests[0].url.host == "api-m.sandbox.paypal.com"


def test_empty_success_body_returns_empty_dict():
    fake = FakePayPal()
    fake.queue("POST", "/v1/x", httpx.Response(204))
    assert fake.client().post("/v1/x") == {}
