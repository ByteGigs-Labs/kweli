from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import User
from api.db.session import get_db
from api.ratelimit import limit_by_ip
from api.services.agreements import accept, agreement_for_token, agreement_text, link_is_live
from paypal.money import to_paypal_value

router = APIRouter(prefix="/v1/portal", tags=["client portal"])


class PortalAgreement(BaseModel):
    freelancer: str
    client: str
    title: str
    deliverables: list[str]
    amount: str
    currency: str
    due_date: date | None
    terms: list[str]
    status: str
    accepted_at: datetime | None


class AcceptIn(BaseModel):
    """A JSON body, so a cross-site HTML form can't submit acceptance."""

    model_config = ConfigDict(extra="forbid")

    accept: Literal[True]


def _portal_limit(request: Request, db: Session = Depends(get_db)) -> None:
    limit_by_ip(db, request, "portal", get_settings().portal_ip_per_minute)


def _load(db: Session, token: str):
    agreement = agreement_for_token(db, token)
    if not agreement:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link isn't valid.")
    if agreement.status != "accepted" and not link_is_live(agreement):
        raise HTTPException(
            status.HTTP_410_GONE, "This link has expired. Ask the freelancer for a new one."
        )
    return agreement


def _view(db: Session, agreement) -> PortalAgreement:
    freelancer = db.get(User, agreement.user_id).name
    return PortalAgreement(
        freelancer=freelancer,
        client=agreement.client.name,
        title=agreement.title,
        deliverables=agreement.deliverables,
        amount=to_paypal_value(agreement.amount_minor, agreement.currency),
        currency=agreement.currency,
        due_date=agreement.due_date,
        terms=agreement_text(agreement, freelancer),
        status=agreement.status,
        accepted_at=agreement.accepted_at,
    )


@router.get("/agreements/{token}", dependencies=[Depends(_portal_limit)])
def view_agreement(token: str, db: Session = Depends(get_db)) -> PortalAgreement:
    return _view(db, _load(db, token))


@router.post("/agreements/{token}/accept", dependencies=[Depends(_portal_limit)])
def accept_agreement(
    token: str, body: AcceptIn, request: Request, db: Session = Depends(get_db)
) -> PortalAgreement:
    agreement = _load(db, token)
    if agreement.status != "accepted":
        ip = request.client.host if request.client else "unknown"
        accept(db, agreement, ip, request.headers.get("user-agent", ""))
    return _view(db, agreement)
