"""Gather the facts for a payment from the database, run the rules, store the results."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.db.models import Agreement, Client, Document, Invoice, Payment, PaymentLink, ProofFlag
from audit.log import record
from proof.rules import (
    AgreementFacts,
    Facts,
    InvoiceFacts,
    PaymentFacts,
    Result,
    evaluate,
    overall,
)

HISTORY_WINDOW = timedelta(days=90)


def _links(
    db: Session, payment: Payment
) -> tuple[Invoice | None, Agreement | None, Document | None]:
    invoice = None
    if payment.paypal_invoice_id:
        invoice = db.scalar(
            select(Invoice).where(
                Invoice.user_id == payment.user_id,
                Invoice.paypal_invoice_id == payment.paypal_invoice_id,
            )
        )
    agreement = (
        db.get(Agreement, invoice.agreement_id) if invoice and invoice.agreement_id else None
    )
    deliverable = None
    if agreement:
        deliverable = db.scalar(
            select(Document)
            .where(Document.agreement_id == agreement.id, Document.kind == "deliverable")
            .order_by(Document.created_at.desc())
            .limit(1)
        )
    return invoice, agreement, deliverable


def facts_for(db: Session, payment: Payment) -> tuple[Facts, PaymentLink]:
    invoice, agreement, deliverable = _links(db, payment)
    client = db.get(Client, agreement.client_id) if agreement else None
    history = db.scalars(
        select(Payment.amount_minor).where(
            Payment.user_id == payment.user_id,
            Payment.id != payment.id,
            Payment.currency == payment.currency,
            Payment.received_at < payment.received_at,
            Payment.received_at >= payment.received_at - HISTORY_WINDOW,
        )
    ).all()
    facts = Facts(
        payment=PaymentFacts(
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            received_at=payment.received_at,
            payment_type=payment.payment_type,
            payer_email=payment.payer_email,
            payer_name=payment.payer_name,
            payer_known=payment.payer_resolved_at is not None,
        ),
        invoice=InvoiceFacts(invoice.number, invoice.amount_minor, invoice.currency)
        if invoice
        else None,
        agreement=AgreementFacts(
            agreement.title, client.name, client.email, agreement.status, agreement.accepted_at
        )
        if agreement and client
        else None,
        deliverable_name=deliverable.filename if deliverable else None,
        recent_amounts_minor=list(history),
    )
    link = PaymentLink(
        payment_id=payment.id,
        invoice_id=invoice.id if invoice else None,
        agreement_id=agreement.id if agreement else None,
        deliverable_document_id=deliverable.id if deliverable else None,
    )
    return facts, link


def evaluate_payment(db: Session, payment: Payment) -> list[Result]:
    """Re-run every rule for one payment and replace its stored results. Caller commits."""
    facts, link = facts_for(db, payment)
    results = evaluate(facts)
    db.merge(link)
    db.execute(delete(ProofFlag).where(ProofFlag.payment_id == payment.id))
    db.add_all(
        ProofFlag(
            payment_id=payment.id,
            rule=result.rule,
            status=result.status,
            explanation=result.explanation[:500],
            fix=result.fix[:500] if result.fix else None,
        )
        for result in results
    )
    record(
        db,
        payment.user_id,
        "proof.evaluated",
        {
            "payment_id": str(payment.id),
            "overall": overall(results),
            "rules": {result.rule: result.status for result in results},
        },
    )
    return results


def reevaluate_for_agreement(db: Session, agreement_id: UUID) -> int:
    payments = db.scalars(
        select(Payment)
        .join(PaymentLink, PaymentLink.payment_id == Payment.id)
        .where(PaymentLink.agreement_id == agreement_id)
    ).all()
    for payment in payments:
        evaluate_payment(db, payment)
    return len(payments)
