from sqlalchemy import select

from api.db.models import Agreement, Client
from tests.helpers import AGREEMENT, accept_link, create_agreement, extractor

THREAD = "Jordan from Acme (jordan@acmeltd.com): logo, $800, due 20 Nov 2026. Deal?"


class FakeExtractor:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.seen = result or {}, error, []

    def extract(self, thread):
        self.seen.append(thread)
        if self.error:
            raise self.error
        return self.result


def test_extract_returns_a_checked_draft(logged_in):
    client = logged_in()
    fake = FakeExtractor({"client_email": "jordan@acmeltd.com", "amount": "800", "currency": "USD"})
    with extractor(fake):
        response = client.post("/v1/agreements/extract", json={"thread": THREAD})
    assert response.status_code == 200
    body = response.json()
    assert body["client_email"] == "jordan@acmeltd.com"
    assert body["amount"] == "800"
    assert "client_name" in body["missing"]


def test_extract_without_ai_says_to_fill_in_by_hand(logged_in):
    client = logged_in()
    with extractor(None):
        response = client.post("/v1/agreements/extract", json={"thread": THREAD})
    assert response.status_code == 503
    assert "by hand" in response.json()["error"]["message"]


def test_extract_provider_failure_is_a_clean_502(logged_in):
    client = logged_in()
    with extractor(FakeExtractor(error=RuntimeError("upstream exploded with secrets"))):
        response = client.post("/v1/agreements/extract", json={"thread": THREAD})
    assert response.status_code == 502
    assert "secrets" not in response.text


def test_extract_requires_login(client):
    assert client.post("/v1/agreements/extract", json={"thread": THREAD}).status_code == 401


def test_create_agreement_reuses_the_client_by_email(logged_in, db):
    client = logged_in()
    first = create_agreement(client)
    second = create_agreement(client, title="Brand guide")
    assert first["client"]["id"] == second["client"]["id"]
    assert first["client"]["email"] == "jordan@acmeltd.com"
    assert first["amount_minor"] == 80000
    assert first["status"] == "draft"
    assert db.scalar(select(Client.name)) == "Acme Ltd"


def test_agreement_validation(logged_in):
    client = logged_in()
    bad = [
        {"amount": "-5"},
        {"amount": "10.999"},
        {"currency": "KES"},
        {"deliverables": ["  "]},
        {"client": {"name": "X", "email": "not-an-email"}},
        {"surprise": "field"},
    ]
    for override in bad:
        response = client.post("/v1/agreements", json=AGREEMENT | override)
        assert response.status_code == 422, override


def test_detail_includes_plain_terms(logged_in):
    client = logged_in()
    agreement = create_agreement(client)
    body = client.get(f"/v1/agreements/{agreement['id']}").json()
    assert body["terms"][0] == "Amina Wanjiru will deliver the work below for Acme Ltd."
    assert "USD 800.00" in body["terms"][2]


def test_users_cannot_see_each_others_agreements(logged_in, client):
    owner = logged_in("owner@kweli.test")
    agreement = create_agreement(owner)
    owner.post("/v1/auth/logout")
    logged_in("other@kweli.test")
    assert client.get(f"/v1/agreements/{agreement['id']}").status_code == 404
    assert client.post(f"/v1/agreements/{agreement['id']}/send").status_code == 404
    assert client.get("/v1/agreements").json() == []


def test_list_is_paginated_with_total(logged_in):
    client = logged_in()
    for index in range(3):
        create_agreement(client, title=f"Job {index}")
    response = client.get("/v1/agreements", params={"_start": 0, "_end": 2})
    assert response.headers["X-Total-Count"] == "3"
    assert len(response.json()) == 2


def test_send_issues_a_hashed_single_use_link(logged_in, db):
    client = logged_in()
    agreement = create_agreement(client)
    first = accept_link(client, agreement["id"])
    second = accept_link(client, agreement["id"])
    stored = db.scalar(select(Agreement.accept_token_hash))
    assert first != second
    assert stored not in (first, second)
    assert client.get(f"/v1/portal/agreements/{first}").status_code == 404
    assert client.get(f"/v1/portal/agreements/{second}").status_code == 200
