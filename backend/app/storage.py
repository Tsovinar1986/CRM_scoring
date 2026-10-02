"""SQLite- or PostgreSQL-backed store, so leads/alerts survive a restart.
SQLite is the zero-config default; set DATABASE_URL to a postgres(ql)://
URL to run against Postgres instead (see db.py, the only module that knows
about the difference between the two).

Multi-tenant: every lead/alert row carries a tenant_id, and every read/write
here takes one. Requests with no Authorization header (see auth.py) are
scoped to DEFAULT_TENANT_ID -- a sentinel, not a real provisioned tenant --
so a single self-hosted buyer gets the exact same zero-config behavior as
before this existed. A seller running one shared instance for multiple
customers provisions real tenants (backend/scripts/create_tenant.py) with
their own API key, and their data never overlaps with anyone else's.

Leads/alerts are stored as serialized JSON rows rather than a normalized
schema: the shape is defined by the pydantic models in models.py and
changes with them, and a JSON blob means storage.py never needs a migration
just because a field was added there.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass
from threading import Lock

from . import db as _db
from .models import Alert, ScoredLead

DEFAULT_TENANT_ID = "default"

_lock = Lock()


# Tenant plans. None is an unmetered workspace -- anything provisioned by
# scripts/create_tenant.py, or signed up while HOSTED_MODE is off. "starter"
# workspaces (hosted free trials and hosted signups) are capped like the
# free tier; "pro"/"advanced" are hosted workspaces with a live subscription.
STARTER_PLAN = "starter"


@dataclass
class Tenant:
    id: str
    name: str
    plan: str | None = None
    email: str | None = None
    # When a cancelled hosted subscription's paid period ends (epoch secs).
    plan_expires_at: float | None = None


# The few statements below genuinely differ between SQLite and Postgres
# (upsert syntax, autoincrement, schema introspection) -- everything else in
# this file is plain SQL that db.py's connection wrapper runs unchanged on
# either backend.
_LEADS_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS leads ("
    "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, domain TEXT NOT NULL, "
    + ("combined_score DOUBLE PRECISION NOT NULL, data TEXT NOT NULL)" if _db.IS_POSTGRES
       else "combined_score REAL NOT NULL, data TEXT NOT NULL)")
)
_ALERTS_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS alerts ("
    + ("seq SERIAL PRIMARY KEY, id TEXT NOT NULL, tenant_id TEXT NOT NULL, data TEXT NOT NULL)" if _db.IS_POSTGRES
       else "seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, tenant_id TEXT NOT NULL, data TEXT NOT NULL)")
)
_TENANTS_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS tenants ("
    "id TEXT PRIMARY KEY, name TEXT NOT NULL, api_key_hash TEXT NOT NULL UNIQUE, "
    + ("created_at DOUBLE PRECISION NOT NULL, email TEXT, password_hash TEXT)" if _db.IS_POSTGRES
       else "created_at REAL NOT NULL, email TEXT, password_hash TEXT)")
)
_PASSWORD_RESETS_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS password_resets ("
    "token_hash TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
    + ("expires_at DOUBLE PRECISION NOT NULL)" if _db.IS_POSTGRES else "expires_at REAL NOT NULL)")
)
_UPSERT_LEAD_SQL = (
    "INSERT INTO leads (id, tenant_id, domain, combined_score, data) VALUES (?, ?, ?, ?, ?) "
    "ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, domain = EXCLUDED.domain, "
    "combined_score = EXCLUDED.combined_score, data = EXCLUDED.data"
    if _db.IS_POSTGRES
    else "INSERT OR REPLACE INTO leads (id, tenant_id, domain, combined_score, data) VALUES (?, ?, ?, ?, ?)"
)
_INSERT_IGNORE_APP_META_SQL = (
    "INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING"
    if _db.IS_POSTGRES
    else "INSERT OR IGNORE INTO app_meta (key, value) VALUES (?, ?)"
)
_UPSERT_APP_META_SQL = (
    "INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    if _db.IS_POSTGRES
    else "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)"
)


def _existing_tenant_columns(conn) -> set[str]:
    if _db.IS_POSTGRES:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'tenants'"
        ).fetchall()
        return {row[0] for row in rows}
    rows = conn.execute("PRAGMA table_info(tenants)").fetchall()
    return {row[1] for row in rows}


def _connect():
    conn = _db.connect()
    conn.execute(_LEADS_TABLE_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_tenant ON leads (tenant_id)")
    conn.execute(_ALERTS_TABLE_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts (tenant_id)")
    conn.execute(_TENANTS_TABLE_DDL)
    # Migration for DBs created before self-serve signup existed -- CREATE
    # TABLE IF NOT EXISTS above only takes effect on a brand-new database.
    existing_cols = _existing_tenant_columns(conn)
    if "email" not in existing_cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN email TEXT")
    if "password_hash" not in existing_cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN password_hash TEXT")
    # Hosted-mode plan metering (see config.HOSTED_MODE); NULL plan =
    # unmetered, so every tenant that existed before this keeps working.
    if "plan" not in existing_cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN plan TEXT")
    if "uploads_used" not in existing_cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN uploads_used INTEGER NOT NULL DEFAULT 0")
    if "subscription_id" not in existing_cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN subscription_id TEXT")
    if "plan_expires_at" not in existing_cols:
        conn.execute(
            "ALTER TABLE tenants ADD COLUMN plan_expires_at "
            + ("DOUBLE PRECISION" if _db.IS_POSTGRES else "REAL")
        )
    # Partial index: enforces uniqueness among real emails while still
    # allowing unlimited NULLs, since scripts/create_tenant.py-provisioned
    # tenants have no email/login of their own. Supported the same way on
    # both SQLite and Postgres.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_email ON tenants (email) WHERE email IS NOT NULL"
    )
    conn.execute(_PASSWORD_RESETS_TABLE_DDL)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    return conn


_conn = _connect()


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_tenant(
    name: str, email: str | None = None, password_hash: str | None = None, plan: str | None = None
) -> tuple[Tenant, str]:
    """Provisions a new tenant with a fresh API key. The plaintext key is
    returned once, here, and never stored -- only its hash is. Give it to
    the customer immediately; there's no way to recover it later, only to
    provision a new one (or, for a self-serve tenant, log in again -- see
    rotate_api_key below).

    email/password_hash are set for a self-serve signup
    (routers/accounts.py); left None for the manual
    scripts/create_tenant.py flow, which has no login of its own. plan is
    STARTER_PLAN for hosted-mode trials/signups, None (unmetered) otherwise.
    """
    tenant_id = secrets.token_hex(8)
    api_key = secrets.token_urlsafe(32)
    with _lock, _conn:
        _conn.execute(
            "INSERT INTO tenants (id, name, api_key_hash, created_at, email, password_hash, plan) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, name, _hash_key(api_key), time.time(), email, password_hash, plan),
        )
    return Tenant(id=tenant_id, name=name, plan=plan, email=email), api_key


def get_tenant_by_api_key(api_key: str) -> Tenant | None:
    with _lock:
        row = _conn.execute(
            "SELECT id, name, plan, email, plan_expires_at FROM tenants WHERE api_key_hash = ?",
            (_hash_key(api_key),),
        ).fetchone()
    if row is None:
        return None
    plan, expires_at = row[2], row[4]
    # A cancelled subscription keeps its plan until the paid period ends,
    # then the workspace is simply back on Starter.
    if plan not in (None, STARTER_PLAN) and expires_at is not None and time.time() >= expires_at:
        plan, expires_at = STARTER_PLAN, None
    return Tenant(id=row[0], name=row[1], plan=plan, email=row[3], plan_expires_at=expires_at)


def get_tenant_by_id(tenant_id: str) -> Tenant | None:
    with _lock:
        row = _conn.execute("SELECT id, name FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    return Tenant(id=row[0], name=row[1]) if row else None


def get_tenant_by_email(email: str) -> Tenant | None:
    with _lock:
        row = _conn.execute("SELECT id, name FROM tenants WHERE email = ?", (email,)).fetchone()
    return Tenant(id=row[0], name=row[1]) if row else None


def get_tenant_auth_by_email(email: str) -> tuple[Tenant, str] | None:
    """(tenant, password_hash) for login verification -- kept separate from
    get_tenant_by_email so nothing outside the login path ever touches a
    password hash. None if there's no account with this email, or if it was
    provisioned via scripts/create_tenant.py (no password of its own).
    """
    with _lock:
        row = _conn.execute(
            "SELECT id, name, password_hash FROM tenants WHERE email = ?", (email,)
        ).fetchone()
    if row is None or row[2] is None:
        return None
    return Tenant(id=row[0], name=row[1]), row[2]


def rotate_api_key(tenant_id: str) -> str:
    """Issues a fresh API key for an existing tenant, invalidating whichever
    one was active before -- this app has exactly one credential type (the
    same Bearer key used everywhere), and only its hash is ever stored, so
    login can't recover the original key issued at signup; it hands back a
    new one instead. Real tradeoff worth knowing: logging in on a second
    device signs the first one out, since there's only ever one valid key
    per tenant at a time, not one per device/session.
    """
    api_key = secrets.token_urlsafe(32)
    with _lock, _conn:
        _conn.execute("UPDATE tenants SET api_key_hash = ? WHERE id = ?", (_hash_key(api_key), tenant_id))
    return api_key


def update_tenant_password(tenant_id: str, password_hash: str) -> None:
    with _lock, _conn:
        _conn.execute("UPDATE tenants SET password_hash = ? WHERE id = ?", (password_hash, tenant_id))


def get_account(tenant_id: str) -> dict | None:
    """Everything the account-settings page shows about one workspace."""
    with _lock:
        row = _conn.execute(
            "SELECT name, email, plan, created_at, uploads_used, subscription_id, plan_expires_at, password_hash "
            "FROM tenants WHERE id = ?",
            (tenant_id,),
        ).fetchone()
    if row is None:
        return None
    name, email, plan, created_at, uploads_used, subscription_id, plan_expires_at, password_hash = row
    return {
        "name": name,
        "email": email,
        "plan": plan,
        "created_at": created_at,
        "uploads_used": uploads_used,
        "subscription_id": subscription_id,
        "plan_expires_at": plan_expires_at,
        "password_hash": password_hash,
    }


def rename_tenant(tenant_id: str, name: str) -> None:
    with _lock, _conn:
        _conn.execute("UPDATE tenants SET name = ? WHERE id = ?", (name, tenant_id))


def delete_tenant(tenant_id: str) -> None:
    """Erases a workspace and everything stored under it, in one transaction."""
    with _lock, _conn:
        _conn.execute("DELETE FROM leads WHERE tenant_id = ?", (tenant_id,))
        _conn.execute("DELETE FROM alerts WHERE tenant_id = ?", (tenant_id,))
        _conn.execute("DELETE FROM password_resets WHERE tenant_id = ?", (tenant_id,))
        _conn.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_password_reset(tenant_id: str, ttl_seconds: float) -> str:
    token = secrets.token_urlsafe(32)
    with _lock, _conn:
        _conn.execute(
            "INSERT INTO password_resets (token_hash, tenant_id, expires_at) VALUES (?, ?, ?)",
            (_hash_token(token), tenant_id, time.time() + ttl_seconds),
        )
    return token


def consume_password_reset(token: str) -> str | None:
    """Validates + immediately deletes a reset token, returning the tenant_id
    it was issued for (or None if it's invalid, expired, or already used) --
    single-use, so a captured/reused link can't reset the password twice.
    """
    token_hash = _hash_token(token)
    with _lock, _conn:
        row = _conn.execute(
            "SELECT tenant_id, expires_at FROM password_resets WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        if row is None:
            return None
        _conn.execute("DELETE FROM password_resets WHERE token_hash = ?", (token_hash,))
        if row[1] < time.time():
            return None
    return row[0]


def upsert_leads(tenant_id: str, leads: list[ScoredLead]) -> None:
    """Replaces any existing lead with the same domain (within this tenant)
    rather than appending a duplicate. Each CSV parse mints a fresh Lead.id
    (see ingestion.py), so without this, re-uploading the same or an updated
    export would duplicate every row instead of refreshing it.
    """
    with _lock, _conn:
        domains = [lead.domain for lead in leads]
        _conn.executemany(
            "DELETE FROM leads WHERE tenant_id = ? AND domain = ?", [(tenant_id, d) for d in domains]
        )
        _conn.executemany(
            _UPSERT_LEAD_SQL,
            [
                (lead.id, tenant_id, lead.domain, lead.combined_score, lead.model_dump_json())
                for lead in leads
            ],
        )


def get_lead(tenant_id: str, lead_id: str) -> ScoredLead | None:
    with _lock:
        row = _conn.execute(
            "SELECT data FROM leads WHERE tenant_id = ? AND id = ?", (tenant_id, lead_id)
        ).fetchone()
    return ScoredLead.model_validate_json(row[0]) if row else None


def update_lead(tenant_id: str, lead: ScoredLead) -> None:
    with _lock, _conn:
        _conn.execute(
            _UPSERT_LEAD_SQL,
            (lead.id, tenant_id, lead.domain, lead.combined_score, lead.model_dump_json()),
        )


def list_leads(tenant_id: str) -> list[ScoredLead]:
    with _lock:
        rows = _conn.execute(
            "SELECT data FROM leads WHERE tenant_id = ? ORDER BY combined_score DESC", (tenant_id,)
        ).fetchall()
    return [ScoredLead.model_validate_json(row[0]) for row in rows]


def add_alert(tenant_id: str, alert: Alert) -> None:
    with _lock, _conn:
        _conn.execute(
            "INSERT INTO alerts (id, tenant_id, data) VALUES (?, ?, ?)",
            (alert.id, tenant_id, alert.model_dump_json()),
        )


def list_alerts(tenant_id: str) -> list[Alert]:
    with _lock:
        rows = _conn.execute(
            "SELECT data FROM alerts WHERE tenant_id = ? ORDER BY seq DESC", (tenant_id,)
        ).fetchall()
    return [Alert.model_validate_json(row[0]) for row in rows]


def clear_all(tenant_id: str) -> None:
    with _lock, _conn:
        _conn.execute("DELETE FROM leads WHERE tenant_id = ?", (tenant_id,))
        _conn.execute("DELETE FROM alerts WHERE tenant_id = ?", (tenant_id,))


def get_or_start_trial() -> float:
    """Deployment-wide (not tenant-scoped, matching /api/license), so this is
    one clock per self-hosted instance, not per tenant, and only the default
    tenant is ever gated by it (see routers/leads.py). Set once on the first
    call ever for this DB file and never overwritten after -- that's what
    makes it a real trial window instead of something a restart resets.
    """
    with _lock, _conn:
        _conn.execute(_INSERT_IGNORE_APP_META_SQL, ("trial_started_at", str(time.time())))
        row = _conn.execute("SELECT value FROM app_meta WHERE key = 'trial_started_at'").fetchone()
    return float(row[0])


def increment_trial_uploads() -> int:
    """Deployment-wide (not tenant-scoped, matching /api/license -- only the
    default tenant is ever gated by this, see routers/leads.py), so this is
    one counter per self-hosted instance, not per tenant. Persists in the
    same SQLite file as everything else, so it survives restarts and can't
    be reset by just restarting the process. Returns the new total.
    """
    with _lock, _conn:
        row = _conn.execute("SELECT value FROM app_meta WHERE key = 'trial_uploads_used'").fetchone()
        count = int(row[0]) + 1 if row else 1
        _conn.execute(_UPSERT_APP_META_SQL, ("trial_uploads_used", str(count)))
    return count


def get_trial_uploads_used() -> int:
    with _lock:
        row = _conn.execute("SELECT value FROM app_meta WHERE key = 'trial_uploads_used'").fetchone()
    return int(row[0]) if row else 0


def get_tenant_uploads_used(tenant_id: str) -> int:
    with _lock:
        row = _conn.execute("SELECT uploads_used FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    return int(row[0]) if row else 0


def increment_tenant_uploads(tenant_id: str) -> int:
    """Per-workspace counterpart of increment_trial_uploads, for hosted
    Starter workspaces (see routers/leads.py). Returns the new total."""
    with _lock, _conn:
        _conn.execute("UPDATE tenants SET uploads_used = uploads_used + 1 WHERE id = ?", (tenant_id,))
        row = _conn.execute("SELECT uploads_used FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    return int(row[0]) if row else 0


def set_tenant_subscription(tenant_id: str, plan: str, subscription_id: str) -> None:
    """Upgrades a hosted workspace after it subscribes from inside the app."""
    with _lock, _conn:
        _conn.execute(
            "UPDATE tenants SET plan = ?, subscription_id = ?, plan_expires_at = NULL WHERE id = ?",
            (plan, subscription_id, tenant_id),
        )


def get_tenant_subscription_id(tenant_id: str) -> str | None:
    with _lock:
        row = _conn.execute("SELECT subscription_id FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    return row[0] if row else None


def end_tenant_subscription(subscription_id: str, access_until: float | None = None) -> None:
    """A hosted workspace's subscription was cancelled or expired. It keeps
    its plan until access_until (the end of what was paid for), or drops to
    Starter right away if that's None. Uploads already used stay used, so
    it's straight back to the upgrade prompt, not a fresh free allowance."""
    with _lock, _conn:
        if access_until is None:
            _conn.execute(
                "UPDATE tenants SET plan = ?, subscription_id = NULL, plan_expires_at = NULL "
                "WHERE subscription_id = ?",
                (STARTER_PLAN, subscription_id),
            )
        else:
            _conn.execute(
                "UPDATE tenants SET subscription_id = NULL, plan_expires_at = ? WHERE subscription_id = ?",
                (access_until, subscription_id),
            )


def _reset_for_tests(path: str) -> None:
    """Test-only: repoints storage at a fresh SQLite file (e.g. a tmp_path
    fixture) so tests don't share state with a real dev database. Always
    SQLite regardless of DATABASE_URL -- tests need a throwaway file, not
    whatever Postgres instance a deployment might be configured against.
    """
    from . import config as _config

    global _conn
    _config.DATABASE_PATH = path
    _db.IS_POSTGRES = False
    _conn.close()
    _conn = _connect()
