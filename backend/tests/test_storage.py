import json
import sqlite3

from app import config, storage
from app.models import Alert

from .conftest import make_scored_lead

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"


def test_reset_for_tests_actually_redirects_storage(tmp_path):
    # Regression test: _reset_for_tests once set a module-level
    # storage.DATABASE_PATH that nothing read anymore (db.py reads
    # config.DATABASE_PATH), so every test silently wrote to whatever real
    # database config.DATABASE_PATH pointed at instead of an isolated tmp
    # file. This pins the fix: after reset, the connection must actually be
    # backed by the requested path, and config.DATABASE_PATH must agree.
    db_path = str(tmp_path / "isolated.db")
    storage._reset_for_tests(db_path)

    assert config.DATABASE_PATH == db_path
    storage.upsert_leads(TENANT, [make_scored_lead()])
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM leads").fetchone()[0]
    conn.close()
    assert count == 1


def test_migrates_pre_signup_schema_without_losing_data(tmp_path):
    # Simulates a real DB from before self-serve signup existed: a tenants
    # table with no email/password_hash columns at all.
    db_path = str(tmp_path / "old.db")
    raw = sqlite3.connect(db_path)
    raw.execute(
        "CREATE TABLE tenants (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "api_key_hash TEXT NOT NULL UNIQUE, created_at REAL NOT NULL)"
    )
    raw.execute(
        "INSERT INTO tenants (id, name, api_key_hash, created_at) VALUES (?, ?, ?, ?)",
        ("old-tenant-id", "Pre-existing Co", "somehash", 1700000000.0),
    )
    raw.commit()
    raw.close()

    storage._reset_for_tests(db_path)  # runs _connect(), which must migrate in place

    # Old data survived the migration...
    found = storage.get_tenant_by_id("old-tenant-id")
    assert found is not None
    assert found.name == "Pre-existing Co"
    # ...and the new self-serve columns now work on this same DB file.
    storage.create_tenant("New Co", email="new@co.com", password_hash="hash")
    assert storage.get_tenant_by_email("new@co.com") is not None


def test_upsert_dedupes_by_domain_not_id():
    storage.upsert_leads(TENANT, [make_scored_lead(domain="a.com", combined_score=50)])
    storage.upsert_leads(TENANT, [make_scored_lead(domain="a.com", combined_score=90)])

    leads = storage.list_leads(TENANT)
    assert len(leads) == 1
    assert leads[0].combined_score == 90


def test_list_leads_sorted_by_combined_score_desc():
    storage.upsert_leads(TENANT, [
        make_scored_lead(domain="low.com", combined_score=40),
        make_scored_lead(domain="high.com", combined_score=95),
        make_scored_lead(domain="mid.com", combined_score=70),
    ])

    domains = [lead.domain for lead in storage.list_leads(TENANT)]
    assert domains == ["high.com", "mid.com", "low.com"]


def test_get_lead_roundtrips_full_shape():
    lead = make_scored_lead(domain="acme.com")
    storage.upsert_leads(TENANT, [lead])

    fetched = storage.get_lead(TENANT, lead.id)
    assert fetched is not None
    assert fetched.company_name == lead.company_name
    assert fetched.score_breakdown.industry_match == lead.score_breakdown.industry_match


def test_get_lead_missing_returns_none():
    assert storage.get_lead(TENANT, "does-not-exist") is None


def test_alerts_returned_most_recent_first():
    storage.add_alert(TENANT, Alert(lead_id="1", company_name="First", combined_score=80, message="first"))
    storage.add_alert(TENANT, Alert(lead_id="2", company_name="Second", combined_score=90, message="second"))

    messages = [a.message for a in storage.list_alerts(TENANT)]
    assert messages == ["second", "first"]


def test_persists_across_reconnect(tmp_path):
    db_path = str(tmp_path / "persist.db")
    storage._reset_for_tests(db_path)
    storage.upsert_leads(TENANT, [make_scored_lead(domain="persist.com")])

    storage._conn.close()
    storage._conn = storage._connect()

    assert len(storage.list_leads(TENANT)) == 1


def test_clear_all_empties_both_tables():
    storage.upsert_leads(TENANT, [make_scored_lead()])
    storage.add_alert(TENANT, Alert(lead_id="1", company_name="X", combined_score=80, message="m"))

    storage.clear_all(TENANT)

    assert storage.list_leads(TENANT) == []
    assert storage.list_alerts(TENANT) == []


def test_leads_isolated_between_tenants():
    storage.upsert_leads(TENANT, [make_scored_lead(domain="a.com")])
    storage.upsert_leads(OTHER_TENANT, [make_scored_lead(domain="b.com")])

    assert [lead.domain for lead in storage.list_leads(TENANT)] == ["a.com"]
    assert [lead.domain for lead in storage.list_leads(OTHER_TENANT)] == ["b.com"]


def test_same_domain_in_two_tenants_does_not_collide():
    storage.upsert_leads(TENANT, [make_scored_lead(domain="shared.com", combined_score=10)])
    storage.upsert_leads(OTHER_TENANT, [make_scored_lead(domain="shared.com", combined_score=99)])

    assert storage.list_leads(TENANT)[0].combined_score == 10
    assert storage.list_leads(OTHER_TENANT)[0].combined_score == 99


def test_get_lead_cannot_cross_tenant_boundary():
    lead = make_scored_lead(domain="secret.com")
    storage.upsert_leads(TENANT, [lead])

    assert storage.get_lead(OTHER_TENANT, lead.id) is None
    assert storage.get_lead(TENANT, lead.id) is not None


def test_alerts_isolated_between_tenants():
    storage.add_alert(TENANT, Alert(lead_id="1", company_name="A", combined_score=80, message="mine"))
    storage.add_alert(OTHER_TENANT, Alert(lead_id="2", company_name="B", combined_score=80, message="theirs"))

    assert [a.message for a in storage.list_alerts(TENANT)] == ["mine"]
    assert [a.message for a in storage.list_alerts(OTHER_TENANT)] == ["theirs"]


def test_create_tenant_and_lookup_by_api_key():
    tenant, api_key = storage.create_tenant("Acme Corp")

    found = storage.get_tenant_by_api_key(api_key)
    assert found is not None
    assert found.id == tenant.id
    assert found.name == "Acme Corp"


def test_lookup_with_wrong_api_key_returns_none():
    storage.create_tenant("Acme Corp")
    assert storage.get_tenant_by_api_key("not-the-real-key") is None


def test_get_tenant_by_id_roundtrips():
    tenant, _ = storage.create_tenant("Acme Corp")
    found = storage.get_tenant_by_id(tenant.id)
    assert found is not None
    assert found.name == "Acme Corp"


def test_get_tenant_by_id_missing_returns_none():
    assert storage.get_tenant_by_id("does-not-exist") is None


def test_self_serve_signup_tenant_findable_by_email():
    tenant, _ = storage.create_tenant("Acme Corp", email="buyer@acme.com", password_hash="hash123")
    found = storage.get_tenant_by_email("buyer@acme.com")
    assert found is not None
    assert found.id == tenant.id


def test_get_tenant_by_email_missing_returns_none():
    assert storage.get_tenant_by_email("nobody@nowhere.com") is None


def test_get_tenant_auth_by_email_returns_password_hash():
    storage.create_tenant("Acme Corp", email="buyer@acme.com", password_hash="hash123")
    auth = storage.get_tenant_auth_by_email("buyer@acme.com")
    assert auth is not None
    tenant, password_hash = auth
    assert tenant.name == "Acme Corp"
    assert password_hash == "hash123"


def test_get_tenant_auth_by_email_none_for_script_provisioned_tenant():
    # create_tenant with no email/password_hash -- the scripts/create_tenant.py
    # flow, which has no login of its own.
    storage.create_tenant("Manually Provisioned Co")
    # No email at all was set, so there's nothing to look up by -- but also
    # confirm a script-provisioned tenant given a bare email later (no
    # password) still correctly reports "no login" rather than crashing.
    assert storage.get_tenant_auth_by_email("nobody@nowhere.com") is None


def test_rotate_api_key_invalidates_the_old_one():
    tenant, old_key = storage.create_tenant("Acme Corp")
    new_key = storage.rotate_api_key(tenant.id)

    assert new_key != old_key
    assert storage.get_tenant_by_api_key(old_key) is None
    found = storage.get_tenant_by_api_key(new_key)
    assert found is not None
    assert found.id == tenant.id


def test_update_tenant_password_changes_auth_hash():
    tenant, _ = storage.create_tenant("Acme Corp", email="buyer@acme.com", password_hash="old-hash")
    storage.update_tenant_password(tenant.id, "new-hash")

    _, password_hash = storage.get_tenant_auth_by_email("buyer@acme.com")
    assert password_hash == "new-hash"


def test_password_reset_token_resolves_to_the_right_tenant():
    tenant, _ = storage.create_tenant("Acme Corp", email="buyer@acme.com", password_hash="hash")
    token = storage.create_password_reset(tenant.id, ttl_seconds=3600)

    assert storage.consume_password_reset(token) == tenant.id


def test_password_reset_token_is_single_use():
    tenant, _ = storage.create_tenant("Acme Corp", email="buyer@acme.com", password_hash="hash")
    token = storage.create_password_reset(tenant.id, ttl_seconds=3600)

    assert storage.consume_password_reset(token) == tenant.id
    assert storage.consume_password_reset(token) is None  # already consumed


def test_expired_password_reset_token_is_rejected():
    tenant, _ = storage.create_tenant("Acme Corp", email="buyer@acme.com", password_hash="hash")
    token = storage.create_password_reset(tenant.id, ttl_seconds=-1)  # already expired

    assert storage.consume_password_reset(token) is None


def test_unknown_password_reset_token_returns_none():
    assert storage.consume_password_reset("not-a-real-token") is None


def test_get_or_start_trial_is_stable_across_calls():
    first = storage.get_or_start_trial()
    second = storage.get_or_start_trial()
    assert first == second


def test_get_or_start_trial_persists_across_reconnect(tmp_path):
    db_path = str(tmp_path / "trial.db")
    storage._reset_for_tests(db_path)
    started = storage.get_or_start_trial()

    storage._conn.close()
    storage._conn = storage._connect()

    assert storage.get_or_start_trial() == started


def test_trial_uploads_starts_at_zero():
    assert storage.get_trial_uploads_used() == 0


def test_increment_trial_uploads_counts_up():
    assert storage.increment_trial_uploads() == 1
    assert storage.increment_trial_uploads() == 2
    assert storage.get_trial_uploads_used() == 2


def test_trial_uploads_persists_across_reconnect(tmp_path):
    db_path = str(tmp_path / "trial_uploads.db")
    storage._reset_for_tests(db_path)
    storage.increment_trial_uploads()
    storage.increment_trial_uploads()

    storage._conn.close()
    storage._conn = storage._connect()

    assert storage.get_trial_uploads_used() == 2


# --- SQL injection: every query in storage.py uses ? placeholders, never
# string-built SQL, so a malicious value in any of these fields should be
# treated as inert data -- never as executable SQL, never able to read or
# affect another tenant's rows.


INJECTION_PAYLOAD = "x'; DROP TABLE leads; --"


def test_tenant_id_containing_sql_metacharacters_is_treated_as_literal_data():
    tenant_id = "tenant'; DROP TABLE leads; --"
    storage.upsert_leads(tenant_id, [make_scored_lead(domain="a.com")])

    # If this were ever interpolated instead of bound, the table would be
    # gone and every call below would raise sqlite3.OperationalError.
    assert len(storage.list_leads(tenant_id)) == 1
    assert storage.list_leads(TENANT) == []  # no cross-tenant bleed either


def test_lead_domain_containing_sql_metacharacters_is_treated_as_literal_data():
    storage.upsert_leads(TENANT, [make_scored_lead(domain=INJECTION_PAYLOAD)])

    leads = storage.list_leads(TENANT)
    assert len(leads) == 1
    assert leads[0].domain == INJECTION_PAYLOAD


def test_lead_id_lookup_with_sql_metacharacters_finds_nothing_not_everything():
    storage.upsert_leads(TENANT, [make_scored_lead(domain="a.com")])

    # A classic injection probe (e.g. "' OR '1'='1") must not turn into a
    # match-everything query -- it should simply find no such id.
    assert storage.get_lead(TENANT, "' OR '1'='1") is None


def test_api_key_lookup_with_sql_metacharacters_finds_nothing():
    storage.create_tenant("Acme Corp")
    assert storage.get_tenant_by_api_key("' OR '1'='1") is None


def test_database_still_usable_after_injection_attempt_in_same_session():
    # Same DB instance, same test -- proves an injection attempt doesn't
    # corrupt state for whatever runs after it, not just that a fresh DB
    # in a different test happens to still work.
    storage.upsert_leads(TENANT, [make_scored_lead(domain=INJECTION_PAYLOAD)])
    storage.get_lead(TENANT, "' OR '1'='1")

    storage.upsert_leads(TENANT, [make_scored_lead(domain="still-here.com")])
    assert "still-here.com" in [lead.domain for lead in storage.list_leads(TENANT)]


def test_list_leads_loads_rows_saved_before_account_fit_rename():
    # Rows written before the Sep 2026 scoring change stored the LLM score as
    # conversion_likelihood and carried since-removed fields -- they must
    # still load rather than 500 the whole leads list.
    old = make_scored_lead(domain="old.example").model_dump()
    old["conversion_likelihood"] = old.pop("account_fit_score")
    old["score_breakdown"]["title_seniority"] = 10.0
    old["outreach_draft"] = None
    with storage._lock, storage._conn:
        storage._conn.execute(
            "INSERT INTO leads (id, tenant_id, domain, combined_score, data) VALUES (?, ?, ?, ?, ?)",
            (old["id"], TENANT, old["domain"], old["combined_score"], json.dumps(old)),
        )

    [lead] = storage.list_leads(TENANT)
    assert lead.account_fit_score == old["conversion_likelihood"]
    assert "conversion_likelihood" not in lead.model_dump_json()
