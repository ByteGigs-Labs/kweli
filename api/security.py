import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import User, UserSession
from api.db.session import get_db

MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str
    name: str
    plan: str


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def normalise_email(email: str) -> str:
    return email.strip().lower()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalise_email(email)))
    password_ok = verify_password(user.password_hash if user else _DUMMY_HASH, password)
    return user if user and user.is_active and password_ok else None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    expires = now + timedelta(hours=get_settings().session_ttl_hours)
    db.add(UserSession(user_id=user.id, token_hash=token_hash(token), expires_at=expires))
    db.commit()
    return token


def end_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == token_hash(token)))
    db.commit()


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        raise unauthorized
    user = db.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash(token),
            UserSession.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
    )
    if not user:
        raise unauthorized
    return Principal(user.id, user.email, user.name, user.plan)
