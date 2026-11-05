# Kweli — Data Model & API Contract

Changes to this contract go through a pull request with the code that implements them.

## Conventions
- Money is stored as **integer minor units + ISO currency** (`amount_minor=80000, currency="USD"`), never floats.
- IDs are UUIDs. PayPal IDs are kept in their own `paypal_*` columns.
- Every table that holds user data has `user_id`, and every query filters by it.
- Timestamps are UTC (`timestamptz`), set by the server.
- Errors use one shape: `{"error": {"code": "...", "message": "...", ...}}`.
- Lists use `?_start&_end&_sort&_order` and return `X-Total-Count`, which Refine's simple-rest expects.

## Tables

| Table | Key columns |
|---|---|
| `users` | id, email, name, password_hash, plan (`free`/`pro`), created_at |
| `sessions` | id (hashed token), user_id, expires_at |
| `clients` | id, user_id, name, email, country, paypal_payer_id (nullable) |
| `agreements` | id, user_id, client_id, scope, deliverables (json), amount_minor, currency, due_date, status (`draft`/`sent`/`accepted`/`expired`), pdf_document_id, accept_token_hash, accepted_at, accepted_ip_hash, accepted_user_agent, created_at |
| `invoices` | id, user_id, client_id, agreement_id, paypal_invoice_id, number, amount_minor, currency, status, sent_at, paid_at |
| `payments` | id, user_id, paypal_capture_id / transaction_id, paypal_invoice_id, payer_email, payer_id, amount_minor, currency, payment_type (`invoice`/`goods_services`/`personal`/`unknown`), received_at, source (`webhook`/`backfill`/`seed`) |
| `documents` | id, user_id, kind (`agreement`/`deliverable`/`correspondence`/`id`/`other`), filename, mime, size, sha256, storage_key, encrypted_dek, created_at |
| `payment_links` | payment_id, invoice_id, agreement_id, deliverable_document_id (all nullable) |
| `proof_flags` | id, payment_id, rule (`P1`–`P7`), status (`pass`/`warn`/`fail`), explanation, fix, evaluated_at |
| `disputes` | id, user_id, paypal_dispute_id, payment_id, reason, status, amount_minor, currency, evidence_due_at, outcome |
| `packs` | id, user_id, period_start, period_end, pdf_document_id, zip_document_id, created_at |
| `agent_actions` | id, user_id, tool, arguments (json), status (`proposed`/`approved`/`rejected`/`executed`/`failed`), approval_token_hash, result (json) |
| `webhook_events` | paypal_event_id (unique), event_type, received_at, processed_at, status |
| `subscriptions` | id, user_id, paypal_subscription_id, plan_id, status |
| `audit_log` | id, user_id, action, payload (json), prev_hash, hash, created_at |

## Endpoints

| Method + path | Purpose |
|---|---|
| `GET /health` | Liveness |
| `POST /v1/auth/login` · `POST /v1/auth/logout` · `GET /v1/auth/me` | Session auth |
| `GET/POST /v1/clients` · `GET/PATCH /v1/clients/{id}` | Clients |
| `POST /v1/agreements/extract` | Pasted thread → structured engagement (LLM) |
| `GET/POST /v1/agreements` · `GET /v1/agreements/{id}` · `POST /v1/agreements/{id}/send` | Agreements |
| `GET /v1/portal/agreements/{token}` · `POST /v1/portal/agreements/{token}/accept` | Public client portal (no login) |
| `GET/POST /v1/invoices` · `POST /v1/invoices/{id}/send` · `POST /v1/invoices/{id}/remind` | Invoices (via the approval gate) |
| `GET /v1/ledger` · `GET /v1/ledger/{payment_id}` · `POST /v1/ledger/{payment_id}/agreement` | Proof ledger + chain; link a payment that has no Kweli invoice to its agreement (`{agreement_id}` or `null` to unlink) |
| `GET /v1/readiness?limit=` | Readiness score, band, "fix next" in priority order, per-client summary ([docs/readiness.md](readiness.md)) |
| `POST /v1/documents` · `GET /v1/documents/{id}/url` | Encrypted vault upload + signed URL. Kinds: `deliverable`, `payer_confirmation` (needs `agreement_id`), `correspondence`, `other` |
| `POST /v1/agent/messages` | Chat with the agent (streams) |
| `POST /v1/agent/actions/{id}/approve` · `POST /v1/agent/actions/{id}/reject` | Approval gate |
| `POST /v1/packs` · `GET /v1/packs` · `GET /v1/packs/{id}` · `PUT /v1/packs/{id}/letter` | Compliance Packs. An edited letter is validated first; a rejected one returns 422 `letter_rejected` with `problems` ([docs/compliance-pack.md](compliance-pack.md)) |
| `GET /v1/disputes` · `GET /v1/disputes/{id}` · `POST /v1/disputes/{id}/prepare` · `PUT /v1/disputes/{id}/response` · `POST /v1/disputes/{id}/approval` · `POST /v1/disputes/{id}/submit` · `POST /v1/disputes/{id}/refresh` · `POST /v1/disputes/{id}/sandbox` | Dispute defender: evidence checklist, checked response, approval token bound to the exact draft, `provide-evidence` ([docs/disputes.md](disputes.md)) |
| `POST /v1/webhooks/paypal` | PayPal webhooks (signature verified) |
| `GET /v1/billing` · `POST /v1/billing/checkout` · `POST /v1/billing/confirm` · `POST /v1/billing/cancel` | Kweli Pro (PayPal Subscriptions). Checkout returns PayPal's approve link; confirm re-reads the subscription and checks plan and `custom_id`. Pro-only routes return 402 |
| `GET /v1/audit/verify` | Audit chain status |

## Agreement and invoice flow (as built)
1. `POST /v1/agreements/extract {thread}` returns an `EngagementDraft`: the fields, plus `missing` (fields the thread didn't state) and `notes` (anything Kweli dropped). The model fills one fixed form, and any email or amount that isn't literally in the thread is removed. With no `ANTHROPIC_API_KEY` this returns 503, and the UI switches to filling in by hand.
2. `POST /v1/agreements` stores the agreement and finds or creates the client by email (per user). The terms the client sees come from a fixed template (`agreement_text`). No AI writes contract terms.
3. `POST /v1/agreements/{id}/send` returns `{url, expires_at}`. The token is shown once and stored as a SHA-256 hash, and a new link invalidates the old one. Links last 14 days.
4. `GET /v1/portal/agreements/{token}` is public and shows no emails. `POST …/accept` needs the JSON body `{"accept": true}` (so a cross-site HTML form can't submit it). It records the time, an HMAC of the IP (never the IP itself) and the user agent. Accepting twice keeps the first time. Expired links return 410, and both portal routes are limited to 30 requests per minute per IP.
5. `POST /v1/invoices {agreement_id, due_date?, note?}` requires an **accepted** agreement (409 otherwise). It creates a PayPal **draft** with `PayPal-Request-Id: kweli-invoice-{id}`, and is idempotent per agreement.
6. `POST /v1/invoices/{id}/send` is the freelancer's explicit approval: PayPal emails the client, with `PayPal-Request-Id: kweli-send-{id}`, and repeat calls change nothing. PayPal errors come back as 502 ("Nothing was sent"), and credential problems as 503.

## Proof rule result (shared shape)

```json
{ "rule": "P3", "status": "warn",
  "explanation": "Paid by a third party (not Acme Ltd).",
  "fix": "Ask the client to confirm the payer in writing, then upload it." }
```
