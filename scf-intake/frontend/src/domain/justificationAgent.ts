// Agent 2 — Business Justification Agent (PRD §7).
// Wraps the transparent scoring engine, applies routing, and drafts the
// (draft-only) deferral / acceptance emails. Never sends mail.

import type {
  RequestRecord,
  EmailDraft,
  BacklogItem,
  ROIAssessment,
  PriorityRecommendation,
} from "./types";
import { scoreRequest, formatUSD, type ScoringWeights } from "./scoring";

export interface JustificationResult {
  roi: ROIAssessment;
  priority: PriorityRecommendation;
  decision: "accept" | "defer" | "needs_human";
  forceHuman: boolean;
}

export function justify(
  rec: RequestRecord,
  backlog: BacklogItem[],
  weights?: ScoringWeights,
): JustificationResult {
  const result = scoreRequest(rec.fields, backlog, weights) as ReturnType<
    typeof scoreRequest
  > & { forceHuman: boolean };

  const { roi, priority } = result;
  const forceHuman = !!result.forceHuman;

  let decision: "accept" | "defer" | "needs_human";
  if (forceHuman) {
    decision = "needs_human";
  } else if (roi.desirability === "low" && !priority.overrideApplied) {
    decision = "defer";
  } else if (roi.desirability === "medium" && priority.recommendedBand === "P3") {
    // Borderline → ask a human to confirm.
    decision = "needs_human";
  } else {
    decision = "accept";
  }

  return { roi, priority, decision, forceHuman };
}

export function draftDeferralEmail(rec: RequestRecord): EmailDraft {
  const f = rec.fields;
  const roi = rec.roi!;
  const pr = rec.priority!;
  const subject = `Update on your SCF intake request: ${f.title} (${rec.requestId})`;

  const annual = f.financial.estimatedAnnualValue ?? 0;
  const valueLine =
    annual > 0
      ? `a projected ${formatUSD(annual)} annual ${f.financial.benefitType.toLowerCase()}`
      : "the benefit as currently described";

  const body = `Hi ${f.requestorName || "there"},

Thank you for taking the time to submit your request "${f.title}" to the Supply Chain Finance platform intake. I've reviewed it carefully alongside the rest of the current backlog.

What you asked for
${oneLine(f.businessJustification)}

Where it stands today
Based on ${valueLine} and an estimated effort of ${f.financial.effortSize ?? "unscoped"}, the request scored ${roi.roiScore}/100 on our transparent prioritization model and currently ranks #${pr.rankInBacklog} in the queue. ${pr.comparisonNotes}

For full transparency, the priority recommendation is "${pr.recommendedBand}". Given the volume of higher-value and time-sensitive work ahead of it, we are not able to schedule this item right now. This is a deferral, not a rejection — the request stays on file.

What would move it up
${reconsiderationConditions(rec)}

If any of the above changes, just reply and we'll happily re-score it. I appreciate your patience and the thought you put into the submission.

Best regards,
SCF Platform Triage
(Drafted by the Business Justification agent — reviewed and sent by a human.)`;

  return {
    type: "deferral",
    to: f.requestorEmail,
    subject,
    body,
    status: "draft",
  };
}

export function draftAcceptanceEmail(rec: RequestRecord): EmailDraft {
  const f = rec.fields;
  const pr = rec.priority!;
  const jiraLine = rec.jira
    ? `It has been logged as ${rec.jira.issueKey} and added to the platform backlog.`
    : "It has been accepted and is being written to the platform backlog.";
  const subject = `Accepted: ${f.title} (${rec.requestId})`;
  const body = `Hi ${f.requestorName || "there"},

Good news — your Supply Chain Finance platform request "${f.title}" has been accepted.

${jiraLine}

Recommended priority: ${pr.recommendedBand} (ranked #${pr.rankInBacklog} in the current queue).
${pr.overrideApplied ? `Note: ${pr.overrideApplied}` : ""}

You'll be able to track delivery progress in Jira. Thank you for the clear, well-quantified submission — it made qualification fast.

Best regards,
SCF Platform Triage
(Drafted by the agent — reviewed and sent by a human.)`;
  return { type: "acceptance", to: f.requestorEmail, subject, body, status: "draft" };
}

function reconsiderationConditions(rec: RequestRecord): string {
  const f = rec.fields;
  const conds: string[] = [];
  if ((f.financial.estimatedAnnualValue ?? 0) === 0) {
    conds.push(
      "• A quantified financial benefit (annual value + how it was derived) would materially raise the score.",
    );
  }
  if (f.financial.confidence === "Low") {
    conds.push(
      "• Firming up the estimate confidence with supporting data would reduce the speculative discount we applied.",
    );
  }
  if (!f.sponsor) {
    conds.push(
      "• A named leadership sponsor would strengthen the strategic-alignment factor.",
    );
  }
  conds.push(
    "• A regulatory, compliance, or hard-deadline driver, if one emerges, would trigger an automatic re-prioritization.",
  );
  return conds.join("\n");
}

function oneLine(s: string): string {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length > 280 ? t.slice(0, 277) + "…" : t;
}
