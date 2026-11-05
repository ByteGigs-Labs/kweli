"""Read a user's payments with their proof checks, links and client names."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Agreement, Client, Payment, PaymentLink, ProofFlag
from proof.readiness import Check, PaymentProof, group_checks


@dataclass
class LedgerContext:
    flags: dict[UUID, list[ProofFlag]]
    links: dict[UUID, PaymentLink]
    clients: dict[UUID, str]

    def client_for(self, payment: Payment) -> str:
        link = self.links.get(payment.id)
        name = self.clients.get(link.agreement_id) if link and link.agreement_id else None
        return name or payment.payer_name or payment.payer_email or "Unknown payer"


def load_context(db: Session, payments: list[Payment]) -> LedgerContext:
    ids = [payment.id for payment in payments]
    flags: dict[UUID, list[ProofFlag]] = {payment_id: [] for payment_id in ids}
    links: dict[UUID, PaymentLink] = {}
    clients: dict[UUID, str] = {}
    if not ids:
        return LedgerContext(flags, links, clients)
    for flag in db.scalars(
        select(ProofFlag).where(ProofFlag.payment_id.in_(ids)).order_by(ProofFlag.rule)
    ):
        flags[flag.payment_id].append(flag)
    links = {
        link.payment_id: link
        for link in db.scalars(select(PaymentLink).where(PaymentLink.payment_id.in_(ids)))
    }
    agreement_ids = [link.agreement_id for link in links.values() if link.agreement_id]
    if agreement_ids:
        clients = dict(
            db.execute(
                select(Agreement.id, Client.name)
                .join(Client, Client.id == Agreement.client_id)
                .where(Agreement.id.in_(agreement_ids))
            ).all()
        )
    return LedgerContext(flags, links, clients)


def proofs_for_user(db: Session, user_id: UUID) -> list[PaymentProof]:
    payments = list(
        db.scalars(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.received_at.desc())
        )
    )
    context = load_context(db, payments)
    checks = group_checks(flag for rows in context.flags.values() for flag in rows)
    proofs = []
    for payment in payments:
        link = context.links.get(payment.id)
        proofs.append(
            PaymentProof(
                payment_id=payment.id,
                received_at=payment.received_at,
                client=context.client_for(payment),
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                agreement_id=link.agreement_id if link else None,
                checks=tuple(checks.get(payment.id, [])),
            )
        )
    return proofs


__all__ = ["Check", "LedgerContext", "load_context", "proofs_for_user"]
