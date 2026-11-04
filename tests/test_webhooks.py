import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from api.config import get_settings
from api.db.models import AuditLog, Invoice, Payment, ProofFlag, WebhookEvent
from tests.helpers import accept_link, create_agreement, paypal
from tests.paypal_fakes import FakePayPal

SIGNATURE = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "PAYPAL-TRANSMISSION-ID": "tx-1",
    "PAYPAL-TRANSMISSION-SIG": "c2lnbmF0dXJl",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-04T10:00:00Z",
}
VERIFY = "/v1/notifications/verify-webhook-signature"


@pytest.fixture(autouse=True)
def webhook_id(monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-KWELI")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def paid_event(invoice_id="INV2-ACME-0042", event_id="WH-EVT-1") -> bytes:
    event = {
        "id": event_id,
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"id": invoice_id, "status": "PAID", "amount": {"value": 999.0}},
    }
    return json.dumps(event, separators=(",", ": ")).encode()


def remote_invoice(paid="800.00", status="PAID", invoice_id="INV2-ACME-0042") -> dict:
    return {
        "id": invoice_id,
        "status": status,
        "payments": {
            "transactions": [
                {
                    "payment_id": "8PAYMENT0042",
                    "payment_date": datetime.now(UTC).isoformat(),
                    "method": "PAYPAL",
                    "amount": {"currency_code": "USD", "value": paid},
                }
            ]
        },
    }


def fake(verification="SUCCESS", remote=None, payer_email="jordan@acmeltd.com") -> FakePayPal:
    fake = FakePayPal()
    fake.queue("POST", VERIFY, httpx.Response(200, json={"verification_status": verification}))
    fake.queue(
        "GET",
        "/v2/invoicing/invoices/INV2-ACME-0042",
        httpx.Response(200, json=remote or remote_invoice()),
    )
    details = []
    if payer_email:
        details = [
            {
                "transaction_info": {"transaction_id": "8PAYMENT0042"},
                "payer_info": {
                    "email_address": payer_email,
                    "account_id": "PAYER1",
                    "payer_name": {"alternate_full_name": "Jordan Doe"},
                },
            }
        ]
    fake.queue(
        "GET",
        "/v1/reporting/transactions",
        httpx.Response(200, json={"transaction_details": details}),
    )
    return fake


def invoiced_agreement(client, db, paypal_invoice_id="INV2-ACME-0042"):
    agreement = create_agreement(client)
    token = accept_link(client, agreement["id"])
    client.post(f"/v1/portal/agreements/{token}/accept", json={"accept": True})
    invoice = Invoice(
        user_id=db.scalar(select(Invoice.user_id).limit(1)) or _user_id(db),
        client_id=agreement["client"]["id"],
        agreement_id=agreement["id"],
        paypal_invoice_id=paypal_invoice_id,
        number="0042",
        description="Logo design",
        amount_minor=80000,
        currency="USD",
        status="sent",
    )
    db.add(invoice)
    db.commit()
    return agreement


def _user_id(db):
    from api.db.models import User

    return db.scalar(select(User.id).limit(1))


def post(client, body: bytes, headers=SIGNATURE):
    return client.post(
        "/v1/webhooks/paypal", content=body, headers=headers | {"Content-Type": "application/json"}
    )


def test_verified_invoice_payment_is_recorded_and_proved(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    body = paid_event()
    paypal_fake = fake()
    with paypal(paypal_fake):
        response = post(client, body)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "processed"}

    payment = db.scalar(select(Payment))
    assert payment.amount_minor == 80000
    assert payment.payer_email == "jordan@acmeltd.com"
    assert payment.payment_type == "invoice"
    rules = {flag.rule: flag.status for flag in db.scalars(select(ProofFlag))}
    assert rules == {
        "P1": "pass",
        "P2": "pass",
        "P3": "pass",
        "P4": "pass",
        "P5": "fail",
        "P6": "pass",
        "P7": "pass",
    }
    invoice = db.scalar(select(Invoice))
    db.refresh(invoice)
    assert invoice.status == "paid"
    actions = [row.action for row in db.scalars(select(AuditLog).order_by(AuditLog.seq))]
    assert actions[-2:] == ["payment.received", "proof.evaluated"]


def test_event_is_sent_back_to_paypal_byte_for_byte(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    body = paid_event()
    paypal_fake = fake()
    with paypal(paypal_fake):
        post(client, body)
    verify_request = paypal_fake.requests[0]
    assert verify_request.url.path == VERIFY
    assert body in verify_request.content
    sent = json.loads(verify_request.content)
    assert sent["webhook_id"] == "WH-KWELI"
    assert sent["transmission_sig"] == "c2lnbmF0dXJl"


def test_amounts_come_from_paypal_not_the_webhook_body(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    with paypal(fake()):
        post(client, paid_event())
    assert db.scalar(select(Payment.amount_minor)) == 80000


def test_forged_event_is_rejected_and_nothing_stored(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    with paypal(fake(verification="FAILURE")):
        response = post(client, paid_event())
    assert response.status_code == 400
    assert db.scalar(select(Payment)) is None
    assert db.scalar(select(WebhookEvent)) is None


def test_missing_signature_headers_are_rejected(client):
    with paypal(fake()):
        response = post(client, paid_event(), headers={})
    assert response.status_code == 400


def test_unconfigured_webhook_refuses_events(client, monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "")
    get_settings.cache_clear()
    with paypal(fake()):
        assert post(client, paid_event()).status_code == 503


def test_replayed_event_is_processed_once(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    with paypal(fake()):
        first = post(client, paid_event())
    with paypal(fake()):
        second = post(client, paid_event())
    assert first.json() == {"status": "processed"}
    assert second.json() == {"status": "duplicate"}
    assert len(db.scalars(select(Payment)).all()) == 1


def test_same_payment_in_two_events_is_stored_once(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    with paypal(fake()):
        post(client, paid_event(event_id="WH-A"))
    with paypal(fake()):
        post(client, paid_event(event_id="WH-B"))
    assert len(db.scalars(select(Payment)).all()) == 1


def test_third_party_payer_is_flagged(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    with paypal(fake(payer_email="someone@else.com")):
        post(client, paid_event())
    flag = db.scalar(select(ProofFlag).where(ProofFlag.rule == "P3"))
    assert flag.status == "warn"
    assert flag.explanation == "Paid by Jordan Doe, not Acme Ltd."


def test_unindexed_payer_is_pending_then_resolved(logged_in, db):
    from api.services.payments import refresh_pending_payers

    client = logged_in()
    invoiced_agreement(client, db)
    with paypal(fake(payer_email=None)):
        post(client, paid_event())
    flag = db.scalar(select(ProofFlag).where(ProofFlag.rule == "P3"))
    assert flag.status == "pending"
    assert refresh_pending_payers(db, fake().client()) == 1
    flag = db.scalar(select(ProofFlag).where(ProofFlag.rule == "P3"))
    assert flag.status == "pass"


def test_partial_payment_warns(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    with paypal(fake(remote=remote_invoice(paid="500.00", status="PARTIALLY_PAID"))):
        post(client, paid_event())
    flag = db.scalar(select(ProofFlag).where(ProofFlag.rule == "P2"))
    assert flag.status == "warn"
    invoice = db.scalar(select(Invoice))
    db.refresh(invoice)
    assert invoice.status == "partially_paid"


def test_unknown_invoice_is_ignored(logged_in, db):
    client = logged_in()
    with paypal(fake()):
        response = post(client, paid_event(invoice_id="INV2-NOT-OURS"))
    assert response.json() == {"status": "ignored"}
    assert db.scalar(select(WebhookEvent.note)) == "not a Kweli invoice"


def test_processing_failure_asks_paypal_to_retry(logged_in, db):
    client = logged_in()
    invoiced_agreement(client, db)
    broken = FakePayPal()
    broken.queue("POST", VERIFY, httpx.Response(200, json={"verification_status": "SUCCESS"}))
    broken.queue("GET", "/v2/invoicing/invoices/INV2-ACME-0042", httpx.Response(503))
    with paypal(broken):
        response = post(client, paid_event())
    assert response.status_code == 503
    assert db.scalar(select(WebhookEvent.status)) == "failed"
    with paypal(fake()):
        retry = post(client, paid_event())
    assert retry.json() == {"status": "processed"}
    assert db.scalar(select(WebhookEvent.attempts)) == 2


def test_capture_from_checkout_uses_order_payer(logged_in, db):
    from api.db.models import User

    client = logged_in()
    user = db.scalar(select(User))
    user.paypal_merchant_id = "MERCHANT1"
    db.commit()
    event = json.dumps(
        {"id": "WH-CAP", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "CAP1"}}
    ).encode()
    capture_fake = FakePayPal()
    capture_fake.queue("POST", VERIFY, httpx.Response(200, json={"verification_status": "SUCCESS"}))
    capture_fake.queue(
        "GET",
        "/v2/payments/captures/CAP1",
        httpx.Response(
            200,
            json={
                "id": "CAP1",
                "status": "COMPLETED",
                "amount": {"currency_code": "USD", "value": "120.00"},
                "payee": {"merchant_id": "MERCHANT1"},
                "create_time": datetime(2026, 11, 4, tzinfo=UTC).isoformat(),
                "supplementary_data": {"related_ids": {"order_id": "ORDER1"}},
            },
        ),
    )
    capture_fake.queue(
        "GET",
        "/v2/checkout/orders/ORDER1",
        httpx.Response(
            200,
            json={
                "payer": {
                    "email_address": "buyer@shop.com",
                    "payer_id": "B1",
                    "name": {"given_name": "Bo", "surname": "Buyer"},
                }
            },
        ),
    )
    with paypal(capture_fake):
        response = post(client, event)
    assert response.json() == {"status": "processed"}
    payment = db.scalar(select(Payment))
    assert payment.payer_name == "Bo Buyer"
    assert payment.payment_type == "goods_services"
    p1 = db.scalar(select(ProofFlag).where(ProofFlag.rule == "P1"))
    assert p1.status == "fail"


def test_unused_event_types_are_ignored(client):
    event = json.dumps(
        {"id": "WH-X", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "O1"}}
    ).encode()
    with paypal(fake()):
        response = post(client, event)
    assert response.json() == {"status": "ignored"}
