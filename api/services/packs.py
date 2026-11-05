"""Build, store and re-letter Compliance Packs."""

import hashlib
import json
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.db.models import Document, DocumentBlob, Pack, User
from api.services.invoicing import ServiceError
from audit.log import record, verify
from packs.citations import Problem, validate
from packs.facts import PackFacts, gather
from packs.letter import Draft, LetterWriter, draft
from packs.render import Rendered, render
from vault.crypto import VaultUnavailable, decrypt, encrypt

MAX_DAYS = 366


class LetterRejected(Exception):
    def __init__(self, problems: list[Problem]) -> None:
        super().__init__("The letter didn't pass the checks")
        self.problems = problems


def fingerprint(facts: PackFacts) -> str:
    """Changes whenever a reference would point at something different."""
    shape = {
        "payments": [
            [p.ref, str(p.payment_id), p.amount_minor, p.currency, list(p.refs)]
            for p in facts.payments
        ],
        "documents": [[d.ref, d.kind, d.title, d.sha256] for d in facts.documents],
    }
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()


def check_period(start: date, end: date, today: date | None = None) -> None:
    today = today or datetime.now(UTC).date()
    if start > end:
        raise ServiceError(422, "The start date must be before the end date.")
    if end > today:
        raise ServiceError(422, "The period can't end in the future.")
    if (end - start).days > MAX_DAYS:
        raise ServiceError(422, "A pack can cover up to 12 months.")


def _read(db: Session, user_id: UUID):
    def read(document_id: UUID) -> bytes:
        document = db.scalar(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        blob = db.get(DocumentBlob, document_id) if document else None
        if not document or not blob:
            raise ServiceError(404, "A document in this pack is missing from the vault.")
        return decrypt(document.id, blob.nonce, blob.ciphertext, document.encrypted_dek)

    return read


def _store(db: Session, user_id: UUID, filename: str, mime: str, data: bytes) -> Document:
    document = Document(
        user_id=user_id,
        kind="pack",
        filename=filename,
        mime=mime,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key="db",
        encrypted_dek="",
    )
    db.add(document)
    db.flush()
    nonce, ciphertext, wrapped = encrypt(document.id, data)
    document.encrypted_dek = wrapped
    db.add(DocumentBlob(document_id=document.id, nonce=nonce, ciphertext=ciphertext))
    return document


def _problems(items) -> list[dict]:
    return [{"code": p.code, "message": p.message, "excerpt": p.excerpt} for p in items]


def _summary(facts: PackFacts, rendered: Rendered, letter: Draft | None, previous: dict) -> dict:
    statuses = {"pass": 0, "warn": 0, "fail": 0, "pending": 0}
    for payment in facts.payments:
        statuses[payment.status] += 1
    summary = {
        "payments": len(facts.payments),
        "clients": len({p.client for p in facts.payments}),
        "statuses": statuses,
        "totals": [
            {"currency": currency, "amount_minor": amount}
            for currency, amount in sorted(facts.totals.items())
        ],
        "documents": len(facts.documents),
        "attached": len(rendered.attached),
        "left_out": rendered.left_out,
        "pdf_sha256": hashlib.sha256(rendered.pdf).hexdigest(),
        "zip_sha256": hashlib.sha256(rendered.zip).hexdigest(),
        "fingerprint": fingerprint(facts),
        "audit_head": rendered.manifest["audit"]["head"],
    }
    if letter is not None:
        summary["ai_rejected"] = _problems(letter.rejected)
        summary["letter_attempts"] = letter.attempts
    else:
        summary["ai_rejected"] = previous.get("ai_rejected", [])
        summary["letter_attempts"] = previous.get("letter_attempts", 0)
    return summary


def _render(db: Session, user: User, pack: Pack, facts: PackFacts, letter: str) -> Rendered:
    chain = verify(db, user.id)
    if not chain.ok:
        raise ServiceError(409, "Your audit log failed its integrity check. Contact support.")
    try:
        rendered = render(facts, letter, pack.id, chain.head, chain.entries, _read(db, user.id))
    except VaultUnavailable:
        raise ServiceError(503, "File storage isn't set up here yet.") from None
    return rendered


def _attach(db: Session, user: User, pack: Pack, facts: PackFacts, rendered: Rendered) -> None:
    stem = f"kweli-pack-{facts.start.isoformat()}-to-{facts.end.isoformat()}"
    old = [pack.pdf_document_id, pack.zip_document_id]
    pdf = _store(db, user.id, f"{stem}.pdf", "application/pdf", rendered.pdf)
    archive = _store(db, user.id, f"{stem}.zip", "application/zip", rendered.zip)
    pack.pdf_document_id, pack.zip_document_id = pdf.id, archive.id
    db.flush()
    stale = [document_id for document_id in old if document_id]
    if stale:
        db.execute(delete(Document).where(Document.id.in_(stale), Document.kind == "pack"))


def build(db: Session, user: User, start: date, end: date, writer: LetterWriter | None) -> Pack:
    check_period(start, end)
    facts = gather(db, user, start, end)
    if not facts.payments:
        raise ServiceError(422, "There are no payments in this period.")
    letter = draft(facts, writer)
    pack = Pack(
        user_id=user.id,
        period_start=start,
        period_end=end,
        letter=letter.text,
        letter_source=letter.source,
    )
    db.add(pack)
    db.flush()
    rendered = _render(db, user, pack, facts, letter.text)
    _attach(db, user, pack, facts, rendered)
    pack.summary = _summary(facts, rendered, letter, {})
    record(
        db,
        user.id,
        "pack.created",
        {
            "pack_id": str(pack.id),
            "period": [start.isoformat(), end.isoformat()],
            "payments": len(facts.payments),
            "letter_source": letter.source,
            "pdf_sha256": pack.summary["pdf_sha256"],
            "zip_sha256": pack.summary["zip_sha256"],
        },
    )
    return pack


def replace_letter(db: Session, user: User, pack: Pack, letter: str) -> Pack:
    facts = gather(db, user, pack.period_start, pack.period_end)
    if fingerprint(facts) != pack.summary.get("fingerprint"):
        raise ServiceError(
            409, "Your records changed since this pack was made. Make a new pack instead."
        )
    problems = validate(letter, facts)
    if problems:
        raise LetterRejected(problems)
    rendered = _render(db, user, pack, facts, letter.strip())
    _attach(db, user, pack, facts, rendered)
    pack.letter = letter.strip()
    pack.letter_source = "edited"
    pack.summary = _summary(facts, rendered, None, pack.summary)
    pack.updated_at = datetime.now(UTC)
    record(
        db,
        user.id,
        "pack.letter_edited",
        {
            "pack_id": str(pack.id),
            "pdf_sha256": pack.summary["pdf_sha256"],
            "zip_sha256": pack.summary["zip_sha256"],
        },
    )
    return pack
