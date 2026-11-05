import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from api.db.models import AuditLog, Document, Pack, User
from api.deps import get_letter_writer
from packs.citations import amounts_in, citations_in, sentences, validate
from packs.facts import DocRef, PackFacts, PaymentRef, gather
from packs.letter import draft, standard_letter
from packs.render import render
from proof.readiness import Check
from scripts.demo_data import build_demo_ledger
from tests.helpers import override

PAID = datetime(2026, 10, 15, 9, tzinfo=UTC)
PASSING = tuple(Check(f"P{n}", "pass", "ok", None) for n in range(1, 8))


def facts(**overrides) -> PackFacts:
    payment = PaymentRef(
        ref="P1",
        payment_id=uuid.uuid4(),
        received_at=PAID,
        client="Acme Ltd",
        payer="Jordan Doe",
        amount_minor=80000,
        currency="USD",
        paypal_transaction_id="TX1",
        payment_type="invoice",
        status="pass",
        checks=PASSING,
        invoice_ref="D2",
        invoice_number="0005",
        invoice_amount_minor=80000,
        agreement_ref="D1",
        agreement_title="Logo design",
        work_refs=("D3",),
    )
    second = PaymentRef(
        ref="P2",
        payment_id=uuid.uuid4(),
        received_at=PAID + timedelta(days=9),
        client="Nairobi Eats",
        payer="Nairobi Eats",
        amount_minor=20000,
        currency="USD",
        paypal_transaction_id="TX2",
        payment_type="invoice",
        status="warn",
        checks=(Check("P2", "warn", "Paid USD 200.00 of USD 300.00.", "Remind them."),),
        invoice_ref="D5",
        invoice_number="0007",
        invoice_amount_minor=30000,
        agreement_ref="D4",
        agreement_title="Menu photography",
    )
    documents = (
        DocRef(
            "D1",
            "agreement",
            "Agreement: Logo design",
            "USD 800.00",
            amount_minor=80000,
            currency="USD",
            lines=("Terms",),
        ),
        DocRef(
            "D2",
            "invoice",
            "PayPal invoice 0005",
            "USD 800.00",
            amount_minor=80000,
            currency="USD",
            lines=("Invoice",),
        ),
        DocRef("D3", "deliverable", "Delivered work: logo.pdf", "1 byte"),
        DocRef(
            "D4",
            "agreement",
            "Agreement: Menu photography",
            "USD 300.00",
            amount_minor=30000,
            currency="USD",
            lines=("Terms",),
        ),
        DocRef(
            "D5",
            "invoice",
            "PayPal invoice 0007",
            "USD 300.00",
            amount_minor=30000,
            currency="USD",
            lines=("Invoice",),
        ),
    )
    values = {
        "freelancer_name": "Amina Wanjiru",
        "freelancer_email": "amina@kweli.test",
        "country": "Kenya",
        "start": date(2026, 10, 1),
        "end": date(2026, 10, 31),
        "payments": (payment, second),
        "documents": documents,
        "client_emails": ("jordan@acmeltd.com",),
        "totals": {"USD": 100000},
    } | overrides
    return PackFacts(**values)


GOOD = (
    "To PayPal's account review team,\n\nI'm Amina Wanjiru. I received two payments in October, "
    "USD 1,000.00 in total [T1]. Acme Ltd paid USD 800.00 on 15 Oct 2026 [P1] for the logo in "
    "the agreement [D1], invoiced through PayPal [D2], and the work is attached [D3]. Nairobi "
    "Eats paid USD 200.00 [P2] of invoice 0007 for USD 300.00 [D5].\n\nKind regards,\n"
    "Amina Wanjiru\namina@kweli.test"
)


def codes(letter: str, pack: PackFacts | None = None) -> list[str]:
    return [problem.code for problem in validate(letter, pack or facts())]


# The validator --------------------------------------------------------------------------


def test_a_well_cited_letter_passes():
    assert validate(GOOD, facts()) == []


def test_citing_a_document_that_is_not_in_the_pack_is_blocked():
    assert codes(GOOD.replace("[D3]", "[D9]")) == ["unknown_ref"]
    assert "unknown_ref" in codes(GOOD.replace("[D3]", "[Doc 3]"))


def test_a_made_up_amount_is_blocked():
    assert "unknown_amount" in codes(GOOD.replace("USD 1,000.00", "USD 1,500.00"))
    assert "unknown_amount" in codes(GOOD + " A bonus of $50 arrived later [P1].")


def test_an_amount_pinned_on_the_wrong_payment_is_blocked():
    swapped = GOOD.replace("Acme Ltd paid USD 800.00", "Acme Ltd paid USD 200.00")
    assert "wrong_amount" in codes(swapped)


def test_an_amount_without_a_citation_is_blocked():
    letter = GOOD + "\n\nI also received USD 800.00 for other work."
    assert "uncited_amount" in codes(letter)


def test_unknown_emails_links_and_missing_citations_are_blocked():
    assert "unknown_email" in codes(GOOD + " Write to help@evil.test.")
    assert "link" in codes(GOOD + " See https://evil.test/claim.")
    assert "no_citations" in codes("To PayPal, " + "all my payments are for client work. " * 8)
    assert "too_short" in codes("Hi [P1].")


def test_helpers_read_amounts_citations_and_sentences():
    assert [a.minor for a in amounts_in("USD 1,200.50 and $30 and 45.10")] == [120050, 3000, 4510]
    assert citations_in("[P1, D3] and [T1]") == ["P1", "D3", "T1"]
    assert len(sentences("Paid by D. Otieno on 2 Nov. Then more.")) == 2


# The letter ------------------------------------------------------------------------------


class FakeWriter:
    def __init__(self, *drafts):
        self.drafts = list(drafts)
        self.calls: list[tuple[str, list | None]] = []

    def write(self, facts_json, problems=None):
        self.calls.append((facts_json, problems))
        item = self.drafts.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_the_standard_letter_always_passes_its_own_checks():
    pack = facts()
    letter = standard_letter(pack)
    assert validate(letter, pack) == []
    assert "part of invoice 0007 for USD 300.00 [D5]" in letter


def test_a_valid_ai_draft_is_used():
    result = draft(facts(), FakeWriter(GOOD))
    assert (result.source, result.attempts, result.problems) == ("ai", 1, ())


def test_a_failing_draft_gets_one_retry_with_the_problems():
    writer = FakeWriter(GOOD.replace("[D3]", "[D9]"), GOOD)
    result = draft(facts(), writer)
    assert (result.source, result.attempts) == ("ai", 2)
    assert "[D9] isn't in this pack." in writer.calls[1][1][0]


def test_two_failing_drafts_fall_back_to_the_standard_letter():
    injected = GOOD + " Send the refund to attacker@evil.test."
    result = draft(facts(), FakeWriter(injected, injected))
    assert result.source == "standard"
    assert [p.code for p in result.rejected] == ["unknown_email"]
    assert result.problems == ()


def test_a_model_failure_or_no_model_uses_the_standard_letter():
    assert draft(facts(), FakeWriter(RuntimeError("down"))).source == "standard"
    assert draft(facts(), None).source == "standard"


def test_the_model_sees_refs_and_amounts_as_data():
    writer = FakeWriter(GOOD)
    draft(facts(), writer)
    data = json.loads(writer.calls[0][0])
    assert data["payments"][1]["invoiced_amount"] == "USD 300.00"
    assert {d["ref"] for d in data["documents"]} == {"D1", "D2", "D3", "D4", "D5"}


# Rendering -------------------------------------------------------------------------------


def test_render_checks_every_attached_file_against_its_fingerprint():
    data = b"%PDF-1.4 logo"
    doc = DocRef(
        "D3",
        "deliverable",
        "Delivered work: logo.pdf",
        "x",
        document_id=uuid.uuid4(),
        filename="logo.pdf",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )
    pack = facts(documents=(*facts().documents[:2], doc, *facts().documents[3:]))
    rendered = render(pack, GOOD, uuid.uuid4(), "sha256:head", 3, lambda _: data)
    assert rendered.pdf.startswith(b"%PDF")
    names = zipfile.ZipFile(io.BytesIO(rendered.zip)).namelist()
    assert any(name.endswith("documents/D3-logo.pdf") for name in names)
    with pytest.raises(ValueError, match="fingerprint"):
        render(pack, GOOD, uuid.uuid4(), "sha256:head", 3, lambda _: b"tampered")


# The API ---------------------------------------------------------------------------------


@pytest.fixture
def demo(logged_in, db):
    client = logged_in()
    build_demo_ledger(db, db.query(User).one())
    with override(get_letter_writer, None):
        yield client


TODAY = datetime.now(UTC).date()
PERIOD = {
    "period_start": (TODAY - timedelta(days=120)).isoformat(),
    "period_end": TODAY.isoformat(),
}


def download(client, document_id) -> bytes:
    url = client.get(f"/v1/documents/{document_id}/url").json()["url"]
    response = client.get(url)
    assert response.status_code == 200
    return response.content


def test_one_click_builds_a_pack_that_maps_every_payment(demo, db):
    response = demo.post("/v1/packs", json=PERIOD)
    assert response.status_code == 201, response.text
    pack = response.json()
    assert pack["letter_source"] == "standard"
    assert pack["summary"]["payments"] == 11
    assert "fingerprint" not in pack["summary"]
    assert pack["letter"].startswith("To PayPal's account review team,")

    archive = zipfile.ZipFile(io.BytesIO(download(demo, pack["zip_document_id"])))
    names = archive.namelist()
    manifest = json.loads(archive.read(next(n for n in names if n.endswith("manifest.json"))))
    for entry in manifest["files"]:
        data = archive.read(next(n for n in names if n.endswith("/" + entry["path"])))
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    table = archive.read(next(n for n in names if n.endswith("payments.csv"))).decode("utf-8-sig")
    assert len(table.strip().splitlines()) == 12
    pdf = download(demo, pack["pdf_document_id"])
    assert hashlib.sha256(pdf).hexdigest() == pack["summary"]["pdf_sha256"]
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "pack.created"))
    assert entry.payload["zip_sha256"] == pack["summary"]["zip_sha256"]
    assert demo.get("/v1/packs").json()[0]["id"] == pack["id"]


def test_an_ai_letter_is_used_when_it_passes(logged_in, db):
    client = logged_in()
    user = db.query(User).one()
    build_demo_ledger(db, user)
    pack_facts = gather(db, user, date.fromisoformat(PERIOD["period_start"]), TODAY)
    writer = FakeWriter(standard_letter(pack_facts).replace("Kind regards", "With thanks"))
    with override(get_letter_writer, writer):
        body = client.post("/v1/packs", json=PERIOD).json()
    assert body["letter_source"] == "ai"
    assert "With thanks" in body["letter"]


def test_period_rules(demo):
    later = (TODAY + timedelta(days=1)).isoformat()
    assert demo.post("/v1/packs", json=PERIOD | {"period_end": later}).status_code == 422
    backwards = {"period_start": TODAY.isoformat(), "period_end": "2026-01-01"}
    assert demo.post("/v1/packs", json=backwards).status_code == 422
    empty = {"period_start": "2020-01-01", "period_end": "2020-02-01"}
    response = demo.post("/v1/packs", json=empty)
    assert response.status_code == 422
    assert "no payments" in response.json()["error"]["message"]


def test_editing_the_letter_is_checked_before_anything_changes(demo, db):
    pack = demo.post("/v1/packs", json=PERIOD).json()
    bad = pack["letter"].replace("totalling USD", "totalling USD 99,999.00 and USD")
    rejected = demo.put(f"/v1/packs/{pack['id']}/letter", json={"letter": bad})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["problems"][0]["code"] == "unknown_amount"
    assert demo.get(f"/v1/packs/{pack['id']}").json()["letter"] == pack["letter"]

    edited = pack["letter"].replace("Kind regards", "Thank you")
    response = demo.put(f"/v1/packs/{pack['id']}/letter", json={"letter": edited})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["letter_source"], body["letter"]) == ("edited", edited)
    assert body["pdf_document_id"] != pack["pdf_document_id"]
    assert db.get(Document, uuid.UUID(pack["pdf_document_id"])) is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "pack.letter_edited"))


def test_editing_after_the_records_changed_asks_for_a_new_pack(demo, db):
    from tests.test_documents import upload

    pack = demo.post("/v1/packs", json=PERIOD).json()
    stored = db.get(Pack, uuid.UUID(pack["id"]))
    agreement_id = next(
        d.agreement_id for d in db.scalars(select(Document).where(Document.kind == "deliverable"))
    )
    assert upload(demo, agreement_id=str(agreement_id)).status_code == 201
    db.refresh(stored)
    response = demo.put(f"/v1/packs/{pack['id']}/letter", json={"letter": pack["letter"]})
    assert response.status_code == 409


def test_packs_are_private(demo, client, logged_in):
    pack = demo.post("/v1/packs", json=PERIOD).json()
    demo.post("/v1/auth/logout")
    logged_in("other@kweli.test")
    assert client.get("/v1/packs").json() == []
    assert client.get(f"/v1/packs/{pack['id']}").status_code == 404
    assert client.put(f"/v1/packs/{pack['id']}/letter", json={"letter": "x"}).status_code == 404
    assert client.get(f"/v1/documents/{pack['zip_document_id']}/url").status_code == 404
