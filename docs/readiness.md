# Readiness score

The overview page answers one question: if PayPal asked what your payments were for today, how ready would you be? The logic is in `proof/readiness.py`. It uses pure functions of the stored proof checks, with no AI involved.

## The score
- Each payment has six scored checks (P1–P6). A check that passes is worth 1 point, one that needs attention is worth 0.5, and a missing one is worth 0.
- Checks still waiting on PayPal (`pending`) are left out, because there's nothing the freelancer can do about them.
- P7 (an unusually large amount) is advice, not proof, so it isn't scored. The overview mentions it separately.
- The score is points earned out of points possible, as a whole number from 0 to 100.

| Band | Rule |
|---|---|
| Ready for a review | 90 or more **and** no payment with missing proof |
| Nearly ready | 70 or more |
| At risk | Below 70 |

A single payment with no paper trail can be enough to start a review. That's why missing proof keeps you out of "ready" even when the score is high.

## Fix next
- One item per payment, listing its steps.
- Steps that only fail because of another one are hidden. With no invoice, P2 can't match. With no agreement, P3 has no client to compare the payer with, and P5 has nothing to attach the work to. Fixing the root step is the real fix.
- Items are ordered by severity (missing before needs attention), then by the points the fix wins, then by amount, then newest first.
- "Fix this payment" opens the payment in the ledger. From there you can make the fix in place:
  - **Upload the delivered work** (P5).
  - **Upload the client's written confirmation** of a third-party payment (P3). It's stored encrypted with the agreement. P3 then passes and names the file.
  - **Link a payment that didn't come through a Kweli invoice** to its agreement (`POST /v1/ledger/{id}/agreement`). This isn't allowed when an invoice already decides the agreement. Every link and unlink is written to the audit log.

## API
`GET /v1/readiness?limit=10` returns the score, band, counts, the first `limit` fix items with `fix_total`, and a per-client summary. The assistant's `ledger_overview` tool uses the same function, so the chat and the dashboard always agree.
