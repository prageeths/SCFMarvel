"""Orchestration Agent: top-level coordinator for invoice processing."""
from __future__ import annotations

import datetime as _dt
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..config import BASE_RATE, FX_TO_USD
from ..schemas import CompanyOnboard, InvoiceCreate
from .base import log_event
from .credit_limit import CreditLimitAgent
from .transaction import TransactionAgent
from .underwriter import UnderwriterAgent

NAME = "OrchestrationAgent"


class CompanyNotFoundError(Exception):
    """Raised when a buyer/seller is not in the roster.

    The ``payload`` attribute tells the client which side is missing so the
    UI can prompt the user to onboard it.
    """

    def __init__(self, message: str, side: Optional[str] = None, name: Optional[str] = None):
        super().__init__(message)
        self.side = side  # "seller" or "buyer"
        self.missing_name = name


class OrchestrationAgent:
    """Front door for new invoices.

    Resolves buyer/seller, validates payload, creates the invoice row,
    and dispatches to the TransactionAgent.
    """

    @staticmethod
    def _resolve_company(db: Session, name: str) -> Optional[models.Company]:
        norm = name.strip()
        if not norm:
            return None
        company = (
            db.query(models.Company)
            .filter(models.Company.name == norm)
            .one_or_none()
        )
        if company is None:
            company = (
                db.query(models.Company)
                .filter(models.Company.name.ilike(norm))
                .first()
            )
        return company

    @staticmethod
    def onboard_company(db: Session, info: CompanyOnboard) -> models.Company:
        """Create a new company, then run the Underwriter + CreditLimit agents."""
        role = info.normalised_role()

        # Prevent duplicates — if the name already matches something, return it.
        existing = OrchestrationAgent._resolve_company(db, info.name)
        if existing is not None:
            return existing

        parent = None
        if info.parent_name:
            parent = OrchestrationAgent._resolve_company(db, info.parent_name)

        founded_year = _dt.datetime.utcnow().year - int(info.years_operated)
        company = models.Company(
            name=info.name.strip(),
            legal_name=info.name.strip(),
            country=info.country.strip().upper()[:2] if len(info.country.strip()) <= 3 else info.country.strip(),
            industry=(info.industry or "Industrial").strip(),
            role=role,
            tax_id=f"EIN-{uuid.uuid4().hex[:8].upper()}",
            website=None,
            founded_year=founded_year,
            employees=max(1, int(info.annual_revenue_usd / 250_000)),
            annual_revenue_usd=float(info.annual_revenue_usd),
            description=f"Onboarded via dashboard on {_dt.datetime.utcnow().date().isoformat()}.",
            parent_id=parent.id if parent else None,
        )
        db.add(company)
        db.flush()

        log_event(
            db,
            NAME,
            "COMPANY_ONBOARDED",
            f"Onboarded new company {company.name} (role={role}, "
            f"country={company.country}, rev=${info.annual_revenue_usd:,.0f}, "
            f"years={info.years_operated}).",
            severity="DECISION",
            company_id=company.id,
            payload={
                "years_operated": info.years_operated,
                "annual_revenue_usd": info.annual_revenue_usd,
                "country": company.country,
                "industry": company.industry,
            },
        )

        # Run the underwriter + credit-limit agents right away so the company
        # has a rating, spread, and global/product credit lines before any
        # invoice is evaluated.
        UnderwriterAgent.build_risk_profile(db, company)
        CreditLimitAgent.ensure_global_limit(db, company)
        from ..config import PRODUCT_FACTORING, PRODUCT_REVERSE_FACTORING
        CreditLimitAgent.ensure_product_limit(db, company, PRODUCT_FACTORING)
        CreditLimitAgent.ensure_product_limit(db, company, PRODUCT_REVERSE_FACTORING)
        db.flush()
        return company

    @staticmethod
    def submit_invoice(db: Session, payload: InvoiceCreate) -> models.Invoice:
        product = payload.normalised_product()
        currency = payload.normalised_currency()
        tenor = payload.validate_tenor()

        seller = OrchestrationAgent._resolve_company(db, payload.seller_name)
        if seller is None and payload.new_seller is not None:
            if payload.new_seller.name.strip().lower() != payload.seller_name.strip().lower():
                raise ValueError(
                    "new_seller.name must match seller_name on the invoice."
                )
            seller = OrchestrationAgent.onboard_company(db, payload.new_seller)
        if seller is None:
            raise CompanyNotFoundError(
                f"No company found matching seller '{payload.seller_name}'",
                side="seller",
                name=payload.seller_name,
            )

        buyer = OrchestrationAgent._resolve_company(db, payload.buyer_name)
        if buyer is None and payload.new_buyer is not None:
            if payload.new_buyer.name.strip().lower() != payload.buyer_name.strip().lower():
                raise ValueError(
                    "new_buyer.name must match buyer_name on the invoice."
                )
            buyer = OrchestrationAgent.onboard_company(db, payload.new_buyer)
        if buyer is None:
            raise CompanyNotFoundError(
                f"No company found matching buyer '{payload.buyer_name}'",
                side="buyer",
                name=payload.buyer_name,
            )

        if seller.id == buyer.id:
            raise ValueError("Seller and buyer must be different companies.")

        amount_usd = round(payload.amount * FX_TO_USD.get(currency, 1.0), 2)
        issue_date = _dt.datetime.utcnow()
        due_date = issue_date + _dt.timedelta(days=tenor)
        invoice_number = payload.invoice_number or f"INV-{uuid.uuid4().hex[:10].upper()}"

        invoice = models.Invoice(
            invoice_number=invoice_number,
            seller_id=seller.id,
            buyer_id=buyer.id,
            product=product,
            amount=payload.amount,
            currency=currency,
            amount_usd=amount_usd,
            tenor_days=tenor,
            grace_period_days=payload.grace_period_days,
            issue_date=issue_date,
            due_date=due_date,
            base_rate=BASE_RATE,
            credit_spread=0.0,
            status="PENDING",
        )
        db.add(invoice)
        db.flush()

        log_event(
            db,
            NAME,
            "INVOICE_RECEIVED",
            f"Received invoice {invoice.invoice_number} from {seller.name} "
            f"to {buyer.name} for {payload.amount:,.2f} {currency} "
            f"(${amount_usd:,.2f} USD), tenor={tenor}d, product={product}.",
            severity="INFO",
            invoice_id=invoice.id,
            payload={
                "amount": payload.amount,
                "currency": currency,
                "amount_usd": amount_usd,
                "product": product,
                "tenor_days": tenor,
            },
        )

        TransactionAgent.evaluate(db, invoice)
        log_event(
            db,
            NAME,
            "FLOW_COMPLETE",
            f"Final status of {invoice.invoice_number}: {invoice.status}.",
            severity="DECISION",
            invoice_id=invoice.id,
            program_id=invoice.program_id,
        )
        db.commit()
        db.refresh(invoice)
        return invoice
