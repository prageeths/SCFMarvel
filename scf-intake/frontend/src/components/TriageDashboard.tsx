import { useMemo, useState } from "react";
import { useStore } from "../state/store";
import type { RequestRecord, RequestStatus, OriginatingOrg } from "../domain/types";
import { StatusBadge, BandBadge, Empty, timeAgo } from "./ui";
import { RequestDetail } from "./RequestDetail";
import { ORGS } from "../domain/schema";
import { formatUSD } from "../domain/scoring";

type SortKey = "roi" | "created" | "needed";

export default function TriageDashboard({ onGoToIntake }: { onGoToIntake: () => void }) {
  const { state, setActive } = useStore();
  const [statusFilter, setStatusFilter] = useState<"all" | "open" | RequestStatus>("all");
  const [orgFilter, setOrgFilter] = useState<"all" | OriginatingOrg>("all");
  const [sort, setSort] = useState<SortKey>("roi");
  const [selected, setSelected] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let rows = [...state.requests];
    if (statusFilter === "open") {
      rows = rows.filter((r) =>
        ["AWAITING_TRIAGE", "NEEDS_MORE_INFO", "AWAITING_REQUESTOR", "VALIDATING", "SCORING"].includes(
          r.status,
        ),
      );
    } else if (statusFilter !== "all") {
      rows = rows.filter((r) => r.status === statusFilter);
    }
    if (orgFilter !== "all") rows = rows.filter((r) => r.fields.org === orgFilter);
    rows.sort((a, b) => {
      if (sort === "roi") return (b.roi?.roiScore ?? -1) - (a.roi?.roiScore ?? -1);
      if (sort === "created")
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      return (a.fields.neededBy || "~").localeCompare(b.fields.neededBy || "~");
    });
    return rows;
  }, [state.requests, statusFilter, orgFilter, sort]);

  const selectedRec = state.requests.find((r) => r.requestId === selected) ?? null;

  const stats = useMemo(() => {
    const all = state.requests;
    return {
      total: all.length,
      awaiting: all.filter((r) => r.status === "AWAITING_TRIAGE").length,
      accepted: all.filter((r) => r.jira?.issueKey).length,
      deferred: all.filter((r) => r.status === "DEFERRED").length,
    };
  }, [state.requests]);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <div className="space-y-3">
        {/* stat tiles */}
        <div className="grid grid-cols-4 gap-2">
          <Stat label="Requests" value={stats.total} />
          <Stat label="Awaiting" value={stats.awaiting} accent />
          <Stat label="In Jira" value={stats.accepted} />
          <Stat label="Deferred" value={stats.deferred} />
        </div>

        {/* filters */}
        <div className="card flex flex-wrap items-center gap-2 p-2.5">
          <select
            className="input w-auto py-1.5 text-xs"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          >
            <option value="all">All statuses</option>
            <option value="open">Open / needs action</option>
            <option value="AWAITING_TRIAGE">Awaiting triage</option>
            <option value="WRITTEN_TO_JIRA">Written to Jira</option>
            <option value="CLOSED">Closed</option>
            <option value="DEFERRED">Deferred</option>
            <option value="NEEDS_MORE_INFO">Needs more info</option>
          </select>
          <select
            className="input w-auto py-1.5 text-xs"
            value={orgFilter}
            onChange={(e) => setOrgFilter(e.target.value as typeof orgFilter)}
          >
            <option value="all">All orgs</option>
            {ORGS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <div className="ml-auto flex items-center gap-1 text-xs text-wf-slate">
            sort
            <select
              className="input w-auto py-1.5 text-xs"
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
            >
              <option value="roi">ROI score</option>
              <option value="created">Newest</option>
              <option value="needed">Needed-by</option>
            </select>
          </div>
        </div>

        {/* queue */}
        <div className="card divide-y divide-wf-line/70 overflow-hidden">
          {filtered.length === 0 ? (
            <Empty>
              <p className="text-sm">No requests match these filters.</p>
              <button onClick={onGoToIntake} className="btn-primary mt-3">
                Submit the first request
              </button>
            </Empty>
          ) : (
            filtered.map((r) => (
              <QueueRow
                key={r.requestId}
                rec={r}
                active={r.requestId === selected}
                onClick={() => {
                  setSelected(r.requestId);
                  setActive(r.requestId);
                }}
              />
            ))
          )}
        </div>
      </div>

      {/* detail */}
      <div className="lg:sticky lg:top-[84px] lg:self-start">
        {selectedRec ? (
          <RequestDetail rec={selectedRec} />
        ) : (
          <div className="card">
            <Empty>
              <div className="mb-2 text-3xl">📥</div>
              <p className="max-w-xs text-sm">
                Select a request to review its full intake, the transparent ROI
                breakdown, backlog comparison, and to accept, defer, or send it
                back — every decision is captured in the audit trail.
              </p>
            </Empty>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`card px-3 py-2.5 ${accent && value > 0 ? "border-wf-gold bg-wf-gold/10" : ""}`}>
      <div className="text-2xl font-extrabold tabular-nums text-wf-ink">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}

function QueueRow({
  rec,
  active,
  onClick,
}: {
  rec: RequestRecord;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-wf-sand/50 ${
        active ? "bg-wf-sand/70" : ""
      }`}
    >
      <div className="flex w-10 shrink-0 flex-col items-center">
        <span className="text-lg font-extrabold tabular-nums text-wf-charcoal">
          {rec.roi?.roiScore ?? "—"}
        </span>
        <span className="text-[9px] uppercase text-wf-slate">roi</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-semibold text-wf-ink">
            {rec.fields.title || "(untitled)"}
          </span>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-wf-slate">
          <span className="font-mono">{rec.requestId.replace("SCF-INTK-", "#")}</span>
          <span>·</span>
          <span>{rec.fields.org ?? "—"}</span>
          {rec.fields.financial.estimatedAnnualValue ? (
            <>
              <span>·</span>
              <span>{formatUSD(rec.fields.financial.estimatedAnnualValue)}/yr</span>
            </>
          ) : null}
          <span>·</span>
          <span>{timeAgo(rec.createdAt)}</span>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {rec.priority && <BandBadge band={rec.priority.recommendedBand} />}
        <StatusBadge status={rec.status} />
      </div>
    </button>
  );
}
