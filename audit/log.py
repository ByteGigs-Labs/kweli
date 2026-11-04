"""Append-only, hash-chained audit log, one chain per user.

Each entry's hash covers its sequence number, action, payload, time and the previous entry's
hash, so editing or deleting any earlier entry breaks every hash after it.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import AuditLog, User

GENESIS = "sha256:" + "0" * 64


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def entry_hash(seq: int, action: str, payload: dict, created_at: datetime, prev: str) -> str:
    body = {
        "seq": seq,
        "action": action,
        "payload": payload,
        "at": created_at.astimezone(UTC).isoformat(),
        "prev": prev,
    }
    return "sha256:" + hashlib.sha256(canonical(body)).hexdigest()


def record(db: Session, user_id: UUID, action: str, payload: dict) -> AuditLog:
    """Add an entry in the caller's transaction. Locks the user row so chains never fork."""
    db.execute(select(User.id).where(User.id == user_id).with_for_update())
    last = db.scalar(
        select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.seq.desc()).limit(1)
    )
    seq = last.seq + 1 if last else 1
    prev = last.entry_hash if last else GENESIS
    created_at = datetime.now(UTC).replace(microsecond=0)
    clean = json.loads(canonical(payload))
    entry = AuditLog(
        user_id=user_id,
        seq=seq,
        action=action,
        payload=clean,
        prev_hash=prev,
        entry_hash=entry_hash(seq, action, clean, created_at, prev),
        created_at=created_at,
    )
    db.add(entry)
    db.flush()
    return entry


@dataclass(frozen=True)
class ChainStatus:
    ok: bool
    entries: int
    head: str
    broken_at: int | None = None


def verify(db: Session, user_id: UUID) -> ChainStatus:
    prev = GENESIS
    count = 0
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.seq))
    for expected_seq, row in enumerate(rows, start=1):
        count += 1
        expected = entry_hash(row.seq, row.action, row.payload, row.created_at, prev)
        if row.seq != expected_seq or row.prev_hash != prev or row.entry_hash != expected:
            return ChainStatus(False, count, prev, broken_at=expected_seq)
        prev = row.entry_hash
    return ChainStatus(True, count, prev)
