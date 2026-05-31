// Transparent, config-driven ROI scoring engine (PRD Section 7.3).
// Weights live in one place and are intentionally tunable — there are no
// hidden heuristics, every factor contribution is reported back to the UI.

import type {
  IntakeRequest,
  ROIAssessment,
  PriorityRecommendation,
  PriorityBand,
  BacklogItem,
  EffortSize,
} from "./types";

export interface ScoringWeights {
  financialValue: number;
  effort: number;
  strategicAlignment: number;
  urgency: number;
  riskCompliance: number;
  confidence: number;
}

// Defaults from PRD §7.3 (sum = 1.0).
export const DEFAULT_WEIGHTS: ScoringWeights = {
  financialValue: 0.3,
  effort: 0.2,
  strategicAlignment: 0.15,
  urgency: 0.15,
  riskCompliance: 0.15,
  confidence: 0.05,
};

export const FACTOR_LABELS: Record<keyof ScoringWeights, string> = {
  financialValue: "Financial value",
  effort: "Effort / cost to deliver",
  strategicAlignment: "Strategic alignment",
  urgency: "Urgency & deadline",
  riskCompliance: "Risk / compliance",
  confidence: "Confidence",
};

const EFFORT_INVERSE_SCORE: Record<EffortSize, number> = {
  S: 100,
  M: 70,
  L: 40,
  XL: 15,
};

const CONFIDENCE_FACTOR: Record<string, number> = {
  Low: 0.4,
  Medium: 0.7,
  High: 1.0,
};

// Normalize an annual $ value into a 0-100 band using a log scale so that the
// difference between $10k and $100k is meaningful but it saturates at ~$10M.
function normalizeValue(annual: number, oneTime: number): number {
  const total = Math.max(0, annual) + Math.max(0, oneTime) * 0.3;
  if (total <= 0) return 0;
  const score = (Math.log10(total) - 3) * 25; // $1k → 0, $10M → 100
  return Math.max(0, Math.min(100, Math.round(score)));
}

function strategicScore(r: IntakeRequest): number {
  let s = 40;
  if (r.org === "Leadership") s += 30;
  if (r.org === "Regulatory" || r.org === "Risk & Compliance") s += 15;
  if (r.impactScope === "Platform-wide") s += 20;
  else if (r.impactScope === "Multi-team") s += 10;
  else if (r.impactScope === "External") s += 15;
  if (r.sponsor && r.sponsor.trim().length > 0) s += 10;
  return Math.max(0, Math.min(100, s));
}

function urgencyScore(r: IntakeRequest): number {
  const base: Record<string, number> = {
    Low: 20,
    Medium: 50,
    High: 75,
    Critical: 100,
  };
  let s = base[r.urgency ?? "Low"] ?? 20;
  if (r.hardDeadlineConsequence && r.hardDeadlineConsequence.trim().length > 0)
    s = Math.min(100, s + 10);
  return s;
}

function riskComplianceScore(r: IntakeRequest): number {
  let s = 20;
  if (r.org === "Regulatory") s = 95;
  else if (r.org === "Risk & Compliance") s = 85;
  if (r.financial.benefitType === "Loss avoidance") s = Math.max(s, 80);
  if (r.financial.benefitType === "Risk reduction") s = Math.max(s, 70);
  if (r.regulatoryCitation && r.regulatoryCitation.trim()) s = Math.max(s, 90);
  return Math.min(100, s);
}

export interface ScoreResult {
  roi: ROIAssessment;
  priority: PriorityRecommendation;
}

function effortMonths(size: EffortSize | null): number {
  switch (size) {
    case "S":
      return 1;
    case "M":
      return 3;
    case "L":
      return 6;
    case "XL":
      return 12;
    default:
      return 3;
  }
}

// Rough $ cost of delivery for payback estimation (synthetic blended rate).
function effortCost(size: EffortSize | null): number {
  return effortMonths(size) * 25000;
}

export function scoreRequest(
  r: IntakeRequest,
  backlog: BacklogItem[],
  weights: ScoringWeights = DEFAULT_WEIGHTS,
): ScoreResult {
  const annual = r.financial.estimatedAnnualValue ?? 0;
  const oneTime = r.financial.oneTimeValue ?? 0;
  const confFactor = CONFIDENCE_FACTOR[r.financial.confidence ?? "Medium"] ?? 0.7;

  // ---- per-factor raw scores (0-100) ----
  const raw = {
    financialValue: normalizeValue(annual, oneTime),
    effort: EFFORT_INVERSE_SCORE[r.financial.effortSize ?? "M"],
    strategicAlignment: strategicScore(r),
    urgency: urgencyScore(r),
    riskCompliance: riskComplianceScore(r),
    confidence: Math.round(confFactor * 100),
  };

  // ---- weighted contributions ----
  const factorBreakdown: Record<string, number> = {};
  let roiScore = 0;
  (Object.keys(weights) as (keyof ScoringWeights)[]).forEach((k) => {
    const contribution = Math.round(raw[k] * weights[k]);
    factorBreakdown[FACTOR_LABELS[k]] = contribution;
    roiScore += contribution;
  });
  roiScore = Math.max(0, Math.min(100, Math.round(roiScore)));

  // ---- plausibility flags ----
  const plausibilityFlags: string[] = [];
  if (annual > 0 && r.financial.basisOfEstimate.trim().length < 15) {
    plausibilityFlags.push(
      "Financial value asserted without a documented basis of estimate.",
    );
  }
  if (annual >= 5_000_000 && (r.financial.confidence ?? "Low") === "Low") {
    plausibilityFlags.push(
      "Very large annual value combined with Low confidence — treat as speculative.",
    );
  }
  if (r.financial.benefitType !== "None" && annual === 0 && oneTime === 0) {
    plausibilityFlags.push(
      "Benefit type declared but no quantified value provided.",
    );
  }

  // confidence-adjusted value
  const confidenceAdjustedValue = Math.round((annual + oneTime * 0.3) * confFactor);

  // payback period (months) using confidence-adjusted annual value
  const annualConf = annual * confFactor;
  const totalCost = effortCost(r.financial.effortSize) + Math.max(0, -annual);
  const paybackPeriodMonths =
    annualConf > 0 ? Math.round((totalCost / annualConf) * 12 * 10) / 10 : null;

  // ---- override rules (hard gates, PRD §7.3) ----
  let overrideApplied: string | null = null;
  let minBand: PriorityBand | null = null;
  let forceHuman = false;

  const isRegMandate =
    r.org === "Regulatory" ||
    !!(r.regulatoryCitation && r.regulatoryCitation.trim());
  const hasHardDeadline =
    r.neededByIsHard === true ||
    !!(r.hardDeadlineConsequence && r.hardDeadlineConsequence.trim());

  if (isRegMandate && hasHardDeadline) {
    overrideApplied =
      "Regulatory mandate with a hard deadline → minimum priority band High; cannot be auto-deferred.";
    minBand = "P1";
  } else if (
    r.org === "Risk & Compliance" &&
    (r.financial.benefitType === "Loss avoidance" ||
      (r.complianceReference && r.complianceReference.trim()))
  ) {
    overrideApplied =
      "Documented loss-avoidance / control gap from Risk & Compliance → escalate to human triage.";
    forceHuman = true;
    minBand = "P2";
  }
  if (r.urgency === "Critical") {
    overrideApplied =
      (overrideApplied ? overrideApplied + " " : "") +
      "Critical urgency → always routed to human review, never auto-deferred.";
    forceHuman = true;
    if (!minBand) minBand = "P2";
  }

  // ---- band from score ----
  let band = bandFromScore(roiScore);
  if (minBand && bandRank(minBand) < bandRank(band)) {
    band = minBand;
  }

  // ---- desirability ----
  let desirability: ROIAssessment["desirability"];
  if (roiScore >= 65) desirability = "high";
  else if (roiScore >= 40) desirability = "medium";
  else desirability = "low";
  // Overrides never allow low desirability to be silently deferred.
  if (overrideApplied && desirability === "low") desirability = "medium";

  // ---- rank in backlog ----
  const higher = backlog.filter((b) => b.roiScore > roiScore).length;
  const rankInBacklog = higher + 1;
  const neighborAbove = [...backlog]
    .sort((a, b) => b.roiScore - a.roiScore)
    .find((b) => b.roiScore <= roiScore);
  const comparisonNotes = buildComparisonNotes(
    roiScore,
    band,
    rankInBacklog,
    backlog.length,
    neighborAbove,
  );

  const rationale = buildRationale(
    r,
    roiScore,
    factorBreakdown,
    desirability,
    overrideApplied,
    paybackPeriodMonths,
  );

  return {
    roi: {
      roiScore,
      factorBreakdown,
      estimatedAnnualValue: annual,
      paybackPeriodMonths,
      confidenceAdjustedValue,
      plausibilityFlags,
      desirability,
      rationale,
    },
    priority: {
      recommendedBand: band,
      rankInBacklog,
      overrideApplied,
      comparisonNotes,
    },
    // forceHuman is surfaced via the orchestrator below.
    ...({ forceHuman } as object),
  } as ScoreResult & { forceHuman: boolean };
}

export function bandFromScore(score: number): PriorityBand {
  if (score >= 80) return "P0";
  if (score >= 65) return "P1";
  if (score >= 45) return "P2";
  if (score >= 30) return "P3";
  return "Defer";
}

export function bandRank(b: PriorityBand): number {
  return { P0: 0, P1: 1, P2: 2, P3: 3, Defer: 4 }[b];
}

function buildComparisonNotes(
  roiScore: number,
  band: PriorityBand,
  rank: number,
  total: number,
  neighborAbove?: BacklogItem,
): string {
  const parts: string[] = [];
  parts.push(
    `Scores ${roiScore}/100, ranking #${rank} of ${total + 1} against the current intake queue.`,
  );
  if (neighborAbove) {
    parts.push(
      `Ranks just below "${neighborAbove.title}" (${neighborAbove.roiScore}/100, ${neighborAbove.band}).`,
    );
  }
  if (band === "Defer") {
    parts.push(
      "Falls below the threshold where the platform team can commit capacity ahead of higher-value work.",
    );
  }
  return parts.join(" ");
}

function buildRationale(
  r: IntakeRequest,
  roiScore: number,
  breakdown: Record<string, number>,
  desirability: string,
  override: string | null,
  payback: number | null,
): string {
  const top = Object.entries(breakdown)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([k]) => k.toLowerCase());
  const annual = r.financial.estimatedAnnualValue ?? 0;
  const lines: string[] = [];
  lines.push(
    `Composite ROI score of ${roiScore}/100 (${desirability} desirability), driven primarily by ${top.join(" and ")}.`,
  );
  if (annual > 0) {
    lines.push(
      `Requestor estimates ${formatUSD(annual)} annual ${r.financial.benefitType.toLowerCase()} at ${r.financial.confidence ?? "unknown"} confidence.`,
    );
  } else {
    lines.push("No quantified annual financial benefit was provided.");
  }
  if (payback !== null) {
    lines.push(`Estimated payback period ≈ ${payback} months (confidence-adjusted).`);
  }
  if (override) {
    lines.push(`Override: ${override}`);
  }
  return lines.join(" ");
}

export function formatUSD(n: number): string {
  if (n === 0) return "$0";
  const abs = Math.abs(n);
  if (abs >= 1_000_000)
    return `${n < 0 ? "-" : ""}$${(abs / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000)
    return `${n < 0 ? "-" : ""}$${(abs / 1_000).toFixed(abs >= 100_000 ? 0 : 0)}k`;
  return `${n < 0 ? "-" : ""}$${abs}`;
}
