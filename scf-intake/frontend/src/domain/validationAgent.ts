// Agent 1 — Intake Validation Agent (PRD §6).
// A deterministic, transparent conversational engine that turns a vague
// submission into a complete, credible, structured IntakeRequest. It asks for
// only what is missing/weak, one or two things at a time, and never invents
// values. (The production backend can swap this for an LLM-backed node behind
// the same interface; the OpenAI adapter is optional by design.)

import type {
  IntakeRequest,
  ChatMessage,
  OriginatingOrg,
  ImpactScope,
  Urgency,
  BenefitType,
  EffortSize,
  Confidence,
  DuplicateMatch,
  BacklogItem,
  RequestRecord,
} from "./types";
import {
  ORGS,
  IMPACT_SCOPES,
  URGENCIES,
  BENEFIT_TYPES,
  EFFORT_SIZES,
  CONFIDENCE_LEVELS,
  isVague,
  missingFields,
} from "./schema";

export const MAX_CLARIFICATION_ROUNDS = 8;

let _id = 0;
export function newMsgId(): string {
  _id += 1;
  return `m${Date.now().toString(36)}-${_id}`;
}

export function nowISO(): string {
  return new Date().toISOString();
}

// ---------------------------------------------------------------------------
// Initial free-text parsing — pre-fill whatever we can from the opening message
// ---------------------------------------------------------------------------
export function parseInitialSubmission(
  text: string,
  base: IntakeRequest,
): IntakeRequest {
  const f: IntakeRequest = structuredClone(base);
  const t = text.trim();

  // Title: first sentence / line, trimmed.
  const firstLine = t.split(/[\n.]/)[0]?.trim() ?? "";
  if (!f.title && firstLine.length >= 4) {
    f.title = firstLine.length > 90 ? firstLine.slice(0, 90) : firstLine;
  }
  // The whole thing seeds the business justification.
  if (!f.businessJustification && t.length >= 25) {
    f.businessJustification = t;
  }

  // Org keyword detection.
  const org = detectOrg(t);
  if (org && !f.org) f.org = org;

  // Urgency keyword detection.
  const urg = detectUrgency(t);
  if (urg && !f.urgency) f.urgency = urg;

  // Money detection → estimated annual value.
  const money = detectMoney(t);
  if (money !== null && f.financial.estimatedAnnualValue === null) {
    f.financial.estimatedAnnualValue = money;
    if (f.financial.benefitType === "None") {
      f.financial.benefitType = detectBenefitType(t) ?? "Cost reduction";
    }
  }
  const bt = detectBenefitType(t);
  if (bt && f.financial.benefitType === "None") f.financial.benefitType = bt;

  // Email detection.
  const email = t.match(/[\w.+-]+@[\w-]+\.[\w.-]+/);
  if (email && !f.requestorEmail) f.requestorEmail = email[0];

  return f;
}

// ---------------------------------------------------------------------------
// Question planning — ask for the highest-priority missing / weak field.
// ---------------------------------------------------------------------------
interface QuestionPlan {
  field: string;
  prompt: string;
  reason: string;
  chips?: string[];
}

// Decision-critical ordering (PRD §6.3 rule 2).
const QUESTION_ORDER: string[] = [
  "requestorName",
  "requestorEmail",
  "org",
  "title",
  "businessJustification",
  "impact",
  "impactScope",
  "financial.benefitType",
  "financial.estimatedAnnualValue",
  "financial.basisOfEstimate",
  "financial.confidence",
  "financial.effortSize",
  "alternativeApproach",
  "urgency",
  "neededBy",
  "regulatoryCitation",
  "complianceReference",
  "hardDeadlineConsequence",
  "affectedSystems",
];

export function planNextQuestion(rec: RequestRecord): QuestionPlan | null {
  const r = rec.fields;
  const missing = new Set(missingFields(r).map((m) => m.key));
  for (const key of QUESTION_ORDER) {
    if (missing.has(key)) {
      return questionFor(key, r);
    }
  }
  return null;
}

function questionFor(key: string, r: IntakeRequest): QuestionPlan {
  switch (key) {
    case "requestorName":
      return {
        field: key,
        prompt: "First, who should I record as the requestor for this intake?",
        reason: "Every request needs an accountable requestor.",
      };
    case "requestorEmail":
      return {
        field: key,
        prompt: `Thanks${r.requestorName ? ", " + r.requestorName.split(" ")[0] : ""}. What's the best email to send the outcome to?`,
        reason: "Used to close the loop with a Jira link or a reasoned outcome.",
      };
    case "org":
      return {
        field: key,
        prompt: "Which organization is this request coming from?",
        reason: "Originating org drives routing and conditional requirements.",
        chips: ORGS,
      };
    case "title":
      return {
        field: key,
        prompt: "Give me a one-line title that summarizes the request.",
        reason: "A normalized title becomes the Jira summary.",
      };
    case "businessJustification":
      return {
        field: key,
        prompt: isVague(r.businessJustification)
          ? "That's a bit general for me to qualify it. Can you be specific about *why* this is needed — what problem does it solve and for whom?"
          : "Why is this needed? Walk me through the business justification.",
        reason: "A specific, credible justification is required before scoring.",
      };
    case "impact":
      return {
        field: key,
        prompt: "Who and what is affected, and how? Describe the impact.",
        reason: "Impact tells us the blast radius of doing (or not doing) this.",
      };
    case "impactScope":
      return {
        field: key,
        prompt: "How broad is the impact?",
        reason: "Scope feeds the strategic-alignment factor.",
        chips: IMPACT_SCOPES,
      };
    case "financial.benefitType":
      return {
        field: key,
        prompt: "What kind of financial outcome does this deliver?",
        reason: "Benefit type anchors the ROI computation.",
        chips: BENEFIT_TYPES,
      };
    case "financial.estimatedAnnualValue":
      return {
        field: key,
        prompt:
          "What's your best estimate of the annual dollar impact? (A number is fine — e.g. \"$250k\". If you truly can't estimate, say \"unknown\".)",
        reason: "Quantified value is the single biggest ROI factor.",
      };
    case "financial.basisOfEstimate":
      return {
        field: key,
        prompt:
          "How did you arrive at that number? Even a rough basis helps me sense-check it.",
        reason: "Unsupported figures get confidence-discounted and flagged.",
      };
    case "financial.confidence":
      return {
        field: key,
        prompt: "How confident are you in that estimate?",
        reason: "Confidence discounts speculative benefits.",
        chips: CONFIDENCE_LEVELS,
      };
    case "financial.effortSize":
      return {
        field: key,
        prompt: "Roughly how big is this to deliver?",
        reason: "Lower effort scores higher on the ROI model.",
        chips: EFFORT_SIZES.map((e) => effortLabel(e)),
      };
    case "alternativeApproach":
      return {
        field: key,
        prompt:
          "What alternatives did you consider — including simply doing nothing? What happens if we don't do this?",
        reason: "Considering alternatives is mandatory for a defensible decision.",
      };
    case "urgency":
      return {
        field: key,
        prompt: "How urgent is this, and why?",
        reason: "Urgency and any hard deadline factor into priority.",
        chips: URGENCIES,
      };
    case "neededBy":
      return {
        field: key,
        prompt:
          "When do you need this by? Tell me the date and whether it's a hard deadline or just a target.",
        reason: "Dated items rise in priority; hard deadlines can trigger overrides.",
      };
    case "regulatoryCitation":
      return {
        field: key,
        prompt:
          "Since this is a regulatory request, I need the specific regulation or rule reference (and the mandate date).",
        reason: "Regulatory items require a citation before they can be validated.",
      };
    case "complianceReference":
      return {
        field: key,
        prompt:
          "Which control or policy ID does this relate to? (e.g., a SOX control or internal policy reference.)",
        reason: "Risk & Compliance items must link to a control.",
      };
    case "hardDeadlineConsequence":
      return {
        field: key,
        prompt:
          "What specifically happens if the deadline is missed? (Fines, audit finding, customer impact, etc.)",
        reason: "Critical/regulatory items need the consequence documented.",
      };
    case "affectedSystems":
      return {
        field: key,
        prompt:
          "Which legacy systems or integration points are involved? Name them so we can scope it.",
        reason: "Legacy-platform items need affected systems identified.",
      };
    default:
      return {
        field: key,
        prompt: "Could you tell me a little more about that?",
        reason: "Additional detail required.",
      };
  }
}

export function buildAgentQuestion(plan: QuestionPlan): ChatMessage {
  return {
    id: newMsgId(),
    role: "agent",
    agent: "Validation",
    content: plan.prompt,
    ts: nowISO(),
    chips: plan.chips,
    field: plan.field,
  };
}

// ---------------------------------------------------------------------------
// Answer application — parse a free-text reply into the targeted field.
// ---------------------------------------------------------------------------
export function applyAnswer(
  fields: IntakeRequest,
  field: string,
  answer: string,
): { fields: IntakeRequest; note?: string } {
  const f: IntakeRequest = structuredClone(fields);
  const a = answer.trim();
  let note: string | undefined;

  switch (field) {
    case "requestorName":
      f.requestorName = stripName(a);
      break;
    case "requestorEmail": {
      const m = a.match(/[\w.+-]+@[\w-]+\.[\w.-]+/);
      f.requestorEmail = m ? m[0] : a;
      break;
    }
    case "org": {
      const org = matchEnum<OriginatingOrg>(a, ORGS) ?? detectOrg(a);
      if (org) f.org = org;
      break;
    }
    case "title":
      f.title = a.length > 90 ? a.slice(0, 90) : a;
      break;
    case "businessJustification":
      f.businessJustification = a;
      break;
    case "impact":
      f.impact = a;
      break;
    case "impactScope": {
      const s = matchEnum<ImpactScope>(a, IMPACT_SCOPES);
      if (s) f.impactScope = s;
      break;
    }
    case "financial.benefitType": {
      const b = matchEnum<BenefitType>(a, BENEFIT_TYPES) ?? detectBenefitType(a);
      if (b) f.financial.benefitType = b;
      break;
    }
    case "financial.estimatedAnnualValue": {
      if (/unknown|not sure|no idea|can't|cannot|n\/?a/i.test(a)) {
        f.financial.estimatedAnnualValue = 0;
        f.financial.confidence = "Low";
        note = "Recorded annual value as unknown (0) with Low confidence — not guessed.";
      } else {
        const v = detectMoney(a);
        if (v !== null) f.financial.estimatedAnnualValue = v;
      }
      break;
    }
    case "financial.basisOfEstimate":
      f.financial.basisOfEstimate = a;
      break;
    case "financial.confidence": {
      const c = matchEnum<Confidence>(a, CONFIDENCE_LEVELS);
      if (c) f.financial.confidence = c;
      break;
    }
    case "financial.effortSize": {
      const e = matchEffort(a);
      if (e) f.financial.effortSize = e;
      break;
    }
    case "alternativeApproach":
      f.alternativeApproach = a;
      break;
    case "urgency": {
      const u = matchEnum<Urgency>(a, URGENCIES) ?? detectUrgency(a);
      if (u) f.urgency = u;
      f.urgencyJustification = a;
      break;
    }
    case "neededBy":
      f.neededBy = a;
      f.neededByIsHard = /hard|firm|must|fixed|drop\s?dead|mandat/i.test(a)
        ? true
        : /target|soft|ideal|nice|flex/i.test(a)
          ? false
          : f.neededByIsHard;
      break;
    case "regulatoryCitation":
      f.regulatoryCitation = a;
      break;
    case "complianceReference":
      f.complianceReference = a;
      break;
    case "hardDeadlineConsequence":
      f.hardDeadlineConsequence = a;
      break;
    case "affectedSystems":
      f.affectedSystems = a;
      break;
  }
  return { fields: f, note };
}

// ---------------------------------------------------------------------------
// Duplicate detection (PRD §6.2 / §6.5)
// ---------------------------------------------------------------------------
export function detectDuplicate(
  fields: IntakeRequest,
  existing: { requestId: string; title: string }[],
  backlog: BacklogItem[],
): DuplicateMatch | null {
  const candidates = [
    ...backlog.map((b) => ({ requestId: b.requestId, title: b.title })),
    ...existing,
  ];
  const target = tokenize(fields.title + " " + fields.businessJustification);
  let best: DuplicateMatch | null = null;
  for (const c of candidates) {
    const sim = jaccard(target, tokenize(c.title));
    if (sim >= 0.4 && (!best || sim > best.similarity)) {
      best = { requestId: c.requestId, title: c.title, similarity: sim };
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// Detectors & matchers
// ---------------------------------------------------------------------------
function detectOrg(t: string): OriginatingOrg | null {
  const s = t.toLowerCase();
  if (/regulat|basel|dodd|frank|sec |finra|occ|mandat/.test(s)) return "Regulatory";
  if (/complian|control|sox|audit|risk\b/.test(s)) return "Risk & Compliance";
  if (/account|reconcil|ledger|gl |reporting|finance/.test(s)) return "Accounting";
  if (/legacy|cobol|mainframe|decommiss|migrat/.test(s)) return "Legacy platform";
  if (/leadership|strateg|executive|board/.test(s)) return "Leadership";
  if (/business line|relationship manager|commercial/.test(s)) return "Business line";
  return null;
}

function detectUrgency(t: string): Urgency | null {
  const s = t.toLowerCase();
  if (/critical|urgent|asap|immediately|emergency|drop\s?dead/.test(s))
    return "Critical";
  if (/high priority|soon|quickly|pressing/.test(s)) return "High";
  if (/low priority|whenever|no rush|eventually/.test(s)) return "Low";
  return null;
}

function detectBenefitType(t: string): BenefitType | null {
  const s = t.toLowerCase();
  if (/revenue|upsell|grow sales|new business/.test(s)) return "Revenue uplift";
  if (/loss|fraud|charge-?off|write-?off/.test(s)) return "Loss avoidance";
  if (/risk|exposure|control gap/.test(s)) return "Risk reduction";
  if (/avoid|prevent.*cost|defer.*cost/.test(s)) return "Cost avoidance";
  if (/save|reduc|efficien|automat|cut cost|cheaper/.test(s)) return "Cost reduction";
  return null;
}

// Parse "$250k", "250000", "1.2M", "2 million", "$3,500" → number
function detectMoney(t: string): number | null {
  const s = t.replace(/,/g, "");
  const m = s.match(
    /\$?\s*(\d+(?:\.\d+)?)\s*(k|thousand|m|mm|million|bn|b|billion)?/i,
  );
  if (!m) return null;
  let n = parseFloat(m[1]);
  const unit = (m[2] ?? "").toLowerCase();
  if (unit.startsWith("k") || unit === "thousand") n *= 1_000;
  else if (unit === "m" || unit === "mm" || unit === "million") n *= 1_000_000;
  else if (unit === "b" || unit === "bn" || unit === "billion") n *= 1_000_000_000;
  if (isNaN(n)) return null;
  // Ignore tiny incidental numbers that are clearly not money unless a $ or unit is present.
  if (n < 1000 && !/[$kmb]/i.test(m[0]) && unit === "") return null;
  return Math.round(n);
}

function matchEnum<T extends string>(a: string, options: readonly T[]): T | null {
  const s = a.trim().toLowerCase();
  // exact / contains
  for (const o of options) {
    if (s === o.toLowerCase()) return o;
  }
  for (const o of options) {
    if (s.includes(o.toLowerCase()) || o.toLowerCase().includes(s)) return o;
  }
  // token overlap fallback
  let best: { o: T; score: number } | null = null;
  for (const o of options) {
    const score = jaccard(tokenize(s), tokenize(o));
    if (score > 0 && (!best || score > best.score)) best = { o, score };
  }
  return best && best.score >= 0.34 ? best.o : null;
}

function matchEffort(a: string): EffortSize | null {
  const s = a.trim().toLowerCase();
  if (/\bxl\b|extra large|x-large|very large|huge/.test(s)) return "XL";
  if (/\bl\b|large\b/.test(s)) return "L";
  if (/\bm\b|medium/.test(s)) return "M";
  if (/\bs\b|small/.test(s)) return "S";
  return null;
}

export function effortLabel(e: EffortSize): string {
  return { S: "S — small", M: "M — medium", L: "L — large", XL: "XL — very large" }[e];
}

function stripName(a: string): string {
  return a
    .replace(/^(my name is|i am|i'm|this is|it's|name:?)\s*/i, "")
    .replace(/[.]+$/, "")
    .trim();
}

const STOP = new Set([
  "the","a","an","to","of","for","and","or","in","on","with","is","are","be",
  "this","that","we","our","i","need","want","would","like","please","scf",
  "supply","chain","finance","platform","request","intake","new","add","make",
]);

function tokenize(s: string): Set<string> {
  return new Set(
    s
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((w) => w.length > 2 && !STOP.has(w)),
  );
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  for (const x of a) if (b.has(x)) inter += 1;
  const union = a.size + b.size - inter;
  return union === 0 ? 0 : inter / union;
}
