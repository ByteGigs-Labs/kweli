import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import LoginAttempt
from api.db.session import get_db

RETENTION = timedelta(hours=1)


def _key(kind: str, value: str) -> str:
    return hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()


def _count_since(db: Session, key: str, window: timedelta) -> int:
    since = datetime.now(UTC) - window
    return db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.key == key, LoginAttempt.attempted_at > since)
    )


def _record(db: Session, key: str) -> None:
    db.execute(
        delete(LoginAttempt).where(LoginAttempt.attempted_at < datetime.now(UTC) - RETENTION)
    )
    db.add(LoginAttempt(key=key))
    db.commit()


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many login attempts. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


def login_ip_limit(request: Request, db: Session = Depends(get_db)) -> None:
    ip = request.client.host if request.client else "unknown"
    key = _key("ip", ip)
    if _count_since(db, key, timedelta(minutes=1)) >= get_settings().login_ip_per_minute:
        raise _too_many(60)
    _record(db, key)


def ensure_account_not_locked(db: Session, email: str) -> None:
    limit = get_settings().login_account_failures_per_15_minutes
    if _count_since(db, _key("account", email), timedelta(minutes=15)) >= limit:
        raise _too_many(900)


def record_login_failure(db: Session, email: str) -> None:
    _record(db, _key("account", email))


def clear_login_failures(db: Session, email: str) -> None:
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == _key("account", email)))
    db.commit()
