"""The citation validator: no cover letter leaves Kweli citing proof that isn't there.

A letter passes only if:
- every citation ([P1], [D3], [T1], or a list like [P1, D3]) points at a payment, document or
  table that is actually in the pack;
- every amount it mentions is a real one: a payment, an invoice, an agreement fee or a total;
- every sentence with an amount cites something;
- when a sentence cites exactly one payment and names exactly one amount, that amount is the
  payment's own amount (or its invoice's), so an amount can't be pinned on the wrong payment;
- it names no email address and no link that isn't in the records.

This checks what can be checked mechanically. It doesn't prove every sentence true, so the
freelancer still reads the letter, and can edit it, before sending.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from packs.facts import PackFacts
from paypal.money import SUPPORTED_CURRENCIES, from_paypal_value

MIN_CHARS = 200
MAX_CHARS = 6000

CITATION = re.compile(r"\[([A-Z]\d+(?:\s*[,;]\s*[A-Z]\d+)*)\]")
LOOSE_REF = re.compile(r"\[\s*([A-Za-z]{1,3})\s*-?\s*(\d+)\s*\]")
CURRENCY_AMOUNT = re.compile(r"\b([A-Z]{3})\s?(\d[\d,]*(?:\.\d+)?)")
DOLLAR_AMOUNT = re.compile(r"(?<![A-Z])\$\s?(\d[\d,]*(?:\.\d+)?)")
BARE_DECIMAL = re.compile(r"(?<![\w.,$])(\d[\d,]*\.\d{2})(?![\d])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LINK = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
SENTENCE_END = re.compile(r"(?<=[.!?])(?<!\s[A-Z]\.)\s+|\n+")


@dataclass(frozen=True)
class Problem:
    code: str
    message: str
    excerpt: str = ""


@dataclass(frozen=True)
class Amount:
    currency: str | None
    minor: int
    text: str


def _to_minor(text: str, currency: str | None) -> int | None:
    digits = text.replace(",", "")
    try:
        Decimal(digits)
    except InvalidOperation:
        return None
    if currency and currency in SUPPORTED_CURRENCIES:
        try:
            return from_paypal_value(digits, currency)
        except ValueError:
            return None
    return int(Decimal(digits) * 100)


def amounts_in(text: str) -> list[Amount]:
    found: list[Amount] = []
    taken: list[tuple[int, int]] = []
    for match in CURRENCY_AMOUNT.finditer(text):
        currency = match.group(1)
        if currency not in SUPPORTED_CURRENCIES:
            continue
        minor = _to_minor(match.group(2), currency)
        if minor is not None:
            found.append(Amount(currency, minor, match.group(0)))
            taken.append(match.span())
    for match in DOLLAR_AMOUNT.finditer(text):
        minor = _to_minor(match.group(1), "USD")
        if minor is not None:
            found.append(Amount("USD", minor, match.group(0)))
            taken.append(match.span())
    for match in BARE_DECIMAL.finditer(text):
        if any(start <= match.start() < end for start, end in taken):
            continue
        minor = _to_minor(match.group(1), None)
        if minor is not None:
            found.append(Amount(None, minor, match.group(0)))
    return found


def citations_in(text: str) -> list[str]:
    refs: list[str] = []
    for match in CITATION.finditer(text):
        refs.extend(part.strip() for part in re.split(r"[,;]", match.group(1)))
    return refs


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_END.split(text) if part and part.strip()]


def _short(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _around(text: str, needle: str, width: int = 90) -> str:
    """A short excerpt centred on the problem, so the freelancer can find it."""
    text = " ".join(text.split())
    at = text.find(needle)
    if at < 0 or len(text) <= width:
        return _short(text, width)
    start = max(0, at - (width - len(needle)) // 2)
    end = min(len(text), start + width)
    start = max(0, end - width)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def validate(letter: str, facts: PackFacts) -> list[Problem]:
    problems: list[Problem] = []
    text = letter.strip()
    if len(text) < MIN_CHARS:
        problems.append(Problem("too_short", "The letter is too short to explain the payments."))
    if len(text) > MAX_CHARS:
        problems.append(Problem("too_long", f"Keep the letter under {MAX_CHARS:,} characters."))

    known = facts.refs
    cited = citations_in(text)
    if not cited and facts.payments:
        problems.append(Problem("no_citations", "The letter doesn't cite any payment or document."))
    for ref in dict.fromkeys(cited):
        if ref not in known:
            problems.append(Problem("unknown_ref", f"[{ref}] isn't in this pack.", f"[{ref}]"))
    for match in LOOSE_REF.finditer(text):
        ref = f"{match.group(1).upper()}{match.group(2)}"
        if not CITATION.fullmatch(match.group(0)) and ref not in known:
            problems.append(
                Problem("unknown_ref", f"{match.group(0)} isn't in this pack.", match.group(0))
            )

    allowed = facts.allowed_amounts()
    allowed_values = {minor for _, minor in allowed}
    for sentence in sentences(text):
        found = amounts_in(sentence)
        if not found:
            continue
        refs = citations_in(sentence)
        for amount in found:
            ok = (
                (amount.currency, amount.minor) in allowed
                if amount.currency
                else amount.minor in allowed_values
            )
            if not ok:
                problems.append(
                    Problem(
                        "unknown_amount",
                        f"{amount.text} doesn't match any payment, invoice or agreement.",
                        _around(sentence, amount.text),
                    )
                )
        if not refs:
            problems.append(
                Problem(
                    "uncited_amount",
                    "This sentence names an amount but doesn't cite where it comes from.",
                    _short(sentence),
                )
            )
            continue
        payments = [facts.payment(ref) for ref in refs if ref.startswith("P")]
        payments = [p for p in payments if p]
        if len(payments) == 1 and len(found) == 1:
            payment, amount = payments[0], found[0]
            own = {payment.amount_minor}
            if payment.invoice_amount_minor is not None:
                own.add(payment.invoice_amount_minor)
            currency_ok = amount.currency in (None, payment.currency)
            if amount.minor not in own or not currency_ok:
                problems.append(
                    Problem(
                        "wrong_amount",
                        f"[{payment.ref}] was {payment.amount}, not {amount.text}.",
                        _around(sentence, amount.text),
                    )
                )

    emails = {facts.freelancer_email.lower(), *facts.client_emails}
    for email in dict.fromkeys(EMAIL.findall(text)):
        if email.lower() not in emails:
            problems.append(Problem("unknown_email", f"{email} isn't in your records.", email))
    for link in dict.fromkeys(LINK.findall(text)):
        problems.append(Problem("link", "Leave links out of the letter.", _short(link, 60)))
    return problems
