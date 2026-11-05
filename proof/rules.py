"""The seven proof rules. Pure functions of the facts: no database, no network, no AI.

Each rule answers one question a payment reviewer asks, and returns a status with a plain
explanation and, when something is missing, the fix.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from paypal.money import to_paypal_value

Status = Literal["pass", "warn", "fail", "pending"]
SEVERITY: dict[str, int] = {"fail": 3, "warn": 2, "pending": 1, "pass": 0}

VOLUME_MULTIPLE = 3
VOLUME_MIN_HISTORY = 3


@dataclass(frozen=True)
class Result:
    rule: str
    status: Status
    explanation: str
    fix: str | None = None


@dataclass(frozen=True)
class PaymentFacts:
    amount_minor: int
    currency: str
    received_at: datetime
    payment_type: str
    payer_email: str | None
    payer_name: str | None
    payer_known: bool


@dataclass(frozen=True)
class InvoiceFacts:
    number: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class AgreementFacts:
    title: str
    client_name: str
    client_email: str
    status: str
    accepted_at: datetime | None


@dataclass(frozen=True)
class Facts:
    payment: PaymentFacts
    invoice: InvoiceFacts | None = None
    agreement: AgreementFacts | None = None
    deliverable_name: str | None = None
    recent_amounts_minor: list[int] = field(default_factory=list)
    payer_confirmation_name: str | None = None


def _money(minor: int, currency: str) -> str:
    return f"{currency} {to_paypal_value(minor, currency)}"


def p1_invoiced(facts: Facts) -> Result:
    if facts.invoice:
        return Result("P1", "pass", f"Matches invoice {facts.invoice.number}.")
    return Result(
        "P1",
        "fail",
        "This payment isn't linked to a Kweli invoice.",
        "Bill this client through a Kweli invoice next time, so each payment has its invoice.",
    )


def p2_amount_matches(facts: Facts) -> Result:
    invoice, payment = facts.invoice, facts.payment
    if not invoice:
        return Result(
            "P2",
            "fail",
            "There's no invoice to compare the amount with.",
            "Link the payment to an invoice first.",
        )
    paid = _money(payment.amount_minor, payment.currency)
    billed = _money(invoice.amount_minor, invoice.currency)
    if payment.currency != invoice.currency:
        return Result(
            "P2",
            "fail",
            f"Paid {paid} against an invoice in {invoice.currency}.",
            "Ask the client to pay in the invoice currency, or reissue the invoice.",
        )
    if payment.amount_minor == invoice.amount_minor:
        return Result("P2", "pass", f"Paid {paid}, the invoiced amount.")
    if payment.amount_minor < invoice.amount_minor:
        return Result(
            "P2",
            "warn",
            f"Paid {paid} of {billed}.",
            "Record it as a part payment, or remind the client about the balance.",
        )
    return Result(
        "P2",
        "warn",
        f"Paid {paid}, more than the {billed} invoiced.",
        "Note why the client paid more, or refund the difference.",
    )


def p3_payer_is_client(facts: Facts) -> Result:
    payment, agreement = facts.payment, facts.agreement
    if not agreement:
        return Result(
            "P3",
            "fail",
            "There's no agreement saying who the client is.",
            "Add an agreement with this client.",
        )
    if not payment.payer_known:
        return Result(
            "P3",
            "pending",
            "Waiting for PayPal to confirm who paid.",
            "Nothing to do. Kweli checks again automatically.",
        )
    if payment.payer_email and payment.payer_email.lower() == agreement.client_email.lower():
        return Result(
            "P3", "pass", f"Paid by {agreement.client_name}, the client on the agreement."
        )
    who = payment.payer_name or "someone else"
    if facts.payer_confirmation_name:
        return Result(
            "P3",
            "pass",
            f"Paid by {who} for {agreement.client_name}. Their written confirmation is on file: "
            f"{facts.payer_confirmation_name}.",
        )
    return Result(
        "P3",
        "warn",
        f"Paid by {who}, not {agreement.client_name}.",
        f"Ask {agreement.client_name} to confirm in writing that this payment is theirs, "
        "and upload it.",
    )


def p4_agreement_accepted(facts: Facts) -> Result:
    agreement = facts.agreement
    if not agreement:
        return Result(
            "P4",
            "fail",
            "There's no agreement for this work.",
            "Link this payment to its agreement, or create one and send it to the client.",
        )
    if agreement.status != "accepted" or not agreement.accepted_at:
        return Result(
            "P4",
            "warn",
            f"The client hasn't accepted '{agreement.title}' yet.",
            "Send them the acceptance link again.",
        )
    if agreement.accepted_at > facts.payment.received_at:
        return Result(
            "P4",
            "warn",
            "The agreement was accepted after the payment arrived.",
            "Fine to keep, but agree terms before payment next time.",
        )
    return Result(
        "P4",
        "pass",
        f"{agreement.client_name} accepted '{agreement.title}' "
        f"on {agreement.accepted_at:%d %b %Y}.",
    )


def p5_work_delivered(facts: Facts) -> Result:
    if facts.deliverable_name:
        return Result("P5", "pass", f"Delivered work on file: {facts.deliverable_name}.")
    if not facts.agreement:
        return Result(
            "P5",
            "fail",
            "There's no agreement to attach the delivered work to.",
            "Add an agreement, then upload the work.",
        )
    return Result(
        "P5",
        "fail",
        "No delivered work is attached.",
        "Upload the final file, or a document linking to it.",
    )


def p6_business_payment(facts: Facts) -> Result:
    kind = facts.payment.payment_type
    if kind in ("invoice", "goods_services"):
        return Result("P6", "pass", "Paid as a business payment.")
    if kind == "personal":
        return Result(
            "P6",
            "warn",
            "Paid as a personal 'friends and family' payment.",
            "Use a Kweli invoice for client work, so it's clearly a business payment.",
        )
    return Result(
        "P6",
        "pending",
        "PayPal hasn't said what kind of payment this is yet.",
        "Nothing to do. Kweli checks again automatically.",
    )


def p7_usual_volume(facts: Facts) -> Result:
    history = facts.recent_amounts_minor
    if len(history) < VOLUME_MIN_HISTORY:
        return Result("P7", "pass", "Not enough history yet to compare amounts.")
    average = sum(history) / len(history)
    if facts.payment.amount_minor > VOLUME_MULTIPLE * average:
        times = facts.payment.amount_minor / average
        return Result(
            "P7",
            "warn",
            f"About {times:.0f}× your usual payment over the last 90 days.",
            "Large payments get extra checks. Make sure everything else here is complete.",
        )
    return Result("P7", "pass", "In line with your usual payments.")


RULES = (
    p1_invoiced,
    p2_amount_matches,
    p3_payer_is_client,
    p4_agreement_accepted,
    p5_work_delivered,
    p6_business_payment,
    p7_usual_volume,
)


def evaluate(facts: Facts) -> list[Result]:
    return [rule(facts) for rule in RULES]


def overall(results: list[Result]) -> Status:
    if not results:
        return "pending"
    return max((result.status for result in results), key=SEVERITY.__getitem__)
