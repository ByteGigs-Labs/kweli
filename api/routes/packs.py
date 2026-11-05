from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Pack, User
from api.db.session import get_db
from api.deps import get_letter_writer
from api.errors import error_body
from api.ratelimit import limit_by_key
from api.security import Principal, current_principal
from api.services.billing import pro_feature
from api.services.invoicing import ServiceError
from api.services.packs import LetterRejected, build, replace_letter
from packs.citations import MAX_CHARS
from packs.letter import LetterWriter

router = APIRouter(prefix="/v1/packs", tags=["packs"])
PACKS_PER_MINUTE = 5


class PackRequest(BaseModel):
    period_start: date
    period_end: date


class LetterRequest(BaseModel):
    letter: str = Field(min_length=1, max_length=MAX_CHARS + 500)


class PackSummaryOut(BaseModel):
    id: UUID
    period_start: date
    period_end: date
    letter_source: str
    payments: int
    statuses: dict[str, int]
    totals: list[dict]
    created_at: datetime
    updated_at: datetime | None
    pdf_document_id: UUID | None
    zip_document_id: UUID | None


class PackOut(PackSummaryOut):
    letter: str
    summary: dict


def _summary_out(pack: Pack) -> PackSummaryOut:
    summary = pack.summary or {}
    return PackSummaryOut(
        id=pack.id,
        period_start=pack.period_start,
        period_end=pack.period_end,
        letter_source=pack.letter_source,
        payments=summary.get("payments", 0),
        statuses=summary.get("statuses", {}),
        totals=summary.get("totals", []),
        created_at=pack.created_at,
        updated_at=pack.updated_at,
        pdf_document_id=pack.pdf_document_id,
        zip_document_id=pack.zip_document_id,
    )


def _out(pack: Pack) -> PackOut:
    public = {
        key: value for key, value in (pack.summary or {}).items() if key not in ("fingerprint",)
    }
    return PackOut(**_summary_out(pack).model_dump(), letter=pack.letter, summary=public)


def _owned(db: Session, principal: Principal, pack_id: UUID) -> Pack:
    pack = db.scalar(select(Pack).where(Pack.id == pack_id, Pack.user_id == principal.user_id))
    if not pack:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pack not found")
    return pack


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(pro_feature("Compliance Packs"))],
)
def create_pack(
    body: PackRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    writer: LetterWriter | None = Depends(get_letter_writer),
) -> PackOut:
    limit_by_key(db, "pack", str(principal.user_id), PACKS_PER_MINUTE)
    db.commit()
    user = db.get(User, principal.user_id)
    try:
        pack = build(db, user, body.period_start, body.period_end, writer)
    except ServiceError as error:
        db.rollback()
        raise HTTPException(error.status, error.message) from None
    db.commit()
    return _out(pack)


@router.get("")
def list_packs(
    principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
) -> list[PackSummaryOut]:
    rows = db.scalars(
        select(Pack)
        .where(Pack.user_id == principal.user_id)
        .order_by(Pack.created_at.desc())
        .limit(50)
    )
    return [_summary_out(pack) for pack in rows]


@router.get("/{pack_id}")
def get_pack(
    pack_id: UUID, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
) -> PackOut:
    return _out(_owned(db, principal, pack_id))


@router.put("/{pack_id}/letter", dependencies=[Depends(pro_feature("Compliance Packs"))])
def edit_letter(
    pack_id: UUID,
    body: LetterRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    pack = _owned(db, principal, pack_id)
    user = db.get(User, principal.user_id)
    try:
        replace_letter(db, user, pack, body.letter)
    except LetterRejected as rejected:
        db.rollback()
        return JSONResponse(
            error_body(
                "letter_rejected",
                "The letter didn't pass the checks, so the pack wasn't changed.",
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
    return _out(pack)
