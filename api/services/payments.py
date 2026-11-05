"""Turn verified PayPal events into payment records, then prove them.

Amounts, payers and IDs are always re-read from PayPal's API. The webhook body only says
which resource changed.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Invoice, Payment, User
from audit.log import record
from paypal.client import PayPalClient
from paypal.invoicing import Invoicing
from paypal.money import from_paypal_value
from paypal.payments import find_transaction, get_capture, get_order, payer_from_transaction
from proof.engine import evaluate_payment

logger = logging.getLogger("kweli.payments")

DISPUTE_EVENTS = frozenset(
    {"CUSTOMER.DISPUTE.CREATED", "CUSTOMER.DISPUTE.UPDATED", "CUSTOMER.DISPUTE.RESOLVED"}
)

INVOICE_STATUS = {
    "PAID": "paid",
    "MARKED_AS_PAID": "paid",
    "PARTIALLY_PAID": "partially_paid",
    "CANCELLED": "cancelled",
    "REFUNDED": "refunded",
    "PARTIALLY_REFUNDED": "refunded",
    "SENT": "sent",
    "UNPAID": "sent",
}


@dataclass(frozen=True)
class Outcome:
    status: str
    note: str


def _when(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    text = value.replace("Z", "+00:00")
    if len(text) == 10:
        text += "T00:00:00+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _transactions(remote: dict) -> list[dict]:
    payments = remote.get("payments") or {}
    if isinstance(payments, list):
        return payments
    return payments.get("transactions") or []


def _resolve_payer(paypal: PayPalClient, payment: Payment) -> None:
    detail = find_transaction(paypal, payment.paypal_transaction_id, payment.received_at)
    if detail:
        payment.payer_email, payment.payer_id, payment.payer_name = payer_from_transaction(detail)
        payment.payer_resolved_at = datetime.now(UTC)


def _store(db: Session, payment: Payment, invoice_number: str | None) -> None:
    db.add(payment)
    db.flush()
    record(
        db,
        payment.user_id,
        "payment.received",
        {
            "payment_id": str(payment.id),
            "paypal_transaction_id": payment.paypal_transaction_id,
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
            "invoice_number": invoice_number,
        },
    )
    evaluate_payment(db, payment)


def ingest_invoice(db: Session, paypal: PayPalClient, paypal_invoice_id: str) -> Outcome:
    invoice = db.scalar(select(Invoice).where(Invoice.paypal_invoice_id == paypal_invoice_id))
    if not invoice:
        return Outcome("ignored", "not a Kweli invoice")
    remote = Invoicing(paypal).get(paypal_invoice_id)
    remote_status = remote.get("status", "")
    added = 0
    for transaction in _transactions(remote):
        transaction_id = transaction.get("payment_id")
        amount = transaction.get("amount") or {}
        if not transaction_id or not amount.get("value"):
            continue
        if db.scalar(select(Payment.id).where(Payment.paypal_transaction_id == transaction_id)):
            continue
        currency = amount.get("currency_code", invoice.currency)
        payment = Payment(
            user_id=invoice.user_id,
            paypal_transaction_id=transaction_id,
            paypal_invoice_id=paypal_invoice_id,
            amount_minor=from_paypal_value(amount["value"], currency),
            currency=currency,
            payment_type="invoice",
            source="webhook",
            received_at=_when(transaction.get("payment_date")),
        )
        _resolve_payer(paypal, payment)
        _store(db, payment, invoice.number)
        added += 1
    if remote_status in INVOICE_STATUS:
        invoice.status = INVOICE_STATUS[remote_status]
        if invoice.status == "paid" and not invoice.paid_at:
            invoice.paid_at = datetime.now(UTC)
    return Outcome("processed", f"invoice {remote_status.lower()}, {added} new payment(s)")


def _owner(db: Session, merchant_id: str | None) -> User | None:
    if merchant_id:
        user = db.scalar(select(User).where(User.paypal_merchant_id == merchant_id))
        if user:
            return user
    owners = db.scalars(select(User).where(User.paypal_merchant_id.is_not(None)).limit(2)).all()
    return owners[0] if len(owners) == 1 else None


def ingest_capture(db: Session, paypal: PayPalClient, capture_id: str) -> Outcome:
    if db.scalar(select(Payment.id).where(Payment.paypal_transaction_id == capture_id)):
        return Outcome("processed", "already recorded")
    capture = get_capture(paypal, capture_id)
    if capture.get("status") != "COMPLETED":
        return Outcome("ignored", f"capture is {capture.get('status', 'unknown').lower()}")
    owner = _owner(db, (capture.get("payee") or {}).get("merchant_id"))
    if not owner:
        return Outcome("ignored", "no Kweli user owns this PayPal account")
    amount = capture.get("amount") or {}
    currency = amount.get("currency_code", "USD")
    invoice = None
    if capture.get("invoice_id"):
        invoice = db.scalar(
            select(Invoice).where(
                Invoice.user_id == owner.id, Invoice.number == capture["invoice_id"]
            )
        )
    payment = Payment(
        user_id=owner.id,
        paypal_transaction_id=capture_id,
        paypal_invoice_id=invoice.paypal_invoice_id if invoice else None,
        amount_minor=from_paypal_value(amount.get("value", "0"), currency),
        currency=currency,
        payment_type="goods_services",
        source="webhook",
        received_at=_when(capture.get("create_time")),
    )
    order_id = ((capture.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
    if order_id:
        payer = get_order(paypal, order_id).get("payer") or {}
        name = payer.get("name") or {}
        payment.payer_email = payer.get("email_address")
        payment.payer_id = payer.get("payer_id")
        payment.payer_name = " ".join(filter(None, [name.get("given_name"), name.get("surname")]))
        payment.payer_resolved_at = datetime.now(UTC)
    else:
        _resolve_payer(paypal, payment)
    _store(db, payment, invoice.number if invoice else None)
    return Outcome("processed", "capture recorded")


def cancel_invoice(db: Session, paypal_invoice_id: str) -> Outcome:
    invoice = db.scalar(select(Invoice).where(Invoice.paypal_invoice_id == paypal_invoice_id))
    if not invoice:
        return Outcome("ignored", "not a Kweli invoice")
    invoice.status = "cancelled"
    return Outcome("processed", "invoice cancelled")


def handle_event(db: Session, paypal: PayPalClient, event: dict) -> Outcome:
    kind = event.get("event_type", "")
    resource = event.get("resource") or {}
    resource_id = str(resource.get("id") or resource.get("dispute_id") or "")
    if not resource_id:
        return Outcome("ignored", "event has no resource id")
    if kind in DISPUTE_EVENTS:
        from api.services.disputes import sync

        return sync(db, paypal, str(resource.get("dispute_id") or resource_id))
    if kind in ("INVOICING.INVOICE.PAID", "INVOICING.INVOICE.UPDATED"):
        return ingest_invoice(db, paypal, resource_id)
    if kind == "INVOICING.INVOICE.CANCELLED":
        return cancel_invoice(db, resource_id)
    if kind == "PAYMENT.CAPTURE.COMPLETED":
        return ingest_capture(db, paypal, resource_id)
    return Outcome("ignored", f"{kind or 'unknown'} is not used yet")


def refresh_pending_payers(db: Session, paypal: PayPalClient, limit: int = 50) -> int:
    """Fill in payers that Transaction Search hadn't indexed yet, then re-prove."""
    pending = db.scalars(
        select(Payment)
        .where(Payment.payer_resolved_at.is_(None), Payment.source != "seed")
        .order_by(Payment.received_at)
        .limit(limit)
    ).all()
    resolved = 0
    for payment in pending:
        _resolve_payer(paypal, payment)
        if payment.payer_resolved_at:
            evaluate_payment(db, payment)
            resolved += 1
    db.commit()
    return resolved
