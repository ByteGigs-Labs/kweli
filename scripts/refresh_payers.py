"""Fill in payers PayPal hadn't indexed when the payment arrived, then re-run the proof rules.

Run it from a scheduled job every 30 minutes, or by hand: python -m scripts.refresh_payers
"""

import sys

from sqlalchemy.orm import Session

from api.db.session import get_engine
from api.services.payments import refresh_pending_payers
from paypal.client import PayPalClient


def main() -> int:
    with Session(get_engine()) as db:
        resolved = refresh_pending_payers(db, PayPalClient())
    print(f"Payers confirmed: {resolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
