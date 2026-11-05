"""Turn the evidence plan into files for PayPal: agreement and invoice PDFs, vault files."""

import hashlib
from collections.abc import Callable
from uuid import UUID

from defender.evidence import DisputeFacts, EvidenceItem
from packs.facts import long_date, money
from packs.render import PackPDF
from paypal.disputes import EvidenceFile


def _pdf(title: str, heading: str, lines: list[str]) -> bytes:
    pdf = PackPDF(title)
    pdf.add_page()
    pdf.heading(heading, 16)
    for line in lines:
        if line:
            pdf.para(line, 10)
        pdf.ln(1.5)
    return bytes(pdf.output())


def agreement_pdf(facts: DisputeFacts) -> bytes:
    a = facts.agreement
    if a is None:
        raise ValueError("No agreement to attach")
    record = [
        f"Between {facts.freelancer_name} and {facts.client}.",
        f"Fee: {money(a.amount_minor, a.currency)}"
        + (f" · Due: {long_date(a.due_date)}" if a.due_date else ""),
        "",
        *a.terms,
        "",
        "Deliverables: " + "; ".join(a.deliverables) if a.deliverables else "",
        "",
        (
            f"Accepted by {facts.client} on {long_date(a.accepted_at)} at "
            f"{a.accepted_at:%H:%M} UTC through Kweli's acceptance link."
            + (
                f" Network fingerprint (one-way hash of the IP address): {a.accepted_ip_hash}."
                if a.accepted_ip_hash
                else ""
            )
        )
        if a.accepted_at
        else "Not accepted yet.",
    ]
    return _pdf(f"Agreement · {a.title}", f"Agreement: {a.title}", record)


def invoice_pdf(facts: DisputeFacts) -> bytes:
    i = facts.invoice
    if i is None:
        raise ValueError("No invoice to attach")
    lines = [
        f"From {facts.freelancer_name} ({facts.freelancer_email}) to {facts.client}"
        + (f" ({facts.client_email})" if facts.client_email else ""),
        f"Invoice number: {i.number}",
        f"PayPal invoice ID: {i.paypal_invoice_id or 'not sent'}",
        f"For: {i.description}",
        f"Amount: {money(i.amount_minor, i.currency)}",
        f"Sent: {long_date(i.sent_at) if i.sent_at else 'not sent'}",
        f"Status: {i.status.replace('_', ' ')}",
    ]
    if facts.transaction_id and facts.payment_amount_minor is not None:
        lines.append(
            f"Paid: {money(facts.payment_amount_minor, facts.currency)} on "
            f"{long_date(facts.payment_received_at)}, PayPal transaction {facts.transaction_id}"
        )
    return _pdf(f"Invoice {i.number}", f"PayPal invoice {i.number}", lines)


def build(
    facts: DisputeFacts, items: list[EvidenceItem], read_file: Callable[[UUID], bytes]
) -> list[tuple[str, EvidenceFile]]:
    """(evidence key, file) for every planned file, each vault file checked against its hash."""
    built: list[tuple[str, EvidenceFile]] = []
    for item in items:
        for planned in item.files:
            if planned.source == "agreement":
                data = agreement_pdf(facts)
            elif planned.source == "invoice":
                data = invoice_pdf(facts)
            else:
                data = read_file(planned.document_id)
                if hashlib.sha256(data).hexdigest() != planned.sha256:
                    raise ValueError(f"{planned.name} doesn't match its stored fingerprint")
            built.append((item.key, EvidenceFile(planned.name, data, planned.mime)))
    return built
