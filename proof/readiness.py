"""Readiness: one score for how ready the freelancer is for a PayPal review, and what to fix.

Pure functions of the stored proof checks. No database, no network, no AI.

Scoring
- Every check that has a result scores: pass = 1, warn = 0.5, fail = 0.
- Checks still waiting on PayPal ("pending") are left out. The freelancer can't act on them.
- P7 (unusual amount) is advice, not proof: a large payment isn't something to fix, so it is
  left out of the score and the fix list. It is counted separately so the UI can mention it.
- Score = points earned / points possible, as a whole number from 0 to 100.
- "Ready" needs 90 or more and no payment with missing proof; "nearly" is 70 or more.

Fix next
- One item per payment with something to fix, listing its steps.
- Steps that only fail because of another missing step are hidden: no invoice means the amount
  can't match (P2), and no agreement means there's no client to compare the payer with (P3) and
  nothing to attach the work to (P5). Fixing the root step is the real fix.
- Ordered by the worst check (missing before needs attention), then by how many score points
  fixing it would win, then by amount, then newest first.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from proof.rules import SEVERITY

POINTS: dict[str, float] = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
ADVISORY = frozenset({"P7"})
READY_AT = 90
NEARLY_AT = 70

Band = Literal["ready", "nearly", "at_risk", "no_payments"]


@dataclass(frozen=True)
class Check:
    rule: str
    status: str
    explanation: str
    fix: str | None


@dataclass(frozen=True)
class PaymentProof:
    payment_id: UUID
    received_at: datetime
    client: str
    amount_minor: int
    currency: str
    agreement_id: UUID | None
    checks: tuple[Check, ...]


@dataclass(frozen=True)
class Step:
    rule: str
    status: str
    problem: str
    fix: str


@dataclass(frozen=True)
class FixItem:
    payment_id: UUID
    agreement_id: UUID | None
    client: str
    amount_minor: int
    currency: str
    received_at: datetime
    status: str
    steps: tuple[Step, ...]
    points: int


@dataclass
class ClientSummary:
    client: str
    payments: int = 0
    totals: dict[str, int] = field(default_factory=dict)
    statuses: dict[str, int] = field(
        default_factory=lambda: {"pass": 0, "warn": 0, "fail": 0, "pending": 0}
    )
    earned: float = 0.0
    possible: int = 0

    @property
    def score(self) -> int | None:
        return round(100 * self.earned / self.possible) if self.possible else None


@dataclass(frozen=True)
class Readiness:
    score: int | None
    band: Band
    payments: int
    statuses: dict[str, int]
    checks: dict[str, int]
    large_payments: int
    fix_next: tuple[FixItem, ...]
    clients: tuple[ClientSummary, ...]


def band_for(score: int | None, missing: int = 0) -> Band:
    """Ready needs the score and no missing proof: one unproven payment can start a review."""
    if score is None:
        return "no_payments"
    if score >= READY_AT and not missing:
        return "ready"
    if score >= NEARLY_AT:
        return "nearly"
    return "at_risk"


def overall(checks: tuple[Check, ...]) -> str:
    if not checks:
        return "pending"
    return max((check.status for check in checks), key=SEVERITY.__getitem__)


def _scored(checks: tuple[Check, ...]) -> list[Check]:
    return [c for c in checks if c.rule not in ADVISORY and c.status in POINTS]


def _hidden(proof: PaymentProof) -> set[str]:
    status = {check.rule: check.status for check in proof.checks}
    hidden: set[str] = set()
    if status.get("P1") == "fail":
        hidden.add("P2")
    if proof.agreement_id is None:
        hidden |= {"P3", "P5"}
    return hidden


def steps_for(proof: PaymentProof) -> tuple[Step, ...]:
    hidden = _hidden(proof)
    steps: list[Step] = []
    seen: set[str] = set()
    for check in sorted(proof.checks, key=lambda c: c.rule):
        if check.rule in ADVISORY or check.rule in hidden:
            continue
        if check.status not in ("warn", "fail") or not check.fix or check.fix in seen:
            continue
        seen.add(check.fix)
        steps.append(Step(check.rule, check.status, check.explanation, check.fix))
    return tuple(steps)


def assess(payments: list[PaymentProof]) -> Readiness:
    earned = 0.0
    possible = 0
    statuses = {"pass": 0, "warn": 0, "fail": 0, "pending": 0}
    checks = {"pass": 0, "warn": 0, "fail": 0, "pending": 0}
    large = 0
    clients: dict[str, ClientSummary] = {}
    per_payment: list[tuple[PaymentProof, float, int]] = []

    for proof in payments:
        worst = overall(proof.checks)
        statuses[worst] += 1
        for check in proof.checks:
            if check.rule in ADVISORY:
                large += check.status == "warn"
            elif check.status in checks:
                checks[check.status] += 1
        scored = _scored(proof.checks)
        mine = sum(POINTS[c.status] for c in scored)
        earned += mine
        possible += len(scored)
        per_payment.append((proof, mine, len(scored)))

        summary = clients.setdefault(proof.client, ClientSummary(proof.client))
        summary.payments += 1
        summary.totals[proof.currency] = summary.totals.get(proof.currency, 0) + proof.amount_minor
        summary.statuses[worst] += 1
        summary.earned += mine
        summary.possible += len(scored)

    score = round(100 * earned / possible) if possible else None
    fixes: list[FixItem] = []
    for proof, mine, count in per_payment:
        steps = steps_for(proof)
        if not steps:
            continue
        gain = round(100 * (count - mine) / possible) if possible else 0
        fixes.append(
            FixItem(
                payment_id=proof.payment_id,
                agreement_id=proof.agreement_id,
                client=proof.client,
                amount_minor=proof.amount_minor,
                currency=proof.currency,
                received_at=proof.received_at,
                status=max((s.status for s in steps), key=SEVERITY.__getitem__),
                steps=steps,
                points=gain,
            )
        )
    fixes.sort(
        key=lambda item: (
            -SEVERITY[item.status],
            -item.points,
            -item.amount_minor,
            -item.received_at.timestamp(),
        )
    )
    ordered_clients = sorted(
        clients.values(),
        key=lambda c: (c.score if c.score is not None else 101, -c.payments, c.client.lower()),
    )
    return Readiness(
        score=score,
        band=band_for(score, statuses["fail"]),
        payments=len(payments),
        statuses=statuses,
        checks=checks,
        large_payments=large,
        fix_next=tuple(fixes),
        clients=tuple(ordered_clients),
    )


def group_checks(rows) -> dict[UUID, list[Check]]:
    """ProofFlag-like rows (payment_id, rule, status, explanation, fix) grouped by payment."""
    grouped: dict[UUID, list[Check]] = defaultdict(list)
    for row in rows:
        grouped[row.payment_id].append(Check(row.rule, row.status, row.explanation, row.fix))
    return grouped
