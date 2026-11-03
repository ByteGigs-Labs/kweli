import pytest
from sqlalchemy.exc import IntegrityError

from api.db.models import Agreement, Client


def make_client(db, user):
    client = Client(user_id=user.id, name="Acme Ltd", email="ap@acme.test")
    db.add(client)
    db.commit()
    return client


@pytest.mark.parametrize(
    "fields",
    [
        {"amount_minor": 0},
        {"amount_minor": -100},
        {"currency": "usd"},
        {"currency": "US"},
        {"status": "signed"},
    ],
)
def test_agreement_constraints_reject_bad_values(db, make_user, fields):
    user = make_user()
    client = make_client(db, user)
    values = {
        "user_id": user.id,
        "client_id": client.id,
        "title": "Logo design",
        "scope": "One logo",
        "amount_minor": 80000,
        "currency": "USD",
    } | fields
    db.add(Agreement(**values))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_client_email_is_unique_per_user(db, make_user):
    user = make_user()
    make_client(db, user)
    db.add(Client(user_id=user.id, name="Acme again", email="ap@acme.test"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
