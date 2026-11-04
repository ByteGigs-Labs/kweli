"""Invoice actions shared by the REST routes and the agent's approved actions."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db.models import Agreement, Invoice
from audit.log import record
from paypal.auth import PayPalAuthError
from paypal.client import PayPalClient
from paypal.errors import PayPalError
from paypal.invoicing import InvoiceDraft, Invoicing, payer_view_url


@dataclass
class ServiceError(Exception):
    status: int
    message: str


def paypal_failure(error: PayPalError) -> ServiceError:
    if isinstance(error, PayPalAuthError):
        return ServiceError(
            503,
            "Kweli can't sign in to PayPal right now, so nothing was sent. "
            "Check the PayPal app credentials.",
        )
    detail = ", ".join(error.issues) or error.name or "unknown error"
    return ServiceError(502, f"PayPal didn't accept this ({detail}). Nothing was sent.")


def owned_agreement(db: Session, user_id: UUID, agreement_id: UUID) -> Agreement:
    agreement = db.scalar(
        select(Agreement)
        .options(selectinload(Agreement.client))
        .where(Agreement.id == agreement_id, Agreement.user_id == user_id)
    )
    if not agreement:
        raise ServiceError(404, "Agreement not found")
    return agreement


def owned_invoice(db: Session, user_id: UUID, invoice_id: UUID) -> Invoice:
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client))
        .where(Invoice.id == invoice_id, Invoice.user_id == user_id)
    )
    if not invoice:
        raise ServiceError(404, "Invoice not found")
    return invoice


def open_invoice_for(db: Session, agreement_id: UUID) -> Invoice | None:
    return db.scalar(
        select(Invoice).where(Invoice.agreement_id == agreement_id, Invoice.status != "cancelled")
    )


def check_can_invoice(agreement: Agreement) -> None:
    if agreement.status != "accepted":
        raise ServiceError(
            409, "The client hasn't accepted this agreement yet. Invoice it after they accept."
        )


def create_draft(
    db: Session,
    user_id: UUID,
    agreement: Agreement,
    paypal: PayPalClient,
    due_date: date | None = None,
    note: str | None = None,
) -> Invoice:
    """Create a PayPal draft for an accepted agreement. Idempotent per agreement. Commits."""
    check_can_invoice(agreement)
    existing = open_invoice_for(db, agreement.id)
    if existing:
        return existing
    invoice = Invoice(
        user_id=user_id,
        client_id=agreement.client_id,
        agreement_id=agreement.id,
        number="pending",
        description=agreement.title,
        amount_minor=agreement.amount_minor,
        currency=agreement.currency,
        due_date=due_date or agreement.due_date,
    )
    db.add(invoice)
    db.flush()
    invoicing = Invoicing(paypal)
    try:
        number = invoicing.next_invoice_number()
        draft = invoicing.create_draft(
            InvoiceDraft(
                invoice_number=number,
                currency=agreement.currency,
                recipient_email=agreement.client.email,
                recipient_name=agreement.client.name,
                item_name=agreement.title,
                item_description="; ".join(agreement.deliverables)[:1000],
                amount_minor=agreement.amount_minor,
                due_date=invoice.due_date,
                note=note or f"For the work agreed on {agreement.accepted_at:%d %b %Y}.",
            ),
            request_id=f"kweli-invoice-{invoice.id}",
        )
    except PayPalError as error:
        db.rollback()
        raise paypal_failure(error) from error
    invoice.number = number
    invoice.paypal_invoice_id = draft["id"]
    record(
        db,
        user_id,
        "invoice.drafted",
        {
            "invoice_id": str(invoice.id),
            "agreement_id": str(agreement.id),
            "paypal_invoice_id": invoice.paypal_invoice_id,
            "amount_minor": invoice.amount_minor,
            "currency": invoice.currency,
        },
    )
    db.commit()
    return invoice


def send(db: Session, user_id: UUID, invoice: Invoice, paypal: PayPalClient) -> Invoice:
    """PayPal emails the invoice to the client. Repeat calls change nothing. Commits."""
    if invoice.status != "draft":
        return invoice
    if not invoice.paypal_invoice_id:
        raise ServiceError(409, "This invoice has no PayPal draft yet")
    try:
        sent = Invoicing(paypal).send(
            invoice.paypal_invoice_id, request_id=f"kweli-send-{invoice.id}"
        )
    except PayPalError as error:
        raise paypal_failure(error) from error
    invoice.status = "sent"
    invoice.sent_at = datetime.now(UTC)
    invoice.payer_view_url = payer_view_url(sent)
    record(db, user_id, "invoice.sent", {"invoice_id": str(invoice.id)})
    db.commit()
    return invoice


def remind(db: Session, user_id: UUID, invoice: Invoice, paypal: PayPalClient) -> Invoice:
    if invoice.status not in ("sent", "partially_paid") or not invoice.paypal_invoice_id:
        raise ServiceError(409, "Only sent, unpaid invoices can get a reminder")
    try:
        Invoicing(paypal).remind(
            invoice.paypal_invoice_id,
            request_id=f"kweli-remind-{invoice.id}-{datetime.now(UTC):%Y%m%d}",
        )
    except PayPalError as error:
        raise paypal_failure(error) from error
    record(db, user_id, "invoice.reminded", {"invoice_id": str(invoice.id)})
    db.commit()
    return invoice
