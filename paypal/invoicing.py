from dataclasses import dataclass
from datetime import date

from paypal.client import PayPalClient
from paypal.money import money

BASE = "/v2/invoicing"


@dataclass(frozen=True)
class InvoiceDraft:
    invoice_number: str
    currency: str
    recipient_email: str
    recipient_name: str
    item_name: str
    amount_minor: int
    due_date: date | None = None
    note: str | None = None
    item_description: str | None = None


def build_invoice_payload(draft: InvoiceDraft) -> dict:
    detail: dict = {"invoice_number": draft.invoice_number, "currency_code": draft.currency}
    if draft.note:
        detail["note"] = draft.note[:4000]
    if draft.due_date:
        detail["payment_term"] = {"due_date": draft.due_date.isoformat()}
    item = {
        "name": draft.item_name[:200],
        "quantity": "1",
        "unit_amount": money(draft.amount_minor, draft.currency),
        "unit_of_measure": "AMOUNT",
    }
    if draft.item_description:
        item["description"] = draft.item_description[:1000]
    return {
        "detail": detail,
        "primary_recipients": [
            {
                "billing_info": {
                    "business_name": draft.recipient_name[:300],
                    "email_address": draft.recipient_email,
                }
            }
        ],
        "items": [item],
    }


def payer_view_url(body: dict) -> str | None:
    for link in body.get("links", []):
        if link.get("rel") == "payer-view":
            return link.get("href")
    if body.get("rel") == "payer-view":
        return body.get("href")
    return None


class Invoicing:
    def __init__(self, client: PayPalClient) -> None:
        self.client = client

    def next_invoice_number(self) -> str:
        return self.client.post(f"{BASE}/generate-next-invoice-number")["invoice_number"]

    def create_draft(self, draft: InvoiceDraft, request_id: str | None = None) -> dict:
        return self.client.post(
            f"{BASE}/invoices",
            json=build_invoice_payload(draft),
            request_id=request_id,
            prefer_representation=True,
        )

    def send(self, invoice_id: str, request_id: str | None = None) -> dict:
        return self.client.post(
            f"{BASE}/invoices/{invoice_id}/send",
            json={"send_to_invoicer": False, "send_to_recipient": True},
            request_id=request_id,
        )

    def remind(self, invoice_id: str, request_id: str | None = None) -> dict:
        return self.client.post(
            f"{BASE}/invoices/{invoice_id}/remind",
            json={"send_to_invoicer": False, "send_to_recipient": True},
            request_id=request_id,
        )

    def cancel(self, invoice_id: str, request_id: str | None = None) -> dict:
        return self.client.post(
            f"{BASE}/invoices/{invoice_id}/cancel",
            json={"send_to_invoicer": False, "send_to_recipient": True},
            request_id=request_id,
        )

    def get(self, invoice_id: str) -> dict:
        return self.client.get(f"{BASE}/invoices/{invoice_id}")
