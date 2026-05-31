import { useState } from "react";
import { useStore } from "./state/store";
import IntakeChat from "./components/IntakeChat";
import TriageDashboard from "./components/TriageDashboard";

type Tab = "intake" | "triage";

export default function App() {
  const [tab, setTab] = useState<Tab>("intake");
  const { state } = useStore();

  const triageCount = state.requests.filter(
    (r) => r.status === "AWAITING_TRIAGE" || r.status === "NEEDS_MORE_INFO",
  ).length;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b-4 border-wf-gold bg-wf-red text-white shadow-md">
        <div className="mx-auto flex max-w-[1400px] items-center gap-4 px-4 py-3 sm:px-6">
          <Logo />
          <div className="mr-2 leading-tight">
            <div className="text-base font-extrabold tracking-tight">
              SCF Intake
            </div>
            <div className="text-[11px] font-medium text-white/80">
              Agentic Request &amp; Prioritization Platform
            </div>
          </div>

          <nav className="ml-2 flex items-center gap-1 rounded-lg bg-black/15 p-1">
            <TabBtn active={tab === "intake"} onClick={() => setTab("intake")}>
              Submit a request
            </TabBtn>
            <TabBtn active={tab === "triage"} onClick={() => setTab("triage")}>
              Triage dashboard
              {triageCount > 0 && (
                <span className="ml-1.5 rounded-full bg-wf-gold px-1.5 text-[10px] font-bold text-wf-ink">
                  {triageCount}
                </span>
              )}
            </TabBtn>
          </nav>

          <div className="ml-auto hidden items-center gap-2 text-[11px] font-medium text-white/85 sm:flex">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-black/20 px-2.5 py-1">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-wf-gold" />
              3 agents · LangGraph flow
            </span>
            <span className="rounded-full bg-black/20 px-2.5 py-1">POC · synthetic data</span>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5 sm:px-6">
        {tab === "intake" ? (
          <IntakeChat onGoToTriage={() => setTab("triage")} />
        ) : (
          <TriageDashboard onGoToIntake={() => setTab("intake")} />
        )}
      </main>

      <footer className="border-t border-wf-line bg-white/60 py-3 text-center text-[11px] text-wf-slate">
        Agentic Intake Request Application · Supply Chain Finance Platform · POC.
        No real customer, account, or PII data — synthetic only. No email is ever
        sent automatically; a human reviews and sends every draft.
      </footer>
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center rounded-md px-3 py-1.5 text-sm font-semibold transition ${
        active ? "bg-white text-wf-red shadow" : "text-white/90 hover:bg-white/10"
      }`}
    >
      {children}
    </button>
  );
}

function Logo() {
  return (
    <div className="grid h-10 w-10 place-items-center rounded-lg bg-wf-gold text-wf-red shadow-inner">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M4 7l8-4 8 4-8 4-8-4z"
          fill="currentColor"
          opacity="0.95"
        />
        <path
          d="M4 12l8 4 8-4M4 17l8 4 8-4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
