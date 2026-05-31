import type { RequestRecord } from "../domain/types";
import { CompletenessMeter, ScoreRing, BandBadge, DesirabilityBadge } from "./ui";
import { formatUSD } from "../domain/scoring";
import { FIELD_LABEL } from "../domain/schema";

export function LiveSummary({ rec }: { rec: RequestRecord }) {
  const f = rec.fields;
  const rows: [string, string | null][] = [
    ["Title", f.title || null],
    ["Requestor", f.requestorName ? `${f.requestorName}` : null],
    ["Org", f.org],
    ["Impact scope", f.impactScope],
    ["Benefit type", f.financial.benefitType !== "None" ? f.financial.benefitType : null],
    [
      "Annual value",
      f.financial.estimatedAnnualValue !== null
        ? formatUSD(f.financial.estimatedAnnualValue)
        : null,
    ],
    ["Effort", f.financial.effortSize],
    ["Confidence", f.financial.confidence],
    ["Urgency", f.urgency],
    ["Needed by", f.neededBy || null],
  ];

  return (
    <aside className="card flex max-h-[calc(100vh-200px)] flex-col overflow-hidden">
      <div className="border-b border-wf-line bg-wf-sand/40 px-4 py-3">
        <div className="label">Live request summary</div>
        <div className="mt-2">
          <CompletenessMeter value={rec.completenessScore} />
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {rec.duplicateOf && (
          <div className="rounded-lg border border-wf-gold/60 bg-wf-gold/15 p-2.5 text-xs text-wf-redDarker">
            Possible duplicate of{" "}
            <span className="font-mono font-semibold">{rec.duplicateOf.requestId}</span> ·{" "}
            {Math.round(rec.duplicateOf.similarity * 100)}% overlap
          </div>
        )}

        <dl className="divide-y divide-wf-line/70">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-3 py-1.5">
              <dt className="text-xs font-medium text-wf-slate">{k}</dt>
              <dd
                className={`text-right text-xs font-semibold ${
                  v ? "text-wf-ink" : "text-wf-slate/40"
                }`}
              >
                {v ?? "—"}
              </dd>
            </div>
          ))}
        </dl>

        {rec.missingFields.length > 0 && (
          <div className="rounded-lg bg-wf-sand/60 p-2.5">
            <div className="label mb-1">Still gathering</div>
            <div className="flex flex-wrap gap-1.5">
              {rec.missingFields.slice(0, 6).map((mf) => (
                <span
                  key={mf}
                  className="rounded-md bg-white px-1.5 py-0.5 text-[10px] font-medium text-wf-slate"
                >
                  {FIELD_LABEL[mf] ?? mf}
                </span>
              ))}
            </div>
          </div>
        )}

        {rec.roi && rec.priority && (
          <div className="rounded-lg border border-wf-line bg-white p-3">
            <div className="label mb-2">Justification agent</div>
            <div className="flex items-center gap-3">
              <ScoreRing score={rec.roi.roiScore} />
              <div className="space-y-1">
                <div className="flex items-center gap-1.5">
                  <BandBadge band={rec.priority.recommendedBand} />
                  <DesirabilityBadge d={rec.roi.desirability} />
                </div>
                <div className="text-xs text-wf-slate">
                  Rank #{rec.priority.rankInBacklog} in backlog
                </div>
                {rec.roi.paybackPeriodMonths !== null && (
                  <div className="text-xs text-wf-slate">
                    Payback ≈ {rec.roi.paybackPeriodMonths} mo
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
