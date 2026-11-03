import json

import httpx

from tests.helpers import accept_link, create_agreement, paypal
from tests.paypal_fakes import FakePayPal


def accepted_agreement(client) -> dict:
    agreement = create_agreement(client)
    token = accept_link(client, agreement["id"])
    response = client.post(f"/v1/portal/agreements/{token}/accept", json={"accept": True})
    assert response.status_code == 200
    return agreement


def fake_paypal() -> FakePayPal:
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v2/invoicing/generate-next-invoice-number",
        httpx.Response(200, json={"invoice_number": "0042"}),
    )
    fake.queue(
        "POST",
        "/v2/invoicing/invoices",
        httpx.Response(201, json={"id": "INV2-ACME-0042", "status": "DRAFT"}),
    )
    fake.queue(
        "POST",
        "/v2/invoicing/invoices/INV2-ACME-0042/send",
        httpx.Response(
            200, json={"rel": "payer-view", "href": "https://sandbox.paypal.test/inv/0042"}
        ),
    )
    return fake


def test_invoice_needs_an_accepted_agreement(logged_in):
    client = logged_in()
    agreement = create_agreement(client)
    with paypal(fake_paypal()):
        response = client.post("/v1/invoices", json={"agreement_id": agreement["id"]})
    assert response.status_code == 409
    assert "hasn't accepted" in response.json()["error"]["message"]


def test_create_makes_a_paypal_draft_only(logged_in):
    client = logged_in()
    agreement = accepted_agreement(client)
    fake = fake_paypal()
    with paypal(fake):
        response = client.post("/v1/invoices", json={"agreement_id": agreement["id"]})
    assert response.status_code == 201, response.text
    invoice = response.json()
    assert invoice["status"] == "draft"
    assert invoice["number"] == "0042"
    assert invoice["paypal_invoice_id"] == "INV2-ACME-0042"
    paths = [request.url.path for request in fake.requests]
    assert paths == ["/v2/invoicing/generate-next-invoice-number", "/v2/invoicing/invoices"]
    body = json.loads(fake.requests[1].content)
    assert body["primary_recipients"][0]["billing_info"]["email_address"] == "jordan@acmeltd.com"
    assert body["items"][0]["unit_amount"] == {"currency_code": "USD", "value": "800.00"}
    assert fake.requests[1].headers["PayPal-Request-Id"] == f"kweli-invoice-{invoice['id']}"


def test_create_twice_returns_the_same_invoice(logged_in):
    client = logged_in()
    agreement = accepted_agreement(client)
    fake = fake_paypal()
    with paypal(fake):
        first = client.post("/v1/invoices", json={"agreement_id": agreement["id"]}).json()
        second = client.post("/v1/invoices", json={"agreement_id": agreement["id"]}).json()
    assert first["id"] == second["id"]
    assert len(fake.requests) == 2


def test_send_is_a_separate_explicit_step(logged_in):
    client = logged_in()
    agreement = accepted_agreement(client)
    fake = fake_paypal()
    with paypal(fake):
        invoice = client.post("/v1/invoices", json={"agreement_id": agreement["id"]}).json()
        sent = client.post(f"/v1/invoices/{invoice['id']}/send").json()
        again = client.post(f"/v1/invoices/{invoice['id']}/send").json()
    assert sent["status"] == "sent"
    assert sent["payer_view_url"] == "https://sandbox.paypal.test/inv/0042"
    assert again["sent_at"] == sent["sent_at"]
    send_calls = [r for r in fake.requests if r.url.path.endswith("/send")]
    assert len(send_calls) == 1
    assert send_calls[0].headers["PayPal-Request-Id"] == f"kweli-send-{invoice['id']}"
    assert client.get(f"/v1/agreements/{agreement['id']}").json()["invoice_id"] == invoice["id"]


def test_paypal_rejection_leaves_nothing_behind(logged_in):
    client = logged_in()
    agreement = accepted_agreement(client)
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v2/invoicing/generate-next-invoice-number",
        httpx.Response(403, json={"name": "NOT_AUTHORIZED"}),
    )
    with paypal(fake):
        response = client.post("/v1/invoices", json={"agreement_id": agreement["id"]})
    assert response.status_code == 502
    assert "Nothing was sent" in response.json()["error"]["message"]
    assert client.get("/v1/invoices").json() == []


def test_invoices_are_private(logged_in, client):
    owner = logged_in("owner@kweli.test")
    agreement = accepted_agreement(owner)
    with paypal(fake_paypal()):
        invoice = owner.post("/v1/invoices", json={"agreement_id": agreement["id"]}).json()
    owner.post("/v1/auth/logout")
    logged_in("other@kweli.test")
    with paypal(fake_paypal()):
        assert client.get(f"/v1/invoices/{invoice['id']}").status_code == 404
        assert client.post(f"/v1/invoices/{invoice['id']}/send").status_code == 404
        response = client.post("/v1/invoices", json={"agreement_id": agreement["id"]})
        assert response.status_code == 404


def test_missing_paypal_credentials_are_explained(logged_in):
    from api.deps import get_paypal
    from api.main import app
    from paypal.client import PayPalClient
    from tests.paypal_fakes import sandbox_settings

    client = logged_in()
    agreement = accepted_agreement(client)
    app.dependency_overrides[get_paypal] = lambda: PayPalClient(
        sandbox_settings(paypal_client_id="", paypal_client_secret="")
    )
    try:
        response = client.post("/v1/invoices", json={"agreement_id": agreement["id"]})
    finally:
        app.dependency_overrides.pop(get_paypal, None)
    assert response.status_code == 503
    assert "can't sign in to PayPal" in response.json()["error"]["message"]
    assert client.get("/v1/invoices").json() == []
