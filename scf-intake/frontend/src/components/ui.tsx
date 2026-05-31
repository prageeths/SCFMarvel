import type { ReactNode } from "react";
import type { RequestStatus, PriorityBand, Desirability } from "../domain/types";

const STATUS_STYLE: Record<RequestStatus, string> = {
  DRAFT: "bg-wf-sand text-wf-slate",
  VALIDATING: "bg-amber-100 text-amber-800",
  AWAITING_REQUESTOR: "bg-amber-100 text-amber-800",
  VALIDATED: "bg-sky-100 text-sky-800",
  SCORING: "bg-sky-100 text-sky-800",
  AWAITING_TRIAGE: "bg-wf-gold/30 text-wf-redDarker",
  ACCEPTED: "bg-emerald-100 text-emerald-800",
  DOCUMENTING: "bg-emerald-100 text-emerald-800",
  WRITTEN_TO_JIRA: "bg-emerald-100 text-emerald-800",
  DEFERRED: "bg-wf-sand text-wf-slate",
  NEEDS_MORE_INFO: "bg-rose-100 text-rose-800",
  CLOSED: "bg-emerald-600 text-white",
};

export function StatusBadge({ status }: { status: RequestStatus }) {
  return (
    <span className={`pill ${STATUS_STYLE[status]}`}>
      {status.replace(/_/g, " ").toLowerCase()}
    </span>
  );
}

const BAND_STYLE: Record<PriorityBand, string> = {
  P0: "bg-wf-red text-white",
  P1: "bg-wf-redDark text-white",
  P2: "bg-wf-gold text-wf-ink",
  P3: "bg-wf-sand text-wf-charcoal",
  Defer: "bg-wf-slate/20 text-wf-slate",
};

export function BandBadge({ band }: { band: PriorityBand }) {
  return <span className={`pill ${BAND_STYLE[band]}`}>{band}</span>;
}

const DESIRE_STYLE: Record<Desirability, string> = {
  high: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-rose-100 text-rose-800",
};

export function DesirabilityBadge({ d }: { d: Desirability }) {
  return <span className={`pill ${DESIRE_STYLE[d]}`}>{d} value</span>;
}

export function CompletenessMeter({ value }: { value: number }) {
  const color =
    value >= 90 ? "bg-emerald-500" : value >= 60 ? "bg-wf-gold" : "bg-wf-red";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-wf-sand">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${Math.max(4, value)}%` }}
        />
      </div>
      <span className="w-9 text-right text-xs font-bold tabular-nums text-wf-charcoal">
        {value}%
      </span>
    </div>
  );
}

export function ScoreRing({ score }: { score: number }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;
  const color = score >= 65 ? "#10b981" : score >= 40 ? "#FFCD41" : "#D71E2B";
  return (
    <svg width="68" height="68" viewBox="0 0 68 68" className="shrink-0">
      <circle cx="34" cy="34" r={r} fill="none" stroke="#F3EDE1" strokeWidth="7" />
      <circle
        cx="34"
        cy="34"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        transform="rotate(-90 34 34)"
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
      <text
        x="34"
        y="38"
        textAnchor="middle"
        className="fill-wf-ink"
        style={{ fontSize: 17, fontWeight: 800 }}
      >
        {score}
      </text>
    </svg>
  );
}

export function Section({
  title,
  children,
  right,
}: {
  title: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <h4 className="label">{title}</h4>
        {right}
      </div>
      <div className="text-sm leading-relaxed text-wf-charcoal">{children}</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-16 text-center text-wf-slate">
      {children}
    </div>
  );
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const d = Math.floor(hr / 24);
  return `${d}d ago`;
}
