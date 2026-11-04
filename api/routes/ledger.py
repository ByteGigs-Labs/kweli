from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Agreement, Client, Document, Invoice, Payment, PaymentLink, ProofFlag
from api.db.session import get_db
from api.listing import ListParams, paginate
from api.security import Principal, current_principal
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


def _overall(statuses: list[str]) -> str:
    return max(statuses, key=SEVERITY.__getitem__) if statuses else "pending"


def _context(db: Session, payments: list[Payment]):
    ids = [payment.id for payment in payments]
    flags: dict[UUID, list[ProofFlag]] = {payment_id: [] for payment_id in ids}
    for flag in db.scalars(
        select(ProofFlag).where(ProofFlag.payment_id.in_(ids)).order_by(ProofFlag.rule)
    ):
        flags[flag.payment_id].append(flag)
    links = {
        link.payment_id: link
        for link in db.scalars(select(PaymentLink).where(PaymentLink.payment_id.in_(ids)))
    }
    agreement_ids = [link.agreement_id for link in links.values() if link.agreement_id]
    clients = dict(
        db.execute(
            select(Agreement.id, Client.name)
            .join(Client, Client.id == Agreement.client_id)
            .where(Agreement.id.in_(agreement_ids))
        ).all()
    )
    return flags, links, clients


def _row(payment: Payment, flags, links, clients) -> LedgerRow:
    link = links.get(payment.id)
    client = clients.get(link.agreement_id) if link and link.agreement_id else None
    own = flags.get(payment.id, [])
    return LedgerRow(
        id=payment.id,
        received_at=payment.received_at,
        client=client or payment.payer_name or payment.payer_email or "Unknown payer",
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
    flags, links, clients = _context(db, payments)
    return [_row(payment, flags, links, clients) for payment in payments]


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
    flags, links, clients = _context(db, [payment])
    row = _row(payment, flags, links, clients)
    link = links.get(payment.id)
    invoice = db.get(Invoice, link.invoice_id) if link and link.invoice_id else None
    agreement = db.get(Agreement, link.agreement_id) if link and link.agreement_id else None
    deliverable = (
        db.get(Document, link.deliverable_document_id)
        if link and link.deliverable_document_id
        else None
    )
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
        flags=[Flag.model_validate(flag, from_attributes=True) for flag in flags[payment.id]],
        chain=chain,
        agreement_id=agreement.id if agreement else None,
        invoice_number=invoice.number if invoice else None,
    )
