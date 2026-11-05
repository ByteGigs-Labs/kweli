"""Check a deployed Kweli end to end, through the web app's URL as a browser would.

Usage: DEMO_USER_PASSWORD=... python -m scripts.smoke https://kweli-web.onrender.com
Prints one line per check and exits non-zero if any fails. It never prints the password.
"""

import os
import sys

import httpx

WEB_HEADERS = ("content-security-policy", "x-frame-options", "strict-transport-security")


def run(base: str, email: str, password: str, client: httpx.Client | None = None) -> list[str]:
    base = base.rstrip("/")
    http = client or httpx.Client(timeout=60, follow_redirects=True)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}{f'  ({detail})' if detail else ''}")
        if not ok:
            failures.append(name)

    page = http.get(f"{base}/")
    check("web app loads", page.status_code == 200 and '<div id="root">' in page.text)
    check(
        "web security headers",
        all(h in page.headers for h in WEB_HEADERS),
        ", ".join(h for h in WEB_HEADERS if h not in page.headers),
    )
    origin = {"Origin": base}
    login = http.post(
        f"{base}/v1/auth/login", json={"email": email, "password": password}, headers=origin
    )
    check("demo login through the rewrite", login.status_code == 200, str(login.status_code))
    cookie = login.headers.get("set-cookie", "").lower()
    check(
        "session cookie is Secure, HttpOnly, Strict",
        all(flag in cookie for flag in ("secure", "httponly", "samesite=strict")),
    )
    if login.status_code != 200:
        return failures
    readiness = http.get(f"{base}/v1/readiness")
    check(
        "readiness score",
        readiness.status_code == 200 and readiness.json().get("payments", 0) > 0,
        f"{readiness.json().get('score')} from {readiness.json().get('payments')} payments"
        if readiness.status_code == 200
        else str(readiness.status_code),
    )
    ledger = http.get(f"{base}/v1/ledger", params={"_end": 5})
    check("proof ledger", ledger.status_code == 200 and ledger.headers.get("x-total-count") != "0")
    billing = http.get(f"{base}/v1/billing")
    check(
        "billing switched on",
        billing.status_code == 200 and billing.json().get("enabled") is True,
        "set PAYPAL_PLAN_ID"
        if billing.status_code == 200 and not billing.json().get("enabled")
        else "",
    )
    disputes = http.get(f"{base}/v1/disputes")
    check("disputes", disputes.status_code == 200)
    refused = http.post(f"{base}/v1/auth/logout", headers={"Origin": "https://evil.test"})
    check("cross-site write refused", refused.status_code == 403)
    http.post(f"{base}/v1/auth/logout", headers=origin)
    return failures


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    password = os.environ.get("DEMO_USER_PASSWORD", "")
    email = os.environ.get("DEMO_USER_EMAIL", "amina@demo.kweli.test")
    if not password:
        print("Set DEMO_USER_PASSWORD.")
        return 2
    failures = run(argv[0], email, password)
    print(f"\n{'All checks passed.' if not failures else f'{len(failures)} check(s) failed.'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
