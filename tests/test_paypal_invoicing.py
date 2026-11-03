import json
from datetime import date

import httpx
import pytest

from paypal.invoicing import InvoiceDraft, Invoicing, build_invoice_payload, payer_view_url
from paypal.money import from_paypal_value, to_paypal_value
from scripts import create_sandbox_invoice
from tests.paypal_fakes import FakePayPal


@pytest.mark.parametrize(
    ("minor", "currency", "value"),
    [(80000, "USD", "800.00"), (5, "EUR", "0.05"), (1500, "JPY", "1500"), (0, "USD", "0.00")],
)
def test_minor_units_round_trip(minor, currency, value):
    assert to_paypal_value(minor, currency) == value
    assert from_paypal_value(value, currency) == minor


def test_too_many_decimals_are_rejected():
    with pytest.raises(ValueError):
        from_paypal_value("10.005", "USD")
    with pytest.raises(ValueError):
        from_paypal_value("10.5", "JPY")


def test_negative_amounts_are_rejected():
    with pytest.raises(ValueError):
        to_paypal_value(-1, "USD")


def draft(**overrides) -> InvoiceDraft:
    values = {
        "invoice_number": "0042",
        "currency": "USD",
        "recipient_email": "ap@acme.test",
        "recipient_name": "Acme Ltd",
        "item_name": "Logo design",
        "amount_minor": 80000,
        "due_date": date(2026, 11, 10),
        "note": "Per agreement AGR-1",
    } | overrides
    return InvoiceDraft(**values)


def test_payload_shape():
    payload = build_invoice_payload(draft())
    assert payload["detail"] == {
        "invoice_number": "0042",
        "currency_code": "USD",
        "note": "Per agreement AGR-1",
        "payment_term": {"due_date": "2026-11-10"},
    }
    assert payload["primary_recipients"][0]["billing_info"]["email_address"] == "ap@acme.test"
    assert payload["items"][0]["unit_amount"] == {"currency_code": "USD", "value": "800.00"}


def test_payload_omits_optional_fields():
    payload = build_invoice_payload(draft(due_date=None, note=None))
    assert "payment_term" not in payload["detail"]
    assert "note" not in payload["detail"]


def test_create_draft_asks_for_full_representation():
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v2/invoicing/invoices",
        httpx.Response(201, json={"id": "INV2-AAAA", "status": "DRAFT"}),
    )
    invoice = Invoicing(fake.client()).create_draft(draft(), request_id="agr-1-invoice")
    request = fake.requests[0]
    assert invoice["id"] == "INV2-AAAA"
    assert request.headers["Prefer"] == "return=representation"
    assert request.headers["PayPal-Request-Id"] == "agr-1-invoice"
    assert json.loads(request.content)["items"][0]["name"] == "Logo design"


def test_send_notifies_only_the_recipient():
    fake = FakePayPal()
    fake.queue("POST", "/v2/invoicing/invoices/INV2-AAAA/send", httpx.Response(202))
    Invoicing(fake.client()).send("INV2-AAAA")
    assert json.loads(fake.requests[0].content) == {
        "send_to_invoicer": False,
        "send_to_recipient": True,
    }


def test_payer_view_url_from_links_or_top_level():
    link = "https://www.sandbox.paypal.com/invoice/p/#INV2-AAAA"
    assert payer_view_url({"links": [{"rel": "payer-view", "href": link}]}) == link
    assert payer_view_url({"rel": "payer-view", "href": link}) == link
    assert payer_view_url({}) is None


def test_script_creates_and_sends(capsys):
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v2/invoicing/generate-next-invoice-number",
        httpx.Response(200, json={"invoice_number": "0007"}),
    )
    fake.queue(
        "POST",
        "/v2/invoicing/invoices",
        httpx.Response(201, json={"id": "INV2-BBBB", "status": "DRAFT"}),
    )
    fake.queue(
        "POST",
        "/v2/invoicing/invoices/INV2-BBBB/send",
        httpx.Response(200, json={"rel": "payer-view", "href": "https://pay.example/INV2-BBBB"}),
    )
    code = create_sandbox_invoice.main(
        ["--to", "client@sandbox.test", "--amount", "10.00", "--send"], client=fake.client()
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "INV2-BBBB" in out
    assert "https://pay.example/INV2-BBBB" in out
    body = json.loads(fake.requests[1].content)
    assert body["items"][0]["unit_amount"]["value"] == "10.00"


def test_script_reports_paypal_errors(capsys):
    fake = FakePayPal()
    fake.queue(
        "POST",
        "/v2/invoicing/generate-next-invoice-number",
        httpx.Response(403, json={"name": "NOT_AUTHORIZED", "message": "Invoicing not enabled"}),
    )
    code = create_sandbox_invoice.main(["--to", "c@x.test", "--amount", "1"], client=fake.client())
    assert code == 1
    assert "NOT_AUTHORIZED" in capsys.readouterr().out
