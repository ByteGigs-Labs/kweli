import json

import httpx
import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("paypal_agent_toolkit")

from agent.paypal_tools import paypal_tools  # noqa: E402
from tests.paypal_fakes import FakePayPal  # noqa: E402

INVOICE_ARGS = {
    "currency_code": "USD",
    "invoice_number": "0042",
    "primary_recipients": [{"billing_info": {"email_address": "ap@acme.test"}}],
    "items": [
        {
            "name": "Logo design",
            "quantity": "1",
            "unit_amount": {"currency_code": "USD", "value": "10.00"},
        }
    ],
}


def tools_by_name(fake, methods):
    return {tool.name: tool for tool in paypal_tools(methods, client=fake.client())}


def test_only_allowed_tools_are_built():
    tools = tools_by_name(FakePayPal(), ["create_invoice", "get_invoice"])
    assert set(tools) == {"create_invoice", "get_invoice"}


def test_unknown_methods_fail_loudly():
    with pytest.raises(ValueError, match="send_money"):
        paypal_tools(["send_money"], client=FakePayPal().client())


def test_toolkit_requests_go_through_kweli_client():
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v2/invoicing/invoices",
        httpx.Response(201, json={"rel": "self", "href": ".../INV2-T00L"}),
    )
    fake.queue("GET", "/v2/invoicing/invoices/INV2-T00L", httpx.Response(200, json={"id": "X"}))
    tools = tools_by_name(fake, ["create_invoice", "get_invoice"])
    result = tools["create_invoice"].invoke(INVOICE_ARGS)
    tools["get_invoice"].invoke({"invoice_id": "INV2-T00L"})
    assert "INV2-T00L" in result
    assert fake.token_calls == 1
    create = fake.requests[0]
    assert create.url.host == "api-m.sandbox.paypal.com"
    assert create.headers["PayPal-Request-Id"]
    assert json.loads(create.content)["items"][0]["name"] == "Logo design"


def test_paypal_errors_come_back_as_safe_text():
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v2/invoicing/invoices",
        httpx.Response(
            422,
            json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INVALID_CURRENCY"}]},
        ),
    )
    result = tools_by_name(fake, ["create_invoice"])["create_invoice"].invoke(INVOICE_ARGS)
    assert result == "PayPal rejected create_invoice: UNPROCESSABLE_ENTITY (INVALID_CURRENCY)"
    assert "client-secret" not in result
