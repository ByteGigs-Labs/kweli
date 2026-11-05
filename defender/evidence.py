"""What evidence a dispute needs, by PayPal's dispute reason, and what Kweli already has.

Pure functions of DisputeFacts. Each need maps to a PayPal evidence type and to the Kweli
proof that satisfies it: the accepted agreement, the PayPal invoice, the delivered work, and
whether the payer is the client.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

PAYPAL_FILE_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024

REASONS: dict[str, tuple[str, str]] = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": (
        "Work not received",
        "The client says they didn't receive the work.",
    ),
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": (
        "Not as described",
        "The client says the work isn't what was agreed.",
    ),
    "UNAUTHORISED": (
        "Unauthorised payment",
        "The account holder says they didn't make this payment.",
    ),
    "CREDIT_NOT_PROCESSED": (
        "Refund not processed",
        "The client says a refund they were promised hasn't arrived.",
    ),
    "DUPLICATE_TRANSACTION": (
        "Charged twice",
        "The client says they were charged more than once.",
    ),
    "INCORRECT_AMOUNT": (
        "Wrong amount",
        "The client says they were charged the wrong amount.",
    ),
    "PAYMENT_BY_OTHER_MEANS": (
        "Paid another way",
        "The client says they already paid another way.",
    ),
    "CANCELED_RECURRING_BILLING": (
        "Cancelled billing",
        "The client says they cancelled a recurring payment.",
    ),
    "PROBLEM_WITH_REMITTANCE": (
        "Payment problem",
        "The client reports a problem with the payment.",
    ),
    "OTHER": ("Other", "The client opened a dispute for another reason."),
}


@dataclass(frozen=True)
class FileInfo:
    document_id: UUID
    filename: str
    mime: str
    size: int
    sha256: str
    uploaded_at: datetime


@dataclass(frozen=True)
class AgreementInfo:
    title: str
    scope: str
    deliverables: tuple[str, ...]
    amount_minor: int
    currency: str
    due_date: date | None
    accepted_at: datetime | None
    accepted_ip_hash: str | None
    terms: tuple[str, ...]


@dataclass(frozen=True)
class InvoiceInfo:
    number: str
    paypal_invoice_id: str | None
    description: str
    amount_minor: int
    currency: str
    sent_at: datetime | None
    status: str


@dataclass(frozen=True)
class DisputeFacts:
    freelancer_name: str
    freelancer_email: str
    reason: str
    amount_minor: int
    currency: str
    client: str | None = None
    client_email: str | None = None
    payer: str | None = None
    payer_matches: bool | None = None
    payment_amount_minor: int | None = None
    payment_received_at: datetime | None = None
    transaction_id: str | None = None
    agreement: AgreementInfo | None = None
    invoice: InvoiceInfo | None = None
    work: tuple[FileInfo, ...] = ()
    confirmation: FileInfo | None = None
    other_payments_for_invoice: int = 0

    def allowed_amounts(self) -> set[tuple[str, int]]:
        allowed = {(self.currency, self.amount_minor)}
        if self.payment_amount_minor is not None:
            allowed.add((self.currency, self.payment_amount_minor))
        if self.agreement:
            allowed.add((self.agreement.currency, self.agreement.amount_minor))
        if self.invoice:
            allowed.add((self.invoice.currency, self.invoice.amount_minor))
        return allowed


@dataclass(frozen=True)
class PlannedFile:
    name: str
    source: str  # agreement, invoice, vault
    mime: str = "application/pdf"
    document_id: UUID | None = None
    sha256: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class EvidenceItem:
    key: str
    label: str
    why: str
    evidence_type: str
    status: str  # ready, partial, missing
    detail: str
    files: tuple[PlannedFile, ...] = ()
    fix: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


CHECKLISTS: dict[str, tuple[str, ...]] = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": ("work", "agreement", "invoice"),
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": ("agreement", "work", "invoice"),
    "UNAUTHORISED": ("agreement", "payer", "invoice", "work"),
    "INCORRECT_AMOUNT": ("agreement", "invoice"),
    "DUPLICATE_TRANSACTION": ("invoice", "agreement"),
    "CREDIT_NOT_PROCESSED": ("agreement", "invoice"),
    "PAYMENT_BY_OTHER_MEANS": ("invoice", "agreement"),
}
DEFAULT_CHECKLIST = ("agreement", "invoice", "work")


def reason_label(reason: str) -> str:
    return REASONS.get(reason, REASONS["OTHER"])[0]


def paypal_name(text: str, extension: str) -> str:
    """PayPal document names must match ^[A-Za-z0-9-_,\\s]+[.][A-Za-z]+$."""
    import re
    import unicodedata

    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9\-_, ]+", " ", ascii_text).strip()
    stem = re.sub(r"\s+", " ", stem)[:80].strip() or "evidence"
    return f"{stem}.{extension}"


def _stem(filename: str) -> str:
    return filename.rsplit(".", 1)[0] if "." in filename else filename


def _agreement(facts: DisputeFacts) -> EvidenceItem:
    a = facts.agreement
    base = dict(
        key="agreement",
        label="Accepted agreement",
        why="Shows the client agreed the scope and the fee before paying.",
        evidence_type="COPY_OF_CONTRACT",
    )
    if not a:
        return EvidenceItem(
            **base,
            status="missing",
            detail="No agreement is linked to this payment.",
            fix="Link the payment to its agreement from the proof ledger.",
        )
    file = PlannedFile(paypal_name(f"Agreement {a.title}", "pdf"), "agreement")
    if not a.accepted_at:
        return EvidenceItem(
            **base,
            status="partial",
            detail=f"'{a.title}' exists but the client hasn't accepted it.",
            files=(file,),
            fix="An unaccepted agreement is weaker evidence. Attach any written approval too.",
        )
    return EvidenceItem(
        **base,
        status="ready",
        detail=f"{facts.client or 'The client'} accepted '{a.title}' on "
        f"{a.accepted_at.day} {a.accepted_at:%b %Y}.",
        files=(file,),
    )


def _invoice(facts: DisputeFacts) -> EvidenceItem:
    i = facts.invoice
    base = dict(
        key="invoice",
        label="PayPal invoice",
        why="Shows what was billed, to whom, and that this payment settled it.",
        evidence_type="PROOF_OF_RECEIPT_COPY",
    )
    if not i:
        return EvidenceItem(
            **base,
            status="missing",
            detail="This payment didn't come through a Kweli invoice.",
            fix="Nothing to fix now. Invoice through Kweli next time.",
        )
    notes = ()
    if facts.reason == "DUPLICATE_TRANSACTION":
        notes = (
            "This is the only payment recorded for this invoice."
            if facts.other_payments_for_invoice == 0
            else f"{facts.other_payments_for_invoice} other payment(s) are recorded for this "
            "invoice. Check whether one should be refunded.",
        )
    return EvidenceItem(
        **base,
        status="ready",
        detail=f"Invoice {i.number}, {i.status.replace('_', ' ')}.",
        files=(PlannedFile(paypal_name(f"Invoice {i.number}", "pdf"), "invoice"),),
        notes=notes,
    )


def _work(facts: DisputeFacts) -> EvidenceItem:
    base = dict(
        key="work",
        label="Delivered work",
        why="Shows the work was delivered, and when.",
        evidence_type="PROOF_FOR_SOFTWARE_OR_SERVICE_DELIVERED",
    )
    if not facts.work:
        return EvidenceItem(
            **base,
            status="missing",
            detail="No delivered work is attached to the agreement.",
            fix="Upload the final files to the agreement, then prepare the response again.",
        )
    files, notes = [], []
    total = 0
    for item in facts.work:
        extension = PAYPAL_FILE_TYPES.get(item.mime)
        if not extension:
            notes.append(
                f"{item.filename} is listed in the response but not attached: PayPal only "
                "accepts PDF, JPG, PNG or GIF."
            )
            continue
        if item.size > MAX_FILE_BYTES or total + item.size > MAX_TOTAL_BYTES:
            notes.append(f"{item.filename} is too large for PayPal and is listed instead.")
            continue
        total += item.size
        files.append(
            PlannedFile(
                paypal_name(f"Delivered {_stem(item.filename)}", extension),
                "vault",
                item.mime,
                item.document_id,
                item.sha256,
                item.size,
            )
        )
    names = ", ".join(item.filename for item in facts.work)
    return EvidenceItem(
        **base,
        status="ready" if files else "partial",
        detail=f"On file: {names}.",
        files=tuple(files),
        notes=tuple(notes),
        fix=None if files else "Upload a PDF or image of the work, or a document linking to it.",
    )


def _payer(facts: DisputeFacts) -> EvidenceItem:
    base = dict(
        key="payer",
        label="Payer is the client",
        why="Shows the PayPal account that paid belongs to the client who accepted the work.",
        evidence_type="OTHER",
    )
    if facts.payer_matches:
        return EvidenceItem(
            **base,
            status="ready",
            detail=f"Paid from {facts.client}'s own PayPal account, the one on the agreement.",
        )
    if facts.confirmation:
        extension = PAYPAL_FILE_TYPES.get(facts.confirmation.mime, "")
        files = (
            (
                PlannedFile(
                    paypal_name(
                        f"Payer confirmation {_stem(facts.confirmation.filename)}", extension
                    ),
                    "vault",
                    facts.confirmation.mime,
                    facts.confirmation.document_id,
                    facts.confirmation.sha256,
                    facts.confirmation.size,
                ),
            )
            if extension
            else ()
        )
        return EvidenceItem(
            **base,
            status="ready",
            detail=f"{facts.payer} paid for {facts.client}, who confirmed it in writing.",
            files=files,
        )
    return EvidenceItem(
        **base,
        status="missing",
        detail=f"Paid by {facts.payer or 'someone'} who isn't the client on the agreement.",
        fix="Ask the client to confirm in writing that the payment is theirs, and upload it.",
    )


BUILDERS = {"agreement": _agreement, "invoice": _invoice, "work": _work, "payer": _payer}


def plan(facts: DisputeFacts) -> list[EvidenceItem]:
    keys = CHECKLISTS.get(facts.reason, DEFAULT_CHECKLIST)
    return [BUILDERS[key](facts) for key in keys]


def strength(items: list[EvidenceItem]) -> str:
    """strong: everything ready; fair: something partial; weak: something missing."""
    if any(item.status == "missing" for item in items):
        return "weak"
    if any(item.status == "partial" for item in items):
        return "fair"
    return "strong"
