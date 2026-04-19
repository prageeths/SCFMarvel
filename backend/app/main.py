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


def _company_to_mini(c: models.Company) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "role": c.role,
        "country": c.country,
        "industry": c.industry,
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
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(models.Company)
    if role:
        q = q.filter(models.Company.role.in_([role.upper(), "BOTH"]))
    total = q.count()
    rows = q.order_by(models.Company.name.asc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_company_to_mini(c) for c in rows]}


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
