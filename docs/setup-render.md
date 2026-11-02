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
2. Render reads `render.yaml` and shows **kweli-api** (web service) and **kweli-db** (Postgres).
3. Fill in the secret values it asks for:

| Key | Value |
|---|---|
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | From the sandbox app |
| `PAYPAL_WEBHOOK_ID` | Leave empty for now, and add it after registering the webhook |
| `ANTHROPIC_API_KEY` | Your key (needed from Day 2) |
| `VAULT_MASTER_KEY` | `python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"` |
| `CORS_ORIGINS` | `["https://kweli-web.onrender.com"]` (set it now, even before the web app exists) |

4. Click **Apply**. The first build takes a few minutes.

## 4. Check it
Open `https://kweli-api.onrender.com/health` and expect `{"status":"ok"}`. If Render added a suffix to the name, use the URL it shows, and update `docs/webhooks.md` and `CORS_ORIGINS`.

## 5. Things to know
- **Free web services sleep** after about 15 minutes idle, and the first request then takes up to a minute. **Before submitting on 12 Nov, move `kweli-api` to a paid instance** so judges don't hit a cold start.
- **Free Postgres expires** after a limited time. Judging runs to **21 Dec 2026**, so upgrade the database (or use credits) before submitting. Check Render's current free-tier limits.
- Region is **Frankfurt**, the closest Render region to Kenya.
- Every push to `main` redeploys automatically (`autoDeploy: true`).
- Never put secrets in `render.yaml`. Only keys marked `sync: false`, with values entered in the dashboard.
