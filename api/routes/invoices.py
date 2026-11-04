from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Invoice
from api.db.session import get_db
from api.deps import get_paypal
from api.listing import ListParams, paginate
from api.schemas import InvoiceIn, InvoiceOut
from api.security import Principal, current_principal
from api.services import invoicing
from api.services.invoicing import ServiceError
from paypal.client import PayPalClient

router = APIRouter(prefix="/v1/invoices", tags=["invoices"])
SORTABLE = {"created_at": Invoice.created_at, "status": Invoice.status}


def _http(error: ServiceError) -> HTTPException:
    return HTTPException(error.status, error.message)


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
    try:
        return InvoiceOut.model_validate(invoicing.owned_invoice(db, principal.user_id, invoice_id))
    except ServiceError as error:
        raise _http(error) from None


@router.post("", status_code=201)
def create_invoice(
    body: InvoiceIn,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> InvoiceOut:
    """Create a PayPal draft for an accepted agreement. Nothing is sent to the client yet."""
    try:
        agreement = invoicing.owned_agreement(db, principal.user_id, body.agreement_id)
        invoice = invoicing.create_draft(
            db, principal.user_id, agreement, paypal, body.due_date, body.note
        )
    except ServiceError as error:
        raise _http(error) from None
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/send")
def send_invoice(
    invoice_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> InvoiceOut:
    """The freelancer's explicit approval: PayPal emails the invoice to the client."""
    try:
        invoice = invoicing.owned_invoice(db, principal.user_id, invoice_id)
        invoice = invoicing.send(db, principal.user_id, invoice, paypal)
    except ServiceError as error:
        raise _http(error) from None
    return InvoiceOut.model_validate(invoice)
