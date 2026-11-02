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
| `PAYMENT.SALE.COMPLETED` | Subscription payment received |

Copy the **Webhook ID** into `PAYPAL_WEBHOOK_ID` (in `.env` locally and in Render).

## Rules for the handler (task M-10)
1. Verify every event with `POST /v1/notifications/verify-webhook-signature`, and reject it if the status isn't `SUCCESS`.
2. Insert `paypal_event_id` into `webhook_events` (unique) **before** processing, and skip duplicates (replays).
3. Return 200 fast. Process in the background, and never let a processing error make PayPal retry forever.
4. Never trust amounts or IDs in the event body alone. Re-fetch the invoice, capture or dispute from the API.

Local development: `cloudflared tunnel --url http://localhost:8000`, then use the printed URL.
