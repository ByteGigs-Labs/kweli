"""PayPal webhook signature verification (postback to PayPal's verify API)."""

import json
from collections.abc import Mapping

from paypal.client import PayPalClient

HEADERS = {
    "auth_algo": "paypal-auth-algo",
    "cert_url": "paypal-cert-url",
    "transmission_id": "paypal-transmission-id",
    "transmission_sig": "paypal-transmission-sig",
    "transmission_time": "paypal-transmission-time",
}


class MissingSignature(ValueError):
    pass


def signature_fields(headers: Mapping[str, str]) -> dict[str, str]:
    lowered = {key.lower(): value for key, value in headers.items()}
    fields = {name: lowered.get(header, "") for name, header in HEADERS.items()}
    if not all(fields.values()):
        raise MissingSignature("PayPal signature headers are missing")
    return fields


def verify(
    client: PayPalClient, headers: Mapping[str, str], raw_body: bytes, webhook_id: str
) -> bool:
    """True only when PayPal confirms the event was signed for this webhook.

    The event goes back to PayPal byte-for-byte. Re-serialising parsed JSON can change number
    formatting or key order and make genuine events fail verification.
    """
    fields = signature_fields(headers) | {"webhook_id": webhook_id}
    head = json.dumps(fields)[:-1]
    body = f'{head}, "webhook_event": {raw_body.decode("utf-8")}}}'.encode()
    response = client.request(
        "POST",
        "/v1/notifications/verify-webhook-signature",
        raw_json=body,
    )
    return response.get("verification_status") == "SUCCESS"
