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
    assert main() == 0
    assert main() == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["Created: amina@demo.kweli.test", "Already exists: amina@demo.kweli.test"]
