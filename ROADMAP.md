# Kweli — Roadmap

**Deadline:** Thursday 12 Nov 2026, 23:00 EAT (Devpost). **Our internal deadline: Thursday 12 Nov, 18:00 EAT**, to leave 5 hours of buffer.

**Prize targets:**
1. **Overall** (1st/2nd/3rd)
2. **Most Impactful**
3. **Best Use of PayPal + AI**
4. **Best Use of AG Grid** (ledger)
5. **Best Use of Render** (hosting)
6. **Best Demo Delivery**

## Submission checklist (from the rules)
- [ ] Public GitHub repo with all source code, and an **MIT LICENSE visible in the About section**
- [ ] Meaningful **PayPal** integration (Invoicing, Disputes, Webhooks, Transactions, Subscriptions) **and** meaningful **AI** (agent + drafting)
- [ ] Working build: a **hosted demo URL on Render** + complete run instructions in the README
- [ ] Text description of features and functionality
- [ ] **Tools section:** which AI models and services were used, and how
- [ ] **Demo video under 3 minutes**, on YouTube, public, showing the app working, with **no copyrighted music**
- [ ] Sandbox only. No real money, no real personal data

---

## Day 0 — Mon 2 Nov (today) · Setup & evidence
- PayPal Developer account. Create a **sandbox Business** account (the freelancer) and a **sandbox Personal** account (the client).
- Create a REST app with **Invoicing + Disputes** enabled, and register a webhook URL (a tunnel for now).
- Public repo `kweli` with the MIT LICENSE, README, ROADMAP, branch protection and secret scanning.
- Render account; claim the sponsor credits if offered.
- Message **6 Kenyan freelancers** (3 each) and ask whether they've had a PayPal limitation or info request, and what documents they had or lacked. This is the evidence for Impact.

## Day 1 — Tue 3 Nov · Foundations
- FastAPI skeleton, Postgres models (users, clients, agreements, invoices, payments, documents, flags, audit), Alembic.
- PayPal client: OAuth token cache, retries, `PayPal-Request-Id` idempotency keys.
- Refine app shell + login + AG Grid installed.
- CI: lint, type-check, tests, gitleaks.
- **Exit:** log in → see an empty ledger. A sandbox invoice can be created from a script.

## Day 2 — Wed 4 Nov · Agreements + invoices
- Thread → structured engagement extraction (LLM, Pydantic-validated).
- Agreement draft → client portal accept link (signed token, timestamp + IP hash).
- Invoice flow: create → approve → send via PayPal.
- **Exit:** paste a thread → agreement accepted by the "client" → PayPal invoice in the client's sandbox inbox.

## Day 3 — Thu 5 Nov · Webhooks + proof engine
- Webhook endpoint with **signature verification** and dedup by event ID.
- Matcher for payment ↔ invoice ↔ agreement ↔ deliverable. Rules P1–P7 with explanations and fixes, plus unit tests.
- Document vault: encrypted upload, deliverable attachment.
- **Exit:** pay the invoice in the sandbox → the ledger row turns ✅. A seeded third-party payment shows ⚠ P3.

## Day 4 — Fri 6 Nov · The agent
- LangChain agent + PayPal Agent Toolkit (invoices, transactions, disputes) + Kweli tools (ledger lookup, vault search).
- Approval gate: the agent proposes, and the user approves with a server-issued token.
- Agent chat panel in the UI.
- **Exit:** "Invoice Acme $800 for the logo, due in 7 days" → approval card → sent.

## Day 5 — Sat 7 Nov · Ledger UX + readiness score
- AG Grid proof ledger: status badges per rule, group by client, filters, export, row detail drawer with the proof chain.
- Readiness score + "fix next" list on the dashboard.
- **Exit:** the dashboard tells a freelancer exactly what to fix, in priority order.

## Day 6 — Sun 8 Nov · Compliance Pack
- Pack builder: cover letter (LLM, citation-validated) + payment-to-document mapping table + attachments → PDF + ZIP.
- Citation validator: blocks any draft that cites a missing document or a wrong amount.
- **Exit:** one click → a downloadable pack that maps every payment to its proof.

## Day 7 — Mon 9 Nov · Dispute defender
- Webhook `CUSTOMER.DISPUTE.CREATED` → fetch the dispute → evidence checklist by dispute reason → draft response.
- Approve → `provide-evidence` (multipart with files). Use the sandbox `require-evidence`/`adjudicate` calls to show the outcome.
- **Exit:** full dispute lifecycle in the sandbox, in the UI.

## Day 8 — Tue 10 Nov · Billing, security, deploy
- Kweli Pro via **PayPal Subscriptions** (plan + subscribe button + webhook activation).
- Security pass: prompt-injection tests, rate limits, upload limits, headers, cookie flags.
- Deploy to **Render** with a `render.yaml` Blueprint, and seed the demo data.
- **Exit:** the full demo path works on the public URL.

## Day 9 — Wed 11 Nov · Polish & user test
- Put 2–3 real freelancers in front of the live app, and capture a quote with permission.
- Bug bash both ways, plus UX polish: empty states, loading states, mobile check.
- Write the demo script and Devpost description.

## Day 10 — Thu 12 Nov · Ship
- Record and upload the video (under 3 minutes, YouTube public).
- Final README pass: screenshots, URL, video, tools section.
- **Submit on Devpost by 18:00 EAT.**

---

## 3-minute video script (draft)
| Time | Shot |
|---|---|
| 0:00–0:20 | Hook: headlines about frozen Kenyan PayPal accounts. "These freelancers did nothing wrong. They just couldn't prove it." |
| 0:20–0:50 | Paste a thread → agent drafts an agreement → client accepts → "Invoice them $800" → approval → invoice sent |
| 0:50–1:20 | Client pays in the sandbox → ledger row turns ✅ → the third-party payment shows ⚠ P3 with its fix |
| 1:20–1:50 | Readiness score → **Generate Compliance Pack** → open the PDF with every payment mapped to cited documents |
| 1:50–2:30 | Dispute opened → agent drafts evidence from the vault → approve → submitted → resolved in the merchant's favour |
| 2:30–2:55 | Glass box + security in one breath: rules decide, the AI drafts, humans approve, everything is audited. Freelancer quote. Business model |

## After the hackathon
- **Month 1:** pilot with 20 Kenyan freelancers, and measure readiness score change and info-request outcomes.
- **Month 2:** go live (production PayPal app review), add an M-Pesa withdrawal log to complete the money trail, and launch the Pro plan.
- **Month 3:** partner with freelance platforms and digital-work programmes, then expand to Nigeria, Ghana, Pakistan and the Philippines.
