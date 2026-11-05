# Demo video: 1 minute

**Rules:** under the time limit, public on YouTube, shows the app working, no copyrighted music (use silence or a royalty-free track). Record the **deployed** app on the PayPal **sandbox**, at 1440×900, with the browser zoom at 100%.

## Script (about 140 words of voice-over)

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:07 | Headline: "PayPal freezes Kenyan freelancers' accounts" (Business Daily, June 2026). Cut to the Kweli sign-in page | "In June, Kenyan freelancers had their PayPal balances frozen. They'd done nothing wrong. They just couldn't prove it." |
| 0:07–0:19 | **Agreements → New**: paste the WhatsApp chat → **Fill in from conversation** → send → the client accepts on a phone. **Assistant**: "Invoice Nairobi Eats for the menu, due in a week" → approval card → **Approve** | "Kweli turns a chat into an agreement the client accepts, and the assistant prepares the PayPal invoice. Nothing is sent until I approve it." |
| 0:19–0:31 | **Overview**: score 88, Fix next. Click **Fix this payment** on Bloom Studio → **Upload delivered work** → back to Overview: the score goes up | "Every payment is checked against seven proof rules, and Kweli tells me exactly what to fix, in order." |
| 0:31–0:43 | **Compliance packs → Build the pack** → the letter with its citations → **Edit**, type a wrong total → **blocked** → **Download PDF** | "When PayPal asks what a payment was for, one click builds the pack. The AI drafts the letter, and a validator blocks any citation or amount that isn't on file." |
| 0:43–0:54 | **Disputes**: "Work not received" → evidence ready → **Prepare the response** → **Approve and send** → Sandbox tools → **Decide in my favour** → "Decided in your favour" | "A dispute? The evidence is already there. I approve, it goes to PayPal, and we win." |
| 0:54–1:00 | **Billing**: Kweli Pro, USD 9 a month, through PayPal Subscriptions. Logo and URL | "Rules decide, AI drafts, people approve. Kweli: proof for every payment." |

## Before you press record
1. The deploy passes `python -m scripts.smoke https://kweli-web.onrender.com` (see [setup-render.md](setup-render.md)).
2. **Reset the demo data** so the score is 88 and Bloom's work is missing: `kweli-api` → **Shell** → `python -m scripts.reset_demo`. It only touches the demo account.
3. **Prepare the dispute in advance:** pay an invoice from the sandbox Personal account and open a "didn't receive" dispute from its Resolution Center, so it's waiting when you record. The seeded demo dispute shows the screens, but it's refused at the send step.
4. Have the WhatsApp text ready to paste (below), and the client acceptance link open on a phone or a narrow browser window.
5. `ANTHROPIC_API_KEY` is set, so the agreement, letter and assistant are the real model. Without a key, the letter and dispute response use Kweli's standard text, and the assistant says it isn't set up.
6. Close other tabs and notifications. Record in 1440×900, then cut to 60 seconds.

**Thread to paste**
> Wanjiru (Kilele Tours, info@kileletours.com): Hi Amina! We loved last year's brochure. Could you do a 2nd edition for 2027? 12 pages, same photos, print PDF + a web version for email. Deadline 30 Nov.
> Amina: Happy to! USD 650 for the full thing.
> Wanjiru: Perfect, let's do it.

## If you extend it later (up to 3 minutes)
Add the third-party payer fix (P3 warning → upload the client's confirmation → pass), the ledger's By client view and CSV export (AG Grid), and the Billing upgrade on PayPal's approve page.
