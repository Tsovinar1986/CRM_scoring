# AI Lead Generation & Scoring Agent (B2B)

An agent pipeline that takes B2B accounts from multiple sources, enriches them with
firmographic and behavioral signals, scores them using a hybrid rule-based + LLM
model, and acts on the top-ranked accounts (CRM sync, alerts). Scoring evaluates
company/account attributes only — never a named individual — and the product
does not draft or send outreach of any kind.

## Running it

`./run.sh` (or `run.bat` on Windows) starts backend + frontend as two dev
servers with hot reload; `./run-prod.sh` (`run-prod.bat`) builds the
frontend once and runs a single merged process on one port — see the root
[README.md](README.md#running-it-two-modes) for both, and how to tell it's
actually working versus just "a server started."

```
# backend (from repo root)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn app.main:app --reload --port 8081

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5000, upload `backend/data/sample_leads.csv` (or your
own CRM export), and the ranked/scored leads appear immediately — no API
keys required. Enrichment (Apollo), CRM push (Salesforce), and Slack
alerts each auto-detect their credentials at startup: with none set they run
on deterministic mock data/logging by default; drop real keys into a `.env`
(see `.env.example`) and the exact same code path calls the live APIs
instead — no code changes needed either way, and a failed live call falls
back to the mock for that lead rather than breaking the run.

## Pipeline

**1. Ingestion**
- Bulk lead import from CRM exports (CSV/XLSX).
- Live pull from Salesforce via API for existing pipeline records.
- Company/domain lists submitted directly for cold enrichment.

**2. Enrichment**
- Third-party firmographic APIs (Apollo-style: company size, industry, revenue,
  tech stack, contact/title data).
- Company website scraping for signals not available via API (careers page
  activity/hiring signal, product pages, tech stack fingerprinting, about-page
  positioning).
- Results normalized into a single `EnrichedLead` record (pydantic model).

**3. Scoring (hybrid)**
- **Rule-based layer:** weighted scoring across configurable firmographic fit
  criteria — industry match, company size band, revenue band, tech stack
  match, geography, and a hiring signal. All company-level attributes;
  nothing here evaluates the contact as an individual. Produces a
  transparent numeric `fit_score` (0–100) with a per-criterion breakdown.
- **LLM layer:** Claude reads the enriched account profile (company
  attributes only — no contact name or title in the prompt) + rule-based
  breakdown and produces a qualitative assessment — an `account_fit_score`
  rating and a short rationale, catching context the rules can't (e.g.
  recent funding news, hiring surges, competitor mentions).
- Final `combined_score` blends both layers; accounts are ranked and
  bucketed (Hot / Warm / Cold).

**4. Output / Actions**
- **Ranked report:** Streamlit dashboard + CSV export of all scored accounts,
  sortable/filterable by score, bucket, industry, source.
- **CRM push:** scores, bucket, and rationale get written back to Salesforce
  as custom fields/tasks so sales has full context in-platform.
- **Alerts:** Slack (and/or email) notification the moment an account crosses
  the "Hot" threshold, so sales can act while the signal is fresh.

## Required configuration (`.env`)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | LLM scoring layer |
| `APOLLO_API_KEY` (or chosen enrichment provider) | Firmographic/contact enrichment |
| `SALESFORCE_*` | CRM read/write |
| `SLACK_BOT_TOKEN` + channel ID | Hot-lead alerts |
| `SMTP_*` (optional) | Email alerts if Slack isn't used |

## Scheduling

APScheduler drives recurring runs (e.g. nightly re-enrichment of active
pipeline, hourly scoring pass on newly added leads) so the dashboard stays
current without manual re-triggering.

## Architecture

- **backend/** — FastAPI app (`app/main.py`). Ingestion (`services/ingestion.py`),
  enrichment (`services/enrichment.py`, Apollo with mock fallback), hybrid
  scoring (`services/scoring.py`), and CRM/Slack integrations
  (`services/crm.py`, `services/alerts.py`) are
  each isolated behind a single function that auto-switches between the live
  API and a mock based on which keys are present in `.env`. Leads/alerts
  persist to SQLite (`storage.py`, path set by `DATABASE_PATH`), scoped by
  tenant (`auth.py`) — a request with no `Authorization` header uses a
  default tenant (zero-config, the common single-buyer case); a seller
  running one shared instance for multiple customers provisions each one a
  real tenant + API key (`scripts/create_tenant.py`) with fully isolated
  data. `backend/tests/` has the pytest suite (`pytest -q` from `backend/`).
- **frontend/** — React + Vite + TypeScript SPA. Upload panel, a ranked/
  filterable leads table, a detail drawer (firmographics, score breakdown,
  LLM rationale, CRM push button), a live
  Slack-alerts panel, a license/billing banner, and a small workspace
  switcher (top-right) for pasting a tenant API key — invisible/unused for
  a single self-hosted buyer, since no key means the default tenant.
  `npm test` runs the Vitest suite.
- **`.github/workflows/ci.yml`** — runs both suites (and the frontend build)
  on every push/PR.

## Selling this

- **`licensing/`** — checkout through Paying (Armenian card/Idram payments) + an offline-verifiable Ed25519 license
  key, for selling this app directly as self-hosted software from your own
  site (`licensing/README.md`, which also has the go-to-market sequencing:
  direct sale → RapidAPI → Salesforce AppExchange →
  AWS Marketplace/AppSumo, roughly cheapest/fastest to most involved).

## Not in scope (v1)

- Training a custom ML conversion-prediction model (would need labeled
  historical won/lost data — can be added later as a third scoring layer).
- Outbound sending automation (drafts are generated for human review/send,
  not auto-sent, to avoid compliance/spam risk).
