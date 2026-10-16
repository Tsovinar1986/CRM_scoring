# Selling this as a self-hosted product

The seller storefront sells Pro and Advanced as subscriptions through
Paying, our self-hosted payment service on Armenian providers (ArCa cards
via an Armenian bank, Ameriabank, Idram). Each plan is billed monthly or
annually. Starter is free and has no price.

After checkout the backend confirms the payment with Paying, signs an
Ed25519 license key, logs it for idempotency, emails it to the buyer and
shows it on screen. Every renewal issues and emails a fresh key. Each key
stays valid a little past the next billing date, so a cancelled
subscription simply stops receiving new keys.

## Setup

1. Generate the signing keypair once:

   ```sh
   python licensing/generate_keypair.py
   ```

   Keep `LICENSE_PRIVATE_KEY` only on the seller deployment. Ship the
   corresponding `LICENSE_PUBLIC_KEY` with buyer deployments.

2. Run the Paying server (see its own README) and register this app on it,
   with the webhook URL. The URL must be public HTTPS:

   ```sh
   python -m paying.cli create-app "CRM Scoring" \
       --webhook https://<your-backend>/api/billing/webhook
   ```

   Set `PAYING_URL` to the Paying server's address, and set the printed
   secret key and webhook secret as `PAYING_SECRET_KEY` and
   `PAYING_WEBHOOK_SECRET`. A sandbox server issues `sk_test_...` keys;
   a live one issues `sk_live_...` keys.

3. Nothing to create by hand: each checkout sends the amount from
   `PRICE_*` and `BILLING_CURRENCY`. Which currencies the card gateways
   accept depends on your bank agreement (AMD always works).

4. Configure SendGrid or SMTP so keys are delivered automatically. Without
   email settings, keys are still appended to
   `licensing/issued_licenses.jsonl` for you to send by hand.

5. Test a full purchase against a sandbox Paying server. Its test bank
   has Pay and Decline buttons. Then point `PAYING_URL` and the keys at
   the live Paying server.

## How checkout works

Both the app (React frontend) and the storefront (`docs/index.html`) send
the buyer to Paying's checkout page:

1. `POST /api/billing/checkout` creates a checkout session for the chosen
   plan and returns the payment page URL. From inside a hosted workspace,
   the session remembers that workspace.
2. After paying, the buyer comes back: to the app as
   `/?checkout=<session id>`, or to the storefront's
   `thank-you.html?session_id=<session id>`. That page calls
   `GET /api/billing/session/<id>`, which confirms the payment, upgrades
   the workspace (hosted) and returns the key.
3. **Webhook** (`POST /api/billing/webhook`): `payment.succeeded` for
   every renewal, `subscription.updated` / `subscription.canceled` for
   cancellations, and a fallback if the buyer never made it back from
   checkout. `subscription.past_due` carries a pay link for the customer.

Each billing period is keyed on the subscription id plus the period's end
date. The buyer's return and the first payment's webhook therefore share a
period and issue only one key.

## License validity

Keys last `LICENSE_VALIDITY_DAYS_MONTHLY` (default 35) or
`LICENSE_VALIDITY_DAYS_ANNUAL` (default 380) days. That covers one billing
period plus Paying's past-due grace period (7 days by default).
