"""Agent 3 — Documentation Agent (PRD §8)."""

from __future__ import annotations

import re

from ..scoring.engine import format_usd
from ..schemas import IntakeRequest, JiraLink, PriorityRecommendation, ROIAssessment
from ..tools.jira import FailingJiraWriter, get_jira_writer

_PERSONA = {
    "Business line": "commercial banking business line",
    "Accounting": "accounting & finance operations team member",
    "Regulatory": "regulatory liaison",
    "Risk & Compliance": "risk & compliance officer",
    "Legacy platform": "legacy platform engineer",
    "Leadership": "commercial banking leadership sponsor",
}

_BAND_TO_PRIORITY = {"P0": "Highest", "P1": "High", "P2": "Medium", "P3": "Low", "Defer": "Lowest"}


def _slug(s: str) -> str:
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _derive_benefit(just: str) -> str:
    m = re.search(r"so that (.+)", just, re.I)
    if m:
        return m.group(1).strip().rstrip(".")
    first = re.split(r"[.;\n]", just)[0].strip()
    return (first or "the business outcome is achieved").rstrip(".").lower()


def build_story(
    request_id: str,
    fields: IntakeRequest,
    roi: ROIAssessment,
    priority: PriorityRecommendation,
) -> dict:
    persona = _PERSONA.get(fields.org.value if fields.org else "", "requestor")
    summary = f"[SCF Intake] {fields.title.strip().capitalize()}"
    benefit = _derive_benefit(fields.business_justification)

    desc_lines = [
        "h2. User story",
        f"As a {persona},",
        f"I want {fields.title.strip().lower()},",
        f"so that {benefit}.",
        "",
        "h2. Business justification",
        fields.business_justification,
        "",
        "h2. Impact & scope",
        fields.impact,
        f"Scope: {fields.impact_scope.value if fields.impact_scope else 'n/a'}.",
        "",
        "h2. Financial outcome / ROI",
        f"Benefit type: {fields.financial.benefit_type.value}",
        f"Estimated annual value: {format_usd(fields.financial.estimated_annual_value or 0)} "
        f"({fields.financial.confidence.value if fields.financial.confidence else 'n/a'} confidence)",
        f"ROI score: {roi.roi_score}/100"
        + (f", payback ≈ {roi.payback_period_months} months" if roi.payback_period_months is not None else ""),
        f"Basis of estimate: {fields.financial.basis_of_estimate or 'not provided'}",
        "",
        "h2. Alternative considered",
        fields.alternative_approach,
        "",
        "h2. Priority rationale",
        priority.comparison_notes,
        (f"Override applied: {priority.override_applied}" if priority.override_applied else ""),
        roi.rationale,
        "",
        "h2. Acceptance criteria",
        f"* Given {fields.impact_scope.value if fields.impact_scope else 'the affected'} users, "
        f"when the change ships, then {benefit}.",
    ]
    if (fields.financial.estimated_annual_value or 0) > 0:
        desc_lines.append(
            f"* Given the stated financial benefit, when delivered, then the realized "
            f"{fields.financial.benefit_type.value.lower()} is measurable against a baseline."
        )

    labels = [
        "scf-intake",
        f"org-{_slug(fields.org.value) if fields.org else 'unknown'}",
        f"urgency-{(fields.urgency.value if fields.urgency else 'low').lower()}",
    ]
    return {
        "summary": summary,
        "issue_type": "Story",
        "description": "\n".join(l for l in desc_lines if l != ""),
        "priority": _BAND_TO_PRIORITY.get(priority.recommended_band, "Medium"),
        "labels": labels,
        "components": ["Supply Chain Finance"],
        "custom_fields": {
            "intake_id": request_id,
            "roi_score": roi.roi_score,
            "needed_by": fields.needed_by,
            "requestor": fields.requestor_name,
        },
    }


def write_to_jira(
    request_id: str, payload: dict, attempt: int, *, force_fail: bool = False
) -> JiraLink:
    writer = FailingJiraWriter() if force_fail else get_jira_writer()
    return writer.create_story(request_id, payload, attempt)
