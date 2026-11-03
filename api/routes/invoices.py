from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db.models import Agreement, Invoice
from api.db.session import get_db
from api.deps import get_paypal
from api.listing import ListParams, paginate
from api.schemas import InvoiceIn, InvoiceOut
from api.security import Principal, current_principal
from paypal.auth import PayPalAuthError
from paypal.client import PayPalClient
from paypal.errors import PayPalError
from paypal.invoicing import InvoiceDraft, Invoicing, payer_view_url

router = APIRouter(prefix="/v1/invoices", tags=["invoices"])
SORTABLE = {"created_at": Invoice.created_at, "status": Invoice.status}


def _paypal_failure(error: PayPalError) -> HTTPException:
    if isinstance(error, PayPalAuthError):
        return HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Kweli can't sign in to PayPal right now, so nothing was sent. "
            "Check the PayPal app credentials.",
        )
    detail = ", ".join(error.issues) or error.name or "unknown error"
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY, f"PayPal didn't accept this ({detail}). Nothing was sent."
    )


def owned_invoice(db: Session, principal: Principal, invoice_id: UUID) -> Invoice:
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.client))
        .where(Invoice.id == invoice_id, Invoice.user_id == principal.user_id)
    )
    if not invoice:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return invoice


@router.get("")
def list_invoices(
    response: Response,
    params: ListParams = Depends(),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[InvoiceOut]:
    query = select(Invoice).where(Invoice.user_id == principal.user_id)
    rows = paginate(db, query, params, SORTABLE, "created_at", response)
    return [InvoiceOut.model_validate(row) for row in rows]


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> InvoiceOut:
    return InvoiceOut.model_validate(owned_invoice(db, principal, invoice_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(
    body: InvoiceIn,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> InvoiceOut:
    """Create a PayPal draft for an accepted agreement. Nothing is sent to the client yet."""
    agreement = db.scalar(
        select(Agreement)
        .options(selectinload(Agreement.client))
        .where(Agreement.id == body.agreement_id, Agreement.user_id == principal.user_id)
    )
    if not agreement:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agreement not found")
    if agreement.status != "accepted":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The client hasn't accepted this agreement yet. Invoice it after they accept.",
        )
    existing = db.scalar(
        select(Invoice).where(Invoice.agreement_id == agreement.id, Invoice.status != "cancelled")
    )
    if existing:
        return InvoiceOut.model_validate(existing)

    invoice = Invoice(
        user_id=principal.user_id,
        client_id=agreement.client_id,
        agreement_id=agreement.id,
        number="pending",
        description=agreement.title,
        amount_minor=agreement.amount_minor,
        currency=agreement.currency,
        due_date=body.due_date or agreement.due_date,
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
                note=body.note or f"For the work agreed on {agreement.accepted_at:%d %b %Y}.",
            ),
            request_id=f"kweli-invoice-{invoice.id}",
        )
    except PayPalError as error:
        db.rollback()
        raise _paypal_failure(error) from error
    invoice.number = number
    invoice.paypal_invoice_id = draft["id"]
    db.commit()
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/send")
def send_invoice(
    invoice_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> InvoiceOut:
    """The freelancer's explicit approval: PayPal emails the invoice to the client."""
    invoice = owned_invoice(db, principal, invoice_id)
    if invoice.status != "draft":
        return InvoiceOut.model_validate(invoice)
    if not invoice.paypal_invoice_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has no PayPal draft yet")
    try:
        sent = Invoicing(paypal).send(
            invoice.paypal_invoice_id, request_id=f"kweli-send-{invoice.id}"
        )
    except PayPalError as error:
        raise _paypal_failure(error) from error
    invoice.status = "sent"
    invoice.sent_at = datetime.now(UTC)
    invoice.payer_view_url = payer_view_url(sent)
    db.commit()
    return InvoiceOut.model_validate(invoice)
