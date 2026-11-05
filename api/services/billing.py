"""Kweli Pro through PayPal Subscriptions.

- Billing is on only when PAYPAL_PLAN_ID is set. Until then every feature is open, so local
  development, tests and a fresh deploy work before the plan exists.
- The plan is never trusted from the browser. Kweli reads the subscription back from PayPal and
  checks that it is for Kweli's own plan and was created for this user (custom_id), so a
  subscription ID from someone else's checkout can't unlock Pro.
- Webhooks (BILLING.SUBSCRIPTION.*) keep the plan in step afterwards, also by re-reading.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Client, Subscription, User
from api.services.invoicing import ServiceError
from api.services.payments import Outcome, _when
from audit.log import record
from paypal.subscriptions import Subscriptions, approve_link

PRO_STATUSES = frozenset({"APPROVED", "ACTIVE"})
FREE_CLIENT_LIMIT = 3
PRO_FEATURES = ("Compliance Packs", "Dispute defender", "Unlimited clients")


def billing_enabled() -> bool:
    return bool(get_settings().paypal_plan_id)


def is_pro(user: User) -> bool:
    return not billing_enabled() or user.plan == "pro"


def require_pro(user: User, feature: str) -> None:
    if not is_pro(user):
        raise ServiceError(402, f"{feature} is part of Kweli Pro. Upgrade on the Billing page.")


def check_client_limit(db: Session, user: User, client_email: str) -> None:
    if is_pro(user):
        return
    existing = db.scalars(select(Client.email).where(Client.user_id == user.id)).all()
    if client_email.lower() in {email.lower() for email in existing}:
        return
    if len(existing) >= FREE_CLIENT_LIMIT:
        raise ServiceError(
            402, f"The free plan covers {FREE_CLIENT_LIMIT} clients. Upgrade to Kweli Pro for more."
        )


def _set_plan(db: Session, user: User, subscription: Subscription, reason: str) -> None:
    plan = "pro" if subscription.status in PRO_STATUSES else "free"
    if user.plan == plan:
        return
    user.plan = plan
    record(
        db,
        user.id,
        "billing.plan_changed",
        {
            "plan": plan,
            "subscription_id": subscription.paypal_subscription_id,
            "status": subscription.status,
            "reason": reason,
        },
    )


def _apply(subscription: Subscription, remote: dict) -> None:
    subscription.status = str(remote.get("status") or "APPROVAL_PENDING")[:20]
    subscription.plan_id = str(remote.get("plan_id") or subscription.plan_id)[:64]
    next_billing = (remote.get("billing_info") or {}).get("next_billing_time")
    subscription.next_billing_at = _when(next_billing) if next_billing else None
    subscription.updated_at = datetime.now(UTC)


def checkout(db: Session, user: User, paypal) -> str:
    """Create the subscription at PayPal and return the link where the freelancer approves it."""
    settings = get_settings()
    if not billing_enabled():
        raise ServiceError(409, "Billing isn't set up on this server yet.")
    if user.plan == "pro":
        raise ServiceError(409, "You're already on Kweli Pro.")
    web = settings.public_web_url.rstrip("/")
    remote = Subscriptions(paypal).create(
        settings.paypal_plan_id,
        str(user.id),
        f"{web}/billing?paypal=approved",
        f"{web}/billing?paypal=cancelled",
        request_id=f"kweli-pro-{user.id}-{datetime.now(UTC):%Y%m%d%H%M}",
    )
    link = approve_link(remote)
    if not remote.get("id") or not link or not link.startswith("https://"):
        raise ServiceError(502, "PayPal didn't return an approval link. Try again.")
    subscription = db.scalar(
        select(Subscription).where(Subscription.paypal_subscription_id == remote["id"])
    ) or Subscription(user_id=user.id, paypal_subscription_id=str(remote["id"])[:64])
    subscription.plan_id = settings.paypal_plan_id
    subscription.status = str(remote.get("status") or "APPROVAL_PENDING")[:20]
    db.add(subscription)
    record(db, user.id, "billing.checkout_started", {"subscription_id": remote["id"]})
    return link


def confirm(db: Session, user: User, paypal, subscription_id: str) -> Subscription:
    """After PayPal sends the freelancer back: verify the subscription, then switch on Pro."""
    remote = Subscriptions(paypal).get(subscription_id)
    if remote.get("plan_id") != get_settings().paypal_plan_id:
        raise ServiceError(422, "That subscription isn't for Kweli Pro.")
    if remote.get("custom_id") != str(user.id):
        raise ServiceError(403, "That subscription belongs to another account.")
    subscription = db.scalar(
        select(Subscription).where(Subscription.paypal_subscription_id == subscription_id)
    )
    if subscription and subscription.user_id != user.id:
        raise ServiceError(403, "That subscription belongs to another account.")
    if not subscription:
        subscription = Subscription(
            user_id=user.id, paypal_subscription_id=subscription_id, plan_id="", status=""
        )
        db.add(subscription)
    _apply(subscription, remote)
    _set_plan(db, user, subscription, "checkout")
    return subscription


def cancel(db: Session, user: User, paypal) -> Subscription:
    subscription = current(db, user)
    if not subscription or subscription.status not in PRO_STATUSES:
        raise ServiceError(409, "There's no active subscription to cancel.")
    client = Subscriptions(paypal)
    client.cancel(
        subscription.paypal_subscription_id,
        "Cancelled by the freelancer in Kweli",
        request_id=f"kweli-cancel-{subscription.paypal_subscription_id}",
    )
    _apply(subscription, client.get(subscription.paypal_subscription_id))
    _set_plan(db, user, subscription, "cancelled")
    return subscription


def current(db: Session, user: User) -> Subscription | None:
    return db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.updated_at.desc().nulls_last(), Subscription.created_at.desc())
        .limit(1)
    )


def sync(db: Session, paypal, subscription_id: str) -> Outcome:
    """A BILLING.SUBSCRIPTION.* webhook: re-read the subscription and update the plan."""
    remote = Subscriptions(paypal).get(subscription_id)
    subscription = db.scalar(
        select(Subscription).where(Subscription.paypal_subscription_id == subscription_id)
    )
    user = db.get(User, subscription.user_id) if subscription else None
    if not subscription:
        custom = str(remote.get("custom_id") or "")
        user = db.scalar(select(User).where(User.id == custom)) if _uuid(custom) else None
        if not user or remote.get("plan_id") != get_settings().paypal_plan_id:
            return Outcome("ignored", "not a Kweli Pro subscription")
        subscription = Subscription(
            user_id=user.id, paypal_subscription_id=subscription_id, plan_id="", status=""
        )
        db.add(subscription)
    _apply(subscription, remote)
    _set_plan(db, user, subscription, "webhook")
    return Outcome("processed", f"subscription {subscription.status.lower()}")


def _uuid(value: str) -> bool:
    from uuid import UUID

    try:
        UUID(value)
    except ValueError:
        return False
    return True


def pro_feature(feature: str):
    """FastAPI dependency: 402 unless the user can use a Pro feature."""
    from fastapi import Depends, HTTPException

    from api.db.session import get_db
    from api.security import Principal, current_principal

    def check(
        principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
    ) -> None:
        user = db.get(User, principal.user_id)
        try:
            require_pro(user, feature)
        except ServiceError as error:
            raise HTTPException(error.status, error.message) from None

    return check
