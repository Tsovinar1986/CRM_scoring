import uuid
from typing import Optional

from pydantic import AliasChoices, BaseModel, Field


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# Bounds on freeform text from an uploaded file -- not a meaningful attack
# surface on their own (Pydantic already enforces type; storage is
# parameterized SQL; the frontend is React, which escapes on render), but a
# spreadsheet cell with megabytes of text in it shouldn't be allowed to
# balloon a stored row indefinitely.
_SHORT_TEXT_MAX = 200


class Lead(BaseModel):
    """Raw lead as ingested from CSV/XLSX or a live CRM pull."""

    id: str = Field(default_factory=new_id)
    company_name: str = Field(max_length=200)
    domain: str = Field(max_length=255)
    contact_name: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)
    contact_title: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)
    industry: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)
    employee_count: Optional[int] = Field(default=None, ge=0)
    revenue_usd: Optional[int] = Field(default=None, ge=0)
    geography: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)
    source: str = "csv_upload"


class EnrichedLead(Lead):
    """Lead after firmographic/website enrichment fills in missing fields."""

    tech_stack: list[str] = Field(default_factory=list)
    is_hiring: bool = False
    enrichment_source: str = "mock"


class ScoreBreakdown(BaseModel):
    industry_match: float
    company_size_fit: float
    revenue_fit: float
    tech_stack_match: float
    geography_fit: float
    hiring_signal: float


class ScoredLead(EnrichedLead):
    fit_score: float
    score_breakdown: ScoreBreakdown
    # Leads stored before account-level-only scoring (Sep 2026) saved this as
    # conversion_likelihood -- accept that name so they still load.
    account_fit_score: float = Field(validation_alias=AliasChoices("account_fit_score", "conversion_likelihood"))
    llm_rationale: str
    combined_score: float
    bucket: str  # "hot" | "warm" | "cold"
    crm_pushed: bool = False


class CrmPushResponse(BaseModel):
    lead_id: str
    crm: str
    status: str
    detail: str


class ChurnCustomer(BaseModel):
    """Raw customer row from a churn-risk export (a different data shape than
    a B2B lead -- individual subscribers/accounts, not companies)."""

    id: str = Field(default_factory=new_id)
    contract: str = Field(max_length=_SHORT_TEXT_MAX)
    tenure_months: int = Field(ge=0)
    monthly_charges: float = Field(ge=0)
    internet_service: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)
    tech_support: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)
    online_security: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)
    payment_method: Optional[str] = Field(default=None, max_length=_SHORT_TEXT_MAX)


class ChurnRiskBreakdown(BaseModel):
    contract_risk: float
    tenure_risk: float
    charges_risk: float
    service_gaps_risk: float
    payment_method_risk: float


class ChurnScoredCustomer(ChurnCustomer):
    risk_score: float
    risk_breakdown: ChurnRiskBreakdown
    bucket: str  # "high" | "medium" | "low"


class Alert(BaseModel):
    id: str = Field(default_factory=new_id)
    lead_id: str
    company_name: str
    combined_score: float
    message: str
    channel: str = "slack"
