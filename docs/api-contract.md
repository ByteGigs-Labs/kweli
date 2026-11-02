# Kweli — Data Model & API Contract (v0, Day 0 draft)

Task **X-01**. After both of you approve this file, changes need a PR approved by both.

## Conventions
- Money is stored as **integer minor units + ISO currency** (`amount_minor=80000, currency="USD"`), never floats.
- IDs are UUIDs. PayPal IDs are kept in their own `paypal_*` columns.
- Every table that holds user data has `user_id`, and every query filters by it.
- Timestamps are UTC (`timestamptz`), set by the server.
- Errors use one shape: `{"error": {"code": "...", "message": "...", ...}}`.
- Lists use `?_start&_end&_sort&_order` and return `X-Total-Count`, which Refine's simple-rest expects.

## Tables

| Table | Key columns | Owner |
|---|---|---|
| `users` | id, email, name, password_hash, plan (`free`/`pro`), created_at | Me |
| `sessions` | id (hashed token), user_id, expires_at | Me |
| `clients` | id, user_id, name, email, country, paypal_payer_id (nullable) | Friend |
| `agreements` | id, user_id, client_id, scope, deliverables (json), amount_minor, currency, due_date, status (`draft`/`sent`/`accepted`/`expired`), pdf_document_id, accept_token_hash, accepted_at, accepted_ip_hash, accepted_user_agent, created_at | Friend |
| `invoices` | id, user_id, client_id, agreement_id, paypal_invoice_id, number, amount_minor, currency, status, sent_at, paid_at | Friend |
| `payments` | id, user_id, paypal_capture_id / transaction_id, paypal_invoice_id, payer_email, payer_id, amount_minor, currency, payment_type (`invoice`/`goods_services`/`personal`/`unknown`), received_at, source (`webhook`/`backfill`/`seed`) | Me |
| `documents` | id, user_id, kind (`agreement`/`deliverable`/`correspondence`/`id`/`other`), filename, mime, size, sha256, storage_key, encrypted_dek, created_at | Friend |
| `payment_links` | payment_id, invoice_id, agreement_id, deliverable_document_id (all nullable) | Me |
| `proof_flags` | id, payment_id, rule (`P1`–`P7`), status (`pass`/`warn`/`fail`), explanation, fix, evaluated_at | Me |
| `disputes` | id, user_id, paypal_dispute_id, payment_id, reason, status, amount_minor, currency, evidence_due_at, outcome | Friend |
| `packs` | id, user_id, period_start, period_end, pdf_document_id, zip_document_id, created_at | Friend |
| `agent_actions` | id, user_id, tool, arguments (json), status (`proposed`/`approved`/`rejected`/`executed`/`failed`), approval_token_hash, result (json) | Friend |
| `webhook_events` | paypal_event_id (unique), event_type, received_at, processed_at, status | Me |
| `subscriptions` | id, user_id, paypal_subscription_id, plan_id, status | Me |
| `audit_log` | id, user_id, action, payload (json), prev_hash, hash, created_at | Me |

## Endpoints

| Method + path | Purpose | Owner |
|---|---|---|
| `GET /health` | Liveness | Friend (done) |
| `POST /v1/auth/login` · `POST /v1/auth/logout` · `GET /v1/auth/me` | Session auth | Me |
| `GET/POST /v1/clients` · `GET/PATCH /v1/clients/{id}` | Clients | Friend |
| `POST /v1/agreements/extract` | Pasted thread → structured engagement (LLM) | Friend |
| `GET/POST /v1/agreements` · `GET /v1/agreements/{id}` · `POST /v1/agreements/{id}/send` | Agreements | Friend |
| `GET /v1/portal/agreements/{token}` · `POST /v1/portal/agreements/{token}/accept` | Public client portal (no login) | Friend |
| `GET/POST /v1/invoices` · `POST /v1/invoices/{id}/send` · `POST /v1/invoices/{id}/remind` | Invoices (via the approval gate) | Friend |
| `GET /v1/ledger` · `GET /v1/ledger/{payment_id}` | Proof ledger + chain | Me |
| `GET /v1/readiness` | Readiness score + "fix next" | Me |
| `POST /v1/documents` · `GET /v1/documents/{id}/url` | Encrypted vault upload + signed URL | Friend |
| `POST /v1/agent/messages` | Chat with the agent (streams) | Friend |
| `POST /v1/agent/actions/{id}/approve` · `POST /v1/agent/actions/{id}/reject` | Approval gate | Friend |
| `POST /v1/packs` · `GET /v1/packs` · `GET /v1/packs/{id}` | Compliance Packs | Friend |
| `GET /v1/disputes` · `GET /v1/disputes/{id}` · `POST /v1/disputes/{id}/draft` | Disputes | Friend |
| `POST /v1/webhooks/paypal` | PayPal webhooks (signature verified) | Me |
| `GET /v1/billing` · `POST /v1/billing/subscribe` | Kweli Pro (PayPal Subscriptions) | Me |
| `GET /v1/audit/verify` | Audit chain status | Me |

## Proof rule result (shared shape)

```json
{ "rule": "P3", "status": "warn",
  "explanation": "Paid by a third party (not Acme Ltd).",
  "fix": "Ask the client to confirm the payer in writing, then upload it." }
```
