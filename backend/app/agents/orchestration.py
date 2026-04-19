"""Orchestration Agent: top-level coordinator for invoice processing."""
from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy.orm import Session

from .. import models
from ..config import BASE_RATE, FX_TO_USD
from ..schemas import InvoiceCreate
from .base import log_event
from .transaction import TransactionAgent

NAME = "OrchestrationAgent"


class CompanyNotFoundError(Exception):
    pass


class OrchestrationAgent:
    """Front door for new invoices.

    Resolves buyer/seller, validates payload, creates the invoice row,
    and dispatches to the TransactionAgent.
    """

    @staticmethod
    def _resolve_company(db: Session, name: str) -> models.Company:
        norm = name.strip()
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
        if company is None:
            raise CompanyNotFoundError(f"No company found matching '{name}'")
        return company

    @staticmethod
    def submit_invoice(db: Session, payload: InvoiceCreate) -> models.Invoice:
        product = payload.normalised_product()
        currency = payload.normalised_currency()
        tenor = payload.validate_tenor()

        seller = OrchestrationAgent._resolve_company(db, payload.seller_name)
        buyer = OrchestrationAgent._resolve_company(db, payload.buyer_name)

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
