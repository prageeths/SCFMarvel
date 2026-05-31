// Core domain types for the Agentic Intake Request Application.
// These mirror the Pydantic models described in the PRD (Sections 3, 5, 7).

export type OriginatingOrg =
  | "Business line"
  | "Accounting"
  | "Regulatory"
  | "Risk & Compliance"
  | "Legacy platform"
  | "Leadership";

export type ImpactScope =
  | "Single team"
  | "Multi-team"
  | "Platform-wide"
  | "External";

export type Urgency = "Low" | "Medium" | "High" | "Critical";

export type BenefitType =
  | "Revenue uplift"
  | "Cost reduction"
  | "Cost avoidance"
  | "Loss avoidance"
  | "Risk reduction"
  | "None";

export type EffortSize = "S" | "M" | "L" | "XL";

export type Confidence = "Low" | "Medium" | "High";

export interface FinancialOutcome {
  benefitType: BenefitType;
  estimatedAnnualValue: number | null;
  oneTimeValue: number | null;
  effortSize: EffortSize | null;
  confidence: Confidence | null;
  basisOfEstimate: string;
}

export interface IntakeRequest {
  title: string;
  requestorName: string;
  requestorEmail: string;
  org: OriginatingOrg | null;
  businessJustification: string;
  impact: string;
  impactScope: ImpactScope | null;
  financial: FinancialOutcome;
  alternativeApproach: string;
  neededBy: string; // ISO date or descriptive
  neededByIsHard: boolean | null;
  urgency: Urgency | null;
  urgencyJustification: string;

  // Conditional fields
  regulatoryCitation?: string;
  complianceReference?: string;
  hardDeadlineConsequence?: string;
  affectedSystems?: string;
  dependencies?: string;
  sponsor?: string;
}

export type PriorityBand = "P0" | "P1" | "P2" | "P3" | "Defer";

export type Desirability = "high" | "medium" | "low";

export interface ROIAssessment {
  roiScore: number; // 0-100 composite
  factorBreakdown: Record<string, number>; // per-factor weighted contribution
  estimatedAnnualValue: number;
  paybackPeriodMonths: number | null;
  confidenceAdjustedValue: number;
  plausibilityFlags: string[];
  desirability: Desirability;
  rationale: string;
}

export interface PriorityRecommendation {
  recommendedBand: PriorityBand;
  rankInBacklog: number;
  overrideApplied: string | null;
  comparisonNotes: string;
}

export interface BacklogItem {
  requestId: string;
  title: string;
  org: OriginatingOrg;
  roiScore: number;
  band: PriorityBand;
}

export interface EmailDraft {
  type: "deferral" | "summary" | "acceptance";
  to: string;
  subject: string;
  body: string;
  status: "draft" | "sent_by_human";
}

export interface JiraLink {
  issueKey: string;
  url: string;
  writeStatus: "written" | "failed" | "pending";
  attempts: number;
}

export type RequestStatus =
  | "DRAFT"
  | "VALIDATING"
  | "AWAITING_REQUESTOR"
  | "VALIDATED"
  | "SCORING"
  | "AWAITING_TRIAGE"
  | "ACCEPTED"
  | "DOCUMENTING"
  | "WRITTEN_TO_JIRA"
  | "DEFERRED"
  | "NEEDS_MORE_INFO"
  | "CLOSED";

export type Actor = "agent" | "human" | "system" | "requestor";

export interface AuditEntry {
  ts: string;
  actor: Actor;
  agent?: string;
  action: string;
  detail?: string;
}

export type ChatRole = "agent" | "requestor" | "system";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  ts: string;
  agent?: string;
  // Optional quick-reply chips offered with an agent question.
  chips?: string[];
  field?: string; // the field this question targets
}

export interface DuplicateMatch {
  requestId: string;
  title: string;
  similarity: number;
}

export interface RequestRecord {
  requestId: string;
  status: RequestStatus;
  createdAt: string;
  updatedAt: string;
  fields: IntakeRequest;
  conversation: ChatMessage[];
  missingFields: string[];
  completenessScore: number;
  clarificationRounds: number;
  roi: ROIAssessment | null;
  priority: PriorityRecommendation | null;
  decision: "accept" | "defer" | "needs_human" | null;
  emailDraft: EmailDraft | null;
  jira: JiraLink | null;
  duplicateOf: DuplicateMatch | null;
  auditTrail: AuditEntry[];
  // Free text of triage human's note for the decision.
  triageNote?: string;
}
