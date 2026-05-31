// A small set of pre-processed example requests so the triage dashboard is
// populated on first load. Synthetic data only (PRD regulated-env guardrails).

import type {
  RequestRecord,
  IntakeRequest,
  BacklogItem,
  RequestStatus,
  ChatMessage,
} from "../domain/types";
import { emptyIntake, completenessScore } from "../domain/schema";
import { justify, draftDeferralEmail, draftAcceptanceEmail } from "../domain/justificationAgent";
import { buildStory, writeToJira } from "../domain/documentationAgent";
import { nowISO } from "../domain/validationAgent";

let mid = 0;
const m = (): string => `seed-${mid++}`;

function chat(role: ChatMessage["role"], content: string, agent?: string): ChatMessage {
  return { id: m(), role, content, ts: nowISO(), agent };
}

function make(
  id: string,
  status: RequestStatus,
  fields: IntakeRequest,
  daysAgo: number,
): RequestRecord {
  const created = new Date(Date.now() - daysAgo * 86400000).toISOString();
  const rec: RequestRecord = {
    requestId: id,
    status,
    createdAt: created,
    updatedAt: created,
    fields,
    conversation: [
      chat("agent", "Hi — I'm the SCF intake assistant. Let's structure your request.", "Validation"),
      chat("requestor", fields.businessJustification),
      chat("agent", `Captured everything I need — ${completenessScore(fields)}% complete and validated.`, "Validation"),
    ],
    missingFields: [],
    completenessScore: completenessScore(fields),
    clarificationRounds: 2,
    roi: null,
    priority: null,
    decision: null,
    emailDraft: null,
    jira: null,
    duplicateOf: null,
    auditTrail: [
      { ts: created, actor: "system", action: "Intake started", detail: `request_id ${id}` },
      { ts: created, actor: "agent", agent: "Validation", action: "Validation complete" },
    ],
  };
  return rec;
}

export function buildSeedRequests(backlog: BacklogItem[]): RequestRecord[] {
  const out: RequestRecord[] = [];

  // 1) Accepted & written to Jira — strong, quantified, low effort.
  {
    const f = emptyIntake();
    f.title = "Auto-match buyer remittances to open factored invoices";
    f.requestorName = "Dana Whitfield";
    f.requestorEmail = "dana.whitfield@example-bank.com";
    f.org = "Accounting";
    f.businessJustification =
      "Our ops team manually matches ~4,000 buyer remittance lines a month to open factored invoices. It's error-prone and eats two FTEs. An auto-match with tolerance rules would clear the bulk automatically and flag only exceptions.";
    f.impact =
      "Affects the SCF reconciliation desk (6 analysts) and downstream GL posting; removes a recurring month-end bottleneck.";
    f.impactScope = "Multi-team";
    f.financial = {
      benefitType: "Cost reduction",
      estimatedAnnualValue: 340000,
      oneTimeValue: 0,
      effortSize: "M",
      confidence: "High",
      basisOfEstimate:
        "Two FTEs at fully-loaded ~$140k plus a measured 18% error-rework cost from the last two quarters.",
    };
    f.alternativeApproach =
      "Considered outsourcing the matching (rejected on data-residency) and doing nothing (rejected — volume is growing 12% YoY).";
    f.neededBy = "End of Q3";
    f.neededByIsHard = false;
    f.urgency = "Medium";
    f.urgencyJustification = "Growing volume but no hard deadline.";
    const rec = make("SCF-INTK-000118", "WRITTEN_TO_JIRA", f, 9);
    const { roi, priority } = justify(rec, backlog);
    rec.roi = roi;
    rec.priority = priority;
    rec.decision = "accept";
    const link = writeToJira(rec);
    rec.jira = link;
    buildStory(rec); // exercise story generation
    rec.emailDraft = draftAcceptanceEmail(rec);
    rec.status = "CLOSED";
    rec.auditTrail.push(
      { ts: rec.createdAt, actor: "agent", agent: "Justification", action: "ROI scored", detail: `score ${roi.roiScore}` },
      { ts: rec.createdAt, actor: "agent", agent: "Documentation", action: "Wrote to Jira", detail: link.issueKey },
    );
    out.push(rec);
  }

  // 2) Regulatory with hard deadline — override → awaiting triage.
  {
    const f = emptyIntake();
    f.title = "Basel III RWA field for receivables-financing exposures";
    f.requestorName = "Priya Nair";
    f.requestorEmail = "priya.nair@example-bank.com";
    f.org = "Regulatory";
    f.businessJustification =
      "The latest regulatory guidance requires we report risk-weighted assets for receivables-financing exposures separately. Our current extract bundles them, which will fail the next supervisory review.";
    f.impact =
      "Affects regulatory reporting and the platform data warehouse extract; non-compliance risks a supervisory finding.";
    f.impactScope = "Platform-wide";
    f.financial = {
      benefitType: "Risk reduction",
      estimatedAnnualValue: 0,
      oneTimeValue: 0,
      effortSize: "L",
      confidence: "High",
      basisOfEstimate: "Mandate — value is avoidance of a supervisory finding rather than a dollar benefit.",
    };
    f.alternativeApproach =
      "Manual quarterly workaround considered but rejected as unsustainable and audit-fragile.";
    f.neededBy = "2026-09-30";
    f.neededByIsHard = true;
    f.urgency = "High";
    f.urgencyJustification = "Regulatory deadline tied to the next reporting cycle.";
    f.regulatoryCitation = "Basel III finalization — CRE receivables RWA, eff. 2026-09-30";
    f.hardDeadlineConsequence =
      "Missing the date means filing a non-compliant return and a likely Matter Requiring Attention.";
    const rec = make("SCF-INTK-000120", "AWAITING_TRIAGE", f, 3);
    const { roi, priority } = justify(rec, backlog);
    rec.roi = roi;
    rec.priority = priority;
    rec.decision = "needs_human";
    rec.auditTrail.push(
      { ts: rec.createdAt, actor: "agent", agent: "Justification", action: "ROI scored", detail: `score ${roi.roiScore}` },
      { ts: rec.createdAt, actor: "agent", agent: "Justification", action: "Override applied", detail: priority.overrideApplied ?? "" },
      { ts: rec.createdAt, actor: "agent", agent: "Justification", action: "Routed to human review" },
    );
    out.push(rec);
  }

  // 3) Low value, no override — deferred with a drafted email.
  {
    const f = emptyIntake();
    f.title = "Custom emoji reactions on the agent decision feed";
    f.requestorName = "Marco Reyes";
    f.requestorEmail = "marco.reyes@example-bank.com";
    f.org = "Business line";
    f.businessJustification =
      "It would be fun if the team could react to agent decisions with custom emojis in the console feed to make reviews feel more engaging.";
    f.impact = "Cosmetic; affects the relationship-manager console UI only.";
    f.impactScope = "Single team";
    f.financial = {
      benefitType: "None",
      estimatedAnnualValue: 0,
      oneTimeValue: 0,
      effortSize: "M",
      confidence: "Low",
      basisOfEstimate: "No quantified benefit identified.",
    };
    f.alternativeApproach = "Could use existing comment field; doing nothing has no operational impact.";
    f.neededBy = "No particular date";
    f.neededByIsHard = false;
    f.urgency = "Low";
    f.urgencyJustification = "Nice-to-have.";
    const rec = make("SCF-INTK-000119", "DEFERRED", f, 6);
    const { roi, priority } = justify(rec, backlog);
    rec.roi = roi;
    rec.priority = priority;
    rec.decision = "defer";
    rec.emailDraft = draftDeferralEmail(rec);
    rec.auditTrail.push(
      { ts: rec.createdAt, actor: "agent", agent: "Justification", action: "ROI scored", detail: `score ${roi.roiScore}` },
      { ts: rec.createdAt, actor: "agent", agent: "Justification", action: "Deferral email drafted (draft-only)" },
      { ts: rec.createdAt, actor: "system", action: "Request deferred", detail: "no Jira issue created" },
    );
    out.push(rec);
  }

  return out;
}
