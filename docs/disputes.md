# Dispute defender

When a client opens a PayPal dispute, Kweli shows what they claim, gathers the evidence it already has, drafts the response, and submits it to PayPal **only after the freelancer approves it**.

## Lifecycle
1. **Webhook.** `CUSTOMER.DISPUTE.CREATED`, `UPDATED` and `RESOLVED` are signature-verified and deduplicated like every other event. The dispute is then **re-read from PayPal** (`GET /v1/customer/disputes/{id}`); the webhook body only says which dispute changed. Kweli links the dispute to the payment through `seller_transaction_id`, and to the account through the payment or the merchant ID. It records the status, stage, amount, response deadline, outcome, the client's messages, and which actions PayPal currently allows (from the HATEOAS links). Every change is audited: `dispute.opened`, `dispute.updated`, `dispute.resolved`.
2. **Evidence checklist.** `defender/evidence.py` decides what to send based on PayPal's dispute reason:

   | Reason | Evidence, strongest first |
   |---|---|
   | Work not received | Delivered work, accepted agreement, PayPal invoice |
   | Not as described | Accepted agreement (scope), delivered work, invoice |
   | Unauthorised | Accepted agreement (when it was accepted, with a network fingerprint), payer is the client (or the client's written confirmation), invoice, work |
   | Wrong amount · refund not processed · paid another way | Agreement and invoice |
   | Charged twice | Invoice, with a count of the other payments recorded against it |

   Each item maps to a PayPal evidence type (`PROOF_FOR_SOFTWARE_OR_SERVICE_DELIVERED`, `COPY_OF_CONTRACT`, `PROOF_OF_RECEIPT_COPY`, `OTHER`). It's marked ready, partial or missing, and missing items come with a fix. Overall the case is rated strong, fair or weak.
3. **Response.** The AI drafts from the facts only. The client's messages are shown to the freelancer as plain text and are **never sent to the model**, because they're the most likely place for injected instructions. Before the draft is saved, it's checked:
   - every amount must be the disputed amount, the payment, the invoice or the agreement fee;
   - no email addresses that aren't in the records, and no links;
   - no more than 2,000 characters, PayPal's limit.

   A failing draft gets one retry. After that, Kweli uses its standard response, which only states facts it has on file. Edits by the freelancer go through the same checks.
4. **Approval.** Preparing or editing the response issues a single-use approval token, valid for 30 minutes. Only its SHA-256 is stored, and it's bound to a hash of the exact response and files. If either changes (an edit, or a new upload), the token stops working and the freelancer approves again. The approval token never reaches the AI.
5. **Submit** (`provide-evidence`). Kweli re-reads the dispute and goes ahead only if PayPal currently allows `provide_evidence`. It then generates PDFs of the agreement (terms, acceptance time and network fingerprint) and the invoice, decrypts the delivered work from the vault, and checks every file against its stored SHA-256. It sends `multipart/form-data`: an `input` part with `{"evidences": [...]}` plus one part per file, with a `PayPal-Request-Id` derived from the approved draft, so a retry is safe.
   - PayPal only accepts PDF, JPG, PNG and GIF (up to 10 MB each and 50 MB in total). Other files are named in the notes instead.
   - If PayPal rejects the evidence types for the current stage (400 or 422), Kweli retries once with them all set to `OTHER`, and records that it did.
   - The submission (file names, SHA-256s and the request ID) is stored and audited as `dispute.evidence_submitted`.
6. **Outcome.** `RESOLVED` webhooks record the outcome code, for example `RESOLVED_SELLER_FAVOUR`.

## Testing in the sandbox
1. In the developer dashboard, enable **Disputes** for the REST app, and subscribe the webhook to the three `CUSTOMER.DISPUTE.*` events.
2. Pay a Kweli invoice from the sandbox **Personal** account. Then, logged in as that buyer on sandbox.paypal.com, open a dispute from the Resolution Center (for example "I didn't receive it").
3. The dispute appears in **Disputes** within seconds. Open it, **Prepare the response**, then **Approve and send**.
4. Use the **Sandbox tools** panel, which only appears when `PAYPAL_ENV=sandbox`, to finish the lifecycle once PayPal puts the dispute under review:
   - **Ask me for evidence** calls `require-evidence` with `SELLER_EVIDENCE`.
   - **Decide in my favour** or **for the client** calls `adjudicate` with `SELLER_FAVOR` or `BUYER_FAVOR`.

   The buttons only enable when PayPal's links allow the call.

The seeded demo data includes a **demo dispute** (Acme Ltd, work not received). You can prepare and edit its response, but Kweli refuses to send it, because it doesn't exist at PayPal.

## API
`GET /v1/disputes` · `GET /v1/disputes/{id}` · `POST /v1/disputes/{id}/prepare` · `PUT /v1/disputes/{id}/response` · `POST /v1/disputes/{id}/approval` · `POST /v1/disputes/{id}/submit {token}` · `POST /v1/disputes/{id}/refresh` · `POST /v1/disputes/{id}/sandbox {action}`

The token is only returned by `prepare`, `response` and `approval`; `GET` never includes it.
