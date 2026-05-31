"""Pydantic v2 models — the single source of truth for the intake schema,
shared across the API and the agents (PRD §3, §4.2, §7.4)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class OriginatingOrg(str, Enum):
    business_line = "Business line"
    accounting = "Accounting"
    regulatory = "Regulatory"
    risk_compliance = "Risk & Compliance"
    legacy_platform = "Legacy platform"
    leadership = "Leadership"


class ImpactScope(str, Enum):
    single_team = "Single team"
    multi_team = "Multi-team"
    platform_wide = "Platform-wide"
    external = "External"


class Urgency(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    critical = "Critical"


class BenefitType(str, Enum):
    revenue_uplift = "Revenue uplift"
    cost_reduction = "Cost reduction"
    cost_avoidance = "Cost avoidance"
    loss_avoidance = "Loss avoidance"
    risk_reduction = "Risk reduction"
    none = "None"


class EffortSize(str, Enum):
    s = "S"
    m = "M"
    l = "L"
    xl = "XL"


class Confidence(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"


class FinancialOutcome(BaseModel):
    benefit_type: BenefitType = BenefitType.none
    estimated_annual_value: Optional[float] = None
    one_time_value: Optional[float] = None
    effort_size: Optional[EffortSize] = None
    confidence: Optional[Confidence] = None
    basis_of_estimate: str = ""


class IntakeRequest(BaseModel):
    title: str = ""
    requestor_name: str = ""
    requestor_email: str = ""
    org: Optional[OriginatingOrg] = None
    business_justification: str = ""
    impact: str = ""
    impact_scope: Optional[ImpactScope] = None
    financial: FinancialOutcome = Field(default_factory=FinancialOutcome)
    alternative_approach: str = ""
    needed_by: str = ""
    needed_by_is_hard: Optional[bool] = None
    urgency: Optional[Urgency] = None
    urgency_justification: str = ""

    # conditional
    regulatory_citation: Optional[str] = None
    compliance_reference: Optional[str] = None
    hard_deadline_consequence: Optional[str] = None
    affected_systems: Optional[str] = None
    dependencies: Optional[str] = None
    sponsor: Optional[str] = None


PriorityBand = Literal["P0", "P1", "P2", "P3", "Defer"]
Desirability = Literal["high", "medium", "low"]


class ROIAssessment(BaseModel):
    roi_score: int
    factor_breakdown: dict[str, int]
    estimated_annual_value: float
    payback_period_months: Optional[float]
    confidence_adjusted_value: float
    plausibility_flags: list[str]
    desirability: Desirability
    rationale: str


class PriorityRecommendation(BaseModel):
    recommended_band: PriorityBand
    rank_in_backlog: int
    override_applied: Optional[str]
    comparison_notes: str


class EmailDraft(BaseModel):
    type: Literal["deferral", "summary", "acceptance"]
    to: str
    subject: str
    body: str
    status: Literal["draft", "sent_by_human"] = "draft"


class JiraLink(BaseModel):
    issue_key: str
    url: str
    write_status: Literal["written", "failed", "pending"]
    attempts: int


class ChatMessage(BaseModel):
    id: str
    role: Literal["agent", "requestor", "system"]
    content: str
    ts: str
    agent: Optional[str] = None
    chips: Optional[list[str]] = None
    field: Optional[str] = None


class AuditEntry(BaseModel):
    ts: str
    actor: Literal["agent", "human", "system", "requestor"]
    action: str
    detail: Optional[str] = None
    agent: Optional[str] = None


RequestStatus = Literal[
    "DRAFT",
    "VALIDATING",
    "AWAITING_REQUESTOR",
    "VALIDATED",
    "SCORING",
    "AWAITING_TRIAGE",
    "ACCEPTED",
    "DOCUMENTING",
    "WRITTEN_TO_JIRA",
    "DEFERRED",
    "NEEDS_MORE_INFO",
    "CLOSED",
]


class RequestRecord(BaseModel):
    request_id: str
    status: RequestStatus
    created_at: datetime
    updated_at: datetime
    fields: IntakeRequest
    conversation: list[ChatMessage] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    completeness_score: int = 0
    clarification_rounds: int = 0
    roi: Optional[ROIAssessment] = None
    priority: Optional[PriorityRecommendation] = None
    decision: Optional[Literal["accept", "defer", "needs_human"]] = None
    email_draft: Optional[EmailDraft] = None
    jira: Optional[JiraLink] = None
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    triage_note: Optional[str] = None


# ---- API request/response bodies ----
class StartIntakeBody(BaseModel):
    text: str
    requestor_name: Optional[str] = None
    requestor_email: Optional[str] = None


class MessageBody(BaseModel):
    text: str


class DecisionBody(BaseModel):
    decision: Literal["accept", "defer", "needs_info"]
    note: str


class BacklogItem(BaseModel):
    request_id: str
    title: str
    org: OriginatingOrg
    roi_score: int
    band: PriorityBand
