import os

from dotenv import load_dotenv

load_dotenv()

# SQLite file leads/alerts persist to, relative to the backend/ working
# directory by default. Fine for one self-hosted buyer's data; a seller
# running one shared multi-tenant instance (see storage.py's docstring)
# should set DATABASE_URL below instead, for real concurrent write support.
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/app.db")
# Optional: a postgres:// or postgresql:// connection string. When set,
# db.py connects to that Postgres instance instead of the SQLite file above
# -- DATABASE_PATH is then ignored entirely. Leave unset for the zero-config
# SQLite default this app has always used; requires the optional psycopg2
# dependency (see requirements.txt) only when actually set.
DATABASE_URL = os.getenv("DATABASE_URL", "")

# "text" (human-readable, for local dev) or "json" (one JSON object per line
# on stdout, for log aggregators like CloudWatch/Datadog/Loki when this runs
# in a container).
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

SALESFORCE_USERNAME = os.getenv("SALESFORCE_USERNAME", "")
SALESFORCE_PASSWORD = os.getenv("SALESFORCE_PASSWORD", "")
SALESFORCE_SECURITY_TOKEN = os.getenv("SALESFORCE_SECURITY_TOKEN", "")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")

# Comma-separated list of frontend origins allowed to call this API. Defaults
# to the local Vite dev server; a production deploy must set this to its
# real frontend origin(s) or the browser will block every request with CORS.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5000").split(",")
    if origin.strip()
]

# --- Transport/network security (app/middleware.py, app/main.py) ---
# Redirects plain HTTP to HTTPS at the app level. Leave false for local dev
# (no TLS cert to redirect to) and for deployments where a proxy already
# handles this (Render does). Turn on only for a self-hosted deployment
# that terminates its own TLS with no proxy in front doing the redirect.
FORCE_HTTPS = os.getenv("FORCE_HTTPS", "false").lower() == "true"
# Trusts X-Forwarded-For/X-Forwarded-Proto from the immediate connecting
# peer -- required for rate limiting and HTTPS-detection to see the real
# client IP/scheme when running behind a reverse proxy (Render, nginx,
# Caddy...), since otherwise every request appears to come from the proxy
# itself. Only enable this when you control what's in front of this
# process -- an internet-facing uvicorn with this on lets any client spoof
# their own IP/scheme via those headers, defeating rate limiting entirely.
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"

# --- Rate limiting (app/middleware.py) ---
# slowapi/limits syntax: "<count>/<second|minute|hour|day>".
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
# Tighter limit for the expensive parse+enrich+score endpoints.
RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "10/minute")
# Tighter still for signup/login/forgot-password (routers/accounts.py) --
# these are classic brute-force/enumeration/spam targets.
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "5/minute")

# --- Upload limits (routers/leads.py, routers/churn.py) ---
# Rejected before parsing -- bounds worst-case memory/CPU from one upload,
# independent of the trial row cap below (which only applies unlicensed).
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "50000"))

# --- Self-serve tenant signup (routers/accounts.py) ---
# Used to build the link in a password-reset email -- must be wherever the
# frontend actually runs (the Vite dev server locally, the real domain in
# production), not the backend's own origin.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")
PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))

# --- Licensing (buyer side) ---
# A signed key issued after purchase (see licensing/issue_license.py). Set by
# whoever self-hosts this app. Verified offline against LICENSE_PUBLIC_KEY --
# no phone-home required.
LICENSE_KEY = os.getenv("LICENSE_KEY", "")
# The seller's Ed25519 public key (base64), baked in at ship time so a buyer's
# instance can verify a license without contacting anything. Safe to commit;
# it can only verify signatures, not create them.
LICENSE_PUBLIC_KEY = os.getenv("LICENSE_PUBLIC_KEY", "")
# When true, the default tenant's upload endpoint 402s immediately without a
# valid Pro/Advanced LICENSE_KEY -- disables the free Starter tier entirely
# for deployments that want to require purchase upfront. Leave false
# (default) so a fresh deployment gets Starter's permanent free allowance
# below. Only ever applies to the default tenant (see routers/leads.py) -- a
# self-serve tenant signed up via routers/accounts.py is a customer of
# whoever runs this deployment, not a buyer of the software itself, so it's
# never gated by this deployment's own license.
LICENSE_REQUIRED = os.getenv("LICENSE_REQUIRED", "false").lower() == "true"
# For the seller's own public deployment (the one crmscoring.com's "Get
# started free" button opens). When true:
# - requests with no workspace key are refused (401) instead of landing in
#   the shared default workspace, which runs on the seller's own license --
#   so visitors can neither see each other's leads nor use that license;
# - POST /api/accounts/trial hands every visitor a private Starter workspace
#   with its own TRIAL_MAX_UPLOADS/TRIAL_MAX_LEADS_PER_UPLOAD allowance;
# - self-serve signups start on Starter too, and a workspace is upgraded by
#   subscribing from inside it (routers/billing.py).
# Leave false for a buyer's self-hosted install -- zero-config as before.
HOSTED_MODE = os.getenv("HOSTED_MODE", "false").lower() == "true"
# Per-IP limit on creating free trial workspaces (hosted mode only) -- each
# one comes with a fresh upload allowance, and every scored lead costs an
# LLM call.
RATE_LIMIT_TRIAL = os.getenv("RATE_LIMIT_TRIAL", "3/hour")
# How many total /api/leads/upload calls the free Starter tier (no
# Pro/Advanced LICENSE_KEY) gets before it starts 402ing -- Starter has no
# time limit, only this lifetime cap; buying Pro or Advanced removes it
# entirely. The counter persists in the same SQLite file as everything else
# (storage.increment_trial_uploads), so it survives restarts and can't be
# reset by just restarting the process.
TRIAL_MAX_UPLOADS = int(os.getenv("TRIAL_MAX_UPLOADS", "10"))
# Caps each /api/leads/upload call to at most this many rows on the Starter
# tier (whether or not TRIAL_MAX_UPLOADS is exhausted) -- lets a prospect
# judge scoring quality on a real sample of their own data without getting
# full free use of a large list. Pro/Advanced have no cap.
TRIAL_MAX_LEADS_PER_UPLOAD = int(os.getenv("TRIAL_MAX_LEADS_PER_UPLOAD", "10"))

# --- Licensing (seller side) ---
# Only used by routers/billing.py, which the seller runs on their own
# storefront deployment -- buyers' self-hosted instances never need these.
# Stripe subscriptions: Pro and Advanced each bill monthly or annually;
# Starter is free and has none. Every paid period issues a fresh expiring
# license key. See licensing/README.md for setup.
LICENSE_PRIVATE_KEY = os.getenv("LICENSE_PRIVATE_KEY", "")
# sk_test_... (test mode, no real charges) or sk_live_... from the Stripe
# Dashboard -> Developers -> API keys; the publishable key isn't needed,
# buyers pay on Stripe's own checkout page. Keep it in .env / the host's secrets.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
# whsec_... of the endpoint https://<backend>/api/billing/stripe/webhook
# (Dashboard -> Developers -> Webhooks); renewals and cancellations need it.
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
# PayPal subscriptions, offered next to card checkout: the REST app's
# client id and secret (developer.paypal.com -> Apps & Credentials), "live"
# or "sandbox", and the id of the webhook pointing at
# https://<backend>/api/billing/paypal/webhook (renewals and cancellations).
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "live").strip().lower()
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")
# Prices are decimal amounts in BILLING_CURRENCY. The matching Stripe price
# is created on the first sale of each plan (found again by a lookup key that
# includes the amount), so changing an amount only affects new subscriptions.
# Advanced is functionally identical to Pro today, priced higher for
# agency/multi-client framing.
BILLING_CURRENCY = os.getenv("BILLING_CURRENCY", "USD")
PRICE_PRO_MONTHLY = os.getenv("PRICE_PRO_MONTHLY", "20.00")
PRICE_PRO_ANNUAL = os.getenv("PRICE_PRO_ANNUAL", "192.00")
PRICE_ADVANCED_MONTHLY = os.getenv("PRICE_ADVANCED_MONTHLY", "40.00")
PRICE_ADVANCED_ANNUAL = os.getenv("PRICE_ADVANCED_ANNUAL", "384.00")
# Public marketing site (docs/) -- buyers who subscribe there land on its
# thank-you.html after paying and on its pricing section if they cancel.
STOREFRONT_URL = os.getenv("STOREFRONT_URL", "https://crmscoring.com")
# Licenses are issued with an expiry this many days out, not a perpetual
# one -- an already-issued offline key can't be revoked, so this bounds
# how long a cancelled subscriber keeps working. Every renewal issues a
# fresh key, so the windows only need to run a little past one billing
# period (to allow for Stripe's payment retries).
LICENSE_VALIDITY_DAYS_MONTHLY = int(os.getenv("LICENSE_VALIDITY_DAYS_MONTHLY", "35"))
LICENSE_VALIDITY_DAYS_ANNUAL = int(os.getenv("LICENSE_VALIDITY_DAYS_ANNUAL", "380"))

# --- Polar (seller side, alternative to Paddle) ---
# Polar is also a merchant-of-record, added alongside Paddle (not instead of
# it) specifically for sellers Paddle can't serve either -- Polar pays out
# via Stripe Connect Express, whose supported *recipient* countries are
# broader than the countries Stripe itself supports for a direct merchant
# account (confirmed: Armenia is a supported Polar/Connect payout country
# even though it isn't a Stripe merchant country). See licensing/README.md.
# Polar models each plan as its own Product (rather than one product with
# multiple Prices, as Paddle does) -- two Product ids here, one per plan.

# --- Email delivery (seller side) ---
# Sends issued license keys to buyers automatically. Without either of these
# set, keys are still issued and logged/appended to
# licensing/issued_licenses.jsonl -- just not emailed, so send them by hand.
# SendGrid is tried first if configured (better deliverability/analytics at
# scale); SMTP is the zero-third-party-account fallback.
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")

# Ideal Customer Profile used by the rule-based scorer. Edit to match the
# business this instance is generating leads for. Deliberately scoped to
# company/account attributes only -- nothing here profiles the named
# contact as an individual (see backend/app/services/scoring.py).
ICP = {
    "target_industries": ["SaaS", "Fintech", "Healthcare Tech", "E-commerce"],
    "employee_range": (50, 1500),
    "revenue_range_usd": (5_000_000, 250_000_000),
    "target_tech_stack": ["Salesforce", "HubSpot", "AWS", "Snowflake", "Stripe"],
    "target_geographies": ["United States", "Canada", "United Kingdom"],
}

# Rule-based scoring weights, must sum to 100.
SCORING_WEIGHTS = {
    "industry_match": 25,
    "company_size_fit": 25,
    "revenue_fit": 15,
    "tech_stack_match": 15,
    "geography_fit": 10,
    "hiring_signal": 10,
}

# Blend of rule-based fit_score vs LLM account_fit_score into combined_score.
RULE_WEIGHT = 0.6
LLM_WEIGHT = 0.4

BUCKET_THRESHOLDS = {"hot": 75, "warm": 50}
