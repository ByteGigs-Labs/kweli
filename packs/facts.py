"""Everything a Compliance Pack says, gathered once from the database.

The cover letter, the mapping table, the PDF and the ZIP are all built from these facts. Each
payment and document gets a short reference ([P1], [D3]) that the letter must cite, and that the
citation validator checks against. [T1] is the payment-to-document table itself.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db.models import Agreement, Document, Invoice, Payment, User
from api.services.ledger import load_context
from paypal.money import to_paypal_value
from proof.readiness import Check, overall

TABLE_REF = "T1"
COUNTRIES = {"KE": "Kenya", "NG": "Nigeria", "GH": "Ghana", "UG": "Uganda", "TZ": "Tanzania"}


def money(amount_minor: int, currency: str) -> str:
    value = to_paypal_value(amount_minor, currency)
    whole, _, cents = value.partition(".")
    grouped = f"{int(whole):,}"
    return f"{currency} {grouped}.{cents}" if cents else f"{currency} {grouped}"


def long_date(value: date | datetime) -> str:
    return f"{value.day} {value:%b %Y}"


@dataclass(frozen=True)
class DocRef:
    ref: str
    kind: str  # agreement, invoice, deliverable, payer_confirmation
    title: str
    detail: str
    document_id: UUID | None = None
    filename: str | None = None
    sha256: str | None = None
    size: int | None = None
    lines: tuple[str, ...] = ()
    amount_minor: int | None = None
    currency: str | None = None


@dataclass(frozen=True)
class PaymentRef:
    ref: str
    payment_id: UUID
    received_at: datetime
    client: str
    payer: str | None
    amount_minor: int
    currency: str
    paypal_transaction_id: str
    payment_type: str
    status: str
    checks: tuple[Check, ...]
    invoice_ref: str | None = None
    invoice_number: str | None = None
    invoice_amount_minor: int | None = None
    agreement_ref: str | None = None
    agreement_title: str | None = None
    work_refs: tuple[str, ...] = ()
    confirmation_ref: str | None = None

    @property
    def amount(self) -> str:
        return money(self.amount_minor, self.currency)

    def check(self, rule: str) -> Check | None:
        return next((c for c in self.checks if c.rule == rule), None)

    @property
    def refs(self) -> tuple[str, ...]:
        found = [self.agreement_ref, self.invoice_ref, *self.work_refs, self.confirmation_ref]
        return tuple(ref for ref in found if ref)


@dataclass(frozen=True)
class PackFacts:
    freelancer_name: str
    freelancer_email: str
    country: str
    start: date
    end: date
    payments: tuple[PaymentRef, ...]
    documents: tuple[DocRef, ...]
    client_emails: tuple[str, ...] = ()
    totals: dict[str, int] = field(default_factory=dict)

    @property
    def refs(self) -> set[str]:
        return {p.ref for p in self.payments} | {d.ref for d in self.documents} | {TABLE_REF}

    def payment(self, ref: str) -> PaymentRef | None:
        return next((p for p in self.payments if p.ref == ref), None)

    def document(self, ref: str) -> DocRef | None:
        return next((d for d in self.documents if d.ref == ref), None)

    def allowed_amounts(self) -> set[tuple[str, int]]:
        """Every amount the letter may mention: payments, invoices, agreement fees, totals."""
        allowed = {(p.currency, p.amount_minor) for p in self.payments}
        allowed |= {
            (p.currency, p.invoice_amount_minor)
            for p in self.payments
            if p.invoice_amount_minor is not None
        }
        allowed |= {(currency, amount) for currency, amount in self.totals.items()}
        allowed |= {
            (d.currency, d.amount_minor)
            for d in self.documents
            if d.currency and d.amount_minor is not None
        }
        return allowed

    @property
    def totals_text(self) -> str:
        return " and ".join(money(amount, cur) for cur, amount in sorted(self.totals.items()))


def _range(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=UTC),
        datetime.combine(end, time.max, tzinfo=UTC),
    )


def gather(db: Session, user: User, start: date, end: date) -> PackFacts:
    since, until = _range(start, end)
    payments = list(
        db.scalars(
            select(Payment)
            .where(
                Payment.user_id == user.id,
                Payment.received_at >= since,
                Payment.received_at <= until,
            )
            .order_by(Payment.received_at)
        )
    )
    context = load_context(db, payments)
    agreement_ids = {
        link.agreement_id for link in context.links.values() if link and link.agreement_id
    }
    agreements = {
        a.id: a
        for a in db.scalars(
            select(Agreement)
            .options(selectinload(Agreement.client))
            .where(Agreement.id.in_(agreement_ids), Agreement.user_id == user.id)
        )
    }
    invoice_ids = {link.invoice_id for link in context.links.values() if link.invoice_id}
    invoices = {
        i.id: i
        for i in db.scalars(
            select(Invoice).where(Invoice.id.in_(invoice_ids), Invoice.user_id == user.id)
        )
    }
    files: dict[UUID, list[Document]] = {}
    for document in db.scalars(
        select(Document)
        .where(
            Document.agreement_id.in_(agreement_ids),
            Document.user_id == user.id,
            Document.kind.in_(("deliverable", "payer_confirmation")),
        )
        .order_by(Document.created_at)
    ):
        files.setdefault(document.agreement_id, []).append(document)

    documents: list[DocRef] = []
    by_key: dict[tuple[str, UUID], str] = {}

    def add(key: tuple[str, UUID], make) -> str:
        if key not in by_key:
            ref = f"D{len(documents) + 1}"
            documents.append(make(ref))
            by_key[key] = ref
        return by_key[key]

    from api.services.agreements import agreement_text

    refs: list[PaymentRef] = []
    for index, payment in enumerate(payments, start=1):
        link = context.links.get(payment.id)
        agreement = agreements.get(link.agreement_id) if link and link.agreement_id else None
        invoice = invoices.get(link.invoice_id) if link and link.invoice_id else None
        agreement_ref = invoice_ref = confirmation_ref = None
        work_refs: list[str] = []
        if agreement:
            accepted = (
                f"Accepted by {agreement.client.name} on {long_date(agreement.accepted_at)}"
                if agreement.accepted_at
                else f"Status: {agreement.status}, not accepted yet"
            )
            agreement_ref = add(
                ("agreement", agreement.id),
                lambda ref, a=agreement, accepted=accepted: DocRef(
                    ref,
                    "agreement",
                    f"Agreement: {a.title}",
                    money(a.amount_minor, a.currency),
                    amount_minor=a.amount_minor,
                    currency=a.currency,
                    lines=(
                        *agreement_text(a, user.name),
                        "",
                        accepted
                        + (
                            f" (UTC {a.accepted_at:%H:%M}, network fingerprint "
                            f"{a.accepted_ip_hash[:16]}…)"
                            if a.accepted_at and a.accepted_ip_hash
                            else ""
                        ),
                    ),
                ),
            )
            for document in files.get(agreement.id, []):
                ref = add(
                    (document.kind, document.id),
                    lambda ref, d=document: DocRef(
                        ref,
                        d.kind,
                        ("Delivered work: " if d.kind == "deliverable" else "Payer confirmation: ")
                        + d.filename,
                        f"{d.size:,} bytes, SHA-256 {d.sha256[:12]}…",
                        document_id=d.id,
                        filename=d.filename,
                        sha256=d.sha256,
                        size=d.size,
                    ),
                )
                if document.kind == "deliverable":
                    work_refs.append(ref)
                else:
                    confirmation_ref = ref
        if invoice:
            invoice_ref = add(
                ("invoice", invoice.id),
                lambda ref, i=invoice: DocRef(
                    ref,
                    "invoice",
                    f"PayPal invoice {i.number}",
                    money(i.amount_minor, i.currency),
                    amount_minor=i.amount_minor,
                    currency=i.currency,
                    lines=(
                        f"Invoice number: {i.number}",
                        f"PayPal invoice ID: {i.paypal_invoice_id or 'not sent'}",
                        f"For: {i.description}",
                        f"Amount: {money(i.amount_minor, i.currency)}",
                        f"Sent: {long_date(i.sent_at) if i.sent_at else 'not sent'}",
                        f"Status: {i.status.replace('_', ' ')}",
                    ),
                ),
            )
        checks = tuple(
            Check(f.rule, f.status, f.explanation, f.fix) for f in context.flags[payment.id]
        )
        refs.append(
            PaymentRef(
                ref=f"P{index}",
                payment_id=payment.id,
                received_at=payment.received_at,
                client=context.client_for(payment),
                payer=payment.payer_name or payment.payer_email,
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                paypal_transaction_id=payment.paypal_transaction_id,
                payment_type=payment.payment_type,
                status=overall(checks),
                checks=checks,
                invoice_ref=invoice_ref,
                invoice_number=invoice.number if invoice else None,
                invoice_amount_minor=invoice.amount_minor if invoice else None,
                agreement_ref=agreement_ref,
                agreement_title=agreement.title if agreement else None,
                work_refs=tuple(work_refs),
                confirmation_ref=confirmation_ref,
            )
        )

    totals: dict[str, int] = {}
    for payment in payments:
        totals[payment.currency] = totals.get(payment.currency, 0) + payment.amount_minor
    return PackFacts(
        freelancer_name=user.name,
        freelancer_email=user.email,
        country=COUNTRIES.get(user.country or "", user.country or ""),
        start=start,
        end=end,
        payments=tuple(refs),
        documents=tuple(documents),
        client_emails=tuple(sorted({a.client.email.lower() for a in agreements.values()})),
        totals=totals,
    )
