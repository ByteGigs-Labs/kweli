import time
from dataclasses import dataclass

import httpx

from api.config import Settings


class PayPalAuthError(RuntimeError):
    pass


@dataclass
class AccessToken:
    value: str
    scopes: list[str]
    app_id: str
    expires_at: float

    def is_fresh(self, margin_seconds: int = 60) -> bool:
        return time.monotonic() < self.expires_at - margin_seconds


def fetch_access_token(settings: Settings, client: httpx.Client | None = None) -> AccessToken:
    secret = settings.paypal_client_secret.get_secret_value()
    if not settings.paypal_client_id or not secret:
        raise PayPalAuthError("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET must be set")
    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    try:
        response = client.post(
            f"{settings.paypal_base_url}/v1/oauth2/token",
            auth=(settings.paypal_client_id, secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
    finally:
        if owns_client:
            client.close()
    if response.status_code != 200:
        raise PayPalAuthError(f"PayPal rejected the credentials (HTTP {response.status_code})")
    body = response.json()
    return AccessToken(
        value=body["access_token"],
        scopes=body.get("scope", "").split(),
        app_id=body.get("app_id", ""),
        expires_at=time.monotonic() + int(body.get("expires_in", 0)),
    )
