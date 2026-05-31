// Intake schema metadata, conditional-field rules and completeness scoring.
// Single source of truth used by the validation agent and the live summary panel.

import type {
  IntakeRequest,
  OriginatingOrg,
  ImpactScope,
  Urgency,
  BenefitType,
  EffortSize,
  Confidence,
} from "./types";

export const ORGS: OriginatingOrg[] = [
  "Business line",
  "Accounting",
  "Regulatory",
  "Risk & Compliance",
  "Legacy platform",
  "Leadership",
];

export const IMPACT_SCOPES: ImpactScope[] = [
  "Single team",
  "Multi-team",
  "Platform-wide",
  "External",
];

export const URGENCIES: Urgency[] = ["Low", "Medium", "High", "Critical"];

export const BENEFIT_TYPES: BenefitType[] = [
  "Revenue uplift",
  "Cost reduction",
  "Cost avoidance",
  "Loss avoidance",
  "Risk reduction",
  "None",
];

export const EFFORT_SIZES: EffortSize[] = ["S", "M", "L", "XL"];

export const CONFIDENCE_LEVELS: Confidence[] = ["Low", "Medium", "High"];

export function emptyIntake(): IntakeRequest {
  return {
    title: "",
    requestorName: "",
    requestorEmail: "",
    org: null,
    businessJustification: "",
    impact: "",
    impactScope: null,
    financial: {
      benefitType: "None",
      estimatedAnnualValue: null,
      oneTimeValue: null,
      effortSize: null,
      confidence: null,
      basisOfEstimate: "",
    },
    alternativeApproach: "",
    neededBy: "",
    neededByIsHard: null,
    urgency: null,
    urgencyJustification: "",
  };
}

// A "field spec" drives both completeness scoring and the validation dialogue.
export interface FieldSpec {
  key: string;
  label: string;
  weight: number; // contribution to completeness (0-100 total across required)
  // Returns true when the field is considered present & credible.
  isComplete: (r: IntakeRequest) => boolean;
  // Whether this field is required for the given request (conditional logic).
  required: (r: IntakeRequest) => boolean;
}

const hasText = (s: string | undefined, min = 1) =>
  !!s && s.trim().length >= min;

// "Quality" check — flags vague justifications such as "we just need it".
const VAGUE_PATTERNS = [
  /^we just need it/i,
  /^because$/i,
  /^idk/i,
  /^n\/?a$/i,
  /^needed$/i,
];

export function isVague(text: string): boolean {
  const t = text.trim();
  if (t.length < 25) return true;
  return VAGUE_PATTERNS.some((p) => p.test(t));
}

export const FIELD_SPECS: FieldSpec[] = [
  {
    key: "title",
    label: "Title",
    weight: 6,
    required: () => true,
    isComplete: (r) => hasText(r.title, 4),
  },
  {
    key: "requestorName",
    label: "Requestor name",
    weight: 5,
    required: () => true,
    isComplete: (r) => hasText(r.requestorName, 2),
  },
  {
    key: "requestorEmail",
    label: "Requestor email",
    weight: 5,
    required: () => true,
    isComplete: (r) => /.+@.+\..+/.test(r.requestorEmail.trim()),
  },
  {
    key: "org",
    label: "Originating org",
    weight: 6,
    required: () => true,
    isComplete: (r) => !!r.org,
  },
  {
    key: "businessJustification",
    label: "Business justification",
    weight: 12,
    required: () => true,
    isComplete: (r) =>
      hasText(r.businessJustification, 25) && !isVague(r.businessJustification),
  },
  {
    key: "impact",
    label: "Impact",
    weight: 10,
    required: () => true,
    isComplete: (r) => hasText(r.impact, 20),
  },
  {
    key: "impactScope",
    label: "Impact scope",
    weight: 5,
    required: () => true,
    isComplete: (r) => !!r.impactScope,
  },
  {
    key: "financial.benefitType",
    label: "Benefit type",
    weight: 6,
    required: () => true,
    isComplete: (r) => !!r.financial.benefitType,
  },
  {
    key: "financial.estimatedAnnualValue",
    label: "Estimated annual value",
    weight: 8,
    required: (r) => r.financial.benefitType !== "None",
    isComplete: (r) =>
      r.financial.benefitType === "None" ||
      r.financial.estimatedAnnualValue !== null,
  },
  {
    key: "financial.effortSize",
    label: "Effort to deliver",
    weight: 5,
    required: () => true,
    isComplete: (r) => !!r.financial.effortSize,
  },
  {
    key: "financial.confidence",
    label: "Estimate confidence",
    weight: 4,
    required: (r) => r.financial.benefitType !== "None",
    isComplete: (r) =>
      r.financial.benefitType === "None" || !!r.financial.confidence,
  },
  {
    key: "financial.basisOfEstimate",
    label: "Basis of estimate",
    weight: 6,
    required: (r) => r.financial.benefitType !== "None",
    isComplete: (r) =>
      r.financial.benefitType === "None" ||
      hasText(r.financial.basisOfEstimate, 15),
  },
  {
    key: "alternativeApproach",
    label: "Alternative approach",
    weight: 8,
    required: () => true,
    isComplete: (r) => hasText(r.alternativeApproach, 15),
  },
  {
    key: "neededBy",
    label: "Timeline / needed-by",
    weight: 5,
    required: () => true,
    isComplete: (r) => hasText(r.neededBy, 3),
  },
  {
    key: "urgency",
    label: "Urgency",
    weight: 5,
    required: () => true,
    isComplete: (r) => !!r.urgency,
  },
  // ---- conditional fields ----
  {
    key: "regulatoryCitation",
    label: "Regulatory citation",
    weight: 5,
    required: (r) => r.org === "Regulatory",
    isComplete: (r) => r.org !== "Regulatory" || hasText(r.regulatoryCitation, 4),
  },
  {
    key: "complianceReference",
    label: "Compliance / control reference",
    weight: 4,
    required: (r) => r.org === "Risk & Compliance",
    isComplete: (r) =>
      r.org !== "Risk & Compliance" || hasText(r.complianceReference, 3),
  },
  {
    key: "hardDeadlineConsequence",
    label: "Hard deadline & consequence",
    weight: 5,
    required: (r) => r.urgency === "Critical" || r.org === "Regulatory",
    isComplete: (r) =>
      !(r.urgency === "Critical" || r.org === "Regulatory") ||
      hasText(r.hardDeadlineConsequence, 10),
  },
  {
    key: "affectedSystems",
    label: "Affected systems / legacy refs",
    weight: 4,
    required: (r) => r.org === "Legacy platform",
    isComplete: (r) =>
      r.org !== "Legacy platform" || hasText(r.affectedSystems, 4),
  },
];

export function requiredFields(r: IntakeRequest): FieldSpec[] {
  return FIELD_SPECS.filter((f) => f.required(r));
}

export function missingFields(r: IntakeRequest): FieldSpec[] {
  return requiredFields(r).filter((f) => !f.isComplete(r));
}

// Completeness score (0-100): weighted proportion of required fields that are
// present & credible, normalized over the *currently required* set.
export function completenessScore(r: IntakeRequest): number {
  const req = requiredFields(r);
  const totalWeight = req.reduce((s, f) => s + f.weight, 0);
  if (totalWeight === 0) return 0;
  const got = req
    .filter((f) => f.isComplete(r))
    .reduce((s, f) => s + f.weight, 0);
  return Math.round((got / totalWeight) * 100);
}

export const FIELD_LABEL: Record<string, string> = Object.fromEntries(
  FIELD_SPECS.map((f) => [f.key, f.label]),
);
