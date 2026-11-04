import uuid

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from api.config import get_settings
from api.db.models import DocumentBlob
from tests.helpers import create_agreement
from vault.crypto import decrypt, encrypt
from vault.sniff import safe_filename, sniff

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload(client, data=PDF, name="Logo final.pdf", **form):
    return client.post(
        "/v1/documents",
        files={"file": (name, data, "application/octet-stream")},
        data={"kind": "deliverable", **form},
    )


def test_round_trip_is_bound_to_the_document():
    first, second = uuid.uuid4(), uuid.uuid4()
    nonce, ciphertext, wrapped = encrypt(first, b"secret work")
    assert decrypt(first, nonce, ciphertext, wrapped) == b"secret work"
    assert b"secret work" not in ciphertext
    with pytest.raises(InvalidTag):
        decrypt(second, nonce, ciphertext, wrapped)


def test_each_file_gets_its_own_key():
    document = uuid.uuid4()
    assert encrypt(document, b"x")[2] != encrypt(document, b"x")[2]


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0rest", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"PK\x03\x04docx", "application/zip"),
        (b"Delivered: https://drive.example/logo", "text/plain"),
        (b"MZ\x90\x00\x03\x00\x00\x00", None),
        (b"\x7fELF\x02\x01", None),
        (b"#!/bin/sh\nrm -rf ~", None),
    ],
)
def test_type_comes_from_the_bytes(data, mime):
    assert sniff(data) == mime


def test_filenames_are_cleaned_and_extension_follows_content():
    assert safe_filename("../../etc/passwd", "text/plain") == "passwd.txt"
    assert safe_filename("invoice.exe", "application/pdf") == "invoice.pdf"
    assert safe_filename("Logo <script>.pdf", "application/pdf") == "Logo _script_.pdf"
    assert safe_filename(None, "image/png") == "document.png"


def test_upload_stores_only_ciphertext(logged_in, db):
    client = logged_in()
    agreement = create_agreement(client)
    response = upload(client, agreement_id=agreement["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mime"] == "application/pdf"
    assert body["filename"] == "Logo final.pdf"
    assert body["agreement_id"] == agreement["id"]
    blob = db.scalar(select(DocumentBlob))
    assert PDF not in blob.ciphertext


def test_executables_are_refused(logged_in):
    client = logged_in()
    response = upload(client, data=b"MZ\x90\x00" + b"\x00" * 64, name="logo.pdf")
    assert response.status_code == 415
    assert "PDF" in response.json()["error"]["message"]


def test_empty_and_oversized_files_are_refused(logged_in, monkeypatch):
    client = logged_in()
    assert upload(client, data=b"").status_code == 422
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "100")
    get_settings.cache_clear()
    try:
        response = upload(client, data=PDF + b"x" * 200)
        assert response.status_code == 413
    finally:
        get_settings.cache_clear()


def test_download_needs_a_fresh_signed_link_and_the_owner(logged_in, client):
    owner = logged_in("owner@kweli.test")
    document = upload(owner).json()
    link = owner.get(f"/v1/documents/{document['id']}/url").json()["url"]
    response = owner.get(link)
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-disposition"] == 'attachment; filename="Logo final.pdf"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"

    tampered = link.replace("signature=", "signature=0")
    assert owner.get(tampered).status_code in (403, 422)
    expired = link.split("expires=")[0] + "expires=1&signature=" + link.split("signature=")[1]
    assert owner.get(expired).status_code == 403

    owner.post("/v1/auth/logout")
    logged_in("other@kweli.test")
    assert client.get(link).status_code == 404
    assert client.get(f"/v1/documents/{document['id']}/url").status_code == 404


def test_cannot_attach_to_someone_elses_agreement(logged_in, client):
    owner = logged_in("owner@kweli.test")
    agreement = create_agreement(owner)
    owner.post("/v1/auth/logout")
    logged_in("other@kweli.test")
    assert upload(client, agreement_id=agreement["id"]).status_code == 404


def test_vault_without_a_key_says_so(logged_in, monkeypatch):
    client = logged_in()
    monkeypatch.setenv("VAULT_MASTER_KEY", "")
    get_settings.cache_clear()
    try:
        response = upload(client)
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
    assert client.get("/v1/documents").json() == []


def test_uploading_a_deliverable_completes_the_proof(logged_in, db):
    from api.db.models import ProofFlag
    from tests.helpers import paypal
    from tests.test_webhooks import fake, invoiced_agreement, paid_event, post

    client = logged_in()
    agreement = invoiced_agreement(client, db)
    import os

    os.environ["PAYPAL_WEBHOOK_ID"] = "WH-KWELI"
    get_settings.cache_clear()
    try:
        with paypal(fake()):
            post(client, paid_event())
    finally:
        os.environ.pop("PAYPAL_WEBHOOK_ID")
        get_settings.cache_clear()
    p5 = db.scalar(select(ProofFlag).where(ProofFlag.rule == "P5"))
    assert p5.status == "fail"
    upload(client, agreement_id=agreement["id"])
    db.expire_all()
    p5 = db.scalar(select(ProofFlag).where(ProofFlag.rule == "P5"))
    assert p5.status == "pass"
    assert p5.explanation == "Delivered work on file: Logo final.pdf."
