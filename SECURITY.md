# Security Policy

Kweli is a project that runs against the **PayPal sandbox only**. It must never hold live credentials or real customer data.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's **Report a vulnerability** button (Security tab → Advisories) on this repository. We aim to reply within 72 hours.

## Design principles

- Secrets live only in server environment variables, never in the browser or the repo.
- PayPal webhooks are verified with PayPal's signature-verification API and deduplicated by event ID.
- Documents are encrypted at rest and served through short-lived signed URLs.
- The AI agent can propose actions but cannot execute money-moving or submitting actions without a human approval token.
- Every agent action and approval is written to a hash-chained audit log.
