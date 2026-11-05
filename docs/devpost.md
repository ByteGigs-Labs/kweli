# Devpost submission text

Copy each section into the matching Devpost field. Fill in the placeholders marked **[…]**.

**Tagline:** Proof for every PayPal payment, so honest freelancers keep their accounts.

**Demo:** https://kweli-web.onrender.com · Sign in with `amina@demo.kweli.test` / **[demo password]** (sandbox only, synthetic data)
**Video:** **[YouTube link]** · **Code:** https://github.com/ByteGigs-Labs/kweli (MIT)

## Inspiration
In June 2026, Kenyan freelancers reported frozen PayPal balances and closed accounts after being asked to prove what their payments were for. Most had done nothing wrong. Their work had been agreed over WhatsApp and paid by a "send money" link, so when PayPal asked for contracts and invoices, they had none. Kweli (Swahili for *true*) makes that proof a by-product of getting paid.

## What it does
- **Agreements from a chat.** Paste the client conversation, and the AI fills in a plain agreement. It drops any email or amount the chat doesn't contain. The client accepts it on their phone, and Kweli records the time and a one-way fingerprint of the network.
- **An assistant that proposes, never acts.** "Invoice Nairobi Eats for the menu, due in a week" produces an approval card. Only the freelancer's click, carrying a single-use token the model never sees, creates and sends the PayPal invoice.
- **A proof ledger (AG Grid).** Every payment arrives through verified webhooks and is checked against seven rules: invoiced, amount matches, payer is the client, agreement accepted, work delivered, business payment, usual amount. Each check comes with a plain explanation and a fix.
- **A readiness score.** One number out of 100, and a "fix next" list in priority order. Every fix can be made in place: upload the work, upload the client's confirmation of a third-party payment, or link an old payment to its agreement.
- **Compliance Packs.** One click builds a PDF and ZIP that map every payment to its agreement, invoice and delivered work, with hashes for every file. The AI drafts the cover letter, and a **citation validator blocks any letter that cites a missing document or a wrong amount**.
- **A dispute defender.** A dispute webhook makes Kweli fetch the dispute from PayPal and build the evidence checklist for that dispute reason from the freelancer's records. It drafts a checked response and, after approval, submits the agreement, invoice and work through `provide-evidence`.
- **Kweli Pro** costs USD 9 a month through **PayPal Subscriptions**.

## How we built it
- **PayPal:**
  - Invoicing v2: draft, send and remind, with `PayPal-Request-Id` idempotency.
  - Webhooks, with signature verification on the raw body and deduplication by event ID.
  - Transaction Search, to resolve payers.
  - Disputes v1: show dispute, multipart `provide-evidence`, and the sandbox `require-evidence` / `adjudicate` calls.
  - Subscriptions: server-side checkout, verified on return, kept in step by webhooks.
  - The **PayPal Agent Toolkit**'s `get_invoice`, `list_invoices` and `list_transactions` tools, run through Kweli's own hardened client.
- **AI:** Claude through the Anthropic API, with tool use for the assistant and a forced tool for extraction. All model output is validated, and the model can only propose; amounts and recipients always come from the database.
- **AG Grid:** the proof ledger, with a badge per rule, quick search, external status and client filters, column filters, a readiness-by-client view and CSV export. Only the Community modules Kweli uses are registered.
- **Render:** a Blueprint with a Docker API that migrates and seeds on start, a static web app with a strict CSP that rewrites `/v1/*` so the session cookie stays first-party, and Postgres.
- **Stack:** FastAPI, SQLAlchemy and Alembic on Postgres; React 19 with Refine and Vite; AES-256-GCM vault; hash-chained audit log; about 270 backend and 50 web tests in CI, plus `pip-audit`, `npm audit`, gitleaks and CodeQL.

## Challenges we ran into
- **Keeping the AI honest.** A letter to PayPal can't invent a document or an amount. We built a validator that checks every citation and amount against the records, and a standard letter that always passes when the AI's draft doesn't.
- **Prompt injection from clients.** Client messages and documents are data, never instructions. Dispute messages never reach the model at all, and the model can't touch money.
- **Cookies on Render.** onrender.com is a public suffix, so the web app proxies the API through a rewrite to keep a `SameSite=Strict` session.

## Accomplishments that we're proud of
- An approval gate that binds each approval to exactly what will be sent.
- A readiness score where every fix can be made in the app.
- Compliance Packs where every file is checked against its stored hash before it goes in. (Building our own demo data caught a placeholder hash.)

## What we learned
**[Your own words: for example, what the freelancers you interviewed said they were missing.]**

## What's next for Kweli
A pilot with 20 Kenyan freelancers, production PayPal app review, an M-Pesa withdrawal log to complete the money trail, then partnerships with freelance platforms in Nigeria, Ghana, Pakistan and the Philippines.

## Built with
`paypal-invoicing` · `paypal-disputes` · `paypal-subscriptions` · `paypal-webhooks` · `paypal-transaction-search` · `paypal-agent-toolkit` · `claude` · `anthropic-api` · `ag-grid` · `render` · `fastapi` · `python` · `postgresql` · `react` · `typescript` · `refine` · `vite`

## Tools section (AI models and services, and how they're used)
- **Claude (Anthropic API):** the assistant's reasoning and tool calls, extraction of agreements from chats, cover letters and dispute responses. Every output is validated before use, and the model only proposes; a person approves anything that sends or submits.
- **PayPal Agent Toolkit:** PayPal's tool definitions for reading invoices and transactions.
- **PayPal REST APIs (sandbox):** Invoicing, Disputes, Subscriptions, Transaction Search and Webhooks.
- **AG Grid Community:** the proof ledger.
- **Render:** hosting for the API, the web app and Postgres.
- **Development:** **[say which AI coding tools, if any, you used to build the project]**

## For judges
- Everything runs on the PayPal **sandbox** with synthetic data. No real money or personal data is involved.
- To try Kweli Pro, open **Billing** → **Upgrade with PayPal**, and approve with the sandbox buyer **[sandbox Personal email / password]**.
- The seeded "demo dispute" shows the dispute screens but is never sent to PayPal. Real sandbox disputes go all the way through.
