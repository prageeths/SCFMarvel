import { useState } from "react";
import { useStore } from "../state/store";
import type { RequestRecord } from "../domain/types";
import { StatusBadge, BandBadge, DesirabilityBadge, ScoreRing, Section } from "./ui";
import { formatUSD, DEFAULT_WEIGHTS, FACTOR_LABELS } from "../domain/scoring";
import { SEED_BACKLOG } from "../domain/backlog";

export function RequestDetail({ rec }: { rec: RequestRecord }) {
  const [tab, setTab] = useState<"intake" | "roi" | "audit">("intake");

  return (
    <div className="card flex max-h-[calc(100vh-110px)] flex-col overflow-hidden">
      <div className="border-b border-wf-line bg-wf-sand/40 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-bold leading-tight text-wf-ink">
              {rec.fields.title || "(untitled)"}
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-wf-slate">
              <span className="font-mono font-semibold">{rec.requestId}</span>
              <StatusBadge status={rec.status} />
              {rec.priority && <BandBadge band={rec.priority.recommendedBand} />}
              {rec.roi && <DesirabilityBadge d={rec.roi.desirability} />}
            </div>
          </div>
          {rec.jira?.issueKey && (
            <a
              href={rec.jira.url}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 rounded-lg bg-emerald-100 px-2.5 py-1 font-mono text-xs font-bold text-emerald-700 hover:bg-emerald-200"
            >
              {rec.jira.issueKey} ↗
            </a>
          )}
        </div>

        <div className="mt-3 flex gap-1">
          {(["intake", "roi", "audit"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-md px-3 py-1 text-xs font-semibold capitalize transition ${
                tab === t ? "bg-wf-red text-white" : "text-wf-slate hover:bg-white"
              }`}
            >
              {t === "roi" ? "ROI & priority" : t === "audit" ? "Audit trail" : "Intake"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {tab === "intake" && <IntakeTab rec={rec} />}
        {tab === "roi" && <RoiTab rec={rec} />}
        {tab === "audit" && <AuditTab rec={rec} />}
      </div>

      <DecisionBar rec={rec} />
    </div>
  );
}

function IntakeTab({ rec }: { rec: RequestRecord }) {
  const f = rec.fields;
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Requestor">{f.requestorName}</Field>
        <Field label="Email">{f.requestorEmail}</Field>
        <Field label="Originating org">{f.org}</Field>
        <Field label="Impact scope">{f.impactScope}</Field>
        <Field label="Urgency">{f.urgency}</Field>
        <Field label="Needed by">
          {f.neededBy} {f.neededByIsHard ? "(hard)" : f.neededByIsHard === false ? "(target)" : ""}
        </Field>
      </div>

      <Section title="Business justification">{f.businessJustification}</Section>
      <Section title="Impact">{f.impact}</Section>
      <Section title="Alternative considered">{f.alternativeApproach}</Section>

      <div className="rounded-lg border border-wf-line bg-wf-sand/30 p-3">
        <div className="label mb-2">Financial outcome</div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Field label="Benefit type">{f.financial.benefitType}</Field>
          <Field label="Annual value">
            {f.financial.estimatedAnnualValue !== null
              ? formatUSD(f.financial.estimatedAnnualValue)
              : "—"}
          </Field>
          <Field label="One-time">
            {f.financial.oneTimeValue ? formatUSD(f.financial.oneTimeValue) : "—"}
          </Field>
          <Field label="Effort">{f.financial.effortSize}</Field>
          <Field label="Confidence">{f.financial.confidence}</Field>
        </div>
        <div className="mt-2">
          <Section title="Basis of estimate">{f.financial.basisOfEstimate || "—"}</Section>
        </div>
      </div>

      {(f.regulatoryCitation || f.complianceReference || f.hardDeadlineConsequence || f.affectedSystems) && (
        <div className="rounded-lg border border-wf-gold/50 bg-wf-gold/10 p-3">
          <div className="label mb-2">Regulatory / compliance / legacy</div>
          {f.regulatoryCitation && <Section title="Regulatory citation">{f.regulatoryCitation}</Section>}
          {f.complianceReference && <Section title="Control reference">{f.complianceReference}</Section>}
          {f.hardDeadlineConsequence && (
            <Section title="Hard deadline consequence">{f.hardDeadlineConsequence}</Section>
          )}
          {f.affectedSystems && <Section title="Affected systems">{f.affectedSystems}</Section>}
        </div>
      )}

      <EmailDraftPane rec={rec} />
    </>
  );
}

function RoiTab({ rec }: { rec: RequestRecord }) {
  if (!rec.roi || !rec.priority) {
    return (
      <div className="py-8 text-center text-sm text-wf-slate">
        Not yet scored — the Business Justification agent runs once the request is
        fully validated.
      </div>
    );
  }
  const { roi, priority } = rec;
  const maxContribution = Math.max(...Object.values(roi.factorBreakdown), 1);

  return (
    <>
      <div className="flex items-center gap-4 rounded-lg border border-wf-line bg-white p-3">
        <ScoreRing score={roi.roiScore} />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <BandBadge band={priority.recommendedBand} />
            <DesirabilityBadge d={roi.desirability} />
          </div>
          <div className="mt-1.5 text-xs text-wf-slate">
            Ranked <strong className="text-wf-ink">#{priority.rankInBacklog}</strong> in the
            current intake queue
            {roi.paybackPeriodMonths !== null && (
              <> · payback ≈ {roi.paybackPeriodMonths} months</>
            )}
          </div>
          <div className="mt-1 text-xs text-wf-slate">
            Confidence-adjusted value:{" "}
            <strong className="text-wf-ink">{formatUSD(roi.confidenceAdjustedValue)}</strong>
          </div>
        </div>
      </div>

      <Section title="Factor breakdown (transparent weighted model)">
        <div className="space-y-1.5">
          {Object.entries(roi.factorBreakdown).map(([factor, contrib]) => {
            const weightKey = (Object.keys(FACTOR_LABELS) as (keyof typeof FACTOR_LABELS)[]).find(
              (k) => FACTOR_LABELS[k] === factor,
            );
            const weight = weightKey ? DEFAULT_WEIGHTS[weightKey] : 0;
            return (
              <div key={factor} className="flex items-center gap-2">
                <div className="w-40 shrink-0 text-xs text-wf-charcoal">
                  {factor}
                  <span className="ml-1 text-wf-slate">·{Math.round(weight * 100)}%</span>
                </div>
                <div className="h-3 flex-1 overflow-hidden rounded-full bg-wf-sand">
                  <div
                    className="h-full rounded-full bg-wf-red"
                    style={{ width: `${(contrib / maxContribution) * 100}%` }}
                  />
                </div>
                <span className="w-7 text-right text-xs font-bold tabular-nums">{contrib}</span>
              </div>
            );
          })}
        </div>
      </Section>

      {priority.overrideApplied && (
        <div className="rounded-lg border border-wf-red/30 bg-wf-red/5 p-3 text-xs text-wf-redDarker">
          <strong>Override applied: </strong>
          {priority.overrideApplied}
        </div>
      )}

      {roi.plausibilityFlags.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3">
          <div className="label mb-1 text-amber-800">Plausibility flags</div>
          <ul className="list-inside list-disc text-xs text-amber-900">
            {roi.plausibilityFlags.map((flag, i) => (
              <li key={i}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      <Section title="Priority rationale">{roi.rationale}</Section>
      <Section title="Backlog comparison">{priority.comparisonNotes}</Section>

      <BacklogStrip score={roi.roiScore} />
    </>
  );
}

function BacklogStrip({ score }: { score: number }) {
  const items = [...SEED_BACKLOG].sort((a, b) => b.roiScore - a.roiScore);
  return (
    <Section title="Where it sits in the queue">
      <div className="space-y-1">
        {items.map((b) => (
          <div key={b.requestId} className="flex items-center gap-2 text-xs">
            <span className="w-7 text-right font-bold tabular-nums text-wf-slate">{b.roiScore}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-wf-sand">
              <div className="h-full bg-wf-slate/40" style={{ width: `${b.roiScore}%` }} />
            </div>
            <span className="w-40 truncate text-wf-slate">{b.title}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-xs">
          <span className="w-7 text-right font-bold tabular-nums text-wf-red">{score}</span>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-wf-red/15">
            <div className="h-full bg-wf-red" style={{ width: `${score}%` }} />
          </div>
          <span className="w-40 truncate font-bold text-wf-red">◀ this request</span>
        </div>
      </div>
    </Section>
  );
}

function AuditTab({ rec }: { rec: RequestRecord }) {
  return (
    <ol className="relative space-y-3 border-l border-wf-line pl-4">
      {rec.auditTrail.map((e, i) => (
        <li key={i} className="relative">
          <span
            className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full ring-2 ring-white ${
              e.actor === "human"
                ? "bg-wf-red"
                : e.actor === "agent"
                  ? "bg-wf-gold"
                  : "bg-wf-slate"
            }`}
          />
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-wf-ink">{e.action}</span>
            <span className="pill bg-wf-sand text-[10px] text-wf-slate">
              {e.agent ?? e.actor}
            </span>
          </div>
          {e.detail && <p className="text-xs text-wf-slate">{e.detail}</p>}
          <p className="text-[10px] text-wf-slate/70">{new Date(e.ts).toLocaleString()}</p>
        </li>
      ))}
    </ol>
  );
}

function EmailDraftPane({ rec }: { rec: RequestRecord }) {
  const { sendEmail } = useStore();
  const [open, setOpen] = useState(false);
  if (!rec.emailDraft) return null;
  const d = rec.emailDraft;

  function downloadEml() {
    const eml = `To: ${d.to}\nSubject: ${d.subject}\nX-Intake-Request: ${rec.requestId}\nContent-Type: text/plain; charset=utf-8\n\n${d.body}\n`;
    const blob = new Blob([eml], { type: "message/rfc822" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${rec.requestId}-${d.type}.eml`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="rounded-lg border border-wf-line bg-white p-3">
      <div className="flex items-center justify-between">
        <div className="label">
          {d.type === "deferral" ? "Deferral email draft" : "Acceptance email draft"}
          {d.status === "sent_by_human" ? (
            <span className="pill ml-2 bg-emerald-100 text-emerald-800">sent by human</span>
          ) : (
            <span className="pill ml-2 bg-amber-100 text-amber-800">draft only</span>
          )}
        </div>
        <button onClick={() => setOpen((o) => !o)} className="text-xs font-semibold text-wf-red">
          {open ? "Hide" : "Review"}
        </button>
      </div>
      <p className="mt-1 text-[11px] text-wf-slate">
        The system never sends mail automatically. A human reviews, edits if
        needed, and sends from their own client.
      </p>
      {open && (
        <div className="mt-2 space-y-2">
          <div className="rounded-md bg-wf-sand/40 p-2 text-xs">
            <div>
              <span className="font-semibold">To:</span> {d.to}
            </div>
            <div>
              <span className="font-semibold">Subject:</span> {d.subject}
            </div>
          </div>
          <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-md border border-wf-line bg-white p-2 text-xs leading-relaxed text-wf-charcoal">
            {d.body}
          </pre>
          <div className="flex gap-2">
            <button onClick={downloadEml} className="btn-ghost px-2.5 py-1 text-xs">
              Download .eml
            </button>
            {d.status !== "sent_by_human" && (
              <button
                onClick={() => sendEmail(rec.requestId)}
                className="btn-gold px-2.5 py-1 text-xs"
              >
                Mark as sent by me
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DecisionBar({ rec }: { rec: RequestRecord }) {
  const { triage, retryJiraWrite } = useStore();
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<"accept" | "defer" | "needs_info" | null>(null);

  if (rec.jira?.writeStatus === "failed") {
    return (
      <div className="border-t border-wf-line bg-rose-50 p-3">
        <div className="mb-2 text-xs font-semibold text-rose-800">
          Jira write failed (attempt {rec.jira.attempts}). The request is preserved.
        </div>
        <button onClick={() => retryJiraWrite(rec.requestId)} className="btn-primary w-full">
          Retry Jira write
        </button>
      </div>
    );
  }

  if (rec.status !== "AWAITING_TRIAGE") {
    return (
      <div className="border-t border-wf-line bg-wf-sand/30 px-4 py-2.5 text-center text-xs text-wf-slate">
        {rec.status === "NEEDS_MORE_INFO"
          ? "Returned to the requestor for more information."
          : rec.jira?.issueKey
            ? `Accepted — logged as ${rec.jira.issueKey}.`
            : rec.status === "DEFERRED"
              ? "Deferred — a draft explanation is ready for a human to send."
              : "No triage action required right now."}
      </div>
    );
  }

  function submit() {
    if (!pending) return;
    if (!note.trim()) return;
    triage(rec.requestId, pending, note.trim());
    setNote("");
    setPending(null);
  }

  return (
    <div className="border-t border-wf-line bg-white p-3">
      <div className="label mb-1.5">Triage decision (human-in-the-loop)</div>
      <div className="mb-2 grid grid-cols-3 gap-2">
        <DecisionBtn label="Accept" tone="accept" active={pending === "accept"} onClick={() => setPending("accept")} />
        <DecisionBtn label="Defer" tone="defer" active={pending === "defer"} onClick={() => setPending("defer")} />
        <DecisionBtn
          label="Needs info"
          tone="info"
          active={pending === "needs_info"}
          onClick={() => setPending("needs_info")}
        />
      </div>
      <textarea
        className="input mb-2 min-h-[52px] resize-none text-sm"
        placeholder="Decision note (required — captured in the audit trail)…"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <button
        className="btn-primary w-full"
        disabled={!pending || !note.trim()}
        onClick={submit}
      >
        {pending === "accept"
          ? "Accept & write to Jira"
          : pending === "defer"
            ? "Defer & draft email"
            : pending === "needs_info"
              ? "Send back for more info"
              : "Choose a decision"}
      </button>
    </div>
  );
}

function DecisionBtn({
  label,
  tone,
  active,
  onClick,
}: {
  label: string;
  tone: "accept" | "defer" | "info";
  active: boolean;
  onClick: () => void;
}) {
  const tones = {
    accept: "border-emerald-300 text-emerald-700 data-[on=true]:bg-emerald-600 data-[on=true]:text-white",
    defer: "border-wf-line text-wf-slate data-[on=true]:bg-wf-slate data-[on=true]:text-white",
    info: "border-amber-300 text-amber-700 data-[on=true]:bg-amber-500 data-[on=true]:text-white",
  }[tone];
  return (
    <button
      data-on={active}
      onClick={onClick}
      className={`rounded-lg border px-2 py-1.5 text-xs font-semibold transition ${tones}`}
    >
      {label}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="text-sm font-medium text-wf-ink">{children || "—"}</div>
    </div>
  );
}
