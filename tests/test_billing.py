import json

import httpx
import pytest
from sqlalchemy import select

from api.config import get_settings
from api.db.models import AuditLog, Subscription, User
from tests.helpers import AGREEMENT, paypal
from tests.paypal_fakes import FakePayPal
from tests.test_webhooks import SIGNATURE, VERIFY, post

PLAN = "P-KWELIPRO"
SUBS = "/v1/billing/subscriptions"


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setenv("PAYPAL_PLAN_ID", PLAN)
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-KWELI")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def remote(user_id, status="ACTIVE", plan=PLAN, sub_id="I-SUB1"):
    return {
        "id": sub_id,
        "status": status,
        "plan_id": plan,
        "custom_id": str(user_id),
        "billing_info": {"next_billing_time": "2026-12-05T10:00:00Z"},
        "links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/webapps/billing/x"}],
    }


def user_of(db) -> User:
    return db.scalar(select(User).where(User.email == "amina@kweli.test"))


def test_without_a_plan_everything_is_open(logged_in):
    client = logged_in()
    body = client.get("/v1/billing").json()
    assert (body["enabled"], body["plan"]) == (False, "pro")
    assert client.post("/v1/billing/checkout").status_code == 409


def test_pro_features_need_pro_when_billing_is_on(billing_on, logged_in):
    client = logged_in()
    assert client.get("/v1/billing").json()["plan"] == "free"
    assert client.get("/v1/auth/me").json()["plan"] == "free"
    response = client.post(
        "/v1/packs", json={"period_start": "2026-01-01", "period_end": "2026-02-01"}
    )
    assert response.status_code == 402
    assert "Kweli Pro" in response.json()["error"]["message"]
    assert (
        client.post(f"/v1/disputes/{'0' * 8}-0000-0000-0000-{'0' * 12}/prepare").status_code == 402
    )
    assert client.get("/v1/disputes").status_code == 200


def test_the_free_plan_covers_three_clients(billing_on, logged_in):
    client = logged_in()
    for index in range(3):
        email = f"client{index}@example.com"
        body = AGREEMENT | {"client": {"name": f"Client {index}", "email": email}}
        assert client.post("/v1/agreements", json=body).status_code == 201
    again = AGREEMENT | {"client": {"name": "Client 0", "email": "CLIENT0@example.com"}}
    assert client.post("/v1/agreements", json=again).status_code == 201
    fourth = AGREEMENT | {"client": {"name": "Client 4", "email": "client4@example.com"}}
    assert client.post("/v1/agreements", json=fourth).status_code == 402


def test_checkout_sends_the_freelancer_to_paypal_and_confirm_turns_on_pro(
    billing_on, logged_in, db
):
    client = logged_in()
    user = user_of(db)
    fake = FakePayPal()
    fake.queue("POST", SUBS, httpx.Response(201, json=remote(user.id, "APPROVAL_PENDING")))
    fake.queue("GET", f"{SUBS}/I-SUB1", httpx.Response(200, json=remote(user.id)))
    with paypal(fake):
        started = client.post("/v1/billing/checkout")
        assert started.status_code == 200, started.text
        assert started.json()["approve_url"].startswith("https://www.sandbox.paypal.com/")
        sent = json.loads(fake.requests[0].read())
        assert sent["plan_id"] == PLAN and sent["custom_id"] == str(user.id)
        assert sent["application_context"]["return_url"].endswith("/billing?paypal=approved")
        confirmed = client.post("/v1/billing/confirm", json={"subscription_id": "I-SUB1"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["plan"] == "pro"
    assert confirmed.json()["subscription_status"] == "ACTIVE"
    db.refresh(user)
    assert user.plan == "pro"
    assert client.get("/v1/auth/me").json()["plan"] == "pro"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "billing.plan_changed"))


@pytest.mark.parametrize(
    ("body", "code"),
    [({"plan_id": "P-SOMETHING-ELSE"}, 422), ({"custom_id": "someone-else"}, 403)],
)
def test_a_subscription_for_another_plan_or_account_is_refused(
    billing_on, logged_in, db, body, code
):
    client = logged_in()
    fake = FakePayPal()
    fake.queue("GET", f"{SUBS}/I-SUB1", httpx.Response(200, json=remote(user_of(db).id) | body))
    with paypal(fake):
        response = client.post("/v1/billing/confirm", json={"subscription_id": "I-SUB1"})
    assert response.status_code == code
    assert user_of(db).plan == "free"


def test_a_subscription_id_cannot_be_claimed_by_a_second_account(billing_on, logged_in, db):
    first = logged_in()
    owner = user_of(db)
    fake = FakePayPal()
    fake.queue("GET", f"{SUBS}/I-SUB1", httpx.Response(200, json=remote(owner.id)))
    with paypal(fake):
        assert (
            first.post("/v1/billing/confirm", json={"subscription_id": "I-SUB1"}).status_code == 200
        )
    first.post("/v1/auth/logout")
    second = logged_in("other@kweli.test")
    with paypal(fake):
        response = second.post("/v1/billing/confirm", json={"subscription_id": "I-SUB1"})
    assert response.status_code == 403


def test_webhooks_keep_the_plan_in_step(billing_on, logged_in, db):
    client = logged_in()
    user = user_of(db)
    fake = FakePayPal()
    fake.queue("POST", VERIFY, httpx.Response(200, json={"verification_status": "SUCCESS"}))
    fake.queue(
        "GET",
        f"{SUBS}/I-SUB1",
        httpx.Response(200, json=remote(user.id)),
        httpx.Response(200, json=remote(user.id, "CANCELLED")),
    )

    def event(kind, event_id):
        body = {"id": event_id, "event_type": kind, "resource": {"id": "I-SUB1"}}
        with paypal(fake):
            return post(client, json.dumps(body).encode(), SIGNATURE)

    assert event("BILLING.SUBSCRIPTION.ACTIVATED", "WH-B1").json() == {"status": "processed"}
    db.refresh(user)
    assert user.plan == "pro"
    assert event("BILLING.SUBSCRIPTION.CANCELLED", "WH-B2").json() == {"status": "processed"}
    db.refresh(user)
    assert user.plan == "free"
    assert db.scalar(select(Subscription)).status == "CANCELLED"


def test_a_webhook_for_a_foreign_subscription_is_ignored(billing_on, logged_in, db):
    client = logged_in()
    fake = FakePayPal()
    fake.queue("POST", VERIFY, httpx.Response(200, json={"verification_status": "SUCCESS"}))
    fake.queue(
        "GET",
        f"{SUBS}/I-OTHER",
        httpx.Response(200, json=remote("not-a-user", plan="P-OTHER", sub_id="I-OTHER")),
    )
    body = {
        "id": "WH-B9",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-OTHER"},
    }
    with paypal(fake):
        assert post(client, json.dumps(body).encode(), SIGNATURE).json() == {"status": "ignored"}
    assert user_of(db).plan == "free"


def test_cancel_goes_through_paypal(billing_on, logged_in, db):
    client = logged_in()
    user = user_of(db)
    fake = FakePayPal()
    fake.queue(
        "GET",
        f"{SUBS}/I-SUB1",
        httpx.Response(200, json=remote(user.id)),
        httpx.Response(200, json=remote(user.id, "CANCELLED")),
    )
    fake.queue("POST", f"{SUBS}/I-SUB1/cancel", httpx.Response(204))
    with paypal(fake):
        client.post("/v1/billing/confirm", json={"subscription_id": "I-SUB1"})
        response = client.post("/v1/billing/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["plan"] == "free"
    assert any(r.url.path.endswith("/cancel") for r in fake.requests)


def test_the_plan_script_creates_a_monthly_plan_once(capsys):
    from scripts.create_pro_plan import main

    fake = FakePayPal()
    fake.queue("GET", "/v1/billing/plans", httpx.Response(200, json={"plans": []}))
    fake.queue("POST", "/v1/catalogs/products", httpx.Response(201, json={"id": "PROD-1"}))
    fake.queue("POST", "/v1/billing/plans", httpx.Response(201, json={"id": "P-NEW"}))
    assert main(fake.client()) == 0
    assert "PAYPAL_PLAN_ID=P-NEW" in capsys.readouterr().out
    plan = json.loads(fake.requests[-1].read())
    cycle = plan["billing_cycles"][0]
    assert cycle["pricing_scheme"]["fixed_price"] == {"value": "9.00", "currency_code": "USD"}
    assert cycle["frequency"] == {"interval_unit": "MONTH", "interval_count": 1}

    again = FakePayPal()
    again.queue(
        "GET",
        "/v1/billing/plans",
        httpx.Response(
            200,
            json={"plans": [{"id": "P-NEW", "name": "Kweli Pro (monthly)", "status": "ACTIVE"}]},
        ),
    )
    assert main(again.client()) == 0
    assert len(again.requests) == 1
