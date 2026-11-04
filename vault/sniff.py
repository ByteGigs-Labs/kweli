"""Decide a file's type from its bytes. The browser's Content-Type is never trusted."""

import re
import unicodedata

ALLOWED = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/zip": ".zip",
    "text/plain": ".txt",
}


EXECUTABLE_MAGIC = (
    b"MZ",
    b"\x7fELF",
    b"#!",
    b"\xca\xfe\xba\xbe",
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
)


def sniff(data: bytes) -> str | None:
    if data.startswith(EXECUTABLE_MAGIC):
        return None
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    if b"\x00" not in data[:4096]:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return "text/plain"
    return None


def safe_filename(name: str | None, mime: str) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[^\w.\- ()]", "_", base).strip(" .") or "document"
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return f"{stem[:120]}{ALLOWED[mime]}"
