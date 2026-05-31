// Agent 3 — Documentation Agent (PRD §8).
// Builds a well-formed Jira story payload and "writes" it via a Jira adapter.
// In the client-only deployment the adapter simulates the MCP write and
// returns an issue key; the production backend swaps in the real Jira MCP tool.

import type { RequestRecord, JiraLink } from "./types";
import { formatUSD } from "./scoring";

const PERSONA_BY_ORG: Record<string, string> = {
  "Business line": "commercial banking business line",
  Accounting: "accounting & finance operations team member",
  Regulatory: "regulatory liaison",
  "Risk & Compliance": "risk & compliance officer",
  "Legacy platform": "legacy platform engineer",
  Leadership: "commercial banking leadership sponsor",
};

export interface JiraStory {
  summary: string;
  issueType: "Story";
  description: string;
  priority: string;
  labels: string[];
  components: string[];
  customFields: Record<string, string | number>;
}

export function buildStory(rec: RequestRecord): JiraStory {
  const f = rec.fields;
  const roi = rec.roi!;
  const pr = rec.priority!;
  const persona = PERSONA_BY_ORG[f.org ?? ""] ?? "requestor";

  const summary = `[SCF Intake] ${normalizeTitle(f.title)}`;

  const description = [
    "h2. User story",
    `As a ${persona},`,
    `I want ${deriveCapability(f.title, f.businessJustification)},`,
    `so that ${deriveBenefit(f.businessJustification)}.`,
    "",
    "h2. Business justification",
    f.businessJustification,
    "",
    "h2. Impact & scope",
    `${f.impact}`,
    `Scope: ${f.impactScope ?? "n/a"}.`,
    "",
    "h2. Financial outcome / ROI",
    `Benefit type: ${f.financial.benefitType}`,
    `Estimated annual value: ${formatUSD(f.financial.estimatedAnnualValue ?? 0)} (${f.financial.confidence ?? "n/a"} confidence)`,
    f.financial.oneTimeValue
      ? `One-time value/cost: ${formatUSD(f.financial.oneTimeValue)}`
      : "",
    `ROI score: ${roi.roiScore}/100${roi.paybackPeriodMonths !== null ? `, payback ≈ ${roi.paybackPeriodMonths} months` : ""}`,
    `Basis of estimate: ${f.financial.basisOfEstimate || "not provided"}`,
    "",
    "h2. Alternative considered",
    f.alternativeApproach,
    "",
    "h2. Priority rationale",
    pr.comparisonNotes,
    pr.overrideApplied ? `Override applied: ${pr.overrideApplied}` : "",
    roi.rationale,
    regulatoryBlock(rec),
    "",
    "h2. Acceptance criteria",
    ...buildAcceptanceCriteria(rec),
  ]
    .filter((l) => l !== "")
    .join("\n");

  const labels = [
    "scf-intake",
    `org-${slug(f.org ?? "unknown")}`,
    `urgency-${(f.urgency ?? "low").toLowerCase()}`,
  ];

  return {
    summary,
    issueType: "Story",
    description,
    priority: mapPriority(pr.recommendedBand),
    labels,
    components: ["Supply Chain Finance"],
    customFields: {
      intake_id: rec.requestId,
      roi_score: roi.roiScore,
      needed_by: f.neededBy,
      requestor: f.requestorName,
    },
  };
}

// Simulated Jira MCP write. In production this calls the Jira MCP tool.
// Returns a JiraLink; can deterministically "fail" to exercise retry handling.
export function writeToJira(
  rec: RequestRecord,
  opts: { forceFail?: boolean } = {},
): JiraLink {
  const attempts = (rec.jira?.attempts ?? 0) + 1;
  if (opts.forceFail) {
    return {
      issueKey: "",
      url: "",
      writeStatus: "failed",
      attempts,
    };
  }
  // Derive a stable, synthetic issue key from the intake id.
  const num = rec.requestId.replace(/\D/g, "").slice(-4) || "0001";
  const issueKey = `SCF-${num}`;
  return {
    issueKey,
    url: `https://jira.example.com/browse/${issueKey}`,
    writeStatus: "written",
    attempts,
  };
}

function mapPriority(band: string): string {
  return (
    {
      P0: "Highest",
      P1: "High",
      P2: "Medium",
      P3: "Low",
      Defer: "Lowest",
    }[band] ?? "Medium"
  );
}

function buildAcceptanceCriteria(rec: RequestRecord): string[] {
  const f = rec.fields;
  const ac: string[] = [];
  ac.push(
    `* Given ${f.impactScope ?? "the affected"} users, when the change ships, then ${deriveBenefit(f.businessJustification)}.`,
  );
  if ((f.financial.estimatedAnnualValue ?? 0) > 0) {
    ac.push(
      `* Given the stated financial benefit, when delivered, then the realized ${f.financial.benefitType.toLowerCase()} is measurable against a baseline.`,
    );
  }
  if (f.org === "Regulatory" && f.regulatoryCitation) {
    ac.push(
      `* Given regulatory citation ${f.regulatoryCitation}, when the deadline arrives, then the obligation is demonstrably met.`,
    );
  }
  if (f.org === "Risk & Compliance" && f.complianceReference) {
    ac.push(
      `* Given control ${f.complianceReference}, when the change is live, then the control gap is closed and evidenced.`,
    );
  }
  return ac;
}

function regulatoryBlock(rec: RequestRecord): string {
  const f = rec.fields;
  const parts: string[] = [];
  if (f.regulatoryCitation) parts.push(`Regulatory citation: ${f.regulatoryCitation}`);
  if (f.complianceReference) parts.push(`Control reference: ${f.complianceReference}`);
  if (f.hardDeadlineConsequence)
    parts.push(`Hard deadline consequence: ${f.hardDeadlineConsequence}`);
  if (parts.length === 0) return "";
  return "\nh2. Regulatory / compliance refs\n" + parts.join("\n");
}

function normalizeTitle(t: string): string {
  const trimmed = t.trim().replace(/\s+/g, " ");
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

function deriveCapability(title: string, just: string): string {
  const base = title.trim().toLowerCase();
  if (base.length > 8) return base;
  const firstClause = just.split(/[.;\n]/)[0]?.trim().toLowerCase();
  return firstClause || "the capability described";
}

function deriveBenefit(just: string): string {
  const m = just.match(/so that (.+)/i);
  if (m) return m[1].trim().replace(/[.]+$/, "");
  const firstClause = just.split(/[.;\n]/)[0]?.trim();
  return (firstClause || "the business outcome is achieved")
    .replace(/[.]+$/, "")
    .toLowerCase();
}

function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
