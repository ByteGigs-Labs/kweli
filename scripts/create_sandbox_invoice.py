"""Create (and optionally send) a PayPal SANDBOX invoice. Proves the Invoicing setup works.

Usage:
  python -m scripts.create_sandbox_invoice --to client@example.com --amount 10.00
  python -m scripts.create_sandbox_invoice --to client@example.com --amount 10.00 --send
"""

import argparse
import sys
from datetime import date, timedelta

from api.config import get_settings
from paypal.client import PayPalClient
from paypal.errors import PayPalError
from paypal.invoicing import InvoiceDraft, Invoicing, payer_view_url
from paypal.money import from_paypal_value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", required=True, help="sandbox client (Personal) account email")
    parser.add_argument("--name", default="Sandbox Client", help="client business name")
    parser.add_argument("--amount", required=True, help="e.g. 10.00")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--item", default="Logo design (Kweli sandbox test)")
    parser.add_argument("--due-days", type=int, default=7)
    parser.add_argument("--send", action="store_true", help="email it to the client")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, client: PayPalClient | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = get_settings()
    if settings.paypal_env != "sandbox":
        print("Refusing to run against live. Set PAYPAL_ENV=sandbox.")
        return 1
    invoicing = Invoicing(client or PayPalClient(settings))
    try:
        number = invoicing.next_invoice_number()
        draft = InvoiceDraft(
            invoice_number=number,
            currency=args.currency.upper(),
            recipient_email=args.to,
            recipient_name=args.name,
            item_name=args.item,
            amount_minor=from_paypal_value(args.amount, args.currency),
            due_date=date.today() + timedelta(days=args.due_days),
            note="Test invoice created by Kweli in the PayPal sandbox.",
        )
        invoice = invoicing.create_draft(draft)
        print(f"Draft created: {invoice['id']} (number {number}, status {invoice.get('status')})")
        if args.send:
            sent = invoicing.send(invoice["id"])
            url = payer_view_url(sent) or "(no payer link returned)"
            print(f"Sent to {args.to}. Payer link: {url}")
    except PayPalError as error:
        print(f"FAIL: {error}")
        for issue in error.issues:
            print(f"  - {issue}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
