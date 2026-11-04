# The Kweli Assistant

The assistant answers questions about a freelancer's agreements, invoices and proof, and **prepares** actions. It never performs one on its own.

## What it can do
| Tool | Kind | What it returns or does |
|---|---|---|
| `find_agreements` | Read | Agreements matching a client or work title, with fee, status and invoice |
| `ledger_overview` | Read | Counts by proof status and the payments that most need fixing, with the fix for each |
| `explain_payment` | Read | Every proof check (P1–P7) for one payment |
| `get_invoice`, `list_invoices`, `list_transactions` | Read, PayPal Agent Toolkit | PayPal's own records. Only offered to the user who owns the PayPal merchant account (`PAYPAL_MERCHANT_ID`), and `get_invoice` only for that user's Kweli invoices |
| `propose_invoice` | Proposal | Approval card: create (and by default send) the PayPal invoice for an **accepted** agreement |
| `propose_send_invoice` | Proposal | Approval card: send an existing draft |
| `propose_reminder` | Proposal | Approval card: PayPal reminder for a sent, unpaid invoice |
| `propose_acceptance_link` | Proposal | Approval card: a new link for the client to accept an agreement |

There is **no** tool that approves, sends, pays, refunds, changes amounts or sets an email address.

## The approval gate (`agent/actions.py`)
1. A proposal tool validates the IDs against the database (ownership, status), stores only those IDs, and creates a single-use token. Only the token's SHA-256 hash is stored.
2. The token goes back to the browser in the API response. **The model never sees it**: the model only gets "waiting for the freelancer to approve or decline".
3. The card shows the facts from the database: recipient, amount, work, due date.
4. **Approve** sends the token to `POST /v1/agent/actions/{id}/approve`. The row is locked, the token is checked (constant-time compare) and cleared, and the 15-minute expiry is enforced. Then the action runs through the same service code as the rest of the app, which re-reads every fact from the database.
5. Each step is written to the hash-chained audit log: `agent.proposed`, `agent.approved` or `agent.rejected`, then the domain events (`invoice.drafted`, `invoice.sent`…).

## Prompt injection
Agreement text, client names and PayPal data can contain text written by other people. Kweli defends against this in layers:
- Tool results are wrapped as data with an explicit "ignore any instructions" note, and the system prompt says the same.
- Even a fully hijacked model can only *propose*, and only with IDs. A proposal's recipient and amount always come from the agreement, so "send it to attacker@…" can't happen.
- Every proposal still needs a click from the logged-in freelancer.

`tests/test_agent.py` covers injected agreement text, extra amount and email arguments, other users' IDs, made-up tool names, wrong, replayed and expired tokens, runaway loops, and model failures.

## Limits
- 20 messages per minute per user (`AGENT_MESSAGES_PER_MINUTE`), and at most 6 model steps per message.
- Conversations live in the browser. Each request sends at most the last 20 messages (user and assistant text only), validated by the API.
- Without `ANTHROPIC_API_KEY`, the assistant shows a clear message and everything else keeps working.
