"""Put the demo account back to its starting state, e.g. before showing Kweli to someone.

Usage: python -m scripts.reset_demo
Deletes the demo user (DEMO_USER_EMAIL) and everything it owns, then seeds it again with the
demo ledger. Nobody else's data is touched.
"""

import sys

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Agreement, Dispute, Invoice, Pack, Payment, PaymentLink, User
from api.db.session import get_engine
from api.security import normalise_email
from scripts.demo_data import build_demo_ledger
from scripts.seed import ensure_demo_user


def reset(db: Session) -> int:
    email = normalise_email(get_settings().demo_user_email)
    user_id = db.scalar(select(User.id).where(User.email == email))
    if user_id:
        # Rows that point across tables without ON DELETE CASCADE go first.
        payments = select(Payment.id).where(Payment.user_id == user_id)
        db.execute(delete(PaymentLink).where(PaymentLink.payment_id.in_(payments)))
        db.execute(delete(Dispute).where(Dispute.user_id == user_id))
        db.execute(delete(Pack).where(Pack.user_id == user_id))
        db.execute(
            update(Agreement).where(Agreement.user_id == user_id).values(pdf_document_id=None)
        )
        db.execute(delete(Invoice).where(Invoice.user_id == user_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()
    user, _ = ensure_demo_user(db)
    return build_demo_ledger(db, user)


def main() -> int:
    with Session(get_engine()) as db:
        added = reset(db)
    print(f"Demo account reset: {added} payments seeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
