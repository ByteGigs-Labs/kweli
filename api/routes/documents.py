import hashlib
import hmac
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import Agreement, Document, DocumentBlob
from api.db.session import get_db
from api.ratelimit import limit_by_key
from api.security import Principal, current_principal
from audit.log import record
from proof.engine import reevaluate_for_agreement
from vault.crypto import VaultUnavailable, decrypt, encrypt
from vault.sniff import ALLOWED, safe_filename, sniff

router = APIRouter(prefix="/v1/documents", tags=["documents"])
LINK_SECONDS = 300
PROOF_KINDS = ("deliverable", "payer_confirmation")


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agreement_id: UUID | None
    kind: str
    filename: str
    mime: str
    size: int
    sha256: str


class DownloadLink(BaseModel):
    url: str
    expires_in: int


def _signature(document_id: UUID, expires: int) -> str:
    key = get_settings().hmac_key.get_secret_value().encode()
    message = f"document:{document_id}:{expires}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _owned(db: Session, principal: Principal, document_id: UUID) -> Document:
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == principal.user_id)
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    kind: Literal["deliverable", "correspondence", "payer_confirmation", "other"] = Form(
        "deliverable"
    ),
    agreement_id: UUID | None = Form(None),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> DocumentOut:
    limit_by_key(db, "upload", str(principal.user_id), get_settings().uploads_per_minute)
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Files can be up to {limit // (1024 * 1024)} MB"
        )
    mime = sniff(data)
    if mime is None:
        kinds = ", ".join(extension.lstrip(".").upper() for extension in ALLOWED.values())
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Upload a {kinds} file")
    if kind == "payer_confirmation" and not agreement_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose the agreement this file belongs to"
        )
    if agreement_id and not db.scalar(
        select(Agreement.id).where(
            Agreement.id == agreement_id, Agreement.user_id == principal.user_id
        )
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agreement not found")

    document = Document(
        user_id=principal.user_id,
        agreement_id=agreement_id,
        kind=kind,
        filename=safe_filename(file.filename, mime),
        mime=mime,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key="db",
        encrypted_dek="",
    )
    db.add(document)
    db.flush()
    try:
        nonce, ciphertext, wrapped = encrypt(document.id, data)
    except VaultUnavailable:
        db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "File storage isn't set up here yet."
        ) from None
    document.encrypted_dek = wrapped
    db.add(DocumentBlob(document_id=document.id, nonce=nonce, ciphertext=ciphertext))
    record(
        db,
        principal.user_id,
        "document.uploaded",
        {
            "document_id": str(document.id),
            "agreement_id": str(agreement_id) if agreement_id else None,
            "kind": kind,
            "sha256": document.sha256,
            "size": document.size,
        },
    )
    if agreement_id and kind in PROOF_KINDS:
        reevaluate_for_agreement(db, agreement_id)
    db.commit()
    return DocumentOut.model_validate(document)


@router.get("")
def list_documents(
    agreement_id: UUID | None = None,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    query = select(Document).where(Document.user_id == principal.user_id)
    if agreement_id:
        query = query.where(Document.agreement_id == agreement_id)
    rows = db.scalars(query.order_by(Document.created_at.desc()).limit(100))
    return [DocumentOut.model_validate(row) for row in rows]


@router.get("/{document_id}/url")
def download_link(
    document_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> DownloadLink:
    _owned(db, principal, document_id)
    expires = int(time.time()) + LINK_SECONDS
    signature = _signature(document_id, expires)
    return DownloadLink(
        url=f"/v1/documents/{document_id}/content?expires={expires}&signature={signature}",
        expires_in=LINK_SECONDS,
    )


@router.get("/{document_id}/content")
def download(
    document_id: UUID,
    expires: int = Query(...),
    signature: str = Query(..., max_length=64),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> Response:
    if expires < time.time() or not hmac.compare_digest(
        signature, _signature(document_id, expires)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This download link has expired")
    document = _owned(db, principal, document_id)
    blob = db.get(DocumentBlob, document.id)
    try:
        data = decrypt(document.id, blob.nonce, blob.ciphertext, document.encrypted_dek)
    except VaultUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "File storage isn't set up here yet."
        ) from None
    return Response(
        data,
        media_type=document.mime,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
