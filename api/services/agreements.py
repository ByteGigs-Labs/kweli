import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Agreement, Client
from api.security import token_hash
from audit.log import record
from paypal.money import to_paypal_value


def find_or_create_client(db: Session, user_id, name: str, email: str, country=None) -> Client:
    email = email.strip().lower()
    client = db.scalar(select(Client).where(Client.user_id == user_id, Client.email == email))
    if client:
        client.name = name
        if country:
            client.country = country
        return client
    client = Client(user_id=user_id, name=name, email=email, country=country)
    db.add(client)
    db.flush()
    return client


def issue_accept_link(db: Session, agreement: Agreement) -> tuple[str, datetime]:
    """A new single-purpose link. Issuing again invalidates the previous one."""
    token = secrets.token_urlsafe(32)
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(days=settings.agreement_link_days)
    agreement.accept_token_hash = token_hash(token)
    agreement.accept_token_expires_at = expires
    agreement.status = "sent"
    agreement.sent_at = datetime.now(UTC)
    db.commit()
    return f"{settings.public_web_url.rstrip('/')}/p/{token}", expires


def agreement_for_token(db: Session, token: str) -> Agreement | None:
    if not token or len(token) > 100:
        return None
    return db.scalar(select(Agreement).where(Agreement.accept_token_hash == token_hash(token)))


def link_is_live(agreement: Agreement) -> bool:
    expires = agreement.accept_token_expires_at
    return expires is not None and expires > datetime.now(UTC)


def pseudonymise_ip(ip: str) -> str:
    key = get_settings().hmac_key.get_secret_value().encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def accept(db: Session, agreement: Agreement, ip: str, user_agent: str) -> None:
    agreement.status = "accepted"
    agreement.accepted_at = datetime.now(UTC)
    agreement.accepted_ip_hash = pseudonymise_ip(ip)
    agreement.accepted_user_agent = user_agent[:300]
    record(
        db,
        agreement.user_id,
        "agreement.accepted",
        {"agreement_id": str(agreement.id), "ip_hash": agreement.accepted_ip_hash},
    )
    db.commit()


def agreement_text(agreement: Agreement, freelancer_name: str) -> list[str]:
    """Plain-language terms built from the stored fields. No AI writes contract terms."""
    amount = to_paypal_value(agreement.amount_minor, agreement.currency)
    due = agreement.due_date.strftime("%d %B %Y") if agreement.due_date else "a date both agree on"
    return [
        f"{freelancer_name} will deliver the work below for {agreement.client.name}.",
        f"Scope: {agreement.scope}",
        f"The total fee is {agreement.currency} {amount}, paid through a PayPal invoice.",
        f"The work is due by {due}.",
        "The client confirms they are paying for this work for their own business, and that "
        "the PayPal payment will come from them, not from someone else.",
        "Accepting below records the date, time and a one-way fingerprint of the network used.",
    ]
