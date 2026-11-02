# Contributing to Kweli

Kweli handles payment records and identity documents, so a few rules are non-negotiable.

## Ground rules

- **Sandbox only.** Never put live PayPal credentials anywhere in this repo or in Render. `PAYPAL_ENV` must be `sandbox`.
- **No real personal data.** Demo data is synthetic. Interview notes are anonymised before they are committed.
- **Never fabricate.** Kweli organises real documents. No code may generate receipts, statements, addresses or backdated agreements.
- **Humans approve money.** Any agent action that sends an invoice, submits dispute evidence, makes an offer or changes a subscription needs a server-issued approval token from a user click.
- **Branch and pull request.** Nobody pushes to `main`. CI must be green, and the other person reviews.
- **Tests with every change.** A change without a test is not done.

## Set up

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
cp .env.example .env              # fill in the PayPal sandbox credentials
docker compose up -d postgres
uvicorn api.main:app --reload
python -m scripts.check_paypal    # verifies the sandbox app and its features
ruff check . && ruff format . && pytest
```

## Changing the API

Update `docs/api-contract.md` in the same PR. Both team members approve contract changes.

## Licence

MIT. By contributing you agree to those terms.
