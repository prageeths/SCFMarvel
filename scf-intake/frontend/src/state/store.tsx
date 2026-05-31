import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import type { RequestRecord, BacklogItem } from "../domain/types";
import { SEED_BACKLOG } from "../domain/backlog";
import {
  startIntake,
  handleRequestorMessage,
  applyTriageDecision,
  retryJira,
  simulateJiraFailure,
  markEmailSentByHuman,
  setBacklog,
} from "../domain/engine";
import { buildSeedRequests } from "./seedRequests";

const STORAGE_KEY = "scf-intake-state-v1";

interface State {
  requests: RequestRecord[];
  backlog: BacklogItem[];
  activeRequestId: string | null;
}

type Action =
  | { type: "START"; text: string }
  | { type: "REQUESTOR_MSG"; id: string; text: string }
  | { type: "TRIAGE"; id: string; decision: "accept" | "defer" | "needs_info"; note: string }
  | { type: "RETRY_JIRA"; id: string }
  | { type: "SIM_FAIL"; id: string }
  | { type: "SEND_EMAIL"; id: string }
  | { type: "SET_ACTIVE"; id: string | null }
  | { type: "RESET" };

function replaceRecord(reqs: RequestRecord[], rec: RequestRecord): RequestRecord[] {
  return reqs.map((r) => (r.requestId === rec.requestId ? rec : r));
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "START": {
      const rec = startIntake(action.text, state.requests, state.backlog);
      return { ...state, requests: [rec, ...state.requests], activeRequestId: rec.requestId };
    }
    case "REQUESTOR_MSG": {
      const rec = state.requests.find((r) => r.requestId === action.id);
      if (!rec) return state;
      const next = handleRequestorMessage(rec, action.text);
      return { ...state, requests: replaceRecord(state.requests, next) };
    }
    case "TRIAGE": {
      const rec = state.requests.find((r) => r.requestId === action.id);
      if (!rec) return state;
      const next = applyTriageDecision(rec, action.decision, action.note);
      return { ...state, requests: replaceRecord(state.requests, next) };
    }
    case "RETRY_JIRA": {
      const rec = state.requests.find((r) => r.requestId === action.id);
      if (!rec) return state;
      return { ...state, requests: replaceRecord(state.requests, retryJira(rec)) };
    }
    case "SIM_FAIL": {
      const rec = state.requests.find((r) => r.requestId === action.id);
      if (!rec) return state;
      return { ...state, requests: replaceRecord(state.requests, simulateJiraFailure(rec)) };
    }
    case "SEND_EMAIL": {
      const rec = state.requests.find((r) => r.requestId === action.id);
      if (!rec) return state;
      return { ...state, requests: replaceRecord(state.requests, markEmailSentByHuman(rec)) };
    }
    case "SET_ACTIVE":
      return { ...state, activeRequestId: action.id };
    case "RESET":
      return init(true);
    default:
      return state;
  }
}

function init(force = false): State {
  if (!force && typeof localStorage !== "undefined") {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as State;
        if (parsed.requests) {
          return { ...parsed, backlog: SEED_BACKLOG };
        }
      }
    } catch {
      /* fall through to fresh state */
    }
  }
  return {
    requests: buildSeedRequests(SEED_BACKLOG),
    backlog: SEED_BACKLOG,
    activeRequestId: null,
  };
}

interface StoreApi {
  state: State;
  start: (text: string) => void;
  sendRequestorMessage: (id: string, text: string) => void;
  triage: (id: string, decision: "accept" | "defer" | "needs_info", note: string) => void;
  retryJiraWrite: (id: string) => void;
  simulateFailure: (id: string) => void;
  sendEmail: (id: string) => void;
  setActive: (id: string | null) => void;
  reset: () => void;
}

const StoreContext = createContext<StoreApi | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, () => init());

  // Keep the engine's backlog reference in sync.
  useEffect(() => {
    setBacklog(state.backlog);
  }, [state.backlog]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* storage may be unavailable */
    }
  }, [state]);

  const api = useMemo<StoreApi>(
    () => ({
      state,
      start: (text) => dispatch({ type: "START", text }),
      sendRequestorMessage: (id, text) => dispatch({ type: "REQUESTOR_MSG", id, text }),
      triage: (id, decision, note) => dispatch({ type: "TRIAGE", id, decision, note }),
      retryJiraWrite: (id) => dispatch({ type: "RETRY_JIRA", id }),
      simulateFailure: (id) => dispatch({ type: "SIM_FAIL", id }),
      sendEmail: (id) => dispatch({ type: "SEND_EMAIL", id }),
      setActive: (id) => dispatch({ type: "SET_ACTIVE", id }),
      reset: () => dispatch({ type: "RESET" }),
    }),
    [state],
  );

  return <StoreContext.Provider value={api}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreApi {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used within StoreProvider");
  return ctx;
}
