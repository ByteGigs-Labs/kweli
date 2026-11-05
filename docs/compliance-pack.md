# Compliance Pack

When PayPal asks what your payments were for, one click builds a pack for a period of your choice (up to 12 months).

## What's in it
| File | What it is |
|---|---|
| `00-cover-letter-and-table.pdf` | The cover letter, **Table 1 [T1]** mapping every payment to its agreement, invoice and delivered work, the document list, an appendix with each agreement's terms and acceptance record and each invoice, and an integrity note |
| `payments.csv` | Table 1 as data, with the PayPal transaction ID and the result of every proof check |
| `agreements/D…txt` · `invoices/D…txt` | Each agreement's terms, with when and from which network (as a one-way fingerprint) the client accepted, and each PayPal invoice |
| `documents/D…` | The delivered work and the clients' payer confirmations, decrypted from the vault. Each file is checked against its stored SHA-256 before it's added |
| `manifest.json` | The SHA-256 of every file, and the audit log's entry count and head hash at build time |

Every payment (`P1`, `P2`…) and every document (`D1`, `D2`…) gets a reference, and the letter cites them in square brackets.

## The cover letter and the citation validator
1. The AI (`packs/letter.py`) drafts the letter from the facts only. The facts are passed as data, with the same "ignore any instructions" rule the assistant has.
2. `packs/citations.py` checks the draft. A draft is **blocked** if:
   - it cites a reference that isn't in the pack, for example `[D40]` or `[Doc 3]`;
   - it names an amount that isn't a real payment, invoice, agreement fee or total;
   - a sentence names an amount without citing its source;
   - a sentence cites one payment and one amount, and the amount isn't that payment's own (or its invoice's);
   - it contains an email address that isn't in the records, or any link;
   - it has no citations at all, or is too short or too long.
3. A blocked draft gets one retry, with the problems listed. If it's blocked again, or no model is set up, Kweli uses its **standard letter**. That letter is built from the same facts and always passes. It's honest about gaps: it names payments with missing proof instead of hiding them. The pack page says which letter was used, and why the AI's draft was rejected.
4. You can edit the letter. Your edit goes through the same validator, so a typo in an amount is caught before the PDF and ZIP are rebuilt. If your records have changed since the pack was made, the edit is refused and you're asked to make a new pack, so references can never point at the wrong thing.

The validator checks what can be checked mechanically. It doesn't prove every sentence true, so you still read the letter before sending it.

## Storage and limits
- The PDF and ZIP are stored encrypted in the vault (`kind=pack`) and downloaded through the usual 5-minute signed links.
- Creating a pack and editing its letter are both written to the hash-chained audit log, with the SHA-256 of the PDF and ZIP.
- Attachments are capped at 40 MB per pack. Anything larger is listed but left out, and the pack says so.
- A pack can't be built if the audit log fails its integrity check.
- At most 5 packs per minute per user.
- Fonts: the API image installs DejaVu, so accented names render correctly. Without it, the PDF falls back to Latin-1 and strips accents.
