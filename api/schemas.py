from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from paypal.money import SUPPORTED_CURRENCIES, from_paypal_value, to_paypal_value


def _currency(value: str) -> str:
    value = value.upper()
    if value not in SUPPORTED_CURRENCIES:
        raise ValueError("PayPal doesn't support this currency")
    return value


class ClientIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    country: str | None
    created_at: datetime


class AgreementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client: ClientIn
    title: str = Field(min_length=1, max_length=200)
    scope: str = Field(min_length=1, max_length=2000)
    deliverables: list[str] = Field(min_length=1, max_length=20)
    amount: str = Field(pattern=r"^\d{1,9}(\.\d{1,2})?$")
    currency: str
    due_date: date | None = None

    _check_currency = field_validator("currency")(_currency)

    @field_validator("deliverables")
    @classmethod
    def clean(cls, items: list[str]) -> list[str]:
        cleaned = [item.strip()[:200] for item in items if item.strip()]
        if not cleaned:
            raise ValueError("Add at least one deliverable")
        return cleaned

    def amount_minor(self) -> int:
        return from_paypal_value(self.amount, self.currency)


class AgreementOut(BaseModel):
    id: UUID
    client: ClientOut
    title: str
    scope: str
    deliverables: list[str]
    amount: str
    amount_minor: int
    currency: str
    due_date: date | None
    status: str
    sent_at: datetime | None
    accepted_at: datetime | None
    created_at: datetime
    invoice_id: UUID | None = None

    @classmethod
    def build(cls, agreement, invoice_id: UUID | None = None) -> "AgreementOut":
        return cls(
            id=agreement.id,
            client=ClientOut.model_validate(agreement.client),
            title=agreement.title,
            scope=agreement.scope,
            deliverables=agreement.deliverables,
            amount=to_paypal_value(agreement.amount_minor, agreement.currency),
            amount_minor=agreement.amount_minor,
            currency=agreement.currency,
            due_date=agreement.due_date,
            status=agreement.status,
            sent_at=agreement.sent_at,
            accepted_at=agreement.accepted_at,
            created_at=agreement.created_at,
            invoice_id=invoice_id,
        )


class AcceptLink(BaseModel):
    url: str
    expires_at: datetime


class InvoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agreement_id: UUID
    due_date: date | None = None
    note: str | None = Field(default=None, max_length=1000)


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agreement_id: UUID | None
    client_id: UUID
    paypal_invoice_id: str | None
    number: str
    description: str
    amount_minor: int
    currency: str
    due_date: date | None
    status: str
    payer_view_url: str | None
    sent_at: datetime | None
    created_at: datetime


class ThreadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread: str = Field(min_length=20, max_length=20_000)
