from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from proof.rules import (
    AgreementFacts,
    Facts,
    InvoiceFacts,
    PaymentFacts,
    evaluate,
    overall,
    p1_invoiced,
    p2_amount_matches,
    p3_payer_is_client,
    p4_agreement_accepted,
    p5_work_delivered,
    p6_business_payment,
    p7_usual_volume,
)

PAID = datetime(2026, 11, 4, 10, tzinfo=UTC)
PAYMENT = PaymentFacts(80000, "USD", PAID, "invoice", "jordan@acmeltd.com", "Jordan Doe", True)
INVOICE = InvoiceFacts("0042", 80000, "USD")
AGREEMENT = AgreementFacts(
    "Logo design", "Acme Ltd", "Jordan@AcmeLtd.com", "accepted", PAID - timedelta(days=3)
)
COMPLETE = Facts(PAYMENT, INVOICE, AGREEMENT, "logo-final.pdf", [70000, 90000, 80000])


def test_a_complete_chain_passes_every_rule():
    results = evaluate(COMPLETE)
    assert [r.rule for r in results] == ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
    assert {r.status for r in results} == {"pass"}
    assert overall(results) == "pass"
    assert all(r.fix is None for r in results)


def test_p1_payment_without_invoice_fails():
    result = p1_invoiced(replace(COMPLETE, invoice=None))
    assert result.status == "fail"
    assert result.fix


@pytest.mark.parametrize(
    ("amount", "currency", "status", "text"),
    [
        (80000, "USD", "pass", "Paid USD 800.00, the invoiced amount."),
        (75000, "USD", "warn", "Paid USD 750.00 of USD 800.00."),
        (90000, "USD", "warn", "more than the USD 800.00 invoiced"),
        (80000, "EUR", "fail", "against an invoice in USD"),
    ],
)
def test_p2_amount_and_currency(amount, currency, status, text):
    facts = replace(COMPLETE, payment=replace(PAYMENT, amount_minor=amount, currency=currency))
    result = p2_amount_matches(facts)
    assert result.status == status
    assert text in result.explanation


def test_p2_without_invoice_fails():
    assert p2_amount_matches(replace(COMPLETE, invoice=None)).status == "fail"


def test_p3_client_paid_is_case_insensitive():
    assert p3_payer_is_client(COMPLETE).status == "pass"


def test_p3_third_party_payer_warns_with_a_fix():
    facts = replace(
        COMPLETE,
        payment=replace(PAYMENT, payer_email="someone@else.com", payer_name="Sam Other"),
    )
    result = p3_payer_is_client(facts)
    assert result.status == "warn"
    assert result.explanation == "Paid by Sam Other, not Acme Ltd."
    assert "confirm in writing" in result.fix


def test_p3_unknown_payer_is_pending_not_failed():
    facts = replace(COMPLETE, payment=replace(PAYMENT, payer_email=None, payer_known=False))
    assert p3_payer_is_client(facts).status == "pending"


def test_p3_without_agreement_fails():
    assert p3_payer_is_client(replace(COMPLETE, agreement=None)).status == "fail"


def test_p4_states():
    assert p4_agreement_accepted(COMPLETE).status == "pass"
    unaccepted = replace(AGREEMENT, status="sent", accepted_at=None)
    assert p4_agreement_accepted(replace(COMPLETE, agreement=unaccepted)).status == "warn"
    late = replace(AGREEMENT, accepted_at=PAID + timedelta(hours=1))
    result = p4_agreement_accepted(replace(COMPLETE, agreement=late))
    assert result.status == "warn"
    assert "after the payment" in result.explanation
    assert p4_agreement_accepted(replace(COMPLETE, agreement=None)).status == "fail"


def test_p5_needs_delivered_work():
    assert p5_work_delivered(COMPLETE).status == "pass"
    result = p5_work_delivered(replace(COMPLETE, deliverable_name=None))
    assert result.status == "fail"
    assert "Upload" in result.fix


@pytest.mark.parametrize(
    ("kind", "status"),
    [("invoice", "pass"), ("goods_services", "pass"), ("personal", "warn"), ("unknown", "pending")],
)
def test_p6_payment_type(kind, status):
    facts = replace(COMPLETE, payment=replace(PAYMENT, payment_type=kind))
    assert p6_business_payment(facts).status == status


def test_p7_needs_history_before_judging():
    facts = replace(COMPLETE, recent_amounts_minor=[1000, 1000])
    assert p7_usual_volume(facts).status == "pass"


def test_p7_flags_a_spike():
    facts = replace(COMPLETE, recent_amounts_minor=[20000, 20000, 20000])
    result = p7_usual_volume(facts)
    assert result.status == "warn"
    assert "4×" in result.explanation


def test_p7_boundary_is_not_a_spike():
    facts = replace(
        COMPLETE,
        payment=replace(PAYMENT, amount_minor=60000),
        recent_amounts_minor=[20000, 20000, 20000],
    )
    assert p7_usual_volume(facts).status == "pass"


def test_overall_takes_the_worst_status():
    results = evaluate(replace(COMPLETE, deliverable_name=None))
    assert overall(results) == "fail"
    pending_only = evaluate(
        replace(COMPLETE, payment=replace(PAYMENT, payer_known=False, payer_email=None))
    )
    assert overall(pending_only) == "pending"


def test_rules_are_deterministic():
    assert evaluate(COMPLETE) == evaluate(COMPLETE)
