# Kweli ✅ — Proof for Every Payment

> **Kweli** (Swahili: *true, truth*) is an AI agent that helps freelancers in emerging markets get paid on PayPal **with a complete, verifiable paper trail for every payment**. That way, when PayPal asks *"what is this money for?"*, the answer is ready in one click.

**Live demo:** `https://kweli-api.onrender.com/health` (API, Day 0) *(PayPal sandbox)* · **License:** MIT

---

## 1. The Problem

Millions of freelancers in Kenya and other emerging markets are paid by overseas clients through PayPal. In 2026 this became risky for them:

- Kenya is on the **FATF grey list**, so payment providers must apply enhanced due diligence to cross-border payments.
- In **June 2026**, Kenyan users reported **frozen balances and permanently banned accounts**, after being asked to prove their employment and residence ([Business Daily](https://www.businessdailyafrica.com/bd/economy/paypal-freeze-block-kenya-accounts-in-money-laundering-fears-5482790), [WeeTracker](https://weetracker.com/2026/06/03/kenyans-furious-paypal-frozen-accounts-freelancers/)).
- Reviews asked for **contracts, invoices, bank statements and proof of address**. Many honest freelancers had never kept them, because work was agreed over WhatsApp and paid by a "send money" link.
- Funds can be held for **up to 180 days**, and accounts left non-compliant for longer can be closed.

The freelancers weren't doing anything wrong. They just **couldn't prove that they weren't**.

## 2. The Solution

Kweli makes **compliance a by-product of getting paid**. Every payment is born with its proof attached:

```
Client agreement  →  PayPal invoice  →  Payment  →  Deliverable  →  ✅ Proof chain complete
   (accepted)         (Invoicing API)    (webhook)    (uploaded)
```

| Feature | What it does | PayPal tech |
|---|---|---|
| **1. Engagement agent** | Paste a WhatsApp/email thread → the agent drafts a plain-language engagement agreement → the client accepts it through a link, and the timestamp is recorded | — |
| **2. Invoice agent** | "Invoice Acme $800 for the logo, due in 7 days" → the agent creates and sends a real PayPal invoice tied to the agreement *(you approve first)* | Agent Toolkit: `create_invoice`, `send_invoice`, `send_invoice_reminder` |
| **3. Proof ledger** | Every incoming payment is matched to its invoice, agreement and deliverable. Gaps are flagged with a plain reason and a fix | Webhooks, Invoicing v2, Transaction Search |
| **4. Readiness score** | The share of your incoming volume that is fully documented, with what's missing and how to fix it | — |
| **5. Compliance Pack** | When an information request arrives, one click builds a PDF + ZIP: a cover letter, a payment-to-document mapping table, contracts, invoices and deliverables, **each cited** | Transaction Search |
| **6. Dispute defender** | A client opens a dispute → the agent assembles evidence from the vault, drafts the response *(you approve)* and submits it | Disputes API: `get_dispute`, `provide-evidence`, `send-message`, `make-offer` |
| **7. Kweli Pro billing** | Subscriptions for Kweli itself, paid through PayPal | Subscriptions API |

### Why it's good for PayPal too
Kweli doesn't help anyone get around checks. It **helps honest users pass them**. PayPal gets better-documented emerging-market accounts and fewer false-positive reviews, and it keeps serving a fast-growing freelancer market instead of losing it to alternatives.

## 3. Glass Box Agent Design

Kweli's AI drafts and acts. **Deterministic rules decide what counts as proof.**

| Layer | Role | Can it be wrong silently? |
|---|---|---|
| **LLM (Claude via LangChain)** | Reads threads, drafts agreements, cover letters and dispute responses, and calls PayPal tools | No: every output goes through validators |
| **Proof rules (Python)** | Decide whether a payment is documented: invoice match, amount match, payer = client, deliverable present | No: deterministic, unit-tested and explained per rule |
| **Citation validator** | Every document the LLM cites must exist in the vault, and every amount must match the ledger. Otherwise the draft is blocked | — |
| **Human approval gate** | Sending an invoice, submitting dispute evidence and making an offer all need an explicit click | — |
| **Hash-chained audit log** | Records every agent action and approval, and makes any later edit detectable | — |

### Proof rules (v1)

| ID | Rule | Example explanation shown to the user |
|---|---|---|
| `P1` | Payment linked to a Kweli invoice | "Payment of $800 matches invoice INV-0042." |
| `P2` | Amount and currency match the invoice | "Paid $750 against an $800 invoice. Record the partial payment or ask the client to pay the balance." |
| `P3` | Payer = the client named on the agreement | "Paid by a third party (not Acme Ltd). Ask the client to confirm in writing." |
| `P4` | A signed or accepted agreement exists | "No agreement on file for this client. Send one for acceptance." |
| `P5` | Deliverable or proof of work attached | "No deliverable attached. Upload the final file or a link." |
| `P6` | Payment type fits business use | "Received as personal/'friends & family'. Use invoices for client work." |
| `P7` | Unusual volume for this account | "3× your 90-day average from a new payer. Make sure P1–P5 are complete." |

## 4. Architecture

```
 ┌──────────────────────┐   ┌──────────────────────┐
 │ Freelancer dashboard │   │ Client portal        │
 │ Refine + AG Grid     │   │ accept agreement     │
 └──────────┬───────────┘   └──────────┬───────────┘
            └────────────┬─────────────┘
                         ▼
                ┌──────────────────┐      ┌────────────────────────┐
                │ FastAPI backend  │◄─────│ PayPal Webhooks        │
                │ auth · RBAC      │      │ (signature verified)   │
                └───┬─────────┬────┘      └────────────────────────┘
                    │         │
        ┌───────────▼──┐   ┌──▼─────────────────┐
        │ Kweli agent  │   │ Proof rules engine │
        │ LangChain +  │   │ P1–P7 + validator  │
        │ PayPal Agent │   └──┬─────────────────┘
        │ Toolkit      │      │
        └──────┬───────┘      ▼
               │        ┌───────────────────────────┐
               ▼        │ Postgres: ledger, vault   │
      ┌───────────────┐ │ index, audit log (hashed) │
      │ PayPal APIs   │ └───────────────────────────┘
      │ Invoicing ·   │       Encrypted document store
      │ Disputes ·    │
      │ Transactions ·│
      │ Subscriptions │
      └───────────────┘
```

## 5. Tools Used (AI and PayPal)

| Tool | How Kweli uses it |
|---|---|
| **Claude (Anthropic), via LangChain** | Agent reasoning and tool calling. Structured extraction from threads. Drafting agreements, cover letters and dispute responses |
| **PayPal Agent Toolkit (Python)** | LangChain tools for invoices, disputes, transactions and subscriptions, with only the actions Kweli needs enabled |
| **PayPal REST APIs (sandbox)** | Invoicing v2, Disputes v1 (`provide-evidence`, plus the sandbox-only `require-evidence`/`adjudicate` to show the full lifecycle), Transaction Search, Subscriptions, Webhooks + signature verification |
| **AG Grid** | Proof ledger: per-payment proof status, rule badges, grouping by client, export |
| **Render** | Hosting for the API, frontend, Postgres and background worker |

## 6. Tech Stack

| Concern | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic, SQLAlchemy + Alembic |
| Agent | LangChain + `paypal-agent-toolkit` + Claude (model swappable) |
| Frontend | React + TypeScript + Refine (headless) + **AG Grid**, custom design system |
| PDF | WeasyPrint (Compliance Pack) |
| Storage | PostgreSQL; documents encrypted (AES-GCM) on disk/object storage |
| Hosting | **Render** (web service, static site, Postgres, background worker) |
| CI | GitHub Actions: lint, type-check, tests, secret scan |

## 7. Repository Structure

```
kweli/
├── api/
│   ├── main.py
│   ├── routes/               # auth, clients, agreements, invoices, ledger, packs, disputes, webhooks, billing
│   ├── security.py           # sessions, RBAC, rate limits
│   └── db/                   # models + migrations
├── paypal/
│   ├── client.py             # OAuth (client credentials), retries, idempotency keys
│   ├── webhooks.py           # signature verification + event routing
│   ├── invoicing.py · disputes.py · transactions.py · subscriptions.py
├── agent/
│   ├── kweli_agent.py        # LangChain agent + PayPal Agent Toolkit
│   ├── prompts/              # system prompts (versioned)
│   ├── extract.py            # thread → structured engagement
│   └── validators.py         # citation + amount checks, approval gate
├── proof/
│   ├── rules.py              # P1–P7
│   ├── matcher.py            # payment ↔ invoice ↔ agreement ↔ deliverable
│   └── score.py              # readiness score
├── packs/                    # Compliance Pack (PDF + ZIP)
├── audit/                    # hash-chained log
├── web/                      # Refine + AG Grid frontend
├── tests/
├── scripts/check_paypal.py   # verifies sandbox credentials + features
├── docs/                     # setup guides, API contract, interview guide
├── render.yaml               # Render Blueprint
├── docker-compose.yml
├── LICENSE
└── README.md
```

## 8. Run It Yourself

Step-by-step guides: [PayPal sandbox](docs/setup-paypal-sandbox.md) · [Render](docs/setup-render.md) · [Webhooks](docs/webhooks.md) · [API contract](docs/api-contract.md) · [Contributing](CONTRIBUTING.md)

### Prerequisites
- A PayPal Developer account (free) with a **sandbox Business** account (the freelancer) and a **sandbox Personal** account (the client)
- A REST app with **Invoicing** and **Disputes** enabled under app features
- An Anthropic API key (or set `LLM_PROVIDER` to another LangChain-supported model)

### Setup
```bash
git clone https://github.com/ByteGigs-Labs/kweli.git && cd kweli
cp .env.example .env     # PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_WEBHOOK_ID, ANTHROPIC_API_KEY, ...
docker compose up --build            # API + Postgres; runs migrations on start
# API: http://localhost:8000/health · docs at http://localhost:8000/docs

# Demo login (set DEMO_USER_PASSWORD in .env first, 10+ characters)
docker compose exec api python -m scripts.seed

# Web app (proxies /v1 to the API, so the session cookie stays same-origin)
cd web && npm install && npm run dev  # http://localhost:5173

# Check the PayPal sandbox app (credentials + enabled features)
python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
python -m scripts.check_paypal
python -m scripts.create_sandbox_invoice --to <sandbox-client-email> --amount 10.00 --send
```

To receive webhooks locally, expose the API (for example with `cloudflared tunnel`) and register `https://<tunnel>/v1/webhooks/paypal` in your app's webhook settings.

### Demo path (about 3 minutes)
1. Log in with the seeded demo freelancer.
2. Paste a client thread → the agent drafts an agreement → open the client link → **Accept**.
3. Ask the agent: *"Invoice them $800 for the logo, due in 7 days"* → approve → the invoice arrives in the sandbox client's inbox → pay it.
4. Watch the payment land in the **Proof ledger** with a full ✅ chain, while an old third-party payment shows ⚠ P3 and its fix.
5. Click **Generate Compliance Pack** → download the PDF with every payment mapped to cited documents.
6. Open a sandbox dispute → Kweli drafts evidence from the vault → approve → submit → adjudicate in the sandbox.

## 9. Security & Privacy

- **Secrets:** PayPal and LLM keys exist only on the server (Render env vars), never in the browser.
- **Webhooks:** each event is verified with PayPal's verify-webhook-signature API and deduplicated by event ID (replay-safe).
- **Least-privilege agent:** only the toolkit actions Kweli needs are enabled. Money-moving or submitting actions require a human approval token that the LLM cannot generate.
- **Prompt-injection defence:** client messages and documents are treated as untrusted data in a separate content channel, and tool calls from them are blocked unless the user approves them.
- **Documents:** encrypted at rest (AES-GCM, per-user keys wrapped by a master key), served via short-lived signed URLs, with MIME and size checks on upload.
- **No fabrication:** Kweli never generates receipts, addresses, statements or backdated agreements. It only organises real documents, and every agreement carries its true acceptance timestamp.
- **Sessions:** httpOnly + Secure + SameSite cookies, Argon2 password hashing, rate-limited login.
- **Audit:** a hash-chained log of every agent action and approval.
- **Data protection:** designed around the Kenya Data Protection Act 2019 (minimisation, export and delete on request).

## 10. Business Model

| Plan | For | Price (indicative) |
|---|---|---|
| **Free** | New freelancers | 3 clients, ledger + readiness score |
| **Pro** | Active freelancers | Monthly subscription via **PayPal Subscriptions**: unlimited clients, Compliance Packs, dispute defender |
| **Agency** | Small agencies and teams | Per-seat pricing, team ledger, subcontractor records |
| **Partners** | Freelance platforms, coworking spaces, digital-work programmes | Bulk licences and white-label |

## 11. Limitations (honest)

- PayPal has **no public API for account-limitation information requests**. Kweli prepares the pack, and the user uploads it in PayPal's Resolution Center.
- Kweli improves documentation. **It cannot guarantee that PayPal will lift a limitation.**
- Transaction Search data can be delayed in the sandbox, so the live demo relies on webhooks and Invoicing for real-time matching.
- Kweli is not legal or financial advice.

## 12. Team

| Name | Owns |
|---|---|
| — | CI/CD + Render, auth, proof rules engine, AG Grid ledger, readiness score, audit log, PayPal billing |
| — | PayPal agent, agreements + client portal, invoicing, document vault, Compliance Pack, dispute defender |

## 13. License

[MIT](LICENSE)
