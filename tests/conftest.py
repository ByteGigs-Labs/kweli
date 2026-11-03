import os
from collections.abc import Iterator

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://kweli:kweli@127.0.0.1:5432/kweli_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["CORS_ORIGINS"] = '["http://localhost:5173"]'
os.environ["COOKIE_SECURE"] = "false"
os.environ["PAYPAL_ENV"] = "sandbox"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.db.models import User  # noqa: E402
from api.main import app  # noqa: E402
from api.security import hash_password  # noqa: E402

PASSWORD = "correct-horse-battery"
TABLES = (
    "audit_log, subscriptions, webhook_events, agent_actions, packs, disputes, proof_flags, "
    "payment_links, payments, invoices, agreements, documents, clients, login_attempts, "
    "sessions, users"
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config("alembic.ini"), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(db) -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_user(db):
    def create(email: str = "amina@kweli.test", active: bool = True, **fields) -> User:
        user = User(
            email=email,
            name=fields.pop("name", "Amina Wanjiru"),
            password_hash=hash_password(PASSWORD),
            is_active=active,
            **fields,
        )
        db.add(user)
        db.commit()
        return user

    return create


@pytest.fixture
def logged_in(client, make_user):
    def login(email: str = "amina@kweli.test") -> TestClient:
        make_user(email=email)
        response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200
        return client

    return login
