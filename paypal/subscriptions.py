"""PayPal Subscriptions v1, for Kweli Pro itself.

Spec: paypal-rest-api-specifications/openapi/billing_subscriptions_v1.json
Kweli creates the subscription on the server and sends the freelancer to PayPal's approve
link, so no PayPal JavaScript runs on Kweli's pages (the strict CSP stays as it is).
"""

from paypal.client import PayPalClient

BASE = "/v1/billing/subscriptions"


def approve_link(subscription: dict) -> str | None:
    for link in subscription.get("links") or []:
        if link.get("rel") == "approve":
            return link.get("href")
    return None


class Subscriptions:
    def __init__(self, client: PayPalClient) -> None:
        self.client = client

    def create(
        self, plan_id: str, custom_id: str, return_url: str, cancel_url: str, request_id: str
    ) -> dict:
        return self.client.post(
            BASE,
            json={
                "plan_id": plan_id,
                "custom_id": custom_id,
                "application_context": {
                    "brand_name": "Kweli",
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "SUBSCRIBE_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            },
            request_id=request_id,
        )

    def get(self, subscription_id: str) -> dict:
        return self.client.get(f"{BASE}/{subscription_id}")

    def cancel(self, subscription_id: str, reason: str, request_id: str) -> None:
        self.client.post(
            f"{BASE}/{subscription_id}/cancel", json={"reason": reason[:128]}, request_id=request_id
        )
