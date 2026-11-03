"""Create the demo freelancer account. Safe to run more than once.

Usage: python -m scripts.seed
"""

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import User
from api.db.session import get_engine
from api.security import MIN_PASSWORD_LENGTH, hash_password, normalise_email


def ensure_demo_user(db: Session) -> tuple[User, bool]:
    settings = get_settings()
    if settings.demo_user_password is None:
        raise SystemExit("Set DEMO_USER_PASSWORD to seed the demo account.")
    password = settings.demo_user_password.get_secret_value()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"DEMO_USER_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters.")
    email = normalise_email(settings.demo_user_email)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user, False
    user = User(
        email=email,
        name=settings.demo_user_name,
        country="KE",
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    return user, True


def main() -> int:
    with Session(get_engine()) as db:
        user, created = ensure_demo_user(db)
        print(f"{'Created' if created else 'Already exists'}: {user.email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
