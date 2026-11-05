from sqlalchemy import func, select

from api.config import get_settings
from api.db.models import AuditLog, Dispute, Payment, User
from scripts.reset_demo import reset


def test_reset_restores_the_demo_and_leaves_everyone_else(db, make_user, monkeypatch):
    monkeypatch.setenv("DEMO_USER_PASSWORD", "demo-password-123")
    monkeypatch.setenv("DEMO_USER_EMAIL", "demo@kweli.test")
    get_settings.cache_clear()
    try:
        other = make_user("other@kweli.test")
        assert reset(db) == 11
        demo = db.scalar(select(User).where(User.email == "demo@kweli.test"))
        db.delete(db.scalar(select(Dispute).where(Dispute.user_id == demo.id)))
        db.commit()
        assert reset(db) == 11
    finally:
        get_settings.cache_clear()
    demo = db.scalar(select(User).where(User.email == "demo@kweli.test"))
    assert db.scalar(select(func.count(Payment.id)).where(Payment.user_id == demo.id)) == 11
    assert db.scalar(select(func.count(Dispute.id)).where(Dispute.user_id == demo.id)) == 1
    assert db.get(User, other.id) is not None
    assert db.scalar(select(func.min(AuditLog.seq)).where(AuditLog.user_id == demo.id)) == 1
