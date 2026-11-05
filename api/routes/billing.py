from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import User
from api.db.session import get_db
from api.deps import get_paypal
from api.ratelimit import limit_by_key
from api.security import Principal, current_principal
from api.services import billing
from api.services.invoicing import ServiceError
from paypal.client import PayPalClient
from paypal.errors import PayPalError, PayPalUnavailable

router = APIRouter(prefix="/v1/billing", tags=["billing"])
PER_MINUTE = 6


class BillingOut(BaseModel):
    plan: str
    enabled: bool
    price: str
    currency: str
    features: list[str]
    free_client_limit: int
    subscription_status: str | None
    next_billing_at: datetime | None


class CheckoutOut(BaseModel):
    approve_url: str


class ConfirmRequest(BaseModel):
    subscription_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


def _out(db: Session, user: User) -> BillingOut:
    settings = get_settings()
    subscription = billing.current(db, user)
    return BillingOut(
        plan="pro" if billing.is_pro(user) else "free",
        enabled=billing.billing_enabled(),
        price=settings.pro_price,
        currency=settings.pro_currency,
        features=list(billing.PRO_FEATURES),
        free_client_limit=billing.FREE_CLIENT_LIMIT,
        subscription_status=subscription.status if subscription else None,
        next_billing_at=subscription.next_billing_at if subscription else None,
    )


def _paypal_error(error: PayPalError) -> HTTPException:
    if isinstance(error, PayPalUnavailable) or error.status in (401, 403):
        return HTTPException(503, "PayPal isn't reachable right now. Try again in a minute.")
    if error.status == 404:
        return HTTPException(404, "PayPal doesn't know that subscription.")
    return HTTPException(502, f"PayPal refused the request ({error.status}).")


def _run(db: Session, action):
    try:
        result = action()
    except ServiceError as error:
        db.rollback()
        raise HTTPException(error.status, error.message) from None
    except PayPalError as error:
        db.rollback()
        raise _paypal_error(error) from None
    db.commit()
    return result


@router.get("")
def get_billing(
    principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
) -> BillingOut:
    return _out(db, db.get(User, principal.user_id))


@router.post("/checkout")
def checkout(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> CheckoutOut:
    limit_by_key(db, "billing", str(principal.user_id), PER_MINUTE)
    user = db.get(User, principal.user_id)
    return CheckoutOut(approve_url=_run(db, lambda: billing.checkout(db, user, paypal)))


@router.post("/confirm")
def confirm(
    body: ConfirmRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> BillingOut:
    limit_by_key(db, "billing", str(principal.user_id), PER_MINUTE)
    user = db.get(User, principal.user_id)
    _run(db, lambda: billing.confirm(db, user, paypal, body.subscription_id))
    return _out(db, user)


@router.post("/cancel")
def cancel(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> BillingOut:
    limit_by_key(db, "billing", str(principal.user_id), PER_MINUTE)
    user = db.get(User, principal.user_id)
    _run(db, lambda: billing.cancel(db, user, paypal))
    return _out(db, user)
