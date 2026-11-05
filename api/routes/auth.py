from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.session import get_db
from api.ratelimit import (
    clear_login_failures,
    ensure_account_not_locked,
    login_ip_limit,
    record_login_failure,
)
from api.security import (
    Principal,
    authenticate,
    create_session,
    current_principal,
    end_session,
    normalise_email,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class Identity(BaseModel):
    id: UUID
    email: str
    name: str
    plan: str


def _cookie_options() -> dict:
    return {
        "path": "/",
        "httponly": True,
        "secure": get_settings().cookie_secure,
        "samesite": "strict",
    }


@router.post("/login", dependencies=[Depends(login_ip_limit)])
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> Identity:
    email = normalise_email(body.email)
    ensure_account_not_locked(db, email)
    user = authenticate(db, email, body.password)
    if not user:
        record_login_failure(db, email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    clear_login_failures(db, email)
    settings = get_settings()
    response.set_cookie(
        settings.cookie_name,
        create_session(db, user),
        max_age=settings.session_ttl_hours * 3600,
        **_cookie_options(),
    )
    return Identity(id=user.id, email=user.email, name=user.name, plan=effective_plan(user.plan))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    name = get_settings().cookie_name
    if token := request.cookies.get(name):
        end_session(db, token)
    response.delete_cookie(name, **_cookie_options())


@router.get("/me")
def me(principal: Principal = Depends(current_principal)) -> Identity:
    return Identity(
        id=principal.user_id,
        email=principal.email,
        name=principal.name,
        plan=effective_plan(principal.plan),
    )


def effective_plan(stored: str) -> str:
    """What the account can use: everything is open until billing is switched on."""
    from api.services.billing import billing_enabled

    return stored if billing_enabled() else "pro"
