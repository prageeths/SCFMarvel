"""Agent 1 — Intake Validation Agent (PRD §6).

Deterministic conversational engine. When OPENAI_API_KEY is set, the LLM
adapter can be used to extract fields / phrase questions, but the default path
needs no key so the service runs offline and in CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import (
    BenefitType,
    Confidence,
    EffortSize,
    ImpactScope,
    IntakeRequest,
    OriginatingOrg,
    Urgency,
)
from .fields import is_vague, missing_fields

_QUESTION_ORDER = [
    "requestor_name",
    "requestor_email",
    "org",
    "title",
    "business_justification",
    "impact",
    "impact_scope",
    "financial.benefit_type",
    "financial.estimated_annual_value",
    "financial.basis_of_estimate",
    "financial.confidence",
    "financial.effort_size",
    "alternative_approach",
    "urgency",
    "needed_by",
    "regulatory_citation",
    "compliance_reference",
    "hard_deadline_consequence",
    "affected_systems",
]

_MONEY_RE = re.compile(
    r"\$?\s*(\d+(?:\.\d+)?)\s*(k|thousand|m|mm|million|bn|b|billion)?", re.I
)


@dataclass
class Question:
    field: str
    prompt: str
    reason: str
    chips: list[str] | None = None


# ---------- detectors ----------
def _detect_org(t: str) -> OriginatingOrg | None:
    s = t.lower()
    if re.search(r"regulat|basel|dodd|frank|sec |finra|occ|mandat", s):
        return OriginatingOrg.regulatory
    if re.search(r"complian|control|sox|audit|risk\b", s):
        return OriginatingOrg.risk_compliance
    if re.search(r"account|reconcil|ledger|gl |reporting|finance", s):
        return OriginatingOrg.accounting
    if re.search(r"legacy|cobol|mainframe|decommiss|migrat", s):
        return OriginatingOrg.legacy_platform
    if re.search(r"leadership|strateg|executive|board", s):
        return OriginatingOrg.leadership
    if re.search(r"business line|relationship manager|commercial", s):
        return OriginatingOrg.business_line
    return None


def _detect_urgency(t: str) -> Urgency | None:
    s = t.lower()
    if re.search(r"critical|urgent|asap|immediately|emergency|drop\s?dead", s):
        return Urgency.critical
    if re.search(r"high priority|soon|quickly|pressing", s):
        return Urgency.high
    if re.search(r"low priority|whenever|no rush|eventually", s):
        return Urgency.low
    return None


def _detect_benefit(t: str) -> BenefitType | None:
    s = t.lower()
    if re.search(r"revenue|upsell|grow sales|new business", s):
        return BenefitType.revenue_uplift
    if re.search(r"loss|fraud|charge-?off|write-?off", s):
        return BenefitType.loss_avoidance
    if re.search(r"risk|exposure|control gap", s):
        return BenefitType.risk_reduction
    if re.search(r"avoid|prevent.*cost|defer.*cost", s):
        return BenefitType.cost_avoidance
    if re.search(r"save|reduc|efficien|automat|cut cost|cheaper", s):
        return BenefitType.cost_reduction
    return None


def _detect_money(t: str) -> float | None:
    s = t.replace(",", "")
    m = _MONEY_RE.search(s)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit.startswith("k") or unit == "thousand":
        n *= 1_000
    elif unit in ("m", "mm", "million"):
        n *= 1_000_000
    elif unit in ("b", "bn", "billion"):
        n *= 1_000_000_000
    if n < 1000 and not re.search(r"[$kmb]", m.group(0), re.I) and unit == "":
        return None
    return round(n)


def parse_initial_submission(text: str, base: IntakeRequest) -> IntakeRequest:
    f = base.model_copy(deep=True)
    t = text.strip()
    first_line = re.split(r"[\n.]", t)[0].strip() if t else ""
    if not f.title and len(first_line) >= 4:
        f.title = first_line[:90]
    if not f.business_justification and len(t) >= 25:
        f.business_justification = t
    org = _detect_org(t)
    if org and not f.org:
        f.org = org
    urg = _detect_urgency(t)
    if urg and not f.urgency:
        f.urgency = urg
    money = _detect_money(t)
    if money is not None and f.financial.estimated_annual_value is None:
        f.financial.estimated_annual_value = money
        if f.financial.benefit_type == BenefitType.none:
            f.financial.benefit_type = _detect_benefit(t) or BenefitType.cost_reduction
    bt = _detect_benefit(t)
    if bt and f.financial.benefit_type == BenefitType.none:
        f.financial.benefit_type = bt
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", t)
    if email and not f.requestor_email:
        f.requestor_email = email.group(0)
    return f


_PROMPTS: dict[str, Question] = {
    "requestor_name": Question("requestor_name", "First, who should I record as the requestor?", "Every request needs an accountable requestor."),
    "requestor_email": Question("requestor_email", "What's the best email for the outcome?", "Used to close the loop."),
    "org": Question("org", "Which organization is this request coming from?", "Drives routing and conditional requirements.", [o.value for o in OriginatingOrg]),
    "title": Question("title", "Give me a one-line title summarizing the request.", "Becomes the Jira summary."),
    "impact": Question("impact", "Who and what is affected, and how?", "Tells us the blast radius."),
    "impact_scope": Question("impact_scope", "How broad is the impact?", "Feeds strategic alignment.", [s.value for s in ImpactScope]),
    "financial.benefit_type": Question("financial.benefit_type", "What kind of financial outcome does this deliver?", "Anchors the ROI computation.", [b.value for b in BenefitType]),
    "financial.estimated_annual_value": Question("financial.estimated_annual_value", "Best estimate of the annual dollar impact? (or say 'unknown')", "Biggest ROI factor."),
    "financial.basis_of_estimate": Question("financial.basis_of_estimate", "How did you arrive at that number?", "Unsupported figures get flagged."),
    "financial.confidence": Question("financial.confidence", "How confident are you in that estimate?", "Discounts speculative benefits.", [c.value for c in Confidence]),
    "financial.effort_size": Question("financial.effort_size", "Roughly how big is this to deliver?", "Lower effort scores higher.", [e.value for e in EffortSize]),
    "alternative_approach": Question("alternative_approach", "What alternatives did you consider, including doing nothing?", "Mandatory for a defensible decision."),
    "urgency": Question("urgency", "How urgent is this, and why?", "Factors into priority.", [u.value for u in Urgency]),
    "needed_by": Question("needed_by", "When do you need this by — and is it a hard deadline or a target?", "Dated items rise; hard deadlines can trigger overrides."),
    "regulatory_citation": Question("regulatory_citation", "Please provide the regulation/rule reference and mandate date.", "Regulatory items require a citation."),
    "compliance_reference": Question("compliance_reference", "Which control or policy ID does this relate to?", "Risk & Compliance items must link to a control."),
    "hard_deadline_consequence": Question("hard_deadline_consequence", "What happens if the deadline is missed?", "Critical/regulatory items need the consequence documented."),
    "affected_systems": Question("affected_systems", "Which legacy systems or integration points are involved?", "Legacy items need affected systems identified."),
}


def plan_next_question(r: IntakeRequest) -> Question | None:
    missing = set(missing_fields(r))
    for key in _QUESTION_ORDER:
        if key in missing:
            if key == "business_justification":
                prompt = (
                    "That's a bit general for me to qualify — can you be specific about *why* "
                    "this is needed and for whom?"
                    if is_vague(r.business_justification)
                    else "Why is this needed? Walk me through the business justification."
                )
                return Question(key, prompt, "A specific justification is required before scoring.")
            return _PROMPTS.get(key, Question(key, "Tell me more about that?", "More detail required."))
    return None


def _match_enum(a: str, options) -> str | None:
    s = a.strip().lower()
    for o in options:
        if s == o.value.lower():
            return o
    for o in options:
        if o.value.lower() in s or s in o.value.lower():
            return o
    return None


def apply_answer(fields: IntakeRequest, field: str, answer: str) -> tuple[IntakeRequest, str | None]:
    f = fields.model_copy(deep=True)
    a = answer.strip()
    note = None
    if field == "requestor_name":
        f.requestor_name = re.sub(r"^(my name is|i am|i'm|this is|name:?)\s*", "", a, flags=re.I).strip(". ")
    elif field == "requestor_email":
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", a)
        f.requestor_email = m.group(0) if m else a
    elif field == "org":
        f.org = _match_enum(a, OriginatingOrg) or _detect_org(a) or f.org
    elif field == "title":
        f.title = a[:90]
    elif field == "impact":
        f.impact = a
    elif field == "impact_scope":
        f.impact_scope = _match_enum(a, ImpactScope) or f.impact_scope
    elif field == "financial.benefit_type":
        f.financial.benefit_type = _match_enum(a, BenefitType) or _detect_benefit(a) or f.financial.benefit_type
    elif field == "financial.estimated_annual_value":
        if re.search(r"unknown|not sure|no idea|can.?t|cannot|n/?a", a, re.I):
            f.financial.estimated_annual_value = 0
            f.financial.confidence = Confidence.low
            note = "Recorded annual value as unknown (0) with Low confidence — not guessed."
        else:
            v = _detect_money(a)
            if v is not None:
                f.financial.estimated_annual_value = v
    elif field == "financial.basis_of_estimate":
        f.financial.basis_of_estimate = a
    elif field == "financial.confidence":
        f.financial.confidence = _match_enum(a, Confidence) or f.financial.confidence
    elif field == "financial.effort_size":
        f.financial.effort_size = _match_effort(a) or f.financial.effort_size
    elif field == "alternative_approach":
        f.alternative_approach = a
    elif field == "urgency":
        f.urgency = _match_enum(a, Urgency) or _detect_urgency(a) or f.urgency
        f.urgency_justification = a
    elif field == "needed_by":
        f.needed_by = a
        if re.search(r"hard|firm|must|fixed|drop\s?dead|mandat", a, re.I):
            f.needed_by_is_hard = True
        elif re.search(r"target|soft|ideal|nice|flex", a, re.I):
            f.needed_by_is_hard = False
    elif field == "business_justification":
        f.business_justification = a
    elif field == "regulatory_citation":
        f.regulatory_citation = a
    elif field == "compliance_reference":
        f.compliance_reference = a
    elif field == "hard_deadline_consequence":
        f.hard_deadline_consequence = a
    elif field == "affected_systems":
        f.affected_systems = a
    return f, note


def _match_effort(a: str) -> EffortSize | None:
    s = a.strip().lower()
    if re.search(r"\bxl\b|extra large|x-large|very large|huge", s):
        return EffortSize.xl
    if re.search(r"\bl\b|large\b", s):
        return EffortSize.l
    if re.search(r"\bm\b|medium", s):
        return EffortSize.m
    if re.search(r"\bs\b|small", s):
        return EffortSize.s
    return None


def validation_step(r: IntakeRequest) -> Question | None:
    """Return the next clarification question, or None when validated."""
    return plan_next_question(r)
