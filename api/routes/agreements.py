from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.config import get_settings
from api.db.models import Agreement, Invoice, User
from api.db.session import get_db
from api.deps import get_extractor
from api.listing import ListParams, paginate
from api.schemas import AcceptLink, AgreementIn, AgreementOut, ThreadIn
from api.security import Principal, current_principal
from api.services.agreements import agreement_text, find_or_create_client, issue_accept_link
from api.services.billing import check_client_limit
from api.services.extract import EngagementDraft, Extractor, check_against_thread
from api.services.invoicing import ServiceError
from audit.log import record

router = APIRouter(prefix="/v1/agreements", tags=["agreements"])
SORTABLE = {"created_at": Agreement.created_at, "status": Agreement.status}


def owned_agreement(db: Session, principal: Principal, agreement_id: UUID) -> Agreement:
    agreement = db.scalar(
        select(Agreement)
        .options(selectinload(Agreement.client))
        .where(Agreement.id == agreement_id, Agreement.user_id == principal.user_id)
    )
    if not agreement:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agreement not found")
    return agreement


def _invoice_ids(db: Session, agreement_ids: list[UUID]) -> dict[UUID, UUID]:
    if not agreement_ids:
        return {}
    rows = db.execute(
        select(Invoice.agreement_id, Invoice.id)
        .where(Invoice.agreement_id.in_(agreement_ids), Invoice.status != "cancelled")
        .order_by(Invoice.created_at)
    )
    return {agreement_id: invoice_id for agreement_id, invoice_id in rows}


@router.post("/extract")
def extract(
    body: ThreadIn,
    principal: Principal = Depends(current_principal),
    extractor: Extractor | None = Depends(get_extractor),
) -> EngagementDraft:
    if extractor is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Reading threads with AI isn't set up here. Fill in the agreement by hand.",
        )
    thread = body.thread[: get_settings().max_thread_chars]
    try:
        raw = extractor.extract(thread)
    except Exception as error:  # noqa: BLE001 - any provider failure means "fill in by hand"
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The AI couldn't read this thread just now. Try again or fill it in by hand.",
        ) from error
    return check_against_thread(raw, thread)


@router.get("")
def list_agreements(
    response: Response,
    params: ListParams = Depends(),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[AgreementOut]:
    query = (
        select(Agreement)
        .options(selectinload(Agreement.client))
        .where(Agreement.user_id == principal.user_id)
    )
    rows = paginate(db, query, params, SORTABLE, "created_at", response)
    invoices = _invoice_ids(db, [row.id for row in rows])
    return [AgreementOut.build(row, invoices.get(row.id)) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_agreement(
    body: AgreementIn,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> AgreementOut:
    try:
        check_client_limit(db, db.get(User, principal.user_id), body.client.email)
    except ServiceError as error:
        raise HTTPException(error.status, error.message) from None
    client = find_or_create_client(
        db, principal.user_id, body.client.name, body.client.email, body.client.country
    )
    agreement = Agreement(
        user_id=principal.user_id,
        client_id=client.id,
        title=body.title,
        scope=body.scope,
        deliverables=body.deliverables,
        amount_minor=body.amount_minor(),
        currency=body.currency,
        due_date=body.due_date,
    )
    db.add(agreement)
    db.flush()
    record(
        db,
        principal.user_id,
        "agreement.created",
        {
            "agreement_id": str(agreement.id),
            "client_id": str(client.id),
            "amount_minor": agreement.amount_minor,
            "currency": agreement.currency,
        },
    )
    db.commit()
    return AgreementOut.build(owned_agreement(db, principal, agreement.id))


@router.get("/{agreement_id}")
def get_agreement(
    agreement_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    agreement = owned_agreement(db, principal, agreement_id)
    invoice_id = _invoice_ids(db, [agreement.id]).get(agreement.id)
    return {
        **AgreementOut.build(agreement, invoice_id).model_dump(mode="json"),
        "terms": agreement_text(agreement, principal.name),
    }


@router.post("/{agreement_id}/send")
def send_for_acceptance(
    agreement_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> AcceptLink:
    agreement = owned_agreement(db, principal, agreement_id)
    if agreement.status == "accepted":
        raise HTTPException(status.HTTP_409_CONFLICT, "The client has already accepted this")
    record(db, principal.user_id, "agreement.link_issued", {"agreement_id": str(agreement.id)})
    url, expires = issue_accept_link(db, agreement)
    return AcceptLink(url=url, expires_at=expires)
