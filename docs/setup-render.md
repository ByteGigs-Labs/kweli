# Render Setup (task M-03)

Render hosts Kweli's API, database and (from Day 1) the web app. The `render.yaml` Blueprint in this repo describes everything.

## 1. Account
1. Go to https://render.com → **Get Started** → **Sign up with GitHub** (use the account that's in ByteGigs-Labs).
2. Check the hackathon's Devpost **Resources** and **Updates** pages for a Render credit code, and redeem it under **Workspace → Billing**.

## 2. Give Render access to the repo
1. In Render, **New → Blueprint**.
2. If `kweli` isn't listed, click **Configure GitHub** → choose **ByteGigs-Labs** → add **kweli** to the repositories Render can see → Save.

## 3. Create the services from the Blueprint
1. **New → Blueprint** → select `ByteGigs-Labs/kweli` → branch `main`.
2. Render reads `render.yaml` and shows **kweli-api** (web service), **kweli-web** (static site) and **kweli-db** (Postgres).
3. Fill in the secret values it asks for:

| Key | Value |
|---|---|
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | From the sandbox app |
| `PAYPAL_WEBHOOK_ID` | Leave empty for now, and add it after registering the webhook |
| `ANTHROPIC_API_KEY` | Your key (needed from Day 2) |
| `VAULT_MASTER_KEY` | `python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"` |
| `DEMO_USER_PASSWORD` | A password of 10+ characters for the demo login (share it with judges in the Devpost text) |

4. Click **Apply**. The first build takes a few minutes.

## 4. Create the demo login and check it
1. `kweli-api` → **Shell** → run `python -m scripts.seed`.
2. Open `https://kweli-api.onrender.com/health` and expect `{"status":"ok"}`.
3. Open `https://kweli-web.onrender.com`, sign in with the demo login, and check that the proof ledger loads.

The web app reaches the API through a rewrite (`/v1/*` → `kweli-api`), so the browser only ever talks to `kweli-web` and the session cookie stays first-party. If Render gives either service a different URL, update the rewrite destination in `render.yaml`, the `CORS_ORIGINS` value and `docs/webhooks.md`.

## 5. Things to know
- **Free web services sleep** after about 15 minutes idle, and the first request then takes up to a minute. **Before submitting on 12 Nov, move `kweli-api` to a paid instance** so judges don't hit a cold start.
- **Free Postgres expires** after a limited time. Judging runs to **21 Dec 2026**, so upgrade the database (or use credits) before submitting. Check Render's current free-tier limits.
- Region is **Frankfurt**, the closest Render region to Kenya.
- Every push to `main` redeploys automatically (`autoDeploy: true`).
- Never put secrets in `render.yaml`. Only keys marked `sync: false`, with values entered in the dashboard.
