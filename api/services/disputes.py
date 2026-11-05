"""Disputes: mirror PayPal's record, plan the evidence, draft, approve and submit.

Facts are always re-read from PayPal (sync) and from Kweli's own records (facts_for). Nothing
is submitted without the freelancer's approval token, and the token only approves the exact
draft it was issued for: any change to the response or to the evidence needs a new approval.
"""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import (
    Agreement,
    Client,
    Dispute,
    Document,
    DocumentBlob,
    Invoice,
    Payment,
    PaymentLink,
    ProofFlag,
    User,
)
from api.security import token_hash
from api.services.agreements import agreement_text
from api.services.invoicing import ServiceError
from api.services.payments import Outcome, _owner, _when
from audit.log import record
from defender import files as evidence_files
from defender.evidence import (
    AgreementInfo,
    DisputeFacts,
    EvidenceItem,
    FileInfo,
    InvoiceInfo,
    plan,
)
from defender.response import MAX_NOTES, Drafted, check, draft
from packs.citations import Problem
from paypal.disputes import Disputes, links
from paypal.errors import PayPalError
from paypal.money import from_paypal_value
from vault.crypto import decrypt

APPROVAL_TTL = timedelta(minutes=30)
SANDBOX_ACTIONS = {"require_evidence", "seller_favor", "buyer_favor"}


class ResponseRejected(Exception):
    def __init__(self, problems: list[Problem]) -> None:
        super().__init__("The response didn't pass the checks")
        self.problems = problems


# Mirroring PayPal ------------------------------------------------------------------------


def apply_remote(dispute: Dispute, remote: dict, payment: Payment | None) -> None:
    amount = remote.get("dispute_amount") or {}
    currency = str(amount.get("currency_code") or dispute.currency or "USD")[:3]
    dispute.reason = str(remote.get("reason") or "OTHER")[:64]
    dispute.status = str(remote.get("status") or "OTHER")[:64]
    dispute.stage = (
        str(remote["dispute_life_cycle_stage"])[:32]
        if remote.get("dispute_life_cycle_stage")
        else None
    )
    dispute.currency = currency
    dispute.amount_minor = from_paypal_value(str(amount.get("value") or "0"), currency)
    due = remote.get("seller_response_due_date")
    dispute.evidence_due_at = _when(due) if due else None
    dispute.outcome = (remote.get("dispute_outcome") or {}).get("outcome_code")
    dispute.allowed = sorted(links(remote))
    dispute.buyer_messages = [
        {
            "posted_by": str(message.get("posted_by") or "")[:20],
            "time": str(message.get("time_posted") or "")[:40],
            "content": str(message.get("content") or "")[:1000],
        }
        for message in (remote.get("messages") or [])[-10:]
    ]
    if payment:
        dispute.payment_id = payment.id
    now = datetime.now(UTC)
    dispute.refreshed_at = now
    if dispute.status == "RESOLVED" and not dispute.resolved_at:
        dispute.resolved_at = now


def _owner_and_payment(db: Session, remote: dict) -> tuple[User | None, Payment | None]:
    merchant = None
    for transaction in remote.get("disputed_transactions") or []:
        seller_transaction = transaction.get("seller_transaction_id")
        if seller_transaction:
            payment = db.scalar(
                select(Payment).where(Payment.paypal_transaction_id == seller_transaction)
            )
            if payment:
                return db.get(User, payment.user_id), payment
        merchant = merchant or (transaction.get("seller") or {}).get("merchant_id")
    return _owner(db, merchant), None


def sync(db: Session, paypal, dispute_id: str) -> Outcome:
    remote = Disputes(paypal).get(dispute_id)
    user, payment = _owner_and_payment(db, remote)
    if not user:
        return Outcome("ignored", "no Kweli user owns this dispute")
    dispute = db.scalar(select(Dispute).where(Dispute.paypal_dispute_id == dispute_id))
    created = dispute is None
    if dispute is None:
        dispute = Dispute(user_id=user.id, paypal_dispute_id=dispute_id, source="webhook")
        db.add(dispute)
    elif dispute.user_id != user.id:
        return Outcome("ignored", "dispute belongs to another account")
    before = (dispute.status, dispute.outcome)
    apply_remote(dispute, remote, payment)
    db.flush()
    if created:
        action = "dispute.opened"
    elif dispute.status == "RESOLVED" and before[0] != "RESOLVED":
        action = "dispute.resolved"
    elif before != (dispute.status, dispute.outcome):
        action = "dispute.updated"
    else:
        return Outcome("processed", f"dispute {dispute.status.lower()}, no change")
    record(
        db,
        user.id,
        action,
        {
            "dispute_id": str(dispute.id),
            "paypal_dispute_id": dispute_id,
            "status": dispute.status,
            "reason": dispute.reason,
            "outcome": dispute.outcome,
            "payment_id": str(dispute.payment_id) if dispute.payment_id else None,
        },
    )
    return Outcome("processed", f"{action} ({dispute.status.lower()})")


# Facts and evidence ----------------------------------------------------------------------


def _file(document: Document) -> FileInfo:
    return FileInfo(
        document.id,
        document.filename,
        document.mime,
        document.size,
        document.sha256,
        document.created_at,
    )


def facts_for(db: Session, user: User, dispute: Dispute) -> DisputeFacts:
    base = dict(
        freelancer_name=user.name,
        freelancer_email=user.email,
        reason=dispute.reason,
        amount_minor=dispute.amount_minor,
        currency=dispute.currency,
    )
    payment = db.get(Payment, dispute.payment_id) if dispute.payment_id else None
    if not payment or payment.user_id != user.id:
        return DisputeFacts(**base)
    link = db.get(PaymentLink, payment.id)
    agreement = (
        db.scalar(
            select(Agreement).where(Agreement.id == link.agreement_id, Agreement.user_id == user.id)
        )
        if link and link.agreement_id
        else None
    )
    invoice = db.get(Invoice, link.invoice_id) if link and link.invoice_id else None
    client = db.get(Client, agreement.client_id) if agreement else None
    documents = (
        list(
            db.scalars(
                select(Document)
                .where(
                    Document.agreement_id == agreement.id,
                    Document.user_id == user.id,
                    Document.kind.in_(("deliverable", "payer_confirmation")),
                )
                .order_by(Document.created_at)
            )
        )
        if agreement
        else []
    )
    p3 = db.scalar(
        select(ProofFlag.status).where(ProofFlag.payment_id == payment.id, ProofFlag.rule == "P3")
    )
    confirmation = next((d for d in reversed(documents) if d.kind == "payer_confirmation"), None)
    others = 0
    if payment.paypal_invoice_id:
        others = db.scalar(
            select(func.count(Payment.id)).where(
                Payment.user_id == user.id,
                Payment.paypal_invoice_id == payment.paypal_invoice_id,
                Payment.id != payment.id,
            )
        )
    payer_is_client = bool(
        client and payment.payer_email and payment.payer_email.lower() == client.email.lower()
    )
    return DisputeFacts(
        **base,
        client=client.name if client else (payment.payer_name or payment.payer_email),
        client_email=client.email if client else None,
        payer=payment.payer_name or payment.payer_email,
        payer_matches=payer_is_client and p3 == "pass",
        payment_amount_minor=payment.amount_minor,
        payment_received_at=payment.received_at,
        transaction_id=payment.paypal_transaction_id,
        agreement=AgreementInfo(
            agreement.title,
            agreement.scope,
            tuple(agreement.deliverables or ()),
            agreement.amount_minor,
            agreement.currency,
            agreement.due_date,
            agreement.accepted_at,
            agreement.accepted_ip_hash,
            tuple(agreement_text(agreement, user.name)),
        )
        if agreement
        else None,
        invoice=InvoiceInfo(
            invoice.number,
            invoice.paypal_invoice_id,
            invoice.description,
            invoice.amount_minor,
            invoice.currency,
            invoice.sent_at,
            invoice.status,
        )
        if invoice
        else None,
        work=tuple(_file(d) for d in documents if d.kind == "deliverable"),
        confirmation=_file(confirmation) if confirmation else None,
        other_payments_for_invoice=others or 0,
    )


def _draft_hash(response: str, items: list[EvidenceItem]) -> str:
    shape = {
        "response": response.strip(),
        "files": [
            [item.key, item.evidence_type, file.name, file.sha256 or file.source]
            for item in items
            for file in item.files
        ],
    }
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()


def _issue_approval(dispute: Dispute, items: list[EvidenceItem]) -> str:
    token = secrets.token_urlsafe(32)
    dispute.approval_token_hash = token_hash(token)
    dispute.approval_expires_at = datetime.now(UTC) + APPROVAL_TTL
    dispute.draft_hash = _draft_hash(dispute.response or "", items)
    return token


def _can_respond(dispute: Dispute) -> None:
    if dispute.submitted_at:
        raise ServiceError(409, "Evidence was already submitted for this dispute.")
    if dispute.status == "RESOLVED":
        raise ServiceError(409, "This dispute is resolved.")


def prepare(db: Session, user: User, dispute: Dispute, writer) -> tuple[list[EvidenceItem], str]:
    _can_respond(dispute)
    facts = facts_for(db, user, dispute)
    items = plan(facts)
    drafted: Drafted = draft(facts, items, writer)
    dispute.response = drafted.text
    dispute.response_source = drafted.source
    dispute.rejected = [
        {"code": p.code, "message": p.message, "excerpt": p.excerpt} for p in drafted.rejected
    ]
    token = _issue_approval(dispute, items)
    record(
        db,
        user.id,
        "dispute.response_drafted",
        {"dispute_id": str(dispute.id), "source": drafted.source, "draft_hash": dispute.draft_hash},
    )
    return items, token


def edit(db: Session, user: User, dispute: Dispute, text: str) -> tuple[list[EvidenceItem], str]:
    _can_respond(dispute)
    facts = facts_for(db, user, dispute)
    problems = check(text, facts)
    if problems:
        raise ResponseRejected(problems)
    items = plan(facts)
    dispute.response = text.strip()
    dispute.response_source = "edited"
    token = _issue_approval(dispute, items)
    record(
        db,
        user.id,
        "dispute.response_edited",
        {"dispute_id": str(dispute.id), "draft_hash": dispute.draft_hash},
    )
    return items, token


def approve_current(db: Session, user: User, dispute: Dispute) -> tuple[list[EvidenceItem], str]:
    """A fresh approval for the response as it stands, e.g. after the page was reloaded."""
    _can_respond(dispute)
    if not dispute.response:
        raise ServiceError(409, "Prepare the response first.")
    facts = facts_for(db, user, dispute)
    problems = check(dispute.response, facts)
    if problems:
        raise ResponseRejected(problems)
    items = plan(facts)
    return items, _issue_approval(dispute, items)


# Submitting ------------------------------------------------------------------------------


def _reader(db: Session, user_id: UUID):
    def read(document_id: UUID) -> bytes:
        document = db.scalar(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        blob = db.get(DocumentBlob, document_id) if document else None
        if not document or not blob:
            raise ServiceError(404, "An evidence file is missing from the vault.")
        return decrypt(document.id, blob.nonce, blob.ciphertext, document.encrypted_dek)

    return read


def evidences_for(items: list[EvidenceItem], response: str, built, generic: bool) -> list[dict]:
    names: dict[str, list[str]] = {}
    for key, file in built:
        names.setdefault(key, []).append(file.name)
    evidences = []
    usable = [item for item in items if item.status in ("ready", "partial")]
    for index, item in enumerate(usable):
        note = response if index == 0 else f"{item.label}: {item.detail}"
        entry = {
            "evidence_type": "OTHER" if generic else item.evidence_type,
            "notes": note[:MAX_NOTES],
        }
        if names.get(item.key):
            entry["documents"] = [{"name": name} for name in names[item.key]]
        evidences.append(entry)
    if not evidences:
        evidences.append({"evidence_type": "OTHER", "notes": response[:MAX_NOTES]})
    return evidences


def submit(db: Session, user: User, dispute: Dispute, token: str, paypal) -> None:
    if dispute.source == "seed":
        raise ServiceError(
            409, "This is a demo dispute, so nothing is sent to PayPal. Open one in the sandbox."
        )
    _can_respond(dispute)
    if not dispute.approval_token_hash or not secrets.compare_digest(
        dispute.approval_token_hash, token_hash(token)
    ):
        raise ServiceError(403, "This approval isn't valid. Review the response and approve again.")
    if not dispute.approval_expires_at or dispute.approval_expires_at < datetime.now(UTC):
        raise ServiceError(403, "This approval has expired. Review the response and approve again.")
    facts = facts_for(db, user, dispute)
    items = plan(facts)
    if _draft_hash(dispute.response or "", items) != dispute.draft_hash:
        raise ServiceError(409, "The evidence changed since you approved it. Review it again.")
    dispute.approval_token_hash = None

    client = Disputes(paypal)
    remote = client.get(dispute.paypal_dispute_id)
    apply_remote(dispute, remote, None)
    if "provide_evidence" not in dispute.allowed:
        db.commit()
        raise ServiceError(
            409,
            f"PayPal isn't accepting evidence for this dispute right now "
            f"(status: {dispute.status.replace('_', ' ').lower()}).",
        )
    built = evidence_files.build(facts, items, _reader(db, user.id))
    files = [file for _, file in built]
    request_id = f"kweli-evidence-{dispute.id}-{dispute.draft_hash[:16]}"
    generic = False
    try:
        client.provide_evidence(
            dispute.paypal_dispute_id,
            evidences_for(items, dispute.response or "", built, generic),
            files,
            request_id,
        )
    except PayPalError as error:
        if error.status not in (400, 422):
            raise
        generic = True
        client.provide_evidence(
            dispute.paypal_dispute_id,
            evidences_for(items, dispute.response or "", built, generic),
            files,
            request_id + "-other",
        )
    now = datetime.now(UTC)
    dispute.submitted_at = now
    dispute.submission = {
        "at": now.isoformat(timespec="seconds"),
        "request_id": request_id,
        "generic_types": generic,
        "notes_sha256": hashlib.sha256((dispute.response or "").encode()).hexdigest(),
        "files": [
            {
                "evidence": key,
                "name": file.name,
                "sha256": hashlib.sha256(file.data).hexdigest(),
                "bytes": len(file.data),
            }
            for key, file in built
        ],
    }
    record(
        db,
        user.id,
        "dispute.evidence_submitted",
        {
            "dispute_id": str(dispute.id),
            "paypal_dispute_id": dispute.paypal_dispute_id,
            "draft_hash": dispute.draft_hash,
            "files": [[f["name"], f["sha256"]] for f in dispute.submission["files"]],
        },
    )
    apply_remote(dispute, client.get(dispute.paypal_dispute_id), None)


def refresh(db: Session, dispute: Dispute, paypal) -> None:
    if dispute.source == "seed":
        return
    sync(db, paypal, dispute.paypal_dispute_id)


def sandbox_action(db: Session, user: User, dispute: Dispute, action: str, paypal) -> None:
    if get_settings().paypal_env != "sandbox":
        raise ServiceError(404, "Sandbox tools only exist in the sandbox.")
    if dispute.source == "seed":
        raise ServiceError(409, "This is a demo dispute. Sandbox tools need a real sandbox one.")
    if action not in SANDBOX_ACTIONS:
        raise ServiceError(422, "Unknown sandbox action.")
    client = Disputes(paypal)
    if action == "require_evidence":
        client.require_evidence(dispute.paypal_dispute_id, "SELLER_EVIDENCE")
    else:
        client.adjudicate(
            dispute.paypal_dispute_id, "SELLER_FAVOR" if action == "seller_favor" else "BUYER_FAVOR"
        )
    record(
        db,
        user.id,
        "dispute.sandbox_action",
        {"dispute_id": str(dispute.id), "action": action},
    )
    sync(db, paypal, dispute.paypal_dispute_id)
