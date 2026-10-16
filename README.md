# AI Lead Generation & Scoring Agent

A B2B lead-scoring pipeline: upload a CRM export, get every account enriched
with firmographic/behavioral signals, scored by a hybrid rule-based + Claude
model, ranked into Hot/Warm/Cold, and (for the hot ones) a one-click CRM
push — all from one screen. Scoring is account/company-level only — the
product never evaluates a named individual and never drafts or sends any
outreach.

FastAPI backend, React + Vite + TypeScript frontend. Every third-party
integration (Claude, Apollo enrichment, Salesforce push, Slack
alerts) auto-detects its credentials: set the key and it makes the real
call, leave it unset and it runs on deterministic mock data — so the whole
thing works end to end with zero API keys for local eval, and flips to
live behavior with zero code changes once keys are added.

## Running it: two modes

**Dev mode** — backend and frontend as two separate servers with hot reload.
This is what you want while making changes.

```
./run.sh          # macOS/Linux — installs deps, starts both, Ctrl+C stops both
run.bat           # Windows    — same, opens two windows
```

or by hand:

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn app.main:app --reload --port 8081

# separate terminal
cd frontend && npm install && npm run dev
```

Open **http://localhost:5000** (the Vite dev server; it proxies `/api/*`
calls to the backend on :8081, see `frontend/vite.config.ts`).

**Merged/production mode** — one process, one port. This is what a
self-hosted buyer actually runs: FastAPI builds+serves the frontend itself
(`backend/app/main.py`'s `FRONTEND_DIST` handling), so there's no separate
frontend server at all.

```
./run-prod.sh      # macOS/Linux
run-prod.bat       # Windows
```

Open **http://localhost:8081** — same origin serves both the UI and the API.

**Docker** — same merged mode, containerized:

```
docker build -t ai-lead-scoring .
docker run --rm -p 8081:8081 --env-file .env -v $(pwd)/backend/data:/app/backend/data ai-lead-scoring
```

The volume mount matters: `backend/data/app.db` is where leads/alerts/trial
state persist, and without mounting it a removed container loses everything
(including the trial clock, which would otherwise just restart itself, one
free trial per container recreation).

**How to tell it's actually working**: hit `/api/health` (`{"status":"ok"}`)
directly, then in the browser upload `backend/data/sample_leads.csv` and
confirm ranked leads + Slack-alert cards appear — that exercises the full
upload → enrich → score → store round trip, not just that a server is up.
Leads/alerts persist to a local SQLite file (`DATABASE_PATH`, default
`backend/data/app.db`) so they survive a restart in either mode.

## What's in here

- **`backend/`** — FastAPI app: ingestion, enrichment, hybrid scoring,
  CRM push, Slack alerts, Stripe-based licensing, and self-serve
  tenant signup/login (`routers/accounts.py` — an alternative to running
  `scripts/create_tenant.py` by hand).
- **`frontend/`** — React SPA: upload panel, ranked/filterable leads table,
  a detail drawer (firmographics, score breakdown, LLM rationale, CRM
  push), and a license/billing banner. `TenantSwitcher` handles
  signup/login/forgot-password for a shared multi-tenant deployment.
- **`licensing/`** — Stripe checkout + an offline-verifiable Ed25519 license
  key, for selling this app directly as self-hosted software.

See **[DESCRIPTION.md](DESCRIPTION.md)** for the full pipeline architecture
and scoring model, and **[licensing/README.md](licensing/README.md)** for
the go-to-market sequencing across sale channels.

## Testing

```
pip install -r requirements-dev.txt
cd backend && pytest -q

cd frontend && npm test        # Vitest
npm run build                  # tsc + production build
```

`.github/workflows/ci.yml` runs both suites plus the frontend build on every
push/PR.

## Deploying

The `Dockerfile` in this repo builds the merged/production image (see
"Running it" above) — point whatever host you use at it. `DATABASE_URL`
lets that host's database be Postgres instead of the zero-config SQLite
default; see `.env.example`.

## Configuration

Copy `.env.example` to `.env` (and `frontend/.env.example` to
`frontend/.env` if the backend isn't on `localhost:8081`) and fill in
whichever keys are available. Every integration degrades gracefully without
one — see `.env.example` for what each variable unlocks.

## Security

- **Response headers** (`app/middleware.py`'s `SecurityHeadersMiddleware`):
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, a `Content-Security-Policy` that allows only the app's own
  origin (checkout happens on Stripe's page, so nothing third-party loads), and `Strict-Transport-Security` (only
  sent once a request is actually HTTPS). No Node "helmet" package here
  since this is a FastAPI backend — same idea, hand-rolled.
- **HTTPS**: `FORCE_HTTPS=true` redirects HTTP→HTTPS at the app level for a
  self-hosted deployment with no proxy in front doing it; Render (and most
  managed hosts) already handles this, so it's off by default.
- **CORS**: locked to `CORS_ALLOWED_ORIGINS`, `GET`/`POST` only (the only
  methods this API has), and a specific header allow-list — not wildcarded.
- **Rate limiting** (`slowapi`): a global default plus a tighter limit on
  the upload/CRM-push endpoints (`RATE_LIMIT_DEFAULT`/
  `RATE_LIMIT_UPLOAD` in `.env.example`). Set `TRUST_PROXY_HEADERS=true`
  only when this genuinely runs behind a trusted reverse proxy (Render
  does) — otherwise a client could spoof its own IP via `X-Forwarded-For`
  and dodge the limit entirely.
- **Input validation**: file uploads are capped by size and row count
  (`MAX_UPLOAD_SIZE_MB`/`MAX_UPLOAD_ROWS`) and restricted to `.csv`/`.xlsx`/
  `.xls` before parsing; request bodies use `Literal` types instead of bare
  `str` wherever only a fixed set of values makes sense (billing interval,
  CRM target); lead/customer text fields have length caps
  and numeric fields reject negatives.
- **SQL**: every query in `storage.py` uses `?` placeholders — no
  string-built queries anywhere, so nothing from an upload or an API
  request is ever interpolated into SQL. `tests/test_storage.py` proves
  this with real injection payloads (`'; DROP TABLE leads; --`, `' OR
  '1'='1`) through every field that flows into a query — tenant ID, lead
  ID, domain, API key — confirming each is treated as inert data, not
  executed or able to cross a tenant boundary.
- **Passwords** (self-serve signup, `services/password.py`): PBKDF2-HMAC-
  SHA256 with a random salt per user and 600,000 iterations (OWASP's 2023
  minimum), not a fast general-purpose hash — stdlib `hashlib` only, no
  bcrypt/argon2/passlib dependency for something this size. Signup/login/
  reset enforce 8+ characters with a letter, a number, and a symbol
  (`RATE_LIMIT_AUTH` in `.env.example` throttles all three against
  brute-forcing). Login can't recover a lost key (only its hash is ever
  stored) — it issues a fresh one instead, invalidating whichever was
  active before.
