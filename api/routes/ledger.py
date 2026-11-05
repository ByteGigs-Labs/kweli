from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Agreement, Document, Invoice, Payment
from api.db.session import get_db
from api.listing import ListParams, paginate
from api.security import Principal, current_principal
from api.services.ledger import LedgerContext, load_context
from audit.log import record
from proof.engine import evaluate_payment, latest_document
from proof.rules import SEVERITY

router = APIRouter(prefix="/v1/ledger", tags=["ledger"])
SORTABLE = {"received_at": Payment.received_at, "amount_minor": Payment.amount_minor}


class Flag(BaseModel):
    rule: str
    status: str
    explanation: str
    fix: str | None


class LedgerRow(BaseModel):
    id: UUID
    received_at: datetime
    client: str
    amount_minor: int
    currency: str
    rules: dict[str, str]
    status: str


class ChainStep(BaseModel):
    name: str
    proven: bool
    detail: str


class LedgerDetail(LedgerRow):
    payer: str | None
    payment_type: str
    flags: list[Flag]
    chain: list[ChainStep]
    agreement_id: UUID | None
    invoice_number: str | None
    linked_by: str | None
    payer_confirmation: str | None


class LinkRequest(BaseModel):
    agreement_id: UUID | None


def _overall(statuses: list[str]) -> str:
    return max(statuses, key=SEVERITY.__getitem__) if statuses else "pending"


def _row(payment: Payment, context: LedgerContext) -> LedgerRow:
    own = context.flags.get(payment.id, [])
    return LedgerRow(
        id=payment.id,
        received_at=payment.received_at,
        client=context.client_for(payment),
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        rules={flag.rule: flag.status for flag in own},
        status=_overall([flag.status for flag in own]),
    )


@router.get("")
def list_ledger(
    response: Response,
    params: ListParams = Depends(),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[LedgerRow]:
    query = select(Payment).where(Payment.user_id == principal.user_id)
    payments = paginate(db, query, params, SORTABLE, "received_at", response)
    context = load_context(db, payments)
    return [_row(payment, context) for payment in payments]


@router.get("/{payment_id}")
def ledger_detail(
    payment_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> LedgerDetail:
    payment = db.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.user_id == principal.user_id)
    )
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    context = load_context(db, [payment])
    row = _row(payment, context)
    link = context.links.get(payment.id)
    invoice = db.get(Invoice, link.invoice_id) if link and link.invoice_id else None
    agreement = db.get(Agreement, link.agreement_id) if link and link.agreement_id else None
    deliverable = (
        db.get(Document, link.deliverable_document_id)
        if link and link.deliverable_document_id
        else None
    )
    confirmation = latest_document(db, agreement.id, "payer_confirmation") if agreement else None
    accepted = bool(agreement and agreement.accepted_at)
    chain = [
        ChainStep(
            name="Agreement",
            proven=accepted,
            detail=f"Accepted {agreement.accepted_at:%d %b}"
            if accepted
            else ("Not accepted" if agreement else "None on file"),
        ),
        ChainStep(
            name="Invoice",
            proven=invoice is not None,
            detail=f"No. {invoice.number}" if invoice else "Not invoiced",
        ),
        ChainStep(name="Payment", proven=True, detail=f"Paid {payment.received_at:%d %b}"),
        ChainStep(
            name="Deliverable",
            proven=deliverable is not None,
            detail="On file" if deliverable else "Not uploaded",
        ),
    ]
    return LedgerDetail(
        **row.model_dump(),
        payer=payment.payer_name or payment.payer_email,
        payment_type=payment.payment_type,
        flags=[
            Flag.model_validate(flag, from_attributes=True) for flag in context.flags[payment.id]
        ],
        chain=chain,
        agreement_id=agreement.id if agreement else None,
        invoice_number=invoice.number if invoice else None,
        linked_by=("invoice" if invoice and agreement else "hand") if agreement else None,
        payer_confirmation=confirmation.filename if confirmation else None,
    )


@router.post("/{payment_id}/agreement")
def link_agreement(
    payment_id: UUID,
    body: LinkRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> LedgerDetail:
    """Link a payment that didn't come through a Kweli invoice to its agreement (or unlink)."""
    payment = db.scalar(
        select(Payment)
        .where(Payment.id == payment_id, Payment.user_id == principal.user_id)
        .with_for_update()
    )
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if payment.paypal_invoice_id and db.scalar(
        select(Invoice.id).where(
            Invoice.user_id == principal.user_id,
            Invoice.paypal_invoice_id == payment.paypal_invoice_id,
        )
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This payment's invoice already links it to an agreement."
        )
    if body.agreement_id and not db.scalar(
        select(Agreement.id).where(
            Agreement.id == body.agreement_id, Agreement.user_id == principal.user_id
        )
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agreement not found")
    previous = payment.agreement_id
    payment.agreement_id = body.agreement_id
    record(
        db,
        principal.user_id,
        "payment.linked" if body.agreement_id else "payment.unlinked",
        {
            "payment_id": str(payment.id),
            "agreement_id": str(body.agreement_id) if body.agreement_id else None,
            "previous_agreement_id": str(previous) if previous else None,
        },
    )
    evaluate_payment(db, payment)
    db.commit()
    return ledger_detail(payment_id, principal, db)
