from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from api.db.models import UserSession
from tests.conftest import PASSWORD


def login(client, email="amina@kweli.test", password=PASSWORD):
    return client.post("/v1/auth/login", json={"email": email, "password": password})


def test_login_sets_a_hardened_session_cookie(client, make_user):
    make_user()
    response = login(client)
    assert response.status_code == 200
    assert response.json()["email"] == "amina@kweli.test"
    cookie = response.headers["set-cookie"].lower()
    assert "kweli_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie


def test_email_is_case_and_space_insensitive(client, make_user):
    make_user()
    assert login(client, email="  AMINA@Kweli.TEST ").status_code == 200


def test_wrong_password_and_unknown_user_look_the_same(client, make_user):
    make_user()
    wrong = login(client, password="not-the-password")
    unknown = login(client, email="nobody@kweli.test")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_inactive_user_cannot_log_in(client, make_user):
    make_user(active=False)
    assert login(client).status_code == 401


def test_me_requires_a_session(client):
    assert client.get("/v1/auth/me").status_code == 401


def test_me_returns_identity_without_secrets(logged_in):
    client = logged_in()
    body = client.get("/v1/auth/me").json()
    assert body["name"] == "Amina Wanjiru"
    assert body["plan"] == "pro"  # billing is off in tests, so every feature is open
    assert "password_hash" not in body


def test_session_token_is_stored_hashed(client, make_user, db):
    make_user()
    response = login(client)
    token = response.cookies["kweli_session"]
    stored = db.scalar(select(UserSession.token_hash))
    assert stored != token
    assert len(stored) == 64


def test_logout_ends_the_session(logged_in):
    client = logged_in()
    token = client.cookies["kweli_session"]
    assert client.post("/v1/auth/logout").status_code == 204
    client.cookies.set("kweli_session", token)
    assert client.get("/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(logged_in, db):
    client = logged_in()
    db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    db.commit()
    assert client.get("/v1/auth/me").status_code == 401


def test_forged_cookie_is_rejected(client):
    client.cookies.set("kweli_session", "forged-token-value")
    assert client.get("/v1/auth/me").status_code == 401


def test_account_locks_after_repeated_failures(client, make_user):
    make_user()
    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401
    locked = login(client)
    assert locked.status_code == 429
    assert locked.headers["Retry-After"] == "900"


def test_successful_login_clears_failures(client, make_user):
    make_user()
    for _ in range(4):
        login(client, password="wrong-password")
    assert login(client).status_code == 200
    for _ in range(4):
        login(client, password="wrong-password")
    assert login(client).status_code == 200


def test_ip_rate_limit(client, make_user):
    make_user()
    statuses = [login(client, email=f"user{i}@kweli.test").status_code for i in range(21)]
    assert statuses[:20] == [401] * 20
    assert statuses[20] == 429


def test_login_rejects_oversized_fields(client):
    response = client.post("/v1/auth/login", json={"email": "a" * 300, "password": "x"})
    assert response.status_code == 422
