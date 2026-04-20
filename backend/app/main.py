"""FastAPI entry point for the AI-Native Supply Chain Finance platform."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .agents.orchestration import CompanyNotFoundError, OrchestrationAgent
from .config import (
    ALLOWED_TENORS,
    BASE_RATE,
    PRODUCT_FACTORING,
    PRODUCT_REVERSE_FACTORING,
    SUPPORTED_CURRENCIES,
)
from .database import SessionLocal, init_db
from . import models, schemas


app = FastAPI(
    title="AI-Native Supply Chain Finance Platform",
    version="1.0.0",
    description=(
        "Multi-agent platform supporting Factoring and Reverse Factoring with "
        "hierarchical credit limits, dynamic pricing, and an end-to-end audit "
        "trail of every agent decision."
    ),
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---------------------------------------------------------------------------
# Front-end (single-page dashboard)
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "templates" / "index.html")


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


@app.get("/api/meta")
def get_meta() -> dict:
    return {
        "base_rate": BASE_RATE,
        "base_rate_pct": f"{BASE_RATE * 100:.2f}%",
        "currencies": SUPPORTED_CURRENCIES,
        "tenors": ALLOWED_TENORS,
        "products": [
            {"value": PRODUCT_FACTORING, "label": "Factoring"},
            {"value": PRODUCT_REVERSE_FACTORING, "label": "Reverse Factoring"},
        ],
        "as_of": _dt.datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


RATING_ORDER = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]


def _company_to_mini(c: models.Company) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "role": c.role,
        "country": c.country,
        "industry": c.industry,
    }


def _company_to_row(c: models.Company) -> dict:
    """Like `_company_to_mini` but includes risk/rating fields for the list view."""
    rp = c.risk_profile
    return {
        "id": c.id,
        "name": c.name,
        "role": c.role,
        "country": c.country,
        "industry": c.industry,
        "annual_revenue_usd": c.annual_revenue_usd,
        "rating": rp.rating if rp else None,
        "credit_spread": rp.credit_spread if rp else None,
        "pd_1y": rp.pd_1y if rp else None,
        "parent_name": c.parent.name if c.parent else None,
    }


@app.get("/api/companies/search")
def search_companies(
    q: str = Query("", min_length=0, max_length=255),
    role: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> List[dict]:
    query = db.query(models.Company)
    if q:
        query = query.filter(models.Company.name.ilike(f"%{q}%"))
    if role:
        query = query.filter(models.Company.role.in_([role.upper(), "BOTH"]))
    rows = query.order_by(models.Company.name.asc()).limit(limit).all()
    return [_company_to_mini(c) for c in rows]


@app.get("/api/companies")
def list_companies(
    role: Optional[str] = None,
    rating: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = "name",
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    """List companies with rating info for the dashboard table.

    Supports filtering by role, rating, and a name substring, plus sort keys:
    ``name`` (default), ``rating`` (best first), ``revenue`` (highest first).
    """
    query = db.query(models.Company)
    if role:
        query = query.filter(models.Company.role.in_([role.upper(), "BOTH"]))
    if q:
        query = query.filter(models.Company.name.ilike(f"%{q}%"))
    if rating:
        query = query.join(models.RiskProfile).filter(
            models.RiskProfile.rating == rating.upper()
        )

    total = query.count()

    if sort == "revenue":
        query = query.order_by(models.Company.annual_revenue_usd.desc().nullslast())
    elif sort == "rating":
        # Sort by the canonical rating ladder at the DB level so pagination
        # works correctly. Unrated companies sink to the bottom.
        from sqlalchemy import case

        rating_rank = case(
            {r: i for i, r in enumerate(RATING_ORDER)},
            value=models.RiskProfile.rating,
            else_=99,
        )
        query = query.outerjoin(models.RiskProfile).order_by(
            rating_rank.asc(), models.Company.name.asc()
        )
    else:
        query = query.order_by(models.Company.name.asc())

    rows = query.offset(offset).limit(limit).all()
    items = [_company_to_row(c) for c in rows]

    return {"total": total, "items": items}


@app.get("/api/companies/{company_id}")
def company_detail(company_id: int, db: Session = Depends(get_db)) -> dict:
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(404, f"Company {company_id} not found")

    programs = (
        db.query(models.Program)
        .filter(
            (models.Program.buyer_id == company_id)
            | (models.Program.seller_id == company_id)
        )
        .order_by(models.Program.id.desc())
        .all()
    )

    rp = company.risk_profile
    return {
        "id": company.id,
        "name": company.name,
        "legal_name": company.legal_name,
        "country": company.country,
        "industry": company.industry,
        "role": company.role,
        "description": company.description,
        "website": company.website,
        "annual_revenue_usd": company.annual_revenue_usd,
        "employees": company.employees,
        "founded_year": company.founded_year,
        "tax_id": company.tax_id,
        "parent": _company_to_mini(company.parent) if company.parent else None,
        "children": [_company_to_mini(ch) for ch in company.children],
        "risk_profile": (
            {
                "rating": rp.rating,
                "pd_1y": rp.pd_1y,
                "credit_spread": rp.credit_spread,
                "industry_risk": rp.industry_risk,
                "country_risk": rp.country_risk,
                "leverage_score": rp.leverage_score,
                "last_reviewed": rp.last_reviewed.isoformat(),
            }
            if rp
            else None
        ),
        "credit_limits": [
            {
                "product": cl.product,
                "limit_usd": cl.limit_usd,
                "utilised_usd": cl.utilised_usd,
                "headroom_usd": round(cl.limit_usd - cl.utilised_usd, 2),
            }
            for cl in company.credit_limits
        ],
        "programs": [
            {
                "id": p.id,
                "name": p.name,
                "product": p.product,
                "buyer": _company_to_mini(p.buyer),
                "seller": _company_to_mini(p.seller),
                "credit_limit_usd": p.credit_limit_usd,
                "utilised_usd": p.utilised_usd,
                "status": p.status,
                "spread_override": p.spread_override,
            }
            for p in programs
        ],
    }


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


@app.get("/api/programs")
def list_programs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(models.Program)
    total = q.count()
    rows = q.order_by(models.Program.id.desc()).offset(offset).limit(limit).all()
    items = []
    for p in rows:
        items.append(
            {
                "id": p.id,
                "name": p.name,
                "product": p.product,
                "buyer": _company_to_mini(p.buyer),
                "seller": _company_to_mini(p.seller),
                "credit_limit_usd": p.credit_limit_usd,
                "utilised_usd": p.utilised_usd,
                "status": p.status,
            }
        )
    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


def _invoice_to_dict(inv: models.Invoice) -> dict:
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "seller": _company_to_mini(inv.seller),
        "buyer": _company_to_mini(inv.buyer),
        "product": inv.product,
        "amount": inv.amount,
        "currency": inv.currency,
        "amount_usd": inv.amount_usd,
        "tenor_days": inv.tenor_days,
        "grace_period_days": inv.grace_period_days,
        "issue_date": inv.issue_date.isoformat(),
        "due_date": inv.due_date.isoformat(),
        "base_rate": inv.base_rate,
        "credit_spread": inv.credit_spread,
        "fee_usd": inv.fee_usd,
        "funded_amount_usd": inv.funded_amount_usd,
        "status": inv.status,
        "decision_reason": inv.decision_reason,
        "program_id": inv.program_id,
    }


@app.post("/api/invoices")
def submit_invoice(
    payload: schemas.InvoiceCreate, db: Session = Depends(get_db)
) -> dict:
    try:
        invoice = OrchestrationAgent.submit_invoice(db, payload)
    except CompanyNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    events = (
        db.query(models.AgentEvent)
        .filter(models.AgentEvent.invoice_id == invoice.id)
        .order_by(models.AgentEvent.id.asc())
        .all()
    )
    return {
        "invoice": _invoice_to_dict(invoice),
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "agent": e.agent,
                "action": e.action,
                "severity": e.severity,
                "message": e.message,
            }
            for e in events
        ],
        "summary": (
            f"{invoice.invoice_number}: {invoice.status} — {invoice.decision_reason}"
        ),
    }


@app.get("/api/invoices")
def list_invoices(
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(models.Invoice)
    if status:
        q = q.filter(models.Invoice.status == status.upper())
    if company_id:
        q = q.filter(
            (models.Invoice.buyer_id == company_id)
            | (models.Invoice.seller_id == company_id)
        )
    total = q.count()
    rows = q.order_by(models.Invoice.id.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [_invoice_to_dict(inv) for inv in rows],
    }


@app.get("/api/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    inv = db.query(models.Invoice).get(invoice_id)
    if not inv:
        raise HTTPException(404, f"Invoice {invoice_id} not found")
    events = (
        db.query(models.AgentEvent)
        .filter(models.AgentEvent.invoice_id == inv.id)
        .order_by(models.AgentEvent.id.asc())
        .all()
    )
    return {
        "invoice": _invoice_to_dict(inv),
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "agent": e.agent,
                "action": e.action,
                "severity": e.severity,
                "message": e.message,
            }
            for e in events
        ],
    }


# ---------------------------------------------------------------------------
# Agent activity console
# ---------------------------------------------------------------------------


@app.get("/api/events")
def list_events(
    agent: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(models.AgentEvent)
    if agent:
        q = q.filter(models.AgentEvent.agent == agent)
    if severity:
        q = q.filter(models.AgentEvent.severity == severity.upper())
    total = q.count()
    rows = (
        q.order_by(models.AgentEvent.id.desc()).offset(offset).limit(limit).all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "agent": e.agent,
                "action": e.action,
                "severity": e.severity,
                "message": e.message,
                "invoice_id": e.invoice_id,
                "company_id": e.company_id,
                "program_id": e.program_id,
            }
            for e in rows
        ],
    }


# ---------------------------------------------------------------------------
# Explainability — facility check trace
# ---------------------------------------------------------------------------


@app.get("/api/programs/{program_id}/facility")
def program_facility_check(
    program_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Return a transparent breakdown of the facility-limit math for a program.

    Demonstrates how invoices in mixed currencies are checked: every invoice
    amount is converted to USD via :data:`FX_TO_USD`, then aggregated against
    the program's bilateral limit, the buyer subtree's hierarchical limits,
    and the seller subtree's hierarchical limits.
    """
    from .agents.credit_limit import CreditLimitAgent
    from .config import FX_TO_USD

    program = db.query(models.Program).get(program_id)
    if not program:
        raise HTTPException(404, f"Program {program_id} not found")

    # All non-rejected invoices count toward utilisation.
    invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.program_id == program_id)
        .order_by(models.Invoice.id.desc())
        .all()
    )
    open_invoices = [i for i in invoices if i.status in ("FUNDED", "APPROVED", "REVIEW")]

    # Per-currency rollup so we can show "5 invoices in EUR + 3 in USD"
    by_currency: dict = {}
    for inv in open_invoices:
        b = by_currency.setdefault(
            inv.currency,
            {
                "currency": inv.currency,
                "count": 0,
                "amount_native": 0.0,
                "fx_to_usd": FX_TO_USD.get(inv.currency, 1.0),
                "amount_usd": 0.0,
            },
        )
        b["count"] += 1
        b["amount_native"] = round(b["amount_native"] + inv.amount, 2)
        b["amount_usd"] = round(b["amount_usd"] + inv.amount_usd, 2)

    total_open_usd = round(sum(b["amount_usd"] for b in by_currency.values()), 2)

    program_limit = program.credit_limit_usd
    program_used = program.utilised_usd
    program_headroom = round(program_limit - program_used, 2)

    buyer_headroom, buyer_breakdown = CreditLimitAgent.hierarchical_headroom(
        db, program.buyer, program.product
    )
    seller_headroom, seller_breakdown = CreditLimitAgent.hierarchical_headroom(
        db, program.seller, program.product
    )

    binding = min(program_headroom, buyer_headroom, seller_headroom)
    if binding == program_headroom:
        binding_constraint = "program_limit"
    elif binding == buyer_headroom:
        binding_constraint = "buyer_hierarchical_limit"
    else:
        binding_constraint = "seller_hierarchical_limit"

    explanation_steps = [
        {
            "step": 1,
            "title": "Normalise every invoice to USD",
            "detail": (
                f"This program holds {len(open_invoices)} live invoices across "
                f"{len(by_currency)} currencies. Each invoice's native amount is "
                f"converted to USD using today's FX snapshot before any limit math "
                f"is performed. Total open exposure: ${total_open_usd:,.2f}."
            ),
        },
        {
            "step": 2,
            "title": "Bilateral program limit",
            "detail": (
                f"Program '{program.name}' carries a ${program_limit:,.2f} bilateral "
                f"limit. Currently utilised: ${program_used:,.2f}. "
                f"Headroom: ${program_headroom:,.2f}."
            ),
        },
        {
            "step": 3,
            "title": "Buyer hierarchical envelope",
            "detail": (
                f"Walk up the buyer's corporate tree. At each ancestor, sum the "
                f"USD utilisation of the entire subtree against that ancestor's "
                f"GLOBAL and {program.product} limits — the smallest available "
                f"headroom wins. Tightest buyer-side headroom: ${buyer_headroom:,.2f}."
            ),
        },
        {
            "step": 4,
            "title": "Seller hierarchical envelope",
            "detail": (
                f"Repeat the same walk for the seller's tree. Tightest seller-side "
                f"headroom: ${seller_headroom:,.2f}."
            ),
        },
        {
            "step": 5,
            "title": "Binding constraint",
            "detail": (
                f"Approve any new invoice whose USD-equivalent ≤ the smallest of "
                f"the three headrooms above. Today the **{binding_constraint}** is "
                f"binding at ${binding:,.2f}."
            ),
        },
    ]

    return {
        "program": {
            "id": program.id,
            "name": program.name,
            "product": program.product,
            "buyer": _company_to_mini(program.buyer),
            "seller": _company_to_mini(program.seller),
            "credit_limit_usd": program_limit,
            "utilised_usd": program_used,
            "headroom_usd": program_headroom,
            "status": program.status,
        },
        "fx_snapshot": FX_TO_USD,
        "open_invoices_by_currency": list(by_currency.values()),
        "open_invoices": [_invoice_to_dict(inv) for inv in open_invoices[:50]],
        "totals": {
            "open_invoice_count": len(open_invoices),
            "open_amount_usd": total_open_usd,
            "program_limit_usd": program_limit,
            "program_utilised_usd": program_used,
            "program_headroom_usd": program_headroom,
            "buyer_subtree_headroom_usd": buyer_headroom,
            "seller_subtree_headroom_usd": seller_headroom,
            "binding_headroom_usd": binding,
            "binding_constraint": binding_constraint,
        },
        "buyer_hierarchy_breakdown": buyer_breakdown,
        "seller_hierarchy_breakdown": seller_breakdown,
        "explanation": explanation_steps,
    }


# ---------------------------------------------------------------------------
# Transactions summary tab
# ---------------------------------------------------------------------------


@app.get("/api/transactions/summary")
def transactions_summary(db: Session = Depends(get_db)) -> dict:
    """Aggregations powering the dedicated 'Transactions' tab."""
    from sqlalchemy import func

    total = db.query(func.count(models.Invoice.id)).scalar() or 0

    # Overall money flows (USD)
    total_amount = db.query(func.sum(models.Invoice.amount_usd)).scalar() or 0.0
    total_fees = db.query(func.sum(models.Invoice.fee_usd)).scalar() or 0.0
    total_funded = db.query(func.sum(models.Invoice.funded_amount_usd)).scalar() or 0.0

    # By status + product
    by_status = {}
    for s, c, a, f in db.query(
        models.Invoice.status,
        func.count(models.Invoice.id),
        func.sum(models.Invoice.amount_usd),
        func.sum(models.Invoice.fee_usd),
    ).group_by(models.Invoice.status).all():
        by_status[s] = {
            "count": int(c or 0),
            "amount_usd": round(float(a or 0.0), 2),
            "fee_usd": round(float(f or 0.0), 2),
        }

    by_product = {}
    for p, c, a, f in db.query(
        models.Invoice.product,
        func.count(models.Invoice.id),
        func.sum(models.Invoice.amount_usd),
        func.sum(models.Invoice.fee_usd),
    ).group_by(models.Invoice.product).all():
        by_product[p] = {
            "count": int(c or 0),
            "amount_usd": round(float(a or 0.0), 2),
            "fee_usd": round(float(f or 0.0), 2),
        }

    by_currency = {}
    for cur, c, a in db.query(
        models.Invoice.currency,
        func.count(models.Invoice.id),
        func.sum(models.Invoice.amount),
    ).group_by(models.Invoice.currency).all():
        by_currency[cur] = {
            "count": int(c or 0),
            "amount_native": round(float(a or 0.0), 2),
        }

    # Top 10 programs by total USD flow
    top_programs_rows = (
        db.query(
            models.Invoice.program_id,
            func.count(models.Invoice.id),
            func.sum(models.Invoice.amount_usd),
        )
        .filter(models.Invoice.program_id.isnot(None))
        .group_by(models.Invoice.program_id)
        .order_by(func.sum(models.Invoice.amount_usd).desc())
        .limit(10)
        .all()
    )
    top_programs = []
    for pid, cnt, amt in top_programs_rows:
        prog = db.query(models.Program).get(pid)
        if prog is None:
            continue
        top_programs.append(
            {
                "program_id": pid,
                "name": prog.name,
                "product": prog.product,
                "buyer": _company_to_mini(prog.buyer),
                "seller": _company_to_mini(prog.seller),
                "invoice_count": int(cnt or 0),
                "amount_usd": round(float(amt or 0.0), 2),
            }
        )

    # Newest 25 invoices for the activity strip
    recent_invoices = (
        db.query(models.Invoice)
        .order_by(models.Invoice.id.desc())
        .limit(25)
        .all()
    )

    return {
        "as_of": _dt.datetime.utcnow().isoformat(),
        "base_rate": BASE_RATE,
        "totals": {
            "invoice_count": int(total),
            "amount_usd": round(float(total_amount), 2),
            "fee_usd": round(float(total_fees), 2),
            "funded_usd": round(float(total_funded), 2),
        },
        "by_status": by_status,
        "by_product": by_product,
        "by_currency": by_currency,
        "top_programs": top_programs,
        "recent_invoices": [_invoice_to_dict(inv) for inv in recent_invoices],
    }


@app.get("/api/summary")
def platform_summary(db: Session = Depends(get_db)) -> dict:
    total_invoices = db.query(models.Invoice).count()
    by_status = {}
    for inv in db.query(models.Invoice.status, models.Invoice.amount_usd).all():
        by_status.setdefault(inv.status, {"count": 0, "amount_usd": 0.0})
        by_status[inv.status]["count"] += 1
        by_status[inv.status]["amount_usd"] += inv.amount_usd or 0.0
    for k, v in by_status.items():
        v["amount_usd"] = round(v["amount_usd"], 2)

    by_product = {}
    for inv in db.query(models.Invoice.product, models.Invoice.amount_usd).all():
        by_product.setdefault(inv.product, {"count": 0, "amount_usd": 0.0})
        by_product[inv.product]["count"] += 1
        by_product[inv.product]["amount_usd"] += inv.amount_usd or 0.0
    for k, v in by_product.items():
        v["amount_usd"] = round(v["amount_usd"], 2)

    last_decisions = (
        db.query(models.AgentEvent)
        .filter(models.AgentEvent.severity == "DECISION")
        .order_by(models.AgentEvent.id.desc())
        .limit(20)
        .all()
    )
    return {
        "base_rate": BASE_RATE,
        "as_of": _dt.datetime.utcnow().isoformat(),
        "totals": {
            "companies": db.query(models.Company).count(),
            "programs": db.query(models.Program).count(),
            "invoices": total_invoices,
            "agent_events": db.query(models.AgentEvent).count(),
        },
        "by_status": by_status,
        "by_product": by_product,
        "recent_decisions": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "agent": e.agent,
                "action": e.action,
                "message": e.message,
                "invoice_id": e.invoice_id,
                "company_id": e.company_id,
            }
            for e in last_decisions
        ],
    }
