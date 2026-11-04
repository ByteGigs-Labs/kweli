from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db.session import get_db
from api.security import Principal, current_principal
from audit.log import verify

router = APIRouter(prefix="/v1/audit", tags=["audit"])


class ChainOut(BaseModel):
    ok: bool
    entries: int
    head: str
    broken_at: int | None


@router.get("/verify")
def verify_chain(
    principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
) -> ChainOut:
    status = verify(db, principal.user_id)
    return ChainOut(
        ok=status.ok, entries=status.entries, head=status.head, broken_at=status.broken_at
    )
