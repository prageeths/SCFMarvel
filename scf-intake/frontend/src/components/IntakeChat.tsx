import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import type { RequestRecord } from "../domain/types";
import { StatusBadge, BandBadge } from "./ui";
import { LiveSummary } from "./LiveSummary";
import { formatUSD } from "../domain/scoring";

const EXAMPLES = [
  "We need a way for suppliers to see the effective APR on early-payment offers before they accept. Right now they call their RM and it's slow. I'm in the business line.",
  "Regulatory: Basel III now requires receivables-financing RWA reported separately. Our extract bundles it and that will fail the next supervisory review. Hard deadline Sept 30.",
  "It'd be nice to add custom emoji reactions to the agent decision feed so reviews feel more fun.",
];

export default function IntakeChat({ onGoToTriage }: { onGoToTriage: () => void }) {
  const { state, start, setActive } = useStore();
  const active = state.requests.find((r) => r.requestId === state.activeRequestId);
  const inFlight = active && isIntakeView(active);

  if (!inFlight) {
    return <StartScreen onStart={start} onGoToTriage={onGoToTriage} hasActive={!!active} />;
  }
  return <Conversation rec={active!} onStartAnother={() => setActive(null)} />;
}

function isIntakeView(r: RequestRecord): boolean {
  // The intake tab "owns" a request through validation/scoring and shows its
  // outcome; once the user starts another (active=null) we return to start.
  return true && r.status !== undefined;
}

function StartScreen({
  onStart,
  onGoToTriage,
  hasActive,
}: {
  onStart: (t: string) => void;
  onGoToTriage: () => void;
  hasActive: boolean;
}) {
  const [text, setText] = useState("");
  return (
    <div className="mx-auto grid max-w-3xl gap-5 py-4">
      <div className="card overflow-hidden">
        <div className="bg-gradient-to-br from-wf-red to-wf-redDarker px-6 py-7 text-white">
          <h1 className="text-2xl font-extrabold tracking-tight">
            Tell us what you need from the SCF platform
          </h1>
          <p className="mt-1.5 max-w-xl text-sm text-white/85">
            Describe your request in plain language. Our intake agent will ask a
            few focused follow-ups, quantify the ROI, and either log it to Jira
            or send back a clear, reasoned outcome — nothing gets silently
            dropped.
          </p>
        </div>
        <div className="space-y-3 p-6">
          <textarea
            className="input min-h-[120px] resize-y"
            placeholder="e.g. Suppliers can't see the effective APR on early-payment offers before accepting — they have to call their relationship manager and it's slow…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && text.trim()) {
                onStart(text.trim());
              }
            }}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-wf-slate">⌘/Ctrl + Enter to start</span>
            <button
              className="btn-primary"
              disabled={text.trim().length < 8}
              onClick={() => onStart(text.trim())}
            >
              Start intake →
            </button>
          </div>
        </div>
      </div>

      <div>
        <div className="label mb-2">Or try an example</div>
        <div className="grid gap-2 sm:grid-cols-3">
          {EXAMPLES.map((ex, i) => (
            <button
              key={i}
              onClick={() => onStart(ex)}
              className="card p-3 text-left text-xs leading-relaxed text-wf-charcoal transition hover:border-wf-red hover:shadow-pop"
            >
              {ex.length > 130 ? ex.slice(0, 130) + "…" : ex}
            </button>
          ))}
        </div>
      </div>

      {hasActive && (
        <button onClick={onGoToTriage} className="text-sm font-semibold text-wf-red hover:underline">
          View the triage dashboard →
        </button>
      )}
    </div>
  );
}

function Conversation({
  rec,
  onStartAnother,
}: {
  rec: RequestRecord;
  onStartAnother: () => void;
}) {
  const { sendRequestorMessage } = useStore();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const lastAgent = [...rec.conversation].reverse().find((m) => m.role === "agent" && m.field);
  const awaiting = rec.status === "AWAITING_REQUESTOR";
  const terminal = ["CLOSED", "DEFERRED", "WRITTEN_TO_JIRA", "NEEDS_MORE_INFO"].includes(
    rec.status,
  );
  const awaitingTriage = rec.status === "AWAITING_TRIAGE";

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [rec.conversation.length]);

  function send(text: string) {
    if (!text.trim()) return;
    sendRequestorMessage(rec.requestId, text.trim());
    setDraft("");
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      {/* chat column */}
      <div className="card flex h-[calc(100vh-200px)] min-h-[480px] flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-wf-line bg-wf-sand/40 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold text-wf-slate">
              {rec.requestId}
            </span>
            <StatusBadge status={rec.status} />
          </div>
          <button onClick={onStartAnother} className="btn-ghost px-2.5 py-1 text-xs">
            New request
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {rec.conversation.map((msg) => (
            <Bubble key={msg.id} role={msg.role} agent={msg.agent}>
              {msg.content}
            </Bubble>
          ))}

          {terminal && <OutcomeCard rec={rec} />}
          {awaitingTriage && (
            <div className="animate-fade-in rounded-lg border border-wf-gold/60 bg-wf-gold/15 p-3 text-sm text-wf-redDarker">
              This request is with a platform triage lead for a decision. Watch
              the triage dashboard for the outcome.
            </div>
          )}
        </div>

        {/* input / chips */}
        {awaiting && (
          <div className="border-t border-wf-line p-3">
            {lastAgent?.chips && (
              <div className="mb-2 flex flex-wrap gap-2">
                {lastAgent.chips.map((c) => (
                  <button
                    key={c}
                    onClick={() => send(c)}
                    className="rounded-full border border-wf-line bg-white px-3 py-1 text-xs font-semibold text-wf-charcoal transition hover:border-wf-red hover:bg-wf-red hover:text-white"
                  >
                    {c}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2">
              <textarea
                className="input max-h-32 min-h-[42px] resize-none"
                rows={1}
                placeholder="Type your answer…"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(draft);
                  }
                }}
              />
              <button className="btn-primary" disabled={!draft.trim()} onClick={() => send(draft)}>
                Send
              </button>
            </div>
          </div>
        )}
      </div>

      {/* live summary panel */}
      <LiveSummary rec={rec} />
    </div>
  );
}

function Bubble({
  role,
  agent,
  children,
}: {
  role: "agent" | "requestor" | "system";
  agent?: string;
  children: React.ReactNode;
}) {
  if (role === "system") {
    return (
      <div className="animate-fade-in text-center">
        <span className="rounded-full bg-wf-sand px-3 py-1 text-[11px] font-medium text-wf-slate">
          {children}
        </span>
      </div>
    );
  }
  const isAgent = role === "agent";
  return (
    <div className={`flex animate-fade-in ${isAgent ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-[85%] ${isAgent ? "" : "text-right"}`}>
        {isAgent && (
          <div className="mb-0.5 ml-1 text-[10px] font-bold uppercase tracking-wide text-wf-red">
            {agent ?? "Agent"} agent
          </div>
        )}
        <div
          className={`whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
            isAgent
              ? "rounded-tl-sm border border-wf-line bg-white text-wf-ink"
              : "rounded-tr-sm bg-wf-red text-white"
          }`}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

function OutcomeCard({ rec }: { rec: RequestRecord }) {
  if (rec.status === "WRITTEN_TO_JIRA" || (rec.status === "CLOSED" && rec.jira?.issueKey)) {
    return (
      <div className="animate-fade-in rounded-xl border border-emerald-200 bg-emerald-50 p-4">
        <div className="text-sm font-bold text-emerald-800">✓ Accepted & logged to Jira</div>
        <p className="mt-1 text-sm text-emerald-900/80">
          Priority {rec.priority && <BandBadge band={rec.priority.recommendedBand} />} · ROI{" "}
          {rec.roi?.roiScore}/100. Track delivery in Jira:
        </p>
        <a
          href={rec.jira?.url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 font-mono text-sm font-bold text-emerald-700 hover:underline"
        >
          {rec.jira?.issueKey} ↗
        </a>
      </div>
    );
  }
  if (rec.status === "DEFERRED") {
    return (
      <div className="animate-fade-in rounded-xl border border-wf-line bg-wf-sand/50 p-4">
        <div className="text-sm font-bold text-wf-charcoal">This request was deferred</div>
        <p className="mt-1 text-sm text-wf-slate">
          Scored {rec.roi?.roiScore}/100 against the current backlog. A respectful
          explanation has been drafted for a human to review and send — it stays
          on file and can be re-scored if circumstances change.
        </p>
      </div>
    );
  }
  if (rec.status === "CLOSED") {
    return (
      <div className="animate-fade-in rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">
        ✓ Request closed.
      </div>
    );
  }
  // NEEDS_MORE_INFO
  return (
    <div className="animate-fade-in rounded-xl border border-rose-200 bg-rose-50 p-4">
      <div className="text-sm font-bold text-rose-800">Sent to a human for follow-up</div>
      <p className="mt-1 text-sm text-rose-900/80">
        We couldn't fully complete the request automatically. A platform triage
        lead has been notified and will reach out. Nothing was lost.
      </p>
    </div>
  );
}

export { formatUSD };
