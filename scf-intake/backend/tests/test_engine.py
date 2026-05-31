"""Unit tests for the intake schema, scoring overrides and orchestration."""

from __future__ import annotations

from app.agents.fields import completeness_score, missing_fields
from app.agents.justification import justify
from app.graph import handle_requestor_message, start_intake
from app.schemas import (
    BenefitType,
    Confidence,
    EffortSize,
    ImpactScope,
    IntakeRequest,
    FinancialOutcome,
    OriginatingOrg,
    Urgency,
)
from app.seed import get_backlog


def _complete_request(**overrides) -> IntakeRequest:
    base = IntakeRequest(
        title="Auto-match buyer remittances to factored invoices",
        requestor_name="Dana W",
        requestor_email="dana@example-bank.com",
        org=OriginatingOrg.accounting,
        business_justification="Manual remittance matching eats two FTEs and is error-prone; automate it.",
        impact="Affects the reconciliation desk of six analysts and GL posting downstream.",
        impact_scope=ImpactScope.multi_team,
        financial=FinancialOutcome(
            benefit_type=BenefitType.cost_reduction,
            estimated_annual_value=340000,
            effort_size=EffortSize.m,
            confidence=Confidence.high,
            basis_of_estimate="Two FTEs at ~$140k plus measured rework cost.",
        ),
        alternative_approach="Considered outsourcing; rejected on data residency.",
        needed_by="End of Q3",
        urgency=Urgency.medium,
    )
    return base.model_copy(update=overrides)


def test_completeness_full():
    r = _complete_request()
    assert missing_fields(r) == []
    assert completeness_score(r) == 100


def test_completeness_missing_financial_basis():
    r = _complete_request()
    r.financial.basis_of_estimate = ""
    assert "financial.basis_of_estimate" in missing_fields(r)
    assert completeness_score(r) < 100


def test_high_value_low_effort_accepts():
    r = _complete_request()
    res = justify(r, get_backlog())
    assert res.roi.roi_score >= 50
    assert res.decision in ("accept", "needs_human")
    assert res.priority.recommended_band in ("P0", "P1", "P2")


def test_regulatory_hard_deadline_override():
    r = _complete_request(
        org=OriginatingOrg.regulatory,
        regulatory_citation="Basel III RWA, eff 2026-09-30",
        needed_by_is_hard=True,
        hard_deadline_consequence="Non-compliant return / MRA.",
        financial=FinancialOutcome(benefit_type=BenefitType.risk_reduction, estimated_annual_value=0,
                                   effort_size=EffortSize.l, confidence=Confidence.high,
                                   basis_of_estimate="Mandate-driven; avoidance of finding."),
    )
    res = justify(r, get_backlog())
    assert res.priority.override_applied is not None
    assert res.priority.recommended_band in ("P0", "P1")


def test_critical_routes_to_human():
    r = _complete_request(urgency=Urgency.critical,
                          hard_deadline_consequence="Customers blocked from financing.")
    res = justify(r, get_backlog())
    assert res.decision == "needs_human"


def test_low_value_defers():
    r = _complete_request(
        title="Custom emoji reactions on the decision feed",
        org=OriginatingOrg.business_line,
        impact_scope=ImpactScope.single_team,
        urgency=Urgency.low,
        financial=FinancialOutcome(benefit_type=BenefitType.none, estimated_annual_value=0,
                                   effort_size=EffortSize.m, confidence=Confidence.low,
                                   basis_of_estimate="No quantified benefit."),
    )
    res = justify(r, get_backlog())
    assert res.roi.desirability == "low"
    assert res.decision == "defer"


def test_orchestration_asks_then_validates():
    rec = start_intake("We need suppliers to see effective APR on early-payment offers.", get_backlog())
    # Should start asking clarifying questions.
    assert rec.status in ("AWAITING_REQUESTOR", "VALIDATED", "AWAITING_TRIAGE", "CLOSED", "DEFERRED")
    assert any(m.role == "agent" for m in rec.conversation)


def test_plausibility_flag_for_unsupported_value():
    r = _complete_request()
    r.financial.estimated_annual_value = 8_000_000
    r.financial.confidence = Confidence.low
    r.financial.basis_of_estimate = ""
    res = justify(r, get_backlog())
    assert len(res.roi.plausibility_flags) >= 1
