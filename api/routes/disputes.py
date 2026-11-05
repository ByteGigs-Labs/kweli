from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Agreement, Client, Dispute, Payment, PaymentLink, User
from api.db.session import get_db
from api.deps import get_paypal, get_response_writer
from api.errors import error_body
from api.ratelimit import limit_by_key
from api.security import Principal, current_principal
from api.services import disputes as service
from api.services.billing import pro_feature
from api.services.invoicing import ServiceError
from defender.evidence import EvidenceItem, plan, reason_label, strength
from defender.response import MAX_NOTES
from paypal.client import PayPalClient
from paypal.errors import PayPalError, PayPalUnavailable

router = APIRouter(prefix="/v1/disputes", tags=["disputes"])
ACTIONS_PER_MINUTE = 10
PRO = Depends(pro_feature("The dispute defender"))


class FileOut(BaseModel):
    name: str
    source: str


class EvidenceOut(BaseModel):
    key: str
    label: str
    why: str
    evidence_type: str
    status: str
    detail: str
    fix: str | None
    notes: list[str]
    files: list[FileOut]


class DisputeSummary(BaseModel):
    id: UUID
    paypal_dispute_id: str
    reason: str
    reason_label: str
    status: str
    amount_minor: int
    currency: str
    client: str | None
    payment_id: UUID | None
    agreement_id: UUID | None
    evidence_due_at: datetime | None
    outcome: str | None
    submitted_at: datetime | None
    source: str
    created_at: datetime


class DisputeOut(DisputeSummary):
    stage: str | None
    allowed: list[str]
    buyer_messages: list[dict]
    response: str | None
    response_source: str | None
    rejected: list[dict]
    evidence: list[EvidenceOut]
    strength: str
    submission: dict | None
    approval_expires_at: datetime | None
    sandbox_tools: bool
    approval_token: str | None = None


class ResponseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_NOTES + 200)


class SubmitRequest(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class SandboxRequest(BaseModel):
    action: Literal["require_evidence", "seller_favor", "buyer_favor"]


def _context(db: Session, disputes: list[Dispute]) -> dict[UUID, tuple[str | None, UUID | None]]:
    payment_ids = [d.payment_id for d in disputes if d.payment_id]
    if not payment_ids:
        return {}
    rows = db.execute(
        select(Payment.id, Client.name, Agreement.id, Payment.payer_name, Payment.payer_email)
        .outerjoin(PaymentLink, PaymentLink.payment_id == Payment.id)
        .outerjoin(Agreement, Agreement.id == PaymentLink.agreement_id)
        .outerjoin(Client, Client.id == Agreement.client_id)
        .where(Payment.id.in_(payment_ids))
    ).all()
    return {
        payment_id: (client or payer_name or payer_email, agreement_id)
        for payment_id, client, agreement_id, payer_name, payer_email in rows
    }


def _summary(dispute: Dispute, context) -> DisputeSummary:
    client, agreement_id = context.get(dispute.payment_id, (None, None))
    return DisputeSummary(
        id=dispute.id,
        paypal_dispute_id=dispute.paypal_dispute_id,
        reason=dispute.reason,
        reason_label=reason_label(dispute.reason),
        status=dispute.status,
        amount_minor=dispute.amount_minor,
        currency=dispute.currency,
        client=client,
        payment_id=dispute.payment_id,
        agreement_id=agreement_id,
        evidence_due_at=dispute.evidence_due_at,
        outcome=dispute.outcome,
        submitted_at=dispute.submitted_at,
        source=dispute.source,
        created_at=dispute.created_at,
    )


def _evidence(items: list[EvidenceItem]) -> list[EvidenceOut]:
    return [
        EvidenceOut(
            key=item.key,
            label=item.label,
            why=item.why,
            evidence_type=item.evidence_type,
            status=item.status,
            detail=item.detail,
            fix=item.fix,
            notes=list(item.notes),
            files=[FileOut(name=f.name, source=f.source) for f in item.files],
        )
        for item in items
    ]


def _out(
    db: Session, user: User, dispute: Dispute, items: list[EvidenceItem] | None = None, token=None
) -> DisputeOut:
    items = items if items is not None else plan(service.facts_for(db, user, dispute))
    live_approval = bool(dispute.approval_token_hash)
    return DisputeOut(
        **_summary(dispute, _context(db, [dispute])).model_dump(),
        stage=dispute.stage,
        allowed=list(dispute.allowed or []),
        buyer_messages=list(dispute.buyer_messages or []),
        response=dispute.response,
        response_source=dispute.response_source,
        rejected=list(dispute.rejected or []),
        evidence=_evidence(items),
        strength=strength(items),
        submission=dispute.submission,
        approval_expires_at=dispute.approval_expires_at if live_approval else None,
        sandbox_tools=get_settings().paypal_env == "sandbox" and dispute.source != "seed",
        approval_token=token,
    )


def _owned(db: Session, principal: Principal, dispute_id: UUID, lock: bool = False) -> Dispute:
    query = select(Dispute).where(Dispute.id == dispute_id, Dispute.user_id == principal.user_id)
    if lock:
        query = query.with_for_update()
    dispute = db.scalar(query)
    if not dispute:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    return dispute


def _paypal_failure(error: PayPalError) -> HTTPException:
    if isinstance(error, PayPalUnavailable) or error.status in (401, 403):
        return HTTPException(503, "PayPal isn't reachable right now. Try again in a minute.")
    return HTTPException(502, f"PayPal refused the request ({error.status}).")


@router.get("")
def list_disputes(
    principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
) -> list[DisputeSummary]:
    rows = list(
        db.scalars(
            select(Dispute)
            .where(Dispute.user_id == principal.user_id)
            .order_by(Dispute.resolved_at.is_not(None), Dispute.evidence_due_at, Dispute.created_at)
            .limit(100)
        )
    )
    context = _context(db, rows)
    return [_summary(row, context) for row in rows]


@router.get("/{dispute_id}")
def get_dispute(
    dispute_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> DisputeOut:
    dispute = _owned(db, principal, dispute_id)
    return _out(db, db.get(User, principal.user_id), dispute)


@router.post("/{dispute_id}/prepare", dependencies=[PRO])
def prepare(
    dispute_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    writer=Depends(get_response_writer),
) -> DisputeOut:
    limit_by_key(db, "dispute", str(principal.user_id), ACTIONS_PER_MINUTE)
    dispute = _owned(db, principal, dispute_id, lock=True)
    user = db.get(User, principal.user_id)
    try:
        items, token = service.prepare(db, user, dispute, writer)
    except ServiceError as error:
        db.rollback()
        raise HTTPException(error.status, error.message) from None
    db.commit()
    return _out(db, user, dispute, items, token)


@router.put("/{dispute_id}/response", dependencies=[PRO])
def edit_response(
    dispute_id: UUID,
    body: ResponseRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    dispute = _owned(db, principal, dispute_id, lock=True)
    user = db.get(User, principal.user_id)
    try:
        items, token = service.edit(db, user, dispute, body.text)
    except service.ResponseRejected as rejected:
        db.rollback()
        return JSONResponse(
            error_body(
                "response_rejected",
                "The response didn't pass the checks, so it wasn't saved.",
                problems=[
                    {"code": p.code, "message": p.message, "excerpt": p.excerpt}
                    for p in rejected.problems
                ],
            ),
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except ServiceError as error:
        db.rollback()
        raise HTTPException(error.status, error.message) from None
    db.commit()
    return _out(db, user, dispute, items, token)


@router.post("/{dispute_id}/approval", dependencies=[PRO])
def approval(
    dispute_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> DisputeOut:
    dispute = _owned(db, principal, dispute_id, lock=True)
    user = db.get(User, principal.user_id)
    try:
        items, token = service.approve_current(db, user, dispute)
    except service.ResponseRejected:
        db.rollback()
        raise HTTPException(409, "Edit the response so it passes the checks first.") from None
    except ServiceError as error:
        db.rollback()
        raise HTTPException(error.status, error.message) from None
    db.commit()
    return _out(db, user, dispute, items, token)


@router.post("/{dispute_id}/submit", dependencies=[PRO])
def submit(
    dispute_id: UUID,
    body: SubmitRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> DisputeOut:
    limit_by_key(db, "dispute", str(principal.user_id), ACTIONS_PER_MINUTE)
    dispute = _owned(db, principal, dispute_id, lock=True)
    user = db.get(User, principal.user_id)
    try:
        service.submit(db, user, dispute, body.token, paypal)
    except ServiceError as error:
        db.rollback()
        raise HTTPException(error.status, error.message) from None
    except PayPalError as error:
        db.rollback()
        raise _paypal_failure(error) from None
    db.commit()
    return _out(db, user, dispute)


@router.post("/{dispute_id}/refresh")
def refresh(
    dispute_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> DisputeOut:
    limit_by_key(db, "dispute", str(principal.user_id), ACTIONS_PER_MINUTE)
    dispute = _owned(db, principal, dispute_id, lock=True)
    try:
        service.refresh(db, dispute, paypal)
    except PayPalError as error:
        db.rollback()
        raise _paypal_failure(error) from None
    db.commit()
    return _out(db, db.get(User, principal.user_id), dispute)


@router.post("/{dispute_id}/sandbox")
def sandbox(
    dispute_id: UUID,
    body: SandboxRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> DisputeOut:
    limit_by_key(db, "dispute", str(principal.user_id), ACTIONS_PER_MINUTE)
    dispute = _owned(db, principal, dispute_id, lock=True)
    user = db.get(User, principal.user_id)
    try:
        service.sandbox_action(db, user, dispute, body.action, paypal)
    except ServiceError as error:
        db.rollback()
        raise HTTPException(error.status, error.message) from None
    except PayPalError as error:
        db.rollback()
        raise _paypal_failure(error) from None
    db.commit()
    return _out(db, user, dispute)
