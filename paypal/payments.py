"""Read-only lookups used to turn a webhook into a trustworthy payment record."""

from datetime import datetime, timedelta

from paypal.client import PayPalClient
from paypal.errors import PayPalError


def get_capture(client: PayPalClient, capture_id: str) -> dict:
    return client.get(f"/v2/payments/captures/{capture_id}")


def get_order(client: PayPalClient, order_id: str) -> dict:
    return client.get(f"/v2/checkout/orders/{order_id}")


def find_transaction(client: PayPalClient, transaction_id: str, around: datetime) -> dict | None:
    """Look a transaction up in Transaction Search. PayPal can take hours to index it."""
    start = (around - timedelta(days=1)).replace(microsecond=0)
    end = (around + timedelta(days=1)).replace(microsecond=0)
    try:
        body = client.get(
            "/v1/reporting/transactions",
            params={
                "transaction_id": transaction_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "fields": "transaction_info,payer_info",
            },
        )
    except PayPalError:
        return None
    details = body.get("transaction_details") or []
    return details[0] if details else None


def payer_from_transaction(detail: dict) -> tuple[str | None, str | None, str | None]:
    info = detail.get("payer_info") or {}
    name = (info.get("payer_name") or {}).get("alternate_full_name")
    return info.get("email_address"), info.get("account_id"), name
