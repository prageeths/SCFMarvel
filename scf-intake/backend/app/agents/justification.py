"""Agent 2 — Business Justification Agent (PRD §7)."""

from __future__ import annotations

from dataclasses import dataclass

from ..scoring.engine import format_usd, score_request
from ..schemas import (
    BacklogItem,
    BenefitType,
    EmailDraft,
    IntakeRequest,
    PriorityRecommendation,
    ROIAssessment,
)


@dataclass
class JustificationResult:
    roi: ROIAssessment
    priority: PriorityRecommendation
    decision: str  # accept | defer | needs_human
    force_human: bool


def justify(fields: IntakeRequest, backlog: list[BacklogItem]) -> JustificationResult:
    res = score_request(fields, backlog)
    roi, priority, force_human = res.roi, res.priority, res.force_human

    if force_human:
        decision = "needs_human"
    elif roi.desirability == "low" and not priority.override_applied:
        decision = "defer"
    elif roi.desirability == "medium" and priority.recommended_band == "P3":
        decision = "needs_human"
    else:
        decision = "accept"
    return JustificationResult(roi=roi, priority=priority, decision=decision, force_human=force_human)


def _reconsideration(fields: IntakeRequest) -> str:
    conds: list[str] = []
    if (fields.financial.estimated_annual_value or 0) == 0:
        conds.append("• A quantified financial benefit would materially raise the score.")
    if fields.financial.confidence and fields.financial.confidence.value == "Low":
        conds.append("• Firming up the estimate confidence would reduce the speculative discount.")
    if not fields.sponsor:
        conds.append("• A named leadership sponsor would strengthen strategic alignment.")
    conds.append("• A regulatory, compliance, or hard-deadline driver would trigger re-prioritization.")
    return "\n".join(conds)


def draft_deferral_email(
    request_id: str, fields: IntakeRequest, roi: ROIAssessment, priority: PriorityRecommendation
) -> EmailDraft:
    annual = fields.financial.estimated_annual_value or 0
    value_line = (
        f"a projected {format_usd(annual)} annual {fields.financial.benefit_type.value.lower()}"
        if annual > 0
        else "the benefit as currently described"
    )
    body = f"""Hi {fields.requestor_name or 'there'},

Thank you for submitting "{fields.title}" to the Supply Chain Finance platform intake. I've reviewed it alongside the rest of the current backlog.

Where it stands today
Based on {value_line} and an estimated effort of {fields.financial.effort_size.value if fields.financial.effort_size else 'unscoped'}, the request scored {roi.roi_score}/100 on our transparent prioritization model and ranks #{priority.rank_in_backlog} in the queue. {priority.comparison_notes}

The priority recommendation is "{priority.recommended_band}". Given the higher-value and time-sensitive work ahead of it, we can't schedule this right now. This is a deferral, not a rejection — it stays on file.

What would move it up
{_reconsideration(fields)}

If any of the above changes, just reply and we'll re-score it.

Best regards,
SCF Platform Triage
(Drafted by the Business Justification agent — reviewed and sent by a human.)"""
    return EmailDraft(
        type="deferral",
        to=fields.requestor_email,
        subject=f"Update on your SCF intake request: {fields.title} ({request_id})",
        body=body,
        status="draft",
    )


def draft_acceptance_email(
    request_id: str, fields: IntakeRequest, priority: PriorityRecommendation, issue_key: str | None
) -> EmailDraft:
    jira_line = (
        f"It has been logged as {issue_key} and added to the platform backlog."
        if issue_key
        else "It has been accepted and is being written to the platform backlog."
    )
    body = f"""Hi {fields.requestor_name or 'there'},

Good news — your Supply Chain Finance platform request "{fields.title}" has been accepted.

{jira_line}

Recommended priority: {priority.recommended_band} (ranked #{priority.rank_in_backlog} in the current queue).
{('Note: ' + priority.override_applied) if priority.override_applied else ''}

You'll be able to track delivery progress in Jira. Thank you for the clear, well-quantified submission.

Best regards,
SCF Platform Triage
(Drafted by the agent — reviewed and sent by a human.)"""
    return EmailDraft(
        type="acceptance",
        to=fields.requestor_email,
        subject=f"Accepted: {fields.title} ({request_id})",
        body=body,
        status="draft",
    )


# silence unused import warning for BenefitType (kept for parity / future use)
_ = BenefitType
