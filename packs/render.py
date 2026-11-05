"""Render a Compliance Pack: a PDF (letter, Table 1, documents, appendix) and a ZIP of everything.

Everything is built in memory from PackFacts plus the decrypted vault files. Attachments are
capped so one pack can't exhaust memory. Files over the cap are listed but left out, and the
pack says so.
"""

import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from packs.facts import TABLE_REF, PackFacts, long_date

MAX_ATTACHMENT_BYTES = 40 * 1024 * 1024
STATUS_WORD = {
    "pass": "Proven",
    "warn": "Needs attention",
    "fail": "Missing proof",
    "pending": "Checking",
}
FONT_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
    Path("/usr/local/share/fonts"),
)
INK = (20, 48, 42)
SOFT = (74, 95, 89)
LINE = (213, 221, 217)
WASH = (227, 242, 234)


@dataclass
class Rendered:
    pdf: bytes
    zip: bytes
    manifest: dict
    attached: list[str] = field(default_factory=list)
    left_out: list[str] = field(default_factory=list)


def _font_files() -> tuple[Path, Path] | None:
    for folder in FONT_DIRS:
        regular, bold = folder / "DejaVuSans.ttf", folder / "DejaVuSans-Bold.ttf"
        if regular.is_file() and bold.is_file():
            return regular, bold
    return None


def _latin(text: str) -> str:
    """Fallback for the built-in PDF font, which only covers Latin-1."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("…", "...").replace("→", "->")
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("latin-1", "ignore").decode("latin-1")


class PackPDF(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__(format="A4")
        self.title_text = title
        fonts = _font_files()
        if fonts:
            self.add_font("Body", "", str(fonts[0]))
            self.add_font("Body", "B", str(fonts[1]))
            self.body_font, self.clean = "Body", (lambda text: text)
        else:
            self.body_font, self.clean = "Helvetica", _latin
        self.set_auto_page_break(True, margin=18)
        self.set_margins(18, 18, 18)
        self.alias_nb_pages()

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self.body_font, "", 8)
        self.set_text_color(*SOFT)
        self.cell(
            0, 5, self.clean(f"{self.title_text} · Page {self.page_no()} of {{nb}}"), align="C"
        )

    def heading(self, text: str, size: float = 15) -> None:
        self.set_font(self.body_font, "B", size)
        self.set_text_color(*INK)
        self.multi_cell(0, size * 0.5, self.clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def para(self, text: str, size: float = 10, color=INK, bold: bool = False) -> None:
        self.set_font(self.body_font, "B" if bold else "", size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.52, self.clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def table_of(self, headings: list[str], rows: list[list[str]], widths: tuple[int, ...]) -> None:
        self.set_font(self.body_font, "", 8.5)
        self.set_text_color(*INK)
        self.set_draw_color(*LINE)
        with self.table(
            col_widths=widths,
            headings_style=_heading_style(self.body_font),
            line_height=4.6,
            padding=1.4,
            text_align="LEFT",
            borders_layout="HORIZONTAL_LINES",
        ) as table:
            table.row([self.clean(h) for h in headings])
            for row in rows:
                table.row([self.clean(cell) for cell in row])
        self.ln(3)


def _heading_style(family: str):
    from fpdf.fonts import FontFace

    return FontFace(family=family, emphasis="BOLD", color=SOFT, fill_color=WASH)


def safe_name(text: str, limit: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.") or "file"
    stem, dot, extension = text.rpartition(".")
    if dot and 1 <= len(extension) <= 5:
        return f"{stem[: limit - len(extension) - 1]}.{extension}".lower()
    return text[:limit].lower()


def _work_cell(payment) -> str:
    if payment.work_refs:
        return ", ".join(payment.work_refs)
    return "Not uploaded" if payment.agreement_ref else "—"


def table_rows(facts: PackFacts) -> list[list[str]]:
    rows = []
    for p in facts.payments:
        client = (
            p.client if not p.payer or p.payer == p.client else f"{p.client}\npaid by {p.payer}"
        )
        if p.confirmation_ref:
            client += f" ({p.confirmation_ref})"
        rows.append(
            [
                p.ref,
                long_date(p.received_at),
                client,
                p.amount,
                p.invoice_ref and f"{p.invoice_ref} · No. {p.invoice_number}" or "None",
                p.agreement_ref or "None",
                _work_cell(p),
                STATUS_WORD[p.status],
            ]
        )
    return rows


def payments_csv(facts: PackFacts) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ref",
            "received",
            "client",
            "paid_by",
            "amount",
            "currency",
            "paypal_transaction_id",
            "invoice",
            "agreement",
            "delivered_work",
            "payer_confirmation",
            "proof",
            *[f"check_{n}" for n in ("P1", "P2", "P3", "P4", "P5", "P6", "P7")],
        ]
    )
    for p in facts.payments:
        by_rule = {c.rule: c.status for c in p.checks}
        writer.writerow(
            [
                p.ref,
                p.received_at.date().isoformat(),
                p.client,
                p.payer or "",
                p.amount.split(" ", 1)[1].replace(",", ""),
                p.currency,
                p.paypal_transaction_id,
                p.invoice_ref or "",
                p.agreement_ref or "",
                " ".join(p.work_refs),
                p.confirmation_ref or "",
                STATUS_WORD[p.status],
                *[by_rule.get(rule, "") for rule in ("P1", "P2", "P3", "P4", "P5", "P6", "P7")],
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")


def render(
    facts: PackFacts,
    letter: str,
    pack_id: UUID,
    audit_head: str,
    audit_entries: int,
    read_file: Callable[[UUID], bytes],
    now: datetime | None = None,
) -> Rendered:
    now = now or datetime.now(UTC)
    title = f"Kweli Compliance Pack · {facts.freelancer_name}"
    folder = f"kweli-pack-{facts.end.isoformat()}"

    attachments: list[tuple[str, bytes]] = []
    left_out: list[str] = []
    budget = MAX_ATTACHMENT_BYTES
    paths: dict[str, str] = {}
    for doc in facts.documents:
        stem = f"{doc.ref}-{safe_name(doc.title.split(': ', 1)[-1])}"
        if doc.document_id:
            name = f"documents/{doc.ref}-{safe_name(doc.filename or 'file')}"
            if (doc.size or 0) > budget:
                left_out.append(doc.ref)
                continue
            data = read_file(doc.document_id)
            if hashlib.sha256(data).hexdigest() != doc.sha256:
                raise ValueError(f"{doc.ref} doesn't match its stored fingerprint")
            budget -= len(data)
            attachments.append((name, data))
        else:
            folder_name = "agreements" if doc.kind == "agreement" else "invoices"
            name = f"{folder_name}/{stem.removesuffix('.txt')}.txt"
            body = "\n".join([doc.title, "", *doc.lines]) + "\n"
            attachments.append((name, body.encode("utf-8")))
        paths[doc.ref] = name

    pdf = PackPDF(title)
    pdf.add_page()
    pdf.heading("Compliance pack", 20)
    pdf.para(
        f"{facts.freelancer_name} · {facts.freelancer_email}\n"
        f"Payments received {long_date(facts.start)} to {long_date(facts.end)} · "
        f"Prepared {long_date(now)} · Pack {str(pack_id)[:8]}",
        9,
        SOFT,
    )
    pdf.ln(5)
    pdf.heading("Cover letter", 13)
    pdf.para(letter, 10)
    pdf.ln(4)

    pdf.add_page(orientation="L")
    pdf.heading(f"Table 1 [{TABLE_REF}]. Every payment and its proof", 13)
    pdf.para(
        f"{len(facts.payments)} payments, {facts.totals_text or 'nothing'} in total. "
        "References in square brackets point to the documents listed after this table.",
        9,
        SOFT,
    )
    pdf.ln(2)
    pdf.table_of(
        ["Ref", "Received", "Client", "Amount", "Invoice", "Agreement", "Work", "Proof"],
        table_rows(facts),
        (10, 24, 62, 30, 34, 22, 34, 28),
    )

    pdf.heading("Documents", 13)
    pdf.table_of(
        ["Ref", "Document", "Detail", "In the ZIP"],
        [
            [d.ref, d.title, d.detail, paths.get(d.ref, "Too large for this pack")]
            for d in facts.documents
        ]
        or [["—", "No documents for this period", "", ""]],
        (14, 92, 62, 76),
    )
    if left_out:
        pdf.para(
            "Left out for size: " + ", ".join(left_out) + ". Ask and they'll be sent separately.",
            9,
            SOFT,
        )

    appendix = [d for d in facts.documents if d.lines]
    if appendix:
        pdf.add_page(orientation="P")
        pdf.heading("Appendix: agreements and invoices", 13)
        for doc in appendix:
            pdf.para(f"[{doc.ref}] {doc.title}", 10.5, bold=True)
            pdf.para("\n".join(line for line in doc.lines), 9)
            pdf.ln(3)

    pdf.ln(2)
    pdf.heading("Integrity", 11)
    pdf.para(
        f"Kweli's audit log for this account has {audit_entries} entries, each chained to the one "
        f"before with SHA-256. The chain was verified when this pack was made. Head: {audit_head}. "
        "Every file in the ZIP is listed with its SHA-256 in manifest.json.",
        8.5,
        SOFT,
    )
    pdf_bytes = bytes(pdf.output())

    files: list[tuple[str, bytes]] = [
        ("00-cover-letter-and-table.pdf", pdf_bytes),
        ("payments.csv", payments_csv(facts)),
        *attachments,
    ]
    manifest = {
        "pack_id": str(pack_id),
        "freelancer": facts.freelancer_name,
        "period": {"from": facts.start.isoformat(), "to": facts.end.isoformat()},
        "generated_at": now.isoformat(timespec="seconds"),
        "audit": {"entries": audit_entries, "head": audit_head},
        "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in files
        ],
        "left_out": left_out,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(f"{folder}/{name}", data)
        archive.writestr(f"{folder}/manifest.json", json.dumps(manifest, indent=2))
    return Rendered(
        pdf=pdf_bytes,
        zip=buffer.getvalue(),
        manifest=manifest,
        attached=[name for name, _ in attachments],
        left_out=left_out,
    )
