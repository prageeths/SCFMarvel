// Client-side orchestrator — mirrors the LangGraph state machine (PRD §5).
// Pure functions operate on a RequestRecord and return a new record plus any
// chat/audit side-effects. The same node sequence (validate → ask_human →
// justify → decision_gate → human_review → document/draft_email → finalize)
// is implemented here so the deployed SPA is fully functional without a server.

import type {
  RequestRecord,
  IntakeRequest,
  ChatMessage,
  AuditEntry,
  Actor,
  BacklogItem,
} from "./types";
import { emptyIntake, completenessScore, missingFields } from "./schema";
import {
  parseInitialSubmission,
  planNextQuestion,
  buildAgentQuestion,
  applyAnswer,
  detectDuplicate,
  newMsgId,
  nowISO,
  MAX_CLARIFICATION_ROUNDS,
} from "./validationAgent";
import { justify, draftDeferralEmail, draftAcceptanceEmail } from "./justificationAgent";
import { buildStory, writeToJira } from "./documentationAgent";

let _seq = 122; // continues after the seeded backlog ids
export function nextRequestId(): string {
  _seq += 1;
  return `SCF-INTK-${String(_seq).padStart(6, "0")}`;
}

function audit(
  rec: RequestRecord,
  actor: Actor,
  action: string,
  detail?: string,
  agent?: string,
): void {
  const entry: AuditEntry = { ts: nowISO(), actor, action, detail, agent };
  rec.auditTrail.push(entry);
}

function agentMsg(content: string, agent: string, chips?: string[], field?: string): ChatMessage {
  return { id: newMsgId(), role: "agent", agent, content, ts: nowISO(), chips, field };
}

function systemMsg(content: string): ChatMessage {
  return { id: newMsgId(), role: "system", content, ts: nowISO() };
}

// ---------------------------------------------------------------------------
// start node
// ---------------------------------------------------------------------------
export function startIntake(
  initialText: string,
  existing: RequestRecord[],
  backlog: BacklogItem[],
): RequestRecord {
  const id = nextRequestId();
  const fields: IntakeRequest = parseInitialSubmission(initialText, emptyIntake());
  const rec: RequestRecord = {
    requestId: id,
    status: "VALIDATING",
    createdAt: nowISO(),
    updatedAt: nowISO(),
    fields,
    conversation: [],
    missingFields: [],
    completenessScore: 0,
    clarificationRounds: 0,
    roi: null,
    priority: null,
    decision: null,
    emailDraft: null,
    jira: null,
    duplicateOf: null,
    auditTrail: [],
  };

  rec.conversation.push(
    agentMsg(
      "Hi — I'm the SCF intake assistant. I'll turn your request into a complete, structured submission and help the platform team prioritize it fairly. Let me see what you've given me so far…",
      "Validation",
    ),
  );
  rec.conversation.push({
    id: newMsgId(),
    role: "requestor",
    content: initialText,
    ts: nowISO(),
  });
  audit(rec, "system", "Intake started", `request_id ${id} created`, undefined);
  audit(rec, "agent", "Parsed initial submission", undefined, "Validation");

  // Duplicate check on the opening submission.
  const dup = detectDuplicate(
    fields,
    existing.map((e) => ({ requestId: e.requestId, title: e.fields.title })),
    backlog,
  );
  if (dup) {
    rec.duplicateOf = dup;
    rec.conversation.push(
      agentMsg(
        `Heads up — this looks similar to an existing request, ${dup.requestId} "${dup.title}" (≈${Math.round(dup.similarity * 100)}% overlap). I'll keep going, but the triage lead may choose to merge them. Let me know if you'd rather link to that one.`,
        "Validation",
      ),
    );
    audit(rec, "agent", "Possible duplicate detected", `${dup.requestId} (${Math.round(dup.similarity * 100)}%)`, "Validation");
  }

  return validateStep(rec);
}

// ---------------------------------------------------------------------------
// validate node (+ ask_human interrupt)
// ---------------------------------------------------------------------------
function validateStep(rec: RequestRecord): RequestRecord {
  rec.completenessScore = completenessScore(rec.fields);
  rec.missingFields = missingFields(rec.fields).map((m) => m.key);

  if (rec.missingFields.length === 0) {
    rec.status = "VALIDATED";
    rec.conversation.push(
      agentMsg(
        `That's everything I need — your submission is ${rec.completenessScore}% complete and validated. Handing off to the Business Justification agent to score it against the current backlog…`,
        "Validation",
      ),
    );
    audit(rec, "agent", "Validation complete", `completeness ${rec.completenessScore}`, "Validation");
    rec.updatedAt = nowISO();
    return scoreStep(rec);
  }

  // Cap rounds → escalate (PRD §6.3 rule 5 / §6.5)
  if (rec.clarificationRounds >= MAX_CLARIFICATION_ROUNDS) {
    rec.status = "NEEDS_MORE_INFO";
    rec.conversation.push(
      agentMsg(
        "We've gone a few rounds and a couple of required details are still missing. I'm escalating this to a human triage lead so we don't keep you here — they'll follow up directly. Thank you for your patience.",
        "Validation",
      ),
    );
    audit(rec, "agent", "Max clarification rounds reached → escalated", rec.missingFields.join(", "), "Validation");
    rec.updatedAt = nowISO();
    return rec;
  }

  // ask_human: pose the next focused question.
  const plan = planNextQuestion(rec);
  if (plan) {
    rec.status = "AWAITING_REQUESTOR";
    rec.conversation.push(buildAgentQuestion(plan));
    audit(rec, "agent", "Asked clarification", `${plan.field}: ${plan.reason}`, "Validation");
  }
  rec.updatedAt = nowISO();
  return rec;
}

// ---------------------------------------------------------------------------
// requestor reply → resume graph at validate
// ---------------------------------------------------------------------------
export function handleRequestorMessage(rec: RequestRecord, text: string): RequestRecord {
  const next = structuredClone(rec);
  next.conversation.push({ id: newMsgId(), role: "requestor", content: text, ts: nowISO() });

  // Find the field the last agent question targeted.
  const lastQuestion = [...next.conversation]
    .reverse()
    .find((m) => m.role === "agent" && m.field);
  const targetField = lastQuestion?.field;

  const prevCompleteness = completenessScore(next.fields);

  if (targetField) {
    const { fields, note } = applyAnswer(next.fields, targetField, text);
    next.fields = fields;
    audit(next, "requestor", "Answered", targetField, undefined);
    if (note) {
      next.conversation.push(agentMsg(note, "Validation"));
      audit(next, "agent", "Recorded value", note, "Validation");
    }
  } else {
    // No targeted question — append to justification context.
    next.fields.businessJustification = (
      next.fields.businessJustification +
      "\n" +
      text
    ).trim();
    audit(next, "requestor", "Added context", undefined, undefined);
  }

  // Only count *unproductive* rounds toward the escalation cap, so a normal
  // multi-field intake never escalates while the requestor makes progress.
  if (completenessScore(next.fields) > prevCompleteness) {
    next.clarificationRounds = 0;
  } else {
    next.clarificationRounds += 1;
  }
  return validateStep(next);
}

// ---------------------------------------------------------------------------
// justify node + decision_gate
// ---------------------------------------------------------------------------
function scoreStep(rec: RequestRecord, backlog?: BacklogItem[]): RequestRecord {
  rec.status = "SCORING";
  const bl = backlog ?? CURRENT_BACKLOG;
  const { roi, priority, decision } = justify(rec, bl);
  rec.roi = roi;
  rec.priority = priority;
  rec.decision = decision;
  audit(
    rec,
    "agent",
    "ROI scored",
    `score ${roi.roiScore}, band ${priority.recommendedBand}, desirability ${roi.desirability}`,
    "Justification",
  );
  if (priority.overrideApplied) {
    audit(rec, "agent", "Override applied", priority.overrideApplied, "Justification");
  }
  roi.plausibilityFlags.forEach((flag) =>
    audit(rec, "agent", "Plausibility flag", flag, "Justification"),
  );

  // decision_gate routing
  if (decision === "needs_human") {
    rec.status = "AWAITING_TRIAGE";
    rec.conversation.push(
      agentMsg(
        `I've scored this at ${roi.roiScore}/100 (band ${priority.recommendedBand}). Because it's ${priority.overrideApplied ? "flagged for mandatory review" : "borderline"}, a platform triage lead will confirm the call before anything is written to Jira. You'll hear back shortly.`,
        "Justification",
      ),
    );
    audit(rec, "agent", "Routed to human review", "decision_gate → human_review", "Justification");
  } else if (decision === "accept") {
    return documentStep(rec);
  } else if (decision === "defer") {
    return draftEmailStep(rec);
  }
  rec.updatedAt = nowISO();
  return rec;
}

// ---------------------------------------------------------------------------
// human_review interrupt (triage decision)
// ---------------------------------------------------------------------------
export function applyTriageDecision(
  rec: RequestRecord,
  decision: "accept" | "defer" | "needs_info",
  note: string,
): RequestRecord {
  const next = structuredClone(rec);
  next.triageNote = note;
  audit(next, "human", `Triage decision: ${decision}`, note || undefined, undefined);

  if (decision === "accept") {
    next.decision = "accept";
    return documentStep(next);
  }
  if (decision === "defer") {
    next.decision = "defer";
    return draftEmailStep(next);
  }
  // needs_info → send back to requestor
  next.decision = "needs_human";
  next.status = "NEEDS_MORE_INFO";
  next.conversation.push(
    agentMsg(
      `The triage lead would like a bit more detail before deciding${note ? `: ${note}` : "."}`,
      "Validation",
    ),
  );
  next.updatedAt = nowISO();
  return next;
}

// ---------------------------------------------------------------------------
// document node → Jira write → finalize
// ---------------------------------------------------------------------------
function documentStep(rec: RequestRecord, forceFail = false): RequestRecord {
  rec.status = "DOCUMENTING";
  rec.decision = "accept";
  const story = buildStory(rec);
  audit(rec, "agent", "Story composed", story.summary, "Documentation");

  const link = writeToJira(rec, { forceFail });
  rec.jira = link;

  if (link.writeStatus === "written") {
    rec.status = "WRITTEN_TO_JIRA";
    audit(rec, "agent", "Wrote to Jira", `${link.issueKey} (attempt ${link.attempts})`, "Documentation");
    rec.emailDraft = draftAcceptanceEmail(rec);
    audit(rec, "agent", "Acceptance email drafted (draft-only)", rec.emailDraft.subject, "Justification");
    rec.conversation.push(
      agentMsg(
        `Accepted and logged as ${link.issueKey}. You can track it in Jira: ${link.url}. An acceptance note has been drafted for a human to review and send. Thanks again!`,
        "Documentation",
      ),
    );
    rec.status = "CLOSED";
    audit(rec, "system", "Request closed", "accepted & written to Jira", undefined);
  } else {
    // Jira write failed — never lose the request (PRD §8.5)
    rec.conversation.push(
      systemMsg(
        `The Jira write failed (attempt ${link.attempts}). The request is safe and a human has been notified to retry — nothing was lost.`,
      ),
    );
    audit(rec, "agent", "Jira write failed", `attempt ${link.attempts}; payload preserved`, "Documentation");
  }
  rec.updatedAt = nowISO();
  return rec;
}

export function retryJira(rec: RequestRecord): RequestRecord {
  const next = structuredClone(rec);
  audit(next, "human", "Manual Jira retry requested", undefined, undefined);
  return documentStep(next, false);
}

// For demonstrating retry handling from the UI.
export function simulateJiraFailure(rec: RequestRecord): RequestRecord {
  const next = structuredClone(rec);
  return documentStep(next, true);
}

// ---------------------------------------------------------------------------
// draft_email node (deferral) → finalize
// ---------------------------------------------------------------------------
function draftEmailStep(rec: RequestRecord): RequestRecord {
  rec.decision = "defer";
  rec.status = "DEFERRED";
  rec.emailDraft = draftDeferralEmail(rec);
  audit(rec, "agent", "Deferral email drafted (draft-only)", rec.emailDraft.subject, "Justification");
  rec.conversation.push(
    agentMsg(
      `After scoring this against the current backlog, it isn't one we can schedule right now (score ${rec.roi?.roiScore}/100). I've drafted a respectful explanation for the team to review and send — this is a deferral, not a rejection, and it stays on file. ${rec.priority?.comparisonNotes ?? ""}`,
      "Justification",
    ),
  );
  audit(rec, "system", "Request deferred", "no Jira issue created", undefined);
  rec.updatedAt = nowISO();
  return rec;
}

// Mark an email draft as sent by a human (the system never auto-sends).
export function markEmailSentByHuman(rec: RequestRecord): RequestRecord {
  const next = structuredClone(rec);
  if (next.emailDraft) {
    next.emailDraft.status = "sent_by_human";
    audit(next, "human", "Email sent by human", next.emailDraft.subject, undefined);
    next.updatedAt = nowISO();
  }
  return next;
}

// A module-level backlog reference so scoreStep can run after async validation
// without threading the backlog through every call. The store sets this once.
export let CURRENT_BACKLOG: BacklogItem[] = [];
export function setBacklog(b: BacklogItem[]): void {
  CURRENT_BACKLOG = b;
}
