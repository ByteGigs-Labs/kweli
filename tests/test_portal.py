from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from api.db.models import Agreement
from tests.helpers import accept_link, create_agreement


def sent_agreement(logged_in):
    client = logged_in()
    agreement = create_agreement(client)
    token = accept_link(client, agreement["id"])
    client.post("/v1/auth/logout")
    client.cookies.clear()
    return client, agreement, token


def test_client_sees_the_agreement_without_logging_in(logged_in):
    client, _, token = sent_agreement(logged_in)
    body = client.get(f"/v1/portal/agreements/{token}").json()
    assert body["freelancer"] == "Amina Wanjiru"
    assert body["client"] == "Acme Ltd"
    assert body["amount"] == "800.00"
    assert body["status"] == "sent"
    assert "email" not in str(body).lower()


def test_accepting_records_evidence_without_storing_the_ip(logged_in, db):
    client, _, token = sent_agreement(logged_in)
    response = client.post(
        f"/v1/portal/agreements/{token}/accept",
        json={"accept": True},
        headers={"User-Agent": "Mozilla/5.0 test"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    row = db.scalar(select(Agreement))
    db.refresh(row)
    assert row.accepted_at is not None
    assert row.accepted_user_agent == "Mozilla/5.0 test"
    assert len(row.accepted_ip_hash) == 64
    assert "testclient" not in row.accepted_ip_hash


def test_accepting_twice_keeps_the_first_time(logged_in, db):
    client, _, token = sent_agreement(logged_in)
    first = client.post(f"/v1/portal/agreements/{token}/accept", json={"accept": True}).json()
    second = client.post(f"/v1/portal/agreements/{token}/accept", json={"accept": True}).json()
    assert first["accepted_at"] == second["accepted_at"]


def test_acceptance_needs_an_explicit_json_body(logged_in):
    client, _, token = sent_agreement(logged_in)
    assert client.post(f"/v1/portal/agreements/{token}/accept").status_code == 422
    form = client.post(f"/v1/portal/agreements/{token}/accept", data={"accept": "true"})
    assert form.status_code == 422
    assert (
        client.post(f"/v1/portal/agreements/{token}/accept", json={"accept": False}).status_code
        == 422
    )


def test_expired_link_is_gone(logged_in, db):
    client, _, token = sent_agreement(logged_in)
    db.execute(update(Agreement).values(accept_token_expires_at=datetime.now(UTC) - timedelta(1)))
    db.commit()
    response = client.get(f"/v1/portal/agreements/{token}")
    assert response.status_code == 410
    assert "Ask the freelancer for a new one" in response.json()["error"]["message"]


def test_unknown_and_oversized_tokens_are_not_found(client):
    assert client.get("/v1/portal/agreements/nope").status_code == 404
    assert client.get("/v1/portal/agreements/" + "a" * 200).status_code == 404


def test_portal_is_rate_limited(client):
    statuses = [client.get("/v1/portal/agreements/guess").status_code for _ in range(31)]
    assert statuses[:30] == [404] * 30
    assert statuses[30] == 429


def test_timestamps_are_always_utc(logged_in):
    client, _, token = sent_agreement(logged_in)
    accepted = client.post(f"/v1/portal/agreements/{token}/accept", json={"accept": True}).json()
    again = client.get(f"/v1/portal/agreements/{token}").json()
    assert accepted["accepted_at"].endswith(("Z", "+00:00"))
    assert again["accepted_at"] == accepted["accepted_at"]
