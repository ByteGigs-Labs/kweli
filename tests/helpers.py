from contextlib import contextmanager

from api.deps import get_extractor, get_paypal
from api.main import app

AGREEMENT = {
    "client": {"name": "Acme Ltd", "email": "Jordan@AcmeLtd.com", "country": "US"},
    "title": "Logo design",
    "scope": "A new logo with three concepts.",
    "deliverables": ["3 concepts", "Final SVG and PNG files"],
    "amount": "800.00",
    "currency": "USD",
    "due_date": "2026-11-20",
}


@contextmanager
def override(dependency, value):
    app.dependency_overrides[dependency] = lambda: value
    try:
        yield value
    finally:
        app.dependency_overrides.pop(dependency, None)


def paypal(fake):
    return override(get_paypal, fake.client())


def extractor(fake):
    return override(get_extractor, fake)


def create_agreement(client, **overrides) -> dict:
    response = client.post("/v1/agreements", json=AGREEMENT | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def accept_link(client, agreement_id: str) -> str:
    response = client.post(f"/v1/agreements/{agreement_id}/send")
    assert response.status_code == 200, response.text
    return response.json()["url"].rsplit("/p/", 1)[1]
