"""The approval gate.

The model can only *propose* an action. A proposal stores validated IDs (never amounts or email
addresses) and a hash of a single-use token. The token goes to the freelancer's browser, never
to the model. Executing needs that token from a click within the time limit. At execution, every
fact (amount, recipient, status) is re-read from the database, not from the proposal.
"""

import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import AgentAction
from api.security import token_hash
from api.services import invoicing
from api.services.agreements import issue_accept_link
from api.services.invoicing import ServiceError
from audit.log import record
from paypal.client import PayPalClient
from paypal.money import to_paypal_value

ACTION_TTL = timedelta(minutes=15)
KINDS = ("create_invoice", "send_invoice", "send_reminder", "acceptance_link")


@dataclass
class Preview:
    title: str
    details: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Proposal:
    action: AgentAction
    token: str
    preview: Preview


def _money(minor: int, currency: str) -> str:
    return f"{currency} {to_paypal_value(minor, currency)}"


def _due(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else "On receipt"


def preview_for(db: Session, user_id: UUID, kind: str, args: dict) -> Preview:
    """Validate the arguments against the database and describe exactly what will happen."""
    if kind == "create_invoice":
        agreement = invoicing.owned_agreement(db, user_id, UUID(args["agreement_id"]))
        invoicing.check_can_invoice(agreement)
        existing = invoicing.open_invoice_for(db, agreement.id)
        if existing and existing.status != "draft":
            raise ServiceError(409, f"This agreement already has invoice {existing.number}.")
        due = date.fromisoformat(args["due_date"]) if args.get("due_date") else agreement.due_date
        verb = "Create and send" if args.get("send", True) else "Create"
        return Preview(
            f"{verb} a PayPal invoice for {agreement.client.name}",
            [
                ("To", agreement.client.email),
                ("Amount", _money(agreement.amount_minor, agreement.currency)),
                ("For", agreement.title),
                ("Due", _due(due)),
            ],
        )
    if kind in ("send_invoice", "send_reminder"):
        invoice = invoicing.owned_invoice(db, user_id, UUID(args["invoice_id"]))
        if kind == "send_invoice" and invoice.status != "draft":
            raise ServiceError(409, f"Invoice {invoice.number} has already been sent.")
        if kind == "send_reminder" and invoice.status not in ("sent", "partially_paid"):
            raise ServiceError(409, f"Invoice {invoice.number} isn't waiting for payment.")
        title = "Send invoice" if kind == "send_invoice" else "Send a payment reminder for invoice"
        return Preview(
            f"{title} {invoice.number}",
            [
                ("To", invoice.client.email),
                ("Amount", _money(invoice.amount_minor, invoice.currency)),
                ("Due", _due(invoice.due_date)),
            ],
        )
    if kind == "acceptance_link":
        agreement = invoicing.owned_agreement(db, user_id, UUID(args["agreement_id"]))
        if agreement.status == "accepted":
            raise ServiceError(409, "The client has already accepted this agreement.")
        return Preview(
            f"Create an acceptance link for '{agreement.title}'",
            [("For", agreement.client.name), ("Send it to", agreement.client.email)],
        )
    raise ServiceError(400, f"Unknown action {kind}")


def propose(db: Session, user_id: UUID, kind: str, args: dict) -> Proposal:
    if kind not in KINDS:
        raise ServiceError(400, f"Unknown action {kind}")
    preview = preview_for(db, user_id, kind, args)
    token = secrets.token_urlsafe(32)
    action = AgentAction(
        user_id=user_id,
        created_at=datetime.now(UTC),
        tool=kind,
        arguments=args | {"preview": {"title": preview.title, "details": preview.details}},
        approval_token_hash=token_hash(token),
    )
    db.add(action)
    db.flush()
    record(db, user_id, "agent.proposed", {"action_id": str(action.id), "kind": kind})
    db.commit()
    return Proposal(action, token, preview)


def expires_at(action: AgentAction) -> datetime:
    return action.created_at + ACTION_TTL


def _locked(db: Session, user_id: UUID, action_id: UUID) -> AgentAction:
    action = db.scalar(
        select(AgentAction)
        .where(AgentAction.id == action_id, AgentAction.user_id == user_id)
        .with_for_update()
    )
    if not action:
        raise ServiceError(404, "Action not found")
    return action


def _execute(db: Session, user_id: UUID, action: AgentAction, paypal: PayPalClient) -> dict:
    args = action.arguments
    if action.tool == "create_invoice":
        agreement = invoicing.owned_agreement(db, user_id, UUID(args["agreement_id"]))
        due = date.fromisoformat(args["due_date"]) if args.get("due_date") else None
        invoice = invoicing.create_draft(db, user_id, agreement, paypal, due)
        if args.get("send", True):
            invoice = invoicing.send(db, user_id, invoice, paypal)
            return {
                "message": f"Invoice {invoice.number} sent to {invoice.client.email}.",
                "invoice_id": str(invoice.id),
                "link": invoice.payer_view_url,
            }
        return {
            "message": f"Draft invoice {invoice.number} created.",
            "invoice_id": str(invoice.id),
        }
    if action.tool == "send_invoice":
        invoice = invoicing.owned_invoice(db, user_id, UUID(args["invoice_id"]))
        invoice = invoicing.send(db, user_id, invoice, paypal)
        return {
            "message": f"Invoice {invoice.number} sent to {invoice.client.email}.",
            "invoice_id": str(invoice.id),
            "link": invoice.payer_view_url,
        }
    if action.tool == "send_reminder":
        invoice = invoicing.owned_invoice(db, user_id, UUID(args["invoice_id"]))
        invoicing.remind(db, user_id, invoice, paypal)
        return {
            "message": f"PayPal reminded {invoice.client.email} about invoice {invoice.number}.",
            "invoice_id": str(invoice.id),
        }
    if action.tool == "acceptance_link":
        agreement = invoicing.owned_agreement(db, user_id, UUID(args["agreement_id"]))
        if agreement.status == "accepted":
            raise ServiceError(409, "The client has already accepted this agreement.")
        record(db, user_id, "agreement.link_issued", {"agreement_id": str(agreement.id)})
        url, _ = issue_accept_link(db, agreement)
        return {
            "message": f"Acceptance link ready. Send it to {agreement.client.email}.",
            "link": url,
            "agreement_id": str(agreement.id),
        }
    raise ServiceError(400, f"Unknown action {action.tool}")


def approve(
    db: Session, user_id: UUID, action_id: UUID, token: str, paypal: PayPalClient
) -> AgentAction:
    action = _locked(db, user_id, action_id)
    if action.status != "proposed":
        raise ServiceError(409, f"This action was already {action.status}.")
    if datetime.now(UTC) > expires_at(action):
        action.status = "rejected"
        action.result = {"message": "Expired before it was approved."}
        db.commit()
        raise ServiceError(410, "This proposal expired. Ask the assistant again.")
    if not action.approval_token_hash or not hmac.compare_digest(
        action.approval_token_hash, token_hash(token)
    ):
        raise ServiceError(403, "This approval isn't valid.")
    action.status = "approved"
    action.approval_token_hash = None
    action.decided_at = datetime.now(UTC)
    record(db, user_id, "agent.approved", {"action_id": str(action.id), "kind": action.tool})
    db.commit()
    try:
        result = _execute(db, user_id, action, paypal)
    except ServiceError as error:
        db.rollback()
        action = db.get(AgentAction, action_id)
        action.status = "failed"
        action.result = {"message": error.message}
        db.commit()
        return action
    action = db.get(AgentAction, action_id)
    action.status = "executed"
    action.result = result
    db.commit()
    return action


def reject(db: Session, user_id: UUID, action_id: UUID) -> AgentAction:
    action = _locked(db, user_id, action_id)
    if action.status != "proposed":
        raise ServiceError(409, f"This action was already {action.status}.")
    action.status = "rejected"
    action.approval_token_hash = None
    action.decided_at = datetime.now(UTC)
    action.result = {"message": "You declined this."}
    record(db, user_id, "agent.rejected", {"action_id": str(action.id), "kind": action.tool})
    db.commit()
    return action
