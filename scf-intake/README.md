# Agentic Intake Request Application — Supply Chain Finance Platform

A conversational "front door" to the SCF platform backlog. Three orchestrated
agents **validate** an incoming request through an interactive dialogue,
**quantify ROI** and recommend a priority relative to the live backlog (drafting
a courteous deferral note for low‑value items), and **document** accepted
requests as well‑formed Jira stories — with an append‑only audit trail and
human‑in‑the‑loop gates throughout.

Built from the [PRD](../Agentic_Intake_Request_Application_PRD_33a1.md) in a
Wells Fargo‑inspired red‑and‑gold theme.

> **Live demo (production):** https://prageeths.github.io/SCFMarvel/

---

## What's here

| Path | What it is |
|---|---|
| `frontend/` | **React + Vite + TypeScript** SPA — intake chat + triage dashboard. Ships a self‑contained TypeScript agent engine so the deployed site is fully functional with no backend. This is the artifact deployed to GitHub Pages. |
| `backend/` | **FastAPI** production‑aware reference service: the same three agents, the transparent ROI scoring engine, SQLite persistence, and the full API surface from PRD §9. The OpenAI model sits behind a swappable adapter and is **optional** — the service runs deterministically with no API key. |
| `.env.example` | All (optional) configuration. |

The two implementations share the same domain logic and scoring rules; the
frontend mirrors the backend so the public URL works without any server or
secrets, exactly as a regulated POC requires (synthetic data only, no
auto‑sent email, transparent scoring).

---

## The three agents (PRD §6–§8)

1. **Intake Validation Agent** — turns a vague submission into a complete,
   credible, structured record. Asks only for what's missing or weak, one or two
   things at a time, never invents values, detects near‑duplicates, and escalates
   to a human after too many *unproductive* clarification rounds.
2. **Business Justification Agent** — computes a **transparent, config‑driven**
   ROI score (weights in one place, every factor contribution surfaced), ranks
   the request against the backlog, applies hard‑gate override rules
   (regulatory + hard deadline, Risk & Compliance loss‑avoidance, any Critical
   urgency → human review), and **drafts** (never sends) a respectful deferral
   email for low‑value items.
3. **Documentation Agent** — composes an "As a / I want / so that" story with
   acceptance criteria, maps intake + ROI to Jira fields, and writes it via the
   Jira adapter, with graceful retry so a request is never lost.

Orchestration follows the LangGraph state machine in PRD §5
(`start → validate → ask_human → justify → decision_gate → human_review →
document/draft_email → finalize`) with the mandatory human‑in‑the‑loop
interrupts.

---

## Run the frontend (the deployed app)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (VITE_BASE defaults to /SCFMarvel/)
# for a clean local root path:
VITE_BASE=/ npm run dev
```

Build for production:

```bash
VITE_BASE=/SCFMarvel/ npm run build   # outputs frontend/dist
```

State persists in `localStorage`, so submitted requests show up in the triage
dashboard across reloads.

## Run the backend (reference service)

```bash
cd backend
pip install -r requirements.txt          # or: pip install --break-system-packages -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
# API docs:    http://localhost:8000/docs
# Health:      http://localhost:8000/api/health
```

Run the tests:

```bash
cd backend && python -m pytest -q
```

### Enabling the LLM / Jira paths

The default build is deterministic and needs no secrets. To enable the
production paths, set values in `.env` (see `.env.example`):

- `OPENAI_API_KEY` → the OpenAI adapter (`app/tools/llm.py`) is used; swap in an
  enterprise gateway by implementing the same `LLMAdapter` interface.
- `SCF_JIRA_MCP_URL` → route Documentation‑agent writes through a Jira MCP server.
- `SCF_INTAKE_DB_URL` → point at Postgres for production (schema is Postgres‑compatible).

---

## API surface (PRD §9)

| Method & path | Purpose |
|---|---|
| `POST /api/intake` | Start a new intake; returns the first agent turn |
| `POST /api/intake/{id}/message` | Send a requestor reply; resumes the graph |
| `GET /api/intake/{id}` | Current state of an in‑flight intake |
| `GET /api/requests` | List requests (filter by `status`, `org`) |
| `GET /api/requests/{id}` | Full request detail incl. ROI & audit trail |
| `POST /api/requests/{id}/decision` | Triage decision (accept / defer / needs_info) |
| `GET /api/requests/{id}/email-draft` | Retrieve the draft deferral/acceptance email |
| `POST /api/requests/{id}/retry-jira` | Re‑attempt a failed Jira write |
| `GET /api/backlog` | Current ranked backlog snapshot |
| `GET /api/health` | Liveness/readiness |

---

## Deployment

Pushing to `main` (or any `cursor/**` branch) triggers
[`deploy-intake-pages.yml`](../.github/workflows/deploy-intake-pages.yml), which
builds `frontend/` with `VITE_BASE=/SCFMarvel/` and publishes it to GitHub Pages
at **https://prageeths.github.io/SCFMarvel/**.

The FastAPI backend is container‑ready for any platform (Render, Fly.io, Cloud
Run, ECS); set the environment variables above and run
`uvicorn app.main:app`.

---

## Non‑negotiable constraints encoded (PRD §15.2)

- **Draft‑only email** — there is no code path that sends mail automatically.
- **Human approval gates** before any Jira write for borderline/critical/regulatory items.
- **Transparent, config‑driven ROI scoring** — no hidden heuristics; every factor is shown.
- **Append‑only audit trail** on every agent and human action.
- **OpenAI behind an interface** so the provider can be swapped.
- **Synthetic data only** — no real customer/account/PII data.
