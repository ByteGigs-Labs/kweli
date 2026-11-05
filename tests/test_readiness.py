import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from api.db.models import AuditLog, Payment, User
from proof.readiness import Check, PaymentProof, assess, band_for
from scripts.demo_data import build_demo_ledger
from tests.helpers import AGREEMENT, create_agreement

NOW = datetime(2026, 11, 5, 9, tzinfo=UTC)
ALL_PASS = {f"P{n}": "pass" for n in range(1, 8)}


def proof(statuses=None, amount=50000, days=1, agreement=True, client="Acme Ltd"):
    statuses = ALL_PASS | (statuses or {})
    return PaymentProof(
        payment_id=uuid.uuid4(),
        received_at=NOW - timedelta(days=days),
        client=client,
        amount_minor=amount,
        currency="USD",
        agreement_id=uuid.uuid4() if agreement else None,
        checks=tuple(
            Check(rule, status, f"{rule} {status}", None if status == "pass" else f"fix {rule}")
            for rule, status in statuses.items()
        ),
    )


def test_no_payments_has_no_score():
    result = assess([])
    assert result.score is None
    assert result.band == "no_payments"
    assert result.fix_next == ()


def test_everything_proven_is_ready():
    result = assess([proof(), proof()])
    assert (result.score, result.band) == (100, "ready")
    assert result.checks["pass"] == 12


def test_warn_is_half_a_point_and_fail_is_none():
    result = assess([proof({"P2": "warn", "P5": "fail"})])
    assert result.score == round(100 * 4.5 / 6)


def test_pending_and_the_volume_check_are_not_scored():
    result = assess([proof({"P3": "pending", "P7": "warn"})])
    assert result.score == 100
    assert result.large_payments == 1
    assert result.checks["pending"] == 1
    assert result.fix_next == ()


def test_missing_proof_is_never_ready_even_with_a_high_score():
    payments = [proof() for _ in range(9)] + [proof({"P5": "fail"})]
    result = assess(payments)
    assert result.score >= 90
    assert result.band == "nearly"
    assert band_for(95, 0) == "ready"
    assert band_for(69) == "at_risk"


def test_root_steps_hide_the_ones_they_cause():
    no_paper = proof(
        {p: "fail" for p in ("P1", "P2", "P3", "P4", "P5")} | {"P6": "warn"}, agreement=False
    )
    (item,) = assess([no_paper]).fix_next
    assert [step.rule for step in item.steps] == ["P1", "P4", "P6"]


def test_fix_next_puts_missing_proof_first_then_the_biggest_gain():
    big_warn = proof({"P3": "warn"}, amount=900000)
    small_fail = proof({"P5": "fail"}, amount=10000)
    two_fails = proof({"P4": "fail", "P5": "fail"}, amount=10000)
    result = assess([big_warn, small_fail, two_fails, proof()])
    order = [item.payment_id for item in result.fix_next]
    assert order == [two_fails.payment_id, small_fail.payment_id, big_warn.payment_id]
    assert sum(item.points for item in result.fix_next) == pytest.approx(100 - result.score, abs=2)


def test_clients_are_summarised_weakest_first():
    result = assess([proof(client="Acme Ltd"), proof({"P5": "fail"}, client="Bloom Studio")])
    assert [summary.client for summary in result.clients] == ["Bloom Studio", "Acme Ltd"]
    assert result.clients[1].score == 100
    assert result.clients[0].totals == {"USD": 50000}


@pytest.fixture
def demo(logged_in, db):
    client = logged_in()
    build_demo_ledger(db, db.query(User).one())
    return client


def payment_from(db, name):
    return db.scalar(select(Payment).where(Payment.payer_name == name))


def test_readiness_endpoint_ranks_the_demo_fixes(demo):
    body = demo.get("/v1/readiness").json()
    assert body["payments"] == 11
    assert body["band"] == "nearly"
    assert 70 <= body["score"] < 90
    first = body["fix_next"][0]
    assert (first["client"], first["status"]) == ("D. Otieno", "fail")
    assert [step["rule"] for step in first["steps"]] == ["P1", "P4", "P6"]
    assert body["fix_total"] == len(body["fix_next"]) == 4
    acme = next(c for c in body["clients"] if c["client"] == "Acme Ltd")
    assert acme["score"] == 100
    assert demo.get("/v1/readiness", params={"limit": 1}).json()["fix_next"] == [first]


def test_readiness_is_private(demo, client, logged_in):
    demo.post("/v1/auth/logout")
    logged_in("other@kweli.test")
    body = client.get("/v1/readiness").json()
    assert (body["payments"], body["score"], body["clients"]) == (0, None, [])


def test_linking_an_unlinked_payment_to_its_agreement(demo, db):
    otieno = payment_from(db, "D. Otieno")
    response = demo.post(
        "/v1/agreements",
        json=AGREEMENT
        | {"client": {"name": "D. Otieno", "email": "d.otieno@mail.com"}, "title": "Poster"},
    )
    agreement = response.json()
    response = demo.post(
        f"/v1/ledger/{otieno.id}/agreement", json={"agreement_id": agreement["id"]}
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["agreement_id"] == agreement["id"]
    assert detail["linked_by"] == "hand"
    assert detail["client"] == "D. Otieno"
    rules = {flag["rule"]: flag for flag in detail["flags"]}
    assert rules["P3"]["status"] == "pass"
    assert rules["P4"]["status"] == "warn"
    assert "hasn't accepted" in rules["P4"]["explanation"]
    entry = db.scalars(select(AuditLog).order_by(AuditLog.seq.desc())).first()
    assert entry.action == "proof.evaluated"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "payment.linked")) is not None

    unlinked = demo.post(f"/v1/ledger/{otieno.id}/agreement", json={"agreement_id": None})
    assert unlinked.json()["agreement_id"] is None


def test_invoiced_payments_and_other_users_agreements_cannot_be_linked(demo, db, logged_in):
    invoiced = payment_from(db, "Mwangi Holdings")
    agreement = create_agreement(demo)
    conflict = demo.post(
        f"/v1/ledger/{invoiced.id}/agreement", json={"agreement_id": agreement["id"]}
    )
    assert conflict.status_code == 409
    otieno = payment_from(db, "D. Otieno")
    missing = demo.post(
        f"/v1/ledger/{otieno.id}/agreement", json={"agreement_id": str(uuid.uuid4())}
    )
    assert missing.status_code == 404
    demo.post("/v1/auth/logout")
    other = logged_in("other@kweli.test")
    theirs = create_agreement(other)
    assert (
        other.post(
            f"/v1/ledger/{otieno.id}/agreement", json={"agreement_id": theirs["id"]}
        ).status_code
        == 404
    )


def test_a_payer_confirmation_proves_a_third_party_payment(demo, db):
    from tests.test_documents import upload

    kilele = payment_from(db, "Mwangi Holdings")
    detail = demo.get(f"/v1/ledger/{kilele.id}").json()
    before = demo.get("/v1/readiness").json()["score"]
    assert (
        demo.post(
            "/v1/documents",
            files={"file": ("confirm.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
            data={"kind": "payer_confirmation"},
        ).status_code
        == 422
    )
    response = upload(
        demo,
        name="Kilele confirmation.pdf",
        kind="payer_confirmation",
        agreement_id=detail["agreement_id"],
    )
    assert response.status_code == 201, response.text
    after = demo.get(f"/v1/ledger/{kilele.id}").json()
    p3 = next(flag for flag in after["flags"] if flag["rule"] == "P3")
    assert p3["status"] == "pass"
    assert "Mwangi Holdings for Kilele Tours" in p3["explanation"]
    assert after["payer_confirmation"] == response.json()["filename"]
    assert demo.get("/v1/readiness").json()["score"] > before
