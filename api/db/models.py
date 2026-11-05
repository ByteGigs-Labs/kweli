import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base

CURRENCY_CHECK = "currency ~ '^[A-Z]{3}$'"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _status_check(column: str, values: tuple[str, ...]) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_allowed")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (_status_check("plan", ("free", "pro")),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), default="KE")
    password_hash: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(10), default="free")
    paypal_merchant_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = _created_at()


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_key_time", "key", "attempted_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = _created_at()


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("user_id", "email"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254))
    country: Mapped[str | None] = mapped_column(String(2))
    paypal_payer_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = _created_at()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        _status_check(
            "kind",
            (
                "agreement",
                "deliverable",
                "correspondence",
                "id",
                "other",
                "payer_confirmation",
                "pack",
            ),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agreements.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))
    encrypted_dek: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()


class DocumentBlob(Base):
    """Encrypted file bytes, kept apart from the metadata so listings stay light."""

    __tablename__ = "document_blobs"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)


class Agreement(Base):
    __tablename__ = "agreements"
    __table_args__ = (
        _status_check("status", ("draft", "sent", "accepted", "expired")),
        CheckConstraint("amount_minor > 0", name="agreement_amount_positive"),
        CheckConstraint(CURRENCY_CHECK, name="agreement_currency_iso"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(Text)
    deliverables: Mapped[list] = mapped_column(JSONB, default=list)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    pdf_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    accept_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    accept_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_ip_hash: Mapped[str | None] = mapped_column(String(64))
    accepted_user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = _created_at()

    client: Mapped[Client] = relationship()


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        _status_check(
            "status", ("draft", "sent", "paid", "partially_paid", "cancelled", "refunded")
        ),
        CheckConstraint("amount_minor > 0", name="invoice_amount_positive"),
        CheckConstraint(CURRENCY_CHECK, name="invoice_currency_iso"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agreements.id"))
    paypal_invoice_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    number: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(500))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    payer_view_url: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    client: Mapped[Client] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        _status_check("payment_type", ("invoice", "goods_services", "personal", "unknown")),
        _status_check("source", ("webhook", "backfill", "seed")),
        CheckConstraint(CURRENCY_CHECK, name="payment_currency_iso"),
        Index("ix_payments_user_received", "user_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    paypal_transaction_id: Mapped[str] = mapped_column(String(64), unique=True)
    paypal_invoice_id: Mapped[str | None] = mapped_column(String(64), index=True)
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agreements.id", ondelete="SET NULL"), index=True
    )
    payer_email: Mapped[str | None] = mapped_column(String(254))
    payer_id: Mapped[str | None] = mapped_column(String(32))
    payer_name: Mapped[str | None] = mapped_column(String(200))
    payer_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    payment_type: Mapped[str] = mapped_column(String(16), default="unknown")
    source: Mapped[str] = mapped_column(String(10))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class PaymentLink(Base):
    __tablename__ = "payment_links"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), primary_key=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agreements.id"))
    deliverable_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProofFlag(Base):
    __tablename__ = "proof_flags"
    __table_args__ = (
        UniqueConstraint("payment_id", "rule"),
        _status_check("status", ("pass", "warn", "fail", "pending")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"))
    rule: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(7))
    explanation: Mapped[str] = mapped_column(String(500))
    fix: Mapped[str | None] = mapped_column(String(500))
    evaluated_at: Mapped[datetime] = _created_at()


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (
        _status_check("source", ("webhook", "seed")),
        CheckConstraint(
            "response_source IS NULL OR response_source IN ('ai', 'standard', 'edited')",
            name="response_source_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    paypal_dispute_id: Mapped[str] = mapped_column(String(64), unique=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    reason: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(10), default="webhook", server_default="webhook")
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    evidence_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(64))
    allowed: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    buyer_messages: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    response: Mapped[str | None] = mapped_column(Text)
    response_source: Mapped[str | None] = mapped_column(String(10))
    rejected: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    approval_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft_hash: Mapped[str | None] = mapped_column(String(64))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission: Mapped[dict | None] = mapped_column(JSONB)
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class Pack(Base):
    __tablename__ = "packs"
    __table_args__ = (
        _status_check("letter_source", ("ai", "standard", "edited")),
        Index("ix_packs_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    pdf_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    zip_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    letter: Mapped[str] = mapped_column(Text, default="", server_default="")
    letter_source: Mapped[str] = mapped_column(
        String(10), default="standard", server_default="standard"
    )
    summary: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentAction(Base):
    __tablename__ = "agent_actions"
    __table_args__ = (
        _status_check("status", ("proposed", "approved", "rejected", "executed", "failed")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    tool: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default="proposed")
    approval_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (_status_check("status", ("received", "processed", "ignored", "failed")),)

    paypal_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="received")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(300))
    received_at: Mapped[datetime] = _created_at()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    paypal_subscription_id: Mapped[str] = mapped_column(String(64), unique=True)
    plan_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    next_billing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (UniqueConstraint("user_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = _user_fk()
    seq: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(71))
    entry_hash: Mapped[str] = mapped_column(String(71))
    created_at: Mapped[datetime] = _created_at()
