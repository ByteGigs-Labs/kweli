"""Check that the PayPal sandbox app in .env works and has the features Kweli needs.

Usage: python -m scripts.check_paypal [--scopes]
"""

import sys

from api.config import get_settings
from paypal.auth import PayPalAuthError, fetch_access_token

REQUIRED_SCOPES = {
    "Invoicing": "https://uri.paypal.com/services/invoicing",
    "Disputes": "https://uri.paypal.com/services/disputes/read-seller",
    "Disputes (respond)": "https://uri.paypal.com/services/disputes/update-seller",
    "Transaction Search": "https://uri.paypal.com/services/reporting/search/read",
    "Subscriptions": "https://uri.paypal.com/services/subscriptions",
}


def main() -> int:
    settings = get_settings()
    print(f"PayPal environment: {settings.paypal_env}")
    if settings.paypal_env != "sandbox":
        print("Refusing to run against live. Set PAYPAL_ENV=sandbox.")
        return 1
    try:
        token = fetch_access_token(settings)
    except PayPalAuthError as error:
        print(f"FAIL: {error}")
        return 1
    print(f"OK: credentials accepted (app {token.app_id or 'unknown'})")
    missing = [feature for feature, scope in REQUIRED_SCOPES.items() if scope not in token.scopes]
    for feature in REQUIRED_SCOPES:
        print(f"  {'WARN' if feature in missing else 'OK  '}  {feature}")
    if missing:
        print("WARN: some scopes are missing from the token. Tick those features in the app")
        print("      on developer.paypal.com and run this again. Full scope list: --scopes")
    if "--scopes" in sys.argv:
        print("\n".join(sorted(token.scopes)))
    if not settings.paypal_webhook_id:
        print("Note: PAYPAL_WEBHOOK_ID is empty. Add it after registering the webhook.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
