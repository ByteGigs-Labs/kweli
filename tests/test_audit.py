from sqlalchemy import select, update

from api.db.models import AuditLog, User
from audit.log import GENESIS, record, verify
from tests.helpers import accept_link, create_agreement


def test_chain_links_each_entry_to_the_last(db, make_user):
    user = make_user()
    first = record(db, user.id, "test.one", {"n": 1})
    second = record(db, user.id, "test.two", {"n": 2})
    db.commit()
    assert first.prev_hash == GENESIS
    assert second.prev_hash == first.entry_hash
    assert (first.seq, second.seq) == (1, 2)
    status = verify(db, user.id)
    assert status.ok and status.entries == 2 and status.head == second.entry_hash


def test_editing_a_payload_breaks_the_chain(db, make_user):
    user = make_user()
    for n in range(3):
        record(db, user.id, "test", {"amount_minor": n})
    db.commit()
    db.execute(update(AuditLog).where(AuditLog.seq == 2).values(payload={"amount_minor": 999}))
    db.commit()
    status = verify(db, user.id)
    assert not status.ok
    assert status.broken_at == 2


def test_deleting_an_entry_breaks_the_chain(db, make_user):
    user = make_user()
    for n in range(3):
        record(db, user.id, "test", {"n": n})
    db.commit()
    db.delete(db.scalar(select(AuditLog).where(AuditLog.seq == 2)))
    db.commit()
    assert verify(db, user.id).broken_at == 2


def test_chains_are_per_user(db, make_user):
    one, two = make_user("one@kweli.test"), make_user("two@kweli.test")
    record(db, one.id, "a", {})
    record(db, two.id, "b", {})
    db.commit()
    assert verify(db, one.id).entries == 1
    assert verify(db, two.id).entries == 1


def test_flow_is_recorded_without_personal_data(logged_in, db):
    client = logged_in()
    agreement = create_agreement(client)
    token = accept_link(client, agreement["id"])
    client.post(f"/v1/portal/agreements/{token}/accept", json={"accept": True})
    rows = db.scalars(select(AuditLog).order_by(AuditLog.seq)).all()
    assert [row.action for row in rows] == [
        "agreement.created",
        "agreement.link_issued",
        "agreement.accepted",
    ]
    dumped = str([row.payload for row in rows])
    assert "acmeltd.com" not in dumped
    assert token not in dumped


def test_verify_endpoint(logged_in, db):
    client = logged_in()
    create_agreement(client)
    body = client.get("/v1/audit/verify").json()
    assert body["ok"] is True
    assert body["entries"] == 1
    user = db.scalar(select(User))
    assert body["head"] == verify(db, user.id).head
