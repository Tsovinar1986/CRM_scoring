import os

# Tests assume a self-hosted install; hosted-mode tests opt in via their own
# fixture. Set before app.config loads a developer's .env, which never
# overrides a variable that's already set.
os.environ["HOSTED_MODE"] = "false"

import pytest  # noqa: E402

from app import storage  # noqa: E402
from app.middleware import limiter  # noqa: E402
from app.models import ScoreBreakdown, ScoredLead  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_storage(tmp_path):
    """Every test gets its own SQLite file so tests never see each other's
    leads/alerts -- storage.py is a real DB now, not an in-memory dict that
    resets itself between test processes.
    """
    storage._reset_for_tests(str(tmp_path / "test.db"))
    yield
    storage._conn.close()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """slowapi's in-memory limiter is a module-level singleton, shared
    across every test in the run (TestClient requests all come from the
    same synthetic address) -- without this, upload-heavy test files trip
    the real rate limit against each other, not against anything the test
    itself is checking.
    """
    limiter.reset()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def make_scored_lead(**overrides) -> ScoredLead:
    defaults = dict(
        company_name="Acme Inc",
        domain="acme.com",
        contact_name="Jane Doe",
        contact_title="VP of Sales",
        industry="SaaS",
        employee_count=200,
        revenue_usd=20_000_000,
        geography="United States",
        tech_stack=["AWS", "Salesforce"],
        is_hiring=True,
        fit_score=80.0,
        score_breakdown=ScoreBreakdown(
            industry_match=25, company_size_fit=25, revenue_fit=15,
            tech_stack_match=15, geography_fit=10, hiring_signal=10,
        ),
        account_fit_score=80.0,
        llm_rationale="strong fit",
        combined_score=80.0,
        bucket="hot",
    )
    defaults.update(overrides)
    return ScoredLead(**defaults)
