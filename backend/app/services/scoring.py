import json
import random

from ..config import (
    BUCKET_THRESHOLDS,
    ICP,
    LLM_WEIGHT,
    RULE_WEIGHT,
    SCORING_WEIGHTS,
)
from ..llm.client import get_client
from ..config import ANTHROPIC_MODEL
from ..models import EnrichedLead, ScoreBreakdown, ScoredLead


def _band_fit(value: int, low: int, high: int) -> float:
    """1.0 inside the band, decaying linearly to 0 the further outside it."""
    if value is None:
        return 0.5
    if low <= value <= high:
        return 1.0
    span = max(high - low, 1)
    distance = (low - value) if value < low else (value - high)
    return max(0.0, 1.0 - distance / span)


def _rule_score(lead: EnrichedLead) -> ScoreBreakdown:
    industry_match = 1.0 if lead.industry in ICP["target_industries"] else 0.25
    company_size_fit = _band_fit(lead.employee_count, *ICP["employee_range"])
    revenue_fit = _band_fit(lead.revenue_usd, *ICP["revenue_range_usd"])

    overlap = set(t.lower() for t in lead.tech_stack) & set(
        t.lower() for t in ICP["target_tech_stack"]
    )
    tech_stack_match = len(overlap) / len(ICP["target_tech_stack"])

    geography_fit = 1.0 if lead.geography in ICP["target_geographies"] else 0.2

    hiring_signal = 1.0 if lead.is_hiring else 0.0

    return ScoreBreakdown(
        industry_match=round(industry_match * SCORING_WEIGHTS["industry_match"], 1),
        company_size_fit=round(company_size_fit * SCORING_WEIGHTS["company_size_fit"], 1),
        revenue_fit=round(revenue_fit * SCORING_WEIGHTS["revenue_fit"], 1),
        tech_stack_match=round(tech_stack_match * SCORING_WEIGHTS["tech_stack_match"], 1),
        geography_fit=round(geography_fit * SCORING_WEIGHTS["geography_fit"], 1),
        hiring_signal=round(hiring_signal * SCORING_WEIGHTS["hiring_signal"], 1),
    )


# The rationale is written in the language the person uploading uses in the
# app (en, hy or ru -- see app/i18n.py); scores don't depend on it.
_LANGUAGE_NAMES = {"hy": "Armenian", "ru": "Russian"}

_MOCK_TEXT = {
    "en": {
        "hiring": "active hiring activity",
        "industry": "industry fit ({0})",
        "tech": "tech stack overlap ({0})",
        "none": "no strong qualitative signals detected",
        "rationale": "[mock LLM] Estimated account fit {fit}/100 for {company}, based on {signals}. Set ANTHROPIC_API_KEY to replace this with a real Claude assessment.",
    },
    "ru": {
        "hiring": "активный набор сотрудников",
        "industry": "соответствие отрасли ({0})",
        "tech": "совпадение технологий ({0})",
        "none": "явных качественных сигналов не обнаружено",
        "rationale": "[mock LLM] Оценка соответствия аккаунта {company}: {fit}/100, на основе: {signals}. Укажите ANTHROPIC_API_KEY, чтобы заменить это настоящей оценкой Claude.",
    },
    "hy": {
        "hiring": "աշխատողների ակտիվ ընդունում",
        "industry": "ոլորտի համապատասխանություն ({0})",
        "tech": "տեխնոլոգիաների համընկնում ({0})",
        "none": "ակնհայտ որակական ազդանշաններ չեն հայտնաբերվել",
        "rationale": "[mock LLM] {company}-ի համապատասխանության գնահատականը՝ {fit}/100, հիմնված՝ {signals}։ Նշեք ANTHROPIC_API_KEY-ը՝ սա Claude-ի իրական գնահատմամբ փոխարինելու համար։",
    },
}


def _mock_llm_assessment(lead: EnrichedLead, fit_score: float, lang: str = "en") -> tuple[float, str]:
    words = _MOCK_TEXT.get(lang, _MOCK_TEXT["en"])
    rng = random.Random(hash(lead.domain) & 0xFFFFFFFF)
    jitter = rng.uniform(-8, 8)
    account_fit = max(0.0, min(100.0, fit_score + jitter))

    signals = []
    if lead.is_hiring:
        signals.append(words["hiring"])
    if lead.industry in ICP["target_industries"]:
        signals.append(words["industry"].format(lead.industry))
    overlap = set(t.lower() for t in lead.tech_stack) & set(
        t.lower() for t in ICP["target_tech_stack"]
    )
    if overlap:
        signals.append(words["tech"].format(", ".join(sorted(overlap))))
    signal_text = "; ".join(signals) if signals else words["none"]

    rationale = words["rationale"].format(fit=f"{account_fit:.0f}", company=lead.company_name, signals=signal_text)
    return account_fit, rationale


def _llm_assessment(lead: EnrichedLead, fit_score: float, breakdown: ScoreBreakdown, lang: str = "en") -> tuple[float, str]:
    client = get_client()
    if client is None:
        return _mock_llm_assessment(lead, fit_score, lang)
    language_note = (
        f"\nWrite the rationale in {_LANGUAGE_NAMES[lang]}. Keep the JSON keys in English." if lang in _LANGUAGE_NAMES else ""
    )

    # Deliberately company/account attributes only -- no contact name or
    # title goes into this prompt, since the assessment is about the
    # account's fit for the ICP, not a judgment about the named individual.
    prompt = f"""You are a B2B sales qualification assistant. Given this enriched account
and its rule-based fit breakdown, assess how well the account fits the ideal
customer profile.

Account:
- Company: {lead.company_name}
- Industry: {lead.industry}
- Employees: {lead.employee_count}
- Revenue (USD): {lead.revenue_usd}
- Geography: {lead.geography}
- Tech stack: {", ".join(lead.tech_stack) or "unknown"}
- Currently hiring: {lead.is_hiring}

Rule-based fit_score: {fit_score:.1f}/100
Breakdown: {breakdown.model_dump()}

Respond with ONLY a JSON object of the form:
{{"account_fit_score": <0-100 number>, "rationale": "<one or two sentence rationale>"}}{language_note}
"""

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        data = json.loads(text.strip().strip("`"))
        return float(data["account_fit_score"]), str(data["rationale"])
    except Exception as exc:  # noqa: BLE001 - fall back rather than break scoring
        account_fit, rationale = _mock_llm_assessment(lead, fit_score, lang)
        return account_fit, f"{rationale} (LLM call failed: {exc})"


def _bucket_for(score: float) -> str:
    if score >= BUCKET_THRESHOLDS["hot"]:
        return "hot"
    if score >= BUCKET_THRESHOLDS["warm"]:
        return "warm"
    return "cold"


def score_lead(lead: EnrichedLead, lang: str = "en") -> ScoredLead:
    breakdown = _rule_score(lead)
    fit_score = round(sum(breakdown.model_dump().values()), 1)

    account_fit_score, rationale = _llm_assessment(lead, fit_score, breakdown, lang)

    combined_score = round(RULE_WEIGHT * fit_score + LLM_WEIGHT * account_fit_score, 1)
    bucket = _bucket_for(combined_score)

    return ScoredLead(
        **lead.model_dump(),
        fit_score=fit_score,
        score_breakdown=breakdown,
        account_fit_score=round(account_fit_score, 1),
        llm_rationale=rationale,
        combined_score=combined_score,
        bucket=bucket,
    )
