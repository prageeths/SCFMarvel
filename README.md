# Marvel SCF — AI-Native Supply Chain Finance Platform

A multi-agent demo platform that supports **Factoring** and **Reverse Factoring**.
It models hierarchical credit limits, multi-currency invoices, dynamic risk
pricing, and a fully auditable trail of every agent decision.

## Highlights

- **Multi-agent backend** — five cooperating agents:
  - `OrchestrationAgent` — front door for new invoices
  - `TransactionAgent` — routes invoices, checks credit limits, prices fees
  - `UnderwriterAgent` — builds risk profiles, opens & decides underwriting cases
  - `CreditLimitAgent` — sets / enforces hierarchical & per-product limits
  - `ReviewAgent` — decides on temporary limit increases
- **Hierarchical credit limits** — each company in a corporate tree
  (Walmart Global → Walmart LATAM → Walmart Brazil) holds its own
  global limit *and* per-product (Factoring / Reverse Factoring) sub-limits.
  Children's combined utilisation is constrained by their parents.
- **Per-program (buyer ↔ seller) bilateral limits** that can be temporarily
  increased through the Review Agent.
- **Dynamic pricing**: fee = principal × (`base_rate` + `credit_spread`) ×
  (tenor + grace) / 360. The base rate is a configurable platform constant
  (default 2%), and the spread is computed from the buyer/seller risk profiles.
- **Multi-currency invoices** (USD, EUR, GBP, CAD, MXN, BRL, COP, JPY) with
  automatic FX-to-USD normalisation for limit accounting.
- **Synthetic dataset**: 560+ companies (520+ US-based sellers, including
  Kellogg, Quaker, Coca-Cola, Pepsi, Reckitt/Delsym, Pfizer/Advil, Thermos, HP,
  Movado, Fossil, Citizen, Bulova, Skagen, ...), Walmart / Target / Kroger /
  Albertsons / Best Buy / Costco / CVS / Walgreens / Whole Foods / Publix /
  H-E-B / Aldi / Trader Joe's / Wegmans / Meijer hierarchical buyers, plus
  tier-2 packaging / ingredients / logistics suppliers, ~1,500 buyer ↔ seller
  programs and 12,000 invoices spread over the last 2 years.
- **Single-page dashboard** with:
  - Live **Base Rate** pill in the top bar
  - **New Invoice** form with searchable buyer / seller, currency dropdown,
    tenor select, and an inline decision trace from the agents
  - **Agent Console** showing every decision with severity and agent tags
  - **Programs** browser
  - **Companies** browser with full drill-down (hierarchy, programs, credit
    limits, risk profile, spread)

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser (SPA)                            │
│  Dashboard · New Invoice · Agent Console · Programs · Companies  │
└──────────────▲────────────────────────────▲──────────────────────┘
               │ JSON                       │ JSON
┌──────────────┴────────────────────────────┴──────────────────────┐
│                         FastAPI (backend.app)                    │
│   /api/meta · /api/summary · /api/companies · /api/programs ·    │
│   /api/invoices · /api/events                                    │
└──────┬─────────────────────────────────────────────────┬─────────┘
       │                                                 │
       ▼                                                 ▼
┌─────────────────────┐                  ┌─────────────────────────┐
│ Orchestration Agent │ ───► Transaction │ Credit Limit Agent      │
│                     │      Agent  ──► │ Underwriter Agent       │
│                     │             ──► │ Review Agent            │
└─────────────────────┘                  └─────────────────────────┘
                              │
                              ▼
                    SQLAlchemy + SQLite (data/scf.db)
```

## Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── agents/               # Agent swarm
│   │   │   ├── orchestration.py
│   │   │   ├── transaction.py
│   │   │   ├── credit_limit.py
│   │   │   ├── underwriter.py
│   │   │   └── review.py
│   │   ├── config.py             # Base rate, currencies, FX, products
│   │   ├── database.py           # SQLAlchemy engine + session
│   │   ├── models.py             # SQLAlchemy schema
│   │   ├── schemas.py            # Pydantic request/response models
│   │   └── main.py               # FastAPI app + REST routes
│   └── seed.py                   # Generates 560+ companies + 12k invoices
├── frontend/
│   ├── templates/index.html      # Single-page dashboard
│   └── static/
│       ├── styles.css
│       └── app.js
├── data/                         # SQLite DB lives here
├── requirements.txt
└── README.md
```

## Running locally

```bash
# 1. Install Python dependencies
pip install -r requirements.txt          # (or: pip install --break-system-packages -r requirements.txt)

# 2. Seed the database (560+ companies, 1.5k programs, 12k invoices)
python -m backend.seed                   # default = 12,000 invoices
# python -m backend.seed 25000           # bigger run

# 3. Start the API + dashboard
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# 4. Open the dashboard
open http://localhost:8000/
```

## Trying it end-to-end

After seeding, in the dashboard:

1. **Dashboard tab** — verify the platform overview (companies, programs,
   invoices, recent decisions, status & product breakdowns).
2. **New Invoice tab** — start typing `Coca` in seller, `Walmart` in buyer,
   pick a currency, amount, tenor, grace and submit. The agent decision trail
   renders live underneath the form.
3. **Agent Console tab** — every decision is logged with the originating
   agent, action and severity (filterable).
4. **Programs tab** — browse all bilateral programs and their utilisation.
5. **Companies tab** — search companies, click any one to inspect hierarchy,
   credit limits per product, risk profile (rating, PD, spread, country &
   industry risk) and all programs they participate in.

## Key configuration

`backend/app/config.py`:

| Setting             | Default | Notes                                       |
|---------------------|---------|---------------------------------------------|
| `BASE_RATE`         | `0.02`  | Override with env var `SCF_BASE_RATE`       |
| `SUPPORTED_CURRENCIES` | 8 currencies + FX rates              |                                             |
| `ALLOWED_TENORS`    | `[30, 60, 90]` | Form & validator both honour this    |
| `DATABASE_URL`      | `sqlite:///data/scf.db` | Override with `SCF_DB_URL`        |

## Rating policy

The Underwriter Agent applies the following floors / caps on top of its
synthetic PD model (see `backend/app/agents/underwriter.py`):

| Trigger                                                         | Effect                |
|-----------------------------------------------------------------|-----------------------|
| Annual revenue (anywhere in the corporate tree) ≥ **$250B**     | Floor at **AAA**      |
| Annual revenue (anywhere in the corporate tree) ≥ **$100B**     | Floor at **AA**       |
| Named-major: Walmart, Amazon, Coca-Cola (any node in the tree)  | Floor at **AAA**      |
| Named-major: Target, Kroger, Albertsons, Jewel-Osco, Costco, Best Buy, CVS, Walgreens, Publix, PepsiCo (any node) | Floor at **AA** |
| Own annual revenue **< $5M**                                    | Cap at **B**          |

Re-rate the entire roster (and re-price historical invoices to match) without
re-seeding:

```bash
python -m backend.rerate
```

The rerate script also seeds a handful of micro-cap (<$5M revenue) demo
suppliers (`Cedar & Sons Roastery`, `Brookline Artisan Snacks`, ...) so the
small-cap floor is observable in the dashboard.

## Explainability

Every program exposes a transparent facility-limit trace at
`GET /api/programs/{id}/facility`. The response shows:

1. All live invoices aggregated **by currency**, with the FX rate used and
   the per-currency USD-equivalent.
2. The bilateral program limit (limit, utilised, headroom).
3. The **buyer hierarchical envelope** — for every ancestor in the buyer's
   corporate tree, the headroom against both that ancestor's GLOBAL and
   product-specific limits, with subtree utilisation rolled up.
4. The same walk for the **seller** subtree.
5. The **binding constraint** — whichever of the three headrooms is tightest
   right now.

This is rendered on the `Transactions` and `Programs` tabs as an "Explain"
button on each program row, producing a step-by-step reasoning panel with
per-currency aggregation, hierarchical breakdown tables, and the binding
constraint highlighted.

### Worked example

For program `Cargill Inc → Jewel-Osco (REVERSE_FACTORING)` with 9 live
invoices in COP / BRL / CAD / MXN, the panel shows:

- Step 1 normalises every invoice into USD via `FX_TO_USD` →
  total open exposure $613,696.
- Step 2 reports the bilateral program limit ($20,436,594) and current
  utilisation, leaving program headroom $19,822,898.
- Step 3 walks the buyer tree (Jewel-Osco → Albertsons Companies),
  taking the *minimum* headroom across both `REVERSE_FACTORING` and
  `GLOBAL` limits at each level. The tightest buyer-side headroom wins.
- Step 4 does the same for the seller (Cargill).
- Step 5 names the binding constraint — here `program_limit` at $19.8M.

## Notes on agent design

The agents are deliberately *deterministic, transparent rules-engines*
wrapped behind a multi-agent persona. That keeps the demo fully offline,
reproducible, and trivially extensible: each agent can be replaced with an
LLM-backed implementation by swapping its module while keeping the same
event log + persistence layer intact.
