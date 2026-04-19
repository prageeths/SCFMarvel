"""Transaction Agent: routes invoices through approve / review / underwrite."""
from __future__ import annotations

import datetime as _dt
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from .. import models
from ..config import BASE_RATE, FX_TO_USD
from .base import log_event
from .credit_limit import CreditLimitAgent
from .review import ReviewAgent
from .underwriter import UnderwriterAgent

NAME = "TransactionAgent"


class TransactionAgent:
    # ---------- helpers ----------
    @staticmethod
    def _to_usd(amount: float, currency: str) -> float:
        return round(amount * FX_TO_USD.get(currency, 1.0), 2)

    @staticmethod
    def _find_program(
        db: Session, buyer_id: int, seller_id: int, product: str
    ) -> Optional[models.Program]:
        return (
            db.query(models.Program)
            .filter(
                models.Program.buyer_id == buyer_id,
                models.Program.seller_id == seller_id,
                models.Program.product == product,
                models.Program.status == "ACTIVE",
            )
            .one_or_none()
        )

    @staticmethod
    def _spread_for(program: Optional[models.Program], invoice: models.Invoice) -> float:
        if program is not None and program.spread_override is not None:
            return program.spread_override
        # Use the WEIGHTED AVERAGE of buyer/seller spreads for risk pricing.
        b = invoice.buyer.risk_profile.credit_spread if invoice.buyer.risk_profile else 0.02
        s = invoice.seller.risk_profile.credit_spread if invoice.seller.risk_profile else 0.02
        return round((b + s) / 2.0, 4)

    @staticmethod
    def _compute_fee(
        invoice: models.Invoice, base_rate: float, spread: float
    ) -> Tuple[float, float]:
        # Annualised total rate × tenor fraction × principal (USD)
        total_rate = base_rate + spread
        days = invoice.tenor_days + (invoice.grace_period_days or 0)
        period = days / 360.0
        fee = invoice.amount_usd * total_rate * period
        funded = invoice.amount_usd - fee
        return round(fee, 2), round(funded, 2)

    # ---------- main entry point ----------
    @staticmethod
    def evaluate(
        db: Session,
        invoice: models.Invoice,
    ) -> models.Invoice:
        # 1. Make sure both parties have risk profiles + base limits.
        for party in (invoice.buyer, invoice.seller):
            if party.risk_profile is None:
                UnderwriterAgent.build_risk_profile(db, party)
            CreditLimitAgent.ensure_global_limit(db, party)
            CreditLimitAgent.ensure_product_limit(db, party, invoice.product)

        # 2. Find program. If none, hand off to underwriting.
        program = TransactionAgent._find_program(
            db, invoice.buyer_id, invoice.seller_id, invoice.product
        )

        if program is None:
            invoice.status = "UNDERWRITING"
            invoice.decision_reason = "No active program; sent to UnderwriterAgent."
            log_event(
                db,
                NAME,
                "ROUTED_TO_UNDERWRITING",
                f"No program for {invoice.seller.name} -> {invoice.buyer.name} "
                f"({invoice.product}). Routing to underwriting.",
                severity="DECISION",
                invoice_id=invoice.id,
            )
            requested = invoice.amount_usd * 5
            case = UnderwriterAgent.open_case_for_program(
                db, invoice, requested_limit_usd=requested
            )
            program = UnderwriterAgent.auto_decide_case(db, case, invoice)
            if program is None:
                # Underwriting rejected — invoice already marked REJECTED.
                return invoice

        # 3. We have a program; check headrooms.
        program_headroom = max(0.0, program.credit_limit_usd - program.utilised_usd)

        buyer_headroom, buyer_breakdown = CreditLimitAgent.hierarchical_headroom(
            db, invoice.buyer, invoice.product
        )
        seller_headroom, seller_breakdown = CreditLimitAgent.hierarchical_headroom(
            db, invoice.seller, invoice.product
        )

        spread = TransactionAgent._spread_for(program, invoice)
        invoice.base_rate = BASE_RATE
        invoice.credit_spread = spread
        fee, funded = TransactionAgent._compute_fee(invoice, BASE_RATE, spread)
        invoice.fee_usd = fee
        invoice.funded_amount_usd = funded
        invoice.program_id = program.id

        log_event(
            db,
            NAME,
            "LIMIT_CHECK",
            (
                f"Headroom check — program=${program_headroom:,.0f} "
                f"buyer_subtree=${buyer_headroom:,.0f} seller_subtree=${seller_headroom:,.0f}"
            ),
            invoice_id=invoice.id,
            program_id=program.id,
            payload={
                "program_headroom": program_headroom,
                "buyer_breakdown": buyer_breakdown,
                "seller_breakdown": seller_breakdown,
                "amount_usd": invoice.amount_usd,
            },
        )

        amount = invoice.amount_usd

        # If subtree limit (hierarchical) is breached, that's a hard fail.
        if amount > buyer_headroom or amount > seller_headroom:
            invoice.status = "REJECTED"
            invoice.decision_reason = (
                f"Hierarchical credit limit exceeded "
                f"(buyer_headroom=${buyer_headroom:,.0f} seller_headroom=${seller_headroom:,.0f})."
            )
            log_event(
                db,
                NAME,
                "REJECTED_HIERARCHICAL_LIMIT",
                invoice.decision_reason,
                severity="DECISION",
                invoice_id=invoice.id,
            )
            return invoice

        # If the program limit is the constraint, we hand off to the Review Agent.
        if amount > program_headroom:
            overage = amount - program_headroom
            invoice.status = "REVIEW"
            invoice.decision_reason = (
                f"Program limit exceeded by ${overage:,.0f}; sent to ReviewAgent."
            )
            log_event(
                db,
                NAME,
                "ROUTED_TO_REVIEW",
                invoice.decision_reason,
                severity="DECISION",
                invoice_id=invoice.id,
                program_id=program.id,
            )
            review_case = ReviewAgent.decide_overage(db, invoice, program, overage)
            if review_case.decision == "DENIED":
                return invoice
            # else: temp increase approved → fall through to APPROVED + reserve

        invoice.status = "APPROVED"
        invoice.decision_reason = (
            f"Approved at base_rate={BASE_RATE:.2%} + spread={spread:.2%} "
            f"=> fee=${fee:,.2f}, funded=${funded:,.2f}."
        )
        CreditLimitAgent.reserve(db, invoice, program)
        log_event(
            db,
            NAME,
            "APPROVED",
            invoice.decision_reason,
            severity="DECISION",
            invoice_id=invoice.id,
            program_id=program.id,
        )

        # Mark FUNDED for completeness (synchronous demo).
        invoice.status = "FUNDED"
        log_event(
            db,
            NAME,
            "FUNDED",
            f"Invoice {invoice.invoice_number} funded ${funded:,.2f}.",
            invoice_id=invoice.id,
            program_id=program.id,
        )
        return invoice
