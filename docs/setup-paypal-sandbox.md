# PayPal Sandbox Setup

The sandbox is PayPal's test environment: fake accounts and fake money, with the same APIs as live. **Kweli only ever uses the sandbox.**

## 0. Whose PayPal login opens the developer dashboard?
You sign in to developer.paypal.com with a normal PayPal login.
- If your PayPal account is **limited or closed**, try logging in anyway: the developer dashboard and the sandbox are separate from your live balance, and often still work.
- If it's blocked, **the teammate whose account is in good standing creates the developer account** and shares the sandbox credentials through a password manager (Bitwarden or 1Password). The sandbox *test accounts* in step 2 can be used by anyone who has their email and password.
- Don't open a new live PayPal account just to get around a permanent limitation. That can breach PayPal's User Agreement Kweli only needs the sandbox.

## 1. Sign in
1. Go to https://developer.paypal.com and click **Log in to Dashboard**.
2. Sign in with your PayPal account (or **Sign Up**, which creates a normal PayPal account).

## 2. Create the two test accounts
**Testing Tools → Sandbox Accounts → Create account:**

| Test account | Type | Country | Used as |
|---|---|---|---|
| `kweli-freelancer` | **Business** | **Kenya** (fall back to United States if Invoicing errors, see step 6) | The freelancer who sends invoices |
| `kweli-client` | **Personal** | United States or United Kingdom | The overseas client who pays |

Give the client account a balance (e.g. 5,000 USD). For each account, open **⋯ → View/Edit account** and note the generated email and password. You'll log in as them at https://www.sandbox.paypal.com.

## 3. Create the app
1. **Apps & Credentials** → make sure the toggle says **Sandbox** → **Create App**.
2. Name: `Kweli`. Type: **Merchant**. Sandbox account: **kweli-freelancer**.
3. Copy the **Client ID** and **Secret** into `.env`:
   ```
   PAYPAL_ENV=sandbox
   PAYPAL_CLIENT_ID=...
   PAYPAL_CLIENT_SECRET=...
   ```
   Never paste the secret in chat, an issue or a commit. CI runs gitleaks to catch mistakes.

## 4. Turn on the features Kweli uses
Open the app → **Features**, and tick:
- **Invoicing**
- **Disputes**
- **Transaction search**
- **Subscriptions**
- **Accept payments** (usually on by default)

Save.

## 5. Check it from the repo
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scripts.check_paypal
```
Expected: `OK: credentials accepted`, with every feature listed as `OK`. A `WARN` means that feature isn't ticked yet, or the change hasn't reached the token. Wait a minute and run it again. `--scopes` prints the full scope list.

## 6. Smoke-test Invoicing (2 minutes)
Log in to https://www.sandbox.paypal.com as **kweli-freelancer** → create and send a $10 invoice to the **kweli-client** email → log in as kweli-client → pay it.
If the Kenya business account can't invoice, create a **United States** Business account, link the app to it (or create a new app), and note it in the README. The story stays the same.

## 7. Webhook (after the Render deploy)
Follow `docs/webhooks.md`: register `https://kweli-api.onrender.com/v1/webhooks/paypal`, then copy the **Webhook ID** into `PAYPAL_WEBHOOK_ID` locally and in Render.
