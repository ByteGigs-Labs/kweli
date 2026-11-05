# PayPal Webhooks

Register **one** webhook in the sandbox app (developer.paypal.com → Apps & Credentials → Sandbox → Kweli → Webhooks → Add Webhook):

- **URL:** `https://kweli-api.onrender.com/v1/webhooks/paypal` (or your tunnel URL while developing locally)
- **Events:**

| Event | Used for |
|---|---|
| `INVOICING.INVOICE.PAID` | Invoice paid → payment + proof chain |
| `INVOICING.INVOICE.CANCELLED` | Invoice status |
| `PAYMENT.CAPTURE.COMPLETED` | Payments outside invoices |
| `PAYMENT.CAPTURE.REFUNDED` | Ledger correction |
| `CUSTOMER.DISPUTE.CREATED` | Dispute defender starts |
| `CUSTOMER.DISPUTE.UPDATED` | Status changes, evidence requests |
| `CUSTOMER.DISPUTE.RESOLVED` | Outcome |
| `BILLING.SUBSCRIPTION.ACTIVATED` | Kweli Pro on |
| `BILLING.SUBSCRIPTION.CANCELLED` | Kweli Pro off |
| `BILLING.SUBSCRIPTION.SUSPENDED` | Kweli Pro paused |
| `BILLING.SUBSCRIPTION.EXPIRED` | Kweli Pro off |
| `BILLING.SUBSCRIPTION.UPDATED` | Next billing date |

Every `BILLING.SUBSCRIPTION.*` event re-reads the subscription from PayPal (`GET /v1/billing/subscriptions/{id}`) and only acts on Kweli's own plan. Dispute events carry `dispute_id` instead of `id`, and they're re-read the same way.

Copy the **Webhook ID** into `PAYPAL_WEBHOOK_ID` (in `.env` locally and in Render).

## How the handler works (`api/routes/webhooks.py`)
1. **Verify.** Every event goes back to PayPal's `POST /v1/notifications/verify-webhook-signature` **byte for byte**, because re-serialised JSON can fail verification. Anything other than `SUCCESS` gets a 400 and nothing is stored. Missing signature headers get a 400, and a missing `PAYPAL_WEBHOOK_ID` gets a 503.
2. **Deduplicate.** The event ID is stored before processing. A replay of a processed or ignored event returns `{"status": "duplicate"}`, and payments are unique by PayPal transaction ID too.
3. **Re-read from PayPal.** Amounts, payers and IDs come from the API (invoice, capture, order and Transaction Search), never from the webhook body.
4. **Retry on failure.** If processing fails (PayPal down, say), the event is marked `failed` and the endpoint returns 503, so PayPal retries. The retry processes it normally.
5. **Prove.** Each new payment runs through rules P1–P7, and the result is written to the hash-chained audit log.

| Event | What Kweli does |
|---|---|
| `INVOICING.INVOICE.PAID` / `UPDATED` | Re-reads the invoice and records each new PayPal payment on it (handles part payments) |
| `INVOICING.INVOICE.CANCELLED` | Marks the invoice cancelled |
| `PAYMENT.CAPTURE.COMPLETED` | Re-reads the capture and, for checkout payments, the order's payer. The owner comes from the payee merchant ID (`PAYPAL_MERCHANT_ID`) |
| Anything else | Stored as `ignored` |

**Payer not known yet?** Transaction Search can take hours to index a payment, so P3 shows "Waiting for PayPal to confirm who paid" (pending, not failed). `python -m scripts.refresh_payers` fills these in and re-runs the rules. Schedule it every 30 minutes on Render (Cron Job) or run it by hand.

**Testing.** The Developer Dashboard's *Webhooks simulator* sends events that **can't be verified**, so Kweli correctly rejects them. To test for real, pay a sandbox invoice as the `kweli-client` account. Delivery and retries show under your app → Webhooks → Events.

Local development: `cloudflared tunnel --url http://localhost:8000`, then use the printed URL.
