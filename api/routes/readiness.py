from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db.session import get_db
from api.security import Principal, current_principal
from api.services.ledger import proofs_for_user
from proof.readiness import NEARLY_AT, READY_AT, assess

router = APIRouter(prefix="/v1/readiness", tags=["readiness"])


class StepOut(BaseModel):
    rule: str
    status: str
    problem: str
    fix: str


class FixOut(BaseModel):
    payment_id: UUID
    agreement_id: UUID | None
    client: str
    amount_minor: int
    currency: str
    received_at: datetime
    status: str
    points: int
    steps: list[StepOut]


class Total(BaseModel):
    currency: str
    amount_minor: int


class ClientOut(BaseModel):
    client: str
    payments: int
    totals: list[Total]
    statuses: dict[str, int]
    score: int | None


class ReadinessOut(BaseModel):
    score: int | None
    band: str
    thresholds: dict[str, int]
    payments: int
    statuses: dict[str, int]
    checks: dict[str, int]
    large_payments: int
    fix_total: int
    fix_next: list[FixOut]
    clients: list[ClientOut]


@router.get("")
def readiness(
    limit: int = Query(10, ge=1, le=50),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> ReadinessOut:
    result = assess(proofs_for_user(db, principal.user_id))
    return ReadinessOut(
        score=result.score,
        band=result.band,
        thresholds={"ready": READY_AT, "nearly": NEARLY_AT},
        payments=result.payments,
        statuses=result.statuses,
        checks=result.checks,
        large_payments=result.large_payments,
        fix_total=len(result.fix_next),
        fix_next=[
            FixOut(
                payment_id=item.payment_id,
                agreement_id=item.agreement_id,
                client=item.client,
                amount_minor=item.amount_minor,
                currency=item.currency,
                received_at=item.received_at,
                status=item.status,
                points=item.points,
                steps=[StepOut(**step.__dict__) for step in item.steps],
            )
            for item in result.fix_next[:limit]
        ],
        clients=[
            ClientOut(
                client=summary.client,
                payments=summary.payments,
                totals=[
                    Total(currency=c, amount_minor=a) for c, a in sorted(summary.totals.items())
                ],
                statuses=summary.statuses,
                score=summary.score,
            )
            for summary in result.clients
        ],
    )
