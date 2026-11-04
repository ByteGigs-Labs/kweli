import pytest
from sqlalchemy import func, select

from api.config import get_settings
from api.db.models import User
from api.security import verify_password
from scripts.seed import ensure_demo_user, main


@pytest.fixture
def demo_password(monkeypatch):
    monkeypatch.setenv("DEMO_USER_PASSWORD", "demo-password-123")
    get_settings.cache_clear()
    yield "demo-password-123"
    get_settings.cache_clear()


def test_seed_creates_the_demo_user_once(db, demo_password):
    user, created = ensure_demo_user(db)
    again, created_again = ensure_demo_user(db)
    assert created and not created_again
    assert again.id == user.id
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert verify_password(user.password_hash, demo_password)


def test_seed_refuses_a_short_password(db, monkeypatch):
    monkeypatch.setenv("DEMO_USER_PASSWORD", "short")
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit):
            ensure_demo_user(db)
    finally:
        get_settings.cache_clear()


def test_seed_command_runs_twice(db, demo_password, capsys):
    assert main([]) == 0
    assert main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["Created: amina@demo.kweli.test", "Already exists: amina@demo.kweli.test"]


def test_demo_ledger_shows_each_kind_of_gap(db, demo_password, capsys):
    from api.db.models import Payment, ProofFlag

    assert main(["--demo-data"]) == 0
    assert main(["--demo-data"]) == 0
    out = capsys.readouterr().out
    assert "11 payments added" in out and "already there" in out
    flags: dict[str, dict[str, str]] = {}
    for payment_id, rule, status in db.execute(
        select(Payment.paypal_transaction_id, ProofFlag.rule, ProofFlag.status).join(
            ProofFlag, ProofFlag.payment_id == Payment.id
        )
    ):
        flags.setdefault(payment_id, {})[rule] = status
    assert set(flags["SEED-PAY-0005"].values()) == {"pass"}
    assert flags["SEED-PAY-0006"]["P5"] == "fail"
    assert flags["SEED-PAY-0007"]["P2"] == "warn"
    assert flags["SEED-PAY-0008"]["P3"] == "warn"
    assert flags["SEED-PAY-0009"]["P7"] == "warn"
    assert flags["SEED-PAY-0010"]["P3"] == "pending"
    assert flags["SEED-PAY-0011"]["P1"] == "fail"
    assert flags["SEED-PAY-0011"]["P6"] == "warn"
