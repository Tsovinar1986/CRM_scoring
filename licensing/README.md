# Selling this as a self-hosted product

The seller storefront sells Pro and Advanced as Stripe subscriptions, each
billed monthly or annually by card. Starter is free and has no price.

After checkout the backend confirms the payment with Stripe, signs an
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

2. Get your Stripe secret key (Dashboard -> Developers -> API keys) and set
   `STRIPE_SECRET_KEY`. Start with the test-mode key (`sk_test_...`). The
   publishable key isn't needed: buyers pay on Stripe's own checkout page.

3. Nothing to create by hand: the first checkout for each plan creates its
   Stripe price from `PRICE_*` and `BILLING_CURRENCY` (lookup keys like
   `crm-scoring-pro-monthly-2000-usd`) and later checkouts reuse it.

4. Add the webhook. It's needed so renewals issue fresh keys and
   cancellations reach hosted workspaces. In the Dashboard, go to
   Developers -> Webhooks -> Add endpoint:
   - URL: `https://<your-backend>/api/billing/stripe/webhook`. It must be
     public HTTPS; `localhost` won't work (use `stripe listen --forward-to
     localhost:8081/api/billing/stripe/webhook` to test locally).
   - Events: `checkout.session.completed`, `invoice.paid`,
     `customer.subscription.updated`, `customer.subscription.deleted`.
   - Copy its signing secret into `STRIPE_WEBHOOK_SECRET`.

5. Configure SendGrid or SMTP so keys are delivered automatically. Without
   email settings, keys are still appended to
   `licensing/issued_licenses.jsonl` for you to send by hand.

6. Test a full purchase in test mode with card `4242 4242 4242 4242`, any
   future expiry and any CVC. Then repeat steps 2 and 4 with your live key
   and a live-mode webhook. Test and live mode have separate keys, prices
   and webhooks.

## How checkout works

Both the app (React frontend) and the storefront (`docs/index.html`) send
the buyer to Stripe Checkout:

1. `POST /api/billing/stripe/checkout` creates a Checkout Session for the
   chosen plan and returns Stripe's payment page URL. From inside a hosted
   workspace, the session remembers that workspace.
2. After paying, Stripe sends the buyer back: to the app as
   `/?checkout=<session id>`, or to the storefront's
   `thank-you.html?session_id=<session id>`. That page calls
   `GET /api/billing/stripe/session/<id>`, which confirms the payment,
   upgrades the workspace (hosted) and returns the key.
3. **Webhook**: every renewal, cancellations, plus a fallback if the buyer
   never made it back from checkout.

Each billing period is keyed on the subscription id plus the period's end
date. The buyer's return and the first invoice's webhook therefore share a
period and issue only one key.

## License validity

Keys last `LICENSE_VALIDITY_DAYS_MONTHLY` (default 35) or
`LICENSE_VALIDITY_DAYS_ANNUAL` (default 380) days. That covers one billing
period plus time for Stripe's payment retries.
