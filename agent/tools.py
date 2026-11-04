"""What the agent can see and do.

Read tools return Kweli's own records, or PayPal's via the official Agent Toolkit. Proposal
tools only create approval cards (agent/actions.py). There is deliberately no tool that
approves, sends money, changes amounts or sets an email address.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from agent import actions
from agent.toolkit import ToolkitClientAdapter, toolkit_specs
from api.config import get_settings
from api.db.models import Agreement, Client, Invoice, Payment, ProofFlag, User
from api.services.invoicing import ServiceError
from paypal.client import PayPalClient
from paypal.errors import PayPalError
from paypal.money import to_paypal_value
from proof.rules import SEVERITY

UUID_SCHEMA = {"type": "string", "description": "An id returned by another tool"}

KWELI_TOOLS = [
    {
        "name": "find_agreements",
        "description": "Search the freelancer's agreements by client name or work title. Returns "
        "each agreement's id, client, fee, status, due date and its invoice if there is one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Client or work, e.g. 'Acme logo'"},
                "status": {"type": "string", "enum": ["draft", "sent", "accepted", "expired"]},
            },
        },
    },
    {
        "name": "ledger_overview",
        "description": "How well the freelancer's received payments are proven: counts by status "
        "and the payments that most need attention, with the reason and fix for each.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "explain_payment",
        "description": "Every proof check for one payment, with explanations and fixes.",
        "input_schema": {
            "type": "object",
            "properties": {"payment_id": UUID_SCHEMA},
            "required": ["payment_id"],
        },
    },
    {
        "name": "propose_invoice",
        "description": "Propose invoicing the client for an ACCEPTED agreement. The amount and "
        "recipient always come from the agreement. Shows an approval card; nothing happens "
        "until the freelancer approves it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agreement_id": UUID_SCHEMA,
                "due_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
                "send": {"type": "boolean", "description": "Email it now (default true)"},
            },
            "required": ["agreement_id"],
        },
    },
    {
        "name": "propose_send_invoice",
        "description": "Propose sending an existing DRAFT invoice. Shows an approval card.",
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": UUID_SCHEMA},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "propose_reminder",
        "description": "Propose a PayPal payment reminder for a sent, unpaid invoice. Shows an "
        "approval card.",
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": UUID_SCHEMA},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "propose_acceptance_link",
        "description": "Propose a new link the client uses to accept an agreement that isn't "
        "accepted yet. Shows an approval card.",
        "input_schema": {
            "type": "object",
            "properties": {"agreement_id": UUID_SCHEMA},
            "required": ["agreement_id"],
        },
    },
]

TOOLKIT_METHODS = {"get_invoice", "list_invoices", "list_transactions"}
LABELS = {
    "find_agreements": "Looked up agreements",
    "ledger_overview": "Checked the proof ledger",
    "explain_payment": "Read a payment's proof checks",
    "propose_invoice": "Prepared an invoice for your approval",
    "propose_send_invoice": "Prepared an invoice to send for your approval",
    "propose_reminder": "Prepared a reminder for your approval",
    "propose_acceptance_link": "Prepared an acceptance link for your approval",
    "get_invoice": "Read the invoice from PayPal",
    "list_invoices": "Listed invoices from PayPal",
    "list_transactions": "Searched PayPal transactions",
}
PROPOSALS = {
    "propose_invoice": "create_invoice",
    "propose_send_invoice": "send_invoice",
    "propose_reminder": "send_reminder",
    "propose_acceptance_link": "acceptance_link",
}
MAX_RESULT_CHARS = 6000


@dataclass
class Step:
    tool: str
    label: str
    ok: bool


@dataclass
class Toolbox:
    db: Session
    user_id: UUID
    paypal: PayPalClient
    steps: list[Step] = field(default_factory=list)
    proposals: list[actions.Proposal] = field(default_factory=list)
    _toolkit: dict | None = None

    def _merchant_owner(self) -> bool:
        merchant = get_settings().paypal_merchant_id
        user = self.db.get(User, self.user_id)
        return bool(merchant and user and user.paypal_merchant_id == merchant)

    def definitions(self) -> list[dict]:
        tools = list(KWELI_TOOLS)
        if self._merchant_owner():
            try:
                self._toolkit = toolkit_specs(TOOLKIT_METHODS)
            except ImportError:
                self._toolkit = {}
            for name, spec in sorted(self._toolkit.items()):
                tools.append(
                    {
                        "name": name,
                        "description": spec["description"][:1000],
                        "input_schema": spec["args_schema"].model_json_schema(),
                    }
                )
        return tools

    def run(self, name: str, arguments: dict) -> tuple[dict, bool]:
        try:
            if name in PROPOSALS:
                result = self._propose(PROPOSALS[name], arguments)
            elif self._toolkit and name in self._toolkit:
                result = self._paypal(name, arguments)
            elif name == "find_agreements":
                result = self._find_agreements(arguments)
            elif name == "ledger_overview":
                result = self._ledger_overview()
            elif name == "explain_payment":
                result = self._explain_payment(arguments)
            else:
                raise ServiceError(400, f"There is no tool called {name}.")
            ok = True
        except ServiceError as error:
            result, ok = {"error": error.message}, False
        except (ValueError, KeyError, TypeError):
            result, ok = {"error": "Those arguments aren't valid for this tool."}, False
        self.steps.append(Step(name, LABELS.get(name, name), ok))
        return result, ok

    # Read tools -------------------------------------------------------------------------

    def _find_agreements(self, arguments: dict) -> dict:
        query = (
            select(Agreement)
            .options(selectinload(Agreement.client))
            .join(Client, Client.id == Agreement.client_id)
            .where(Agreement.user_id == self.user_id)
            .order_by(Agreement.created_at.desc())
            .limit(10)
        )
        if text := str(arguments.get("query") or "").strip()[:100]:
            words = [word for word in text.split() if len(word) > 1][:5]
            for word in words:
                query = query.where(
                    or_(Client.name.ilike(f"%{word}%"), Agreement.title.ilike(f"%{word}%"))
                )
        if status := arguments.get("status"):
            query = query.where(Agreement.status == str(status))
        rows = self.db.scalars(query).all()
        invoices = {
            invoice.agreement_id: invoice
            for invoice in self.db.scalars(
                select(Invoice).where(
                    Invoice.agreement_id.in_([row.id for row in rows]),
                    Invoice.status != "cancelled",
                )
            )
        }
        return {
            "agreements": [
                {
                    "id": str(row.id),
                    "client": row.client.name,
                    "work": row.title,
                    "fee": f"{row.currency} {to_paypal_value(row.amount_minor, row.currency)}",
                    "status": row.status,
                    "due_date": row.due_date.isoformat() if row.due_date else None,
                    "invoice": {
                        "id": str(invoices[row.id].id),
                        "number": invoices[row.id].number,
                        "status": invoices[row.id].status,
                    }
                    if row.id in invoices
                    else None,
                }
                for row in rows
            ]
        }

    def _ledger_overview(self) -> dict:
        payments = self.db.scalars(
            select(Payment)
            .where(Payment.user_id == self.user_id)
            .order_by(Payment.received_at.desc())
        ).all()
        flags: dict[UUID, list[ProofFlag]] = {}
        for flag in self.db.scalars(
            select(ProofFlag).where(ProofFlag.payment_id.in_([p.id for p in payments]))
        ):
            flags.setdefault(flag.payment_id, []).append(flag)
        counts = {"pass": 0, "warn": 0, "fail": 0, "pending": 0}
        attention = []
        for payment in payments:
            own = flags.get(payment.id, [])
            overall = max((f.status for f in own), key=SEVERITY.__getitem__, default="pending")
            counts[overall] += 1
            problems = [f for f in own if f.status in ("fail", "warn")]
            if problems:
                attention.append(
                    {
                        "payment_id": str(payment.id),
                        "received": payment.received_at.date().isoformat(),
                        "amount": f"{payment.currency} "
                        f"{to_paypal_value(payment.amount_minor, payment.currency)}",
                        "status": overall,
                        "problems": [
                            {"check": f.rule, "explanation": f.explanation, "fix": f.fix}
                            for f in sorted(problems, key=lambda f: f.rule)
                        ],
                    }
                )
        attention.sort(key=lambda item: SEVERITY[item["status"]], reverse=True)
        return {
            "payments": len(payments),
            "fully_proven": counts["pass"],
            "need_attention": counts["warn"],
            "missing_proof": counts["fail"],
            "being_checked": counts["pending"],
            "most_urgent": attention[:5],
        }

    def _explain_payment(self, arguments: dict) -> dict:
        payment = self.db.scalar(
            select(Payment).where(
                Payment.id == UUID(str(arguments["payment_id"])), Payment.user_id == self.user_id
            )
        )
        if not payment:
            raise ServiceError(404, "Payment not found")
        rows = self.db.scalars(
            select(ProofFlag).where(ProofFlag.payment_id == payment.id).order_by(ProofFlag.rule)
        )
        return {
            "amount": f"{payment.currency} "
            f"{to_paypal_value(payment.amount_minor, payment.currency)}",
            "received": payment.received_at.date().isoformat(),
            "checks": [
                {"check": f.rule, "status": f.status, "explanation": f.explanation, "fix": f.fix}
                for f in rows
            ],
        }

    def _paypal(self, name: str, arguments: dict) -> dict:
        if name == "get_invoice":
            owned = self.db.scalar(
                select(Invoice.id).where(
                    Invoice.user_id == self.user_id,
                    Invoice.paypal_invoice_id == str(arguments.get("invoice_id", "")),
                )
            )
            if not owned:
                raise ServiceError(404, "That isn't one of your Kweli invoices.")
        spec = self._toolkit[name]
        try:
            raw = spec["execute"](ToolkitClientAdapter(self.paypal), dict(arguments))
        except PayPalError as error:
            raise ServiceError(502, f"PayPal said {error.name or error.status}.") from None
        try:
            return {"paypal": json.loads(raw)}
        except (TypeError, ValueError):
            return {"paypal": str(raw)[:MAX_RESULT_CHARS]}

    # Proposal tools ---------------------------------------------------------------------

    def _propose(self, kind: str, arguments: dict) -> dict:
        args: dict = {}
        for key in ("agreement_id", "invoice_id"):
            if key in arguments:
                args[key] = str(UUID(str(arguments[key])))
        if kind == "create_invoice":
            args["send"] = bool(arguments.get("send", True))
            if arguments.get("due_date"):
                due = date.fromisoformat(str(arguments["due_date"]))
                today = datetime.now(UTC).date()
                if not today <= due <= today + timedelta(days=365):
                    raise ServiceError(422, "The due date must be between today and a year away.")
                args["due_date"] = due.isoformat()
        proposal = actions.propose(self.db, self.user_id, kind, args)
        self.proposals.append(proposal)
        return {
            "proposal_id": str(proposal.action.id),
            "shown_to_freelancer": proposal.preview.title,
            "details": dict(proposal.preview.details),
            "status": "waiting for the freelancer to approve or decline",
        }
