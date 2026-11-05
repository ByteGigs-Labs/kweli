"""Create the Kweli Pro product and monthly plan in the PayPal sandbox, once.

Usage: python -m scripts.create_pro_plan
Prints the plan ID. Put it in PAYPAL_PLAN_ID (Render → kweli-api → Environment) to turn on
billing. Safe to run twice: it reuses an existing active "Kweli Pro" plan.
"""

import sys

from api.config import get_settings
from paypal.client import PayPalClient

PRODUCT = {
    "name": "Kweli Pro",
    "description": "Compliance Packs, the dispute defender and unlimited clients",
    "type": "SERVICE",
    "category": "SOFTWARE",
}


def plan_body(product_id: str, price: str, currency: str) -> dict:
    return {
        "product_id": product_id,
        "name": "Kweli Pro (monthly)",
        "description": "Kweli Pro, billed monthly",
        "status": "ACTIVE",
        "billing_cycles": [
            {
                "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0,
                "pricing_scheme": {"fixed_price": {"value": price, "currency_code": currency}},
            }
        ],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "setup_fee_failure_action": "CANCEL",
            "payment_failure_threshold": 2,
        },
    }


def existing_plan(client: PayPalClient) -> str | None:
    plans = client.get("/v1/billing/plans", params={"page_size": 20}).get("plans") or []
    for plan in plans:
        if plan.get("name") == "Kweli Pro (monthly)" and plan.get("status") == "ACTIVE":
            return plan.get("id")
    return None


def main(client: PayPalClient | None = None) -> int:
    settings = get_settings()
    if settings.paypal_env != "sandbox":
        print("Refusing to run against live. Set PAYPAL_ENV=sandbox.")
        return 1
    client = client or PayPalClient()
    plan_id = existing_plan(client)
    if not plan_id:
        product = client.post(
            "/v1/catalogs/products", json=PRODUCT, request_id="kweli-pro-product-v1"
        )
        plan = client.post(
            "/v1/billing/plans",
            json=plan_body(product["id"], settings.pro_price, settings.pro_currency),
            request_id="kweli-pro-plan-v1",
        )
        plan_id = plan["id"]
    print(f"PAYPAL_PLAN_ID={plan_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
