"""Pre-processed example requests so the dashboard is populated on first run.

Synthetic data only (PRD regulated-environment guardrails)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .agents.documentation import build_story, write_to_jira
from .agents.fields import completeness_score
from .agents.justification import draft_acceptance_email, draft_deferral_email, justify
from .schemas import (
    AuditEntry,
    BenefitType,
    ChatMessage,
    Confidence,
    EffortSize,
    FinancialOutcome,
    ImpactScope,
    IntakeRequest,
    OriginatingOrg,
    RequestRecord,
    Urgency,
)
from .seed import get_backlog


def _ts(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _record(rid: str, fields: IntakeRequest, days_ago: int) -> RequestRecord:
    created = _ts(days_ago)
    return RequestRecord(
        request_id=rid,
        status="VALIDATED",
        created_at=created,
        updated_at=created,
        fields=fields,
        completeness_score=completeness_score(fields),
        clarification_rounds=2,
        conversation=[
            ChatMessage(id=f"{rid}-1", role="agent", agent="Validation", content="Let's structure your request.", ts=created.isoformat()),
            ChatMessage(id=f"{rid}-2", role="requestor", content=fields.business_justification, ts=created.isoformat()),
        ],
        audit_trail=[
            AuditEntry(ts=created.isoformat(), actor="system", action="Intake started", detail=f"request_id {rid}"),
            AuditEntry(ts=created.isoformat(), actor="agent", agent="Validation", action="Validation complete"),
        ],
    )


def build_examples() -> list[RequestRecord]:
    backlog = get_backlog()
    out: list[RequestRecord] = []

    # 1) Accepted & written to Jira
    f = IntakeRequest(
        title="Auto-match buyer remittances to open factored invoices",
        requestor_name="Dana Whitfield",
        requestor_email="dana.whitfield@example-bank.com",
        org=OriginatingOrg.accounting,
        business_justification=(
            "Our ops team manually matches ~4,000 buyer remittance lines a month to open factored "
            "invoices. It's error-prone and eats two FTEs. Auto-match with tolerance rules would "
            "clear the bulk automatically and flag only exceptions."
        ),
        impact="Affects the SCF reconciliation desk (6 analysts) and downstream GL posting.",
        impact_scope=ImpactScope.multi_team,
        financial=FinancialOutcome(
            benefit_type=BenefitType.cost_reduction,
            estimated_annual_value=340000,
            effort_size=EffortSize.m,
            confidence=Confidence.high,
            basis_of_estimate="Two FTEs at ~$140k plus a measured 18% error-rework cost.",
        ),
        alternative_approach="Considered outsourcing (rejected on data-residency) and doing nothing (volume +12% YoY).",
        needed_by="End of Q3",
        needed_by_is_hard=False,
        urgency=Urgency.medium,
        urgency_justification="Growing volume, no hard deadline.",
    )
    rec = _record("SCF-INTK-000118", f, 9)
    res = justify(f, backlog)
    rec.roi, rec.priority, rec.decision = res.roi, res.priority, "accept"
    payload = build_story(rec.request_id, f, res.roi, res.priority)
    rec.jira = write_to_jira(rec.request_id, payload, 1)
    rec.email_draft = draft_acceptance_email(rec.request_id, f, res.priority, rec.jira.issue_key)
    rec.status = "CLOSED"
    out.append(rec)

    # 2) Regulatory + hard deadline → awaiting triage
    f2 = IntakeRequest(
        title="Basel III RWA field for receivables-financing exposures",
        requestor_name="Priya Nair",
        requestor_email="priya.nair@example-bank.com",
        org=OriginatingOrg.regulatory,
        business_justification=(
            "Latest regulatory guidance requires risk-weighted assets for receivables-financing "
            "exposures reported separately. Our extract bundles them, which will fail supervisory review."
        ),
        impact="Affects regulatory reporting and the platform data warehouse extract.",
        impact_scope=ImpactScope.platform_wide,
        financial=FinancialOutcome(
            benefit_type=BenefitType.risk_reduction,
            estimated_annual_value=0,
            effort_size=EffortSize.l,
            confidence=Confidence.high,
            basis_of_estimate="Mandate — value is avoidance of a supervisory finding.",
        ),
        alternative_approach="Manual quarterly workaround rejected as unsustainable.",
        needed_by="2026-09-30",
        needed_by_is_hard=True,
        urgency=Urgency.high,
        urgency_justification="Regulatory deadline.",
        regulatory_citation="Basel III finalization — CRE receivables RWA, eff. 2026-09-30",
        hard_deadline_consequence="Missing the date means a non-compliant return and a likely MRA.",
    )
    rec2 = _record("SCF-INTK-000120", f2, 3)
    res2 = justify(f2, backlog)
    rec2.roi, rec2.priority, rec2.decision = res2.roi, res2.priority, "needs_human"
    rec2.status = "AWAITING_TRIAGE"
    out.append(rec2)

    # 3) Low value, no override → deferred with drafted email
    f3 = IntakeRequest(
        title="Custom emoji reactions on the agent decision feed",
        requestor_name="Marco Reyes",
        requestor_email="marco.reyes@example-bank.com",
        org=OriginatingOrg.business_line,
        business_justification=(
            "It would be fun if the team could react to agent decisions with custom emojis in the "
            "console feed to make reviews feel more engaging."
        ),
        impact="Cosmetic; affects the relationship-manager console UI only.",
        impact_scope=ImpactScope.single_team,
        financial=FinancialOutcome(
            benefit_type=BenefitType.none,
            estimated_annual_value=0,
            effort_size=EffortSize.m,
            confidence=Confidence.low,
            basis_of_estimate="No quantified benefit identified.",
        ),
        alternative_approach="Could use the existing comment field; doing nothing has no operational impact.",
        needed_by="No particular date",
        needed_by_is_hard=False,
        urgency=Urgency.low,
        urgency_justification="Nice-to-have.",
    )
    rec3 = _record("SCF-INTK-000119", f3, 6)
    res3 = justify(f3, backlog)
    rec3.roi, rec3.priority, rec3.decision = res3.roi, res3.priority, "defer"
    rec3.email_draft = draft_deferral_email(rec3.request_id, f3, res3.roi, res3.priority)
    rec3.status = "DEFERRED"
    out.append(rec3)

    return out
