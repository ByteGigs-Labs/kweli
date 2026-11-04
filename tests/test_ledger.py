import pytest

from api.db.models import User
from scripts.demo_data import build_demo_ledger


@pytest.fixture
def demo(logged_in, db):
    client = logged_in()
    user = db.query(User).one()
    build_demo_ledger(db, user)
    return client


def test_ledger_lists_newest_first_with_rule_statuses(demo):
    response = demo.get("/v1/ledger", params={"_start": 0, "_end": 50})
    assert response.headers["X-Total-Count"] == "11"
    rows = response.json()
    assert rows[0]["client"] == "Bloom Studio"
    assert rows[0]["status"] == "pending"
    statuses = {row["client"]: row["status"] for row in rows}
    assert statuses["D. Otieno"] == "fail"
    complete = [row for row in rows if set(row["rules"].values()) == {"pass"}]
    assert len(complete) == 5
    assert all(len(row["rules"]) == 7 for row in rows)


def test_detail_explains_each_rule_and_the_chain(demo):
    rows = demo.get("/v1/ledger", params={"_end": 50}).json()
    kilele = next(row for row in rows if row["client"] == "Kilele Tours")
    detail = demo.get(f"/v1/ledger/{kilele['id']}").json()
    p3 = next(flag for flag in detail["flags"] if flag["rule"] == "P3")
    assert p3["explanation"] == "Paid by Mwangi Holdings, not Kilele Tours."
    assert "confirm in writing" in p3["fix"]
    assert [step["name"] for step in detail["chain"]] == [
        "Agreement",
        "Invoice",
        "Payment",
        "Deliverable",
    ]
    assert all(step["proven"] for step in detail["chain"])
    assert detail["invoice_number"] == "0008"


def test_unlinked_payment_shows_an_empty_chain(demo):
    rows = demo.get("/v1/ledger", params={"_end": 50}).json()
    otieno = next(row for row in rows if row["client"] == "D. Otieno")
    detail = demo.get(f"/v1/ledger/{otieno['id']}").json()
    assert [step["proven"] for step in detail["chain"]] == [False, False, True, False]
    assert detail["agreement_id"] is None


def test_ledger_is_private(demo, client, logged_in):
    rows = demo.get("/v1/ledger").json()
    demo.post("/v1/auth/logout")
    logged_in("other@kweli.test")
    assert client.get("/v1/ledger").json() == []
    assert client.get(f"/v1/ledger/{rows[0]['id']}").status_code == 404


def test_ledger_requires_login(client):
    assert client.get("/v1/ledger").status_code == 401
