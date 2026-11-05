"""A demo ledger where each payment shows one kind of proof gap. Synthetic data only."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Agreement, Document, DocumentBlob, Invoice, Payment, User
from api.services.agreements import find_or_create_client
from proof.engine import evaluate_payment
from vault.crypto import encrypt


@dataclass(frozen=True)
class Scenario:
    key: str
    client: str
    email: str
    title: str
    billed: int
    paid: int
    days_ago: int
    payer: tuple[str, str] | None = None
    deliverable: bool = True
    payment_type: str = "invoice"
    invoiced: bool = True
    payer_known: bool = True


SCENARIOS = (
    Scenario("h1", "Acme Ltd", "jordan@acmeltd.com", "Social media kit", 60000, 60000, 80),
    Scenario(
        "h2", "Bloom Studio", "hello@bloomstudio.co.uk", "Product descriptions", 40000, 40000, 66
    ),
    Scenario("h3", "Acme Ltd", "jordan@acmeltd.com", "Pitch deck design", 90000, 90000, 52),
    Scenario(
        "h4", "Bloom Studio", "hello@bloomstudio.co.uk", "Newsletter templates", 50000, 50000, 40
    ),
    Scenario("complete", "Acme Ltd", "jordan@acmeltd.com", "Logo design", 80000, 80000, 21),
    Scenario(
        "no-work",
        "Bloom Studio",
        "hello@bloomstudio.co.uk",
        "Website copy",
        45000,
        45000,
        15,
        deliverable=False,
    ),
    Scenario(
        "partial", "Nairobi Eats", "orders@nairobieats.com", "Menu photography", 30000, 20000, 12
    ),
    Scenario(
        "third-party",
        "Kilele Tours",
        "info@kileletours.com",
        "Safari brochure",
        60000,
        60000,
        9,
        payer=("Mwangi Holdings", "accounts@mwangiholdings.com"),
    ),
    Scenario("spike", "Acme Ltd", "jordan@acmeltd.com", "Brand guidelines", 350000, 350000, 5),
    Scenario(
        "pending",
        "Bloom Studio",
        "hello@bloomstudio.co.uk",
        "Blog posts",
        25000,
        25000,
        1,
        payer_known=False,
    ),
    Scenario(
        "personal",
        "",
        "",
        "",
        0,
        15000,
        3,
        payer=("D. Otieno", "d.otieno@mail.com"),
        deliverable=False,
        payment_type="personal",
        invoiced=False,
    ),
)

PDF = b"%PDF-1.4\n%Kweli demo deliverable\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _deliverable(db: Session, user: User, agreement: Agreement, title: str) -> None:
    document = Document(
        user_id=user.id,
        agreement_id=agreement.id,
        kind="deliverable",
        filename=f"{title.lower().replace(' ', '-')}-final.pdf",
        mime="application/pdf",
        size=len(PDF),
        sha256=hashlib.sha256(PDF).hexdigest(),
        storage_key="db",
        encrypted_dek="",
    )
    db.add(document)
    db.flush()
    nonce, ciphertext, wrapped = encrypt(document.id, PDF)
    document.encrypted_dek = wrapped
    db.add(DocumentBlob(document_id=document.id, nonce=nonce, ciphertext=ciphertext))


def build_demo_ledger(db: Session, user: User, now: datetime | None = None) -> int:
    """Create the demo ledger once. Returns how many payments were added."""
    if db.scalar(select(Payment.id).where(Payment.user_id == user.id, Payment.source == "seed")):
        return 0
    now = now or datetime.now(UTC)
    payments: list[Payment] = []
    for index, scenario in enumerate(SCENARIOS, start=1):
        received = (now - timedelta(days=scenario.days_ago)).replace(microsecond=0)
        paypal_invoice_id = None
        if scenario.invoiced:
            client = find_or_create_client(db, user.id, scenario.client, scenario.email)
            agreement = Agreement(
                user_id=user.id,
                client_id=client.id,
                title=scenario.title,
                scope=f"{scenario.title} for {scenario.client}.",
                deliverables=[f"Final {scenario.title.lower()} files"],
                amount_minor=scenario.billed,
                currency="USD",
                due_date=date.fromordinal(received.toordinal()),
                status="accepted",
                sent_at=received - timedelta(days=9),
                accepted_at=received - timedelta(days=8),
            )
            db.add(agreement)
            db.flush()
            paypal_invoice_id = f"SEED-INV-{index:04d}"
            db.add(
                Invoice(
                    user_id=user.id,
                    client_id=client.id,
                    agreement_id=agreement.id,
                    paypal_invoice_id=paypal_invoice_id,
                    number=f"{index:04d}",
                    description=scenario.title,
                    amount_minor=scenario.billed,
                    currency="USD",
                    due_date=agreement.due_date,
                    status="paid" if scenario.paid >= scenario.billed else "partially_paid",
                    sent_at=received - timedelta(days=7),
                    paid_at=received,
                )
            )
            if scenario.deliverable:
                _deliverable(db, user, agreement, scenario.title)
        payer_name, payer_email = scenario.payer or (scenario.client, scenario.email)
        payment = Payment(
            user_id=user.id,
            paypal_transaction_id=f"SEED-PAY-{index:04d}",
            paypal_invoice_id=paypal_invoice_id,
            payer_email=payer_email if scenario.payer_known else None,
            payer_name=payer_name if scenario.payer_known else None,
            payer_resolved_at=received if scenario.payer_known else None,
            amount_minor=scenario.paid,
            currency="USD",
            payment_type=scenario.payment_type,
            source="seed",
            received_at=received,
        )
        db.add(payment)
        payments.append(payment)
    db.flush()
    for payment in payments:
        evaluate_payment(db, payment)
    db.commit()
    return len(payments)
