"""Envelope encryption for stored documents.

Each file gets its own random 256-bit data key (AES-256-GCM). The data key is wrapped with a
master key derived from VAULT_MASTER_KEY, and both encryptions are bound to the document ID,
so a ciphertext can't be swapped onto another document.
"""

import base64
import os
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from api.config import get_settings

NONCE_BYTES = 12


class VaultUnavailable(RuntimeError):
    pass


def _master_key() -> bytes:
    secret = get_settings().vault_master_key
    if secret is None or not secret.get_secret_value():
        raise VaultUnavailable("VAULT_MASTER_KEY is not set")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"kweli-vault-v1").derive(
        secret.get_secret_value().encode()
    )


def encrypt(document_id: UUID, data: bytes) -> tuple[bytes, bytes, str]:
    """Return (nonce, ciphertext, wrapped data key)."""
    master = AESGCM(_master_key())
    data_key = AESGCM.generate_key(bit_length=256)
    aad = document_id.bytes
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(data_key).encrypt(nonce, data, aad)
    wrap_nonce = os.urandom(NONCE_BYTES)
    wrapped = wrap_nonce + master.encrypt(wrap_nonce, data_key, aad)
    return nonce, ciphertext, base64.b64encode(wrapped).decode()


def decrypt(document_id: UUID, nonce: bytes, ciphertext: bytes, wrapped_key: str) -> bytes:
    raw = base64.b64decode(wrapped_key)
    aad = document_id.bytes
    data_key = AESGCM(_master_key()).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad)
    return AESGCM(data_key).decrypt(nonce, ciphertext, aad)
