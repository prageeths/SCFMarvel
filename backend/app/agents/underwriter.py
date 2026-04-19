"""Underwriter Agent: builds risk profiles and credit limits."""
from __future__ import annotations

import math
import random
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from .base import log_event

NAME = "UnderwriterAgent"

# Rating ladder used for both initial profiling and re-rating.
_RATING_BANDS = [
    # (rating, max_pd_1y, base_spread)
    ("AAA", 0.0010, 0.0050),
    ("AA",  0.0030, 0.0080),
    ("A",   0.0070, 0.0120),
    ("BBB", 0.0150, 0.0180),
    ("BB",  0.0350, 0.0260),
    ("B",   0.0700, 0.0380),
    ("CCC", 1.0000, 0.0600),
]

_INDUSTRY_RISK = {
    "Food & Beverage": 0.002,
    "Retail": 0.003,
    "Pharmaceuticals": 0.0015,
    "Consumer Electronics": 0.004,
    "Apparel": 0.005,
    "Home Goods": 0.0035,
    "Logistics": 0.004,
    "Packaging": 0.003,
    "Ingredients": 0.0035,
    "Watches & Accessories": 0.0045,
    "Industrial": 0.005,
}

_COUNTRY_RISK = {
    "US": 0.0005, "CA": 0.0008, "MX": 0.0040, "BR": 0.0060,
    "CO": 0.0070, "GB": 0.0010, "DE": 0.0010, "FR": 0.0015,
    "JP": 0.0010,
}


class UnderwriterAgent:
    """Builds (or refreshes) the risk profile and global/product credit lines."""

    @staticmethod
    def build_risk_profile(db: Session, company: models.Company, *, rng: Optional[random.Random] = None) -> models.RiskProfile:
        rng = rng or random.Random(company.id * 7919 + 13)

        revenue = company.annual_revenue_usd or rng.uniform(5e6, 5e9)
        leverage = rng.uniform(0.1, 0.9)  # debt / assets proxy
        size_factor = max(0.0001, 1.0 / (1.0 + math.log10(max(revenue, 1e6))))

        industry_risk = _INDUSTRY_RISK.get(company.industry or "", 0.004)
        country_risk = _COUNTRY_RISK.get(company.country or "US", 0.002)

        # Synthetic 1y PD blending size, leverage, industry, country.
        pd_1y = max(
            0.0002,
            min(0.20, size_factor * 0.05 + leverage * 0.04 + industry_risk + country_risk),
        )

        rating = "CCC"
        spread = 0.06
        for band_rating, max_pd, band_spread in _RATING_BANDS:
            if pd_1y <= max_pd:
                rating = band_rating
                spread = band_spread
                break

        # Add a small random jitter to the spread so different companies in the
        # same band don't all look identical.
        spread = round(spread + rng.uniform(-0.0015, 0.0030), 4)
        spread = max(0.0025, spread)

        existing = company.risk_profile
        if existing:
            existing.rating = rating
            existing.pd_1y = pd_1y
            existing.credit_spread = spread
            existing.industry_risk = industry_risk
            existing.country_risk = country_risk
            existing.leverage_score = leverage
            existing.notes = "Re-rated by UnderwriterAgent"
            profile = existing
        else:
            profile = models.RiskProfile(
                company_id=company.id,
                rating=rating,
                pd_1y=pd_1y,
                credit_spread=spread,
                industry_risk=industry_risk,
                country_risk=country_risk,
                leverage_score=leverage,
                notes="Initial profile by UnderwriterAgent",
            )
            db.add(profile)

        log_event(
            db,
            NAME,
            "RISK_PROFILED",
            f"Profiled {company.name}: rating={rating} spread={spread:.2%} pd_1y={pd_1y:.2%}",
            severity="DECISION",
            company_id=company.id,
            payload={"rating": rating, "spread": spread, "pd_1y": pd_1y},
        )
        return profile

    @staticmethod
    def open_case_for_program(
        db: Session,
        invoice: models.Invoice,
        *,
        requested_limit_usd: float,
    ) -> models.UnderwritingCase:
        case = models.UnderwritingCase(
            invoice_id=invoice.id,
            buyer_id=invoice.buyer_id,
            seller_id=invoice.seller_id,
            product=invoice.product,
            requested_limit_usd=requested_limit_usd,
            status="OPEN",
        )
        db.add(case)
        db.flush()
        log_event(
            db,
            NAME,
            "UNDERWRITING_CASE_OPENED",
            f"No program exists for buyer={invoice.buyer.name} seller={invoice.seller.name} "
            f"product={invoice.product}. Underwriting requested limit ${requested_limit_usd:,.0f}.",
            severity="DECISION",
            invoice_id=invoice.id,
        )
        return case

    @staticmethod
    def auto_decide_case(
        db: Session,
        case: models.UnderwritingCase,
        invoice: models.Invoice,
    ) -> Optional[models.Program]:
        """Auto-decision rules so the demo flows end-to-end:

        Approve a brand new program if:
          * Both parties have BBB or better ratings, AND
          * The requested limit is <= 5x the invoice amount, AND
          * Neither party is currently breaching its own global limit.
        Otherwise, decline.
        """
        from .credit_limit import CreditLimitAgent  # local import to avoid cycle

        buyer = invoice.buyer
        seller = invoice.seller
        for party in (buyer, seller):
            if party.risk_profile is None:
                UnderwriterAgent.build_risk_profile(db, party)

        b_rating = buyer.risk_profile.rating
        s_rating = seller.risk_profile.rating
        ladder = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]

        approve = (
            ladder.index(b_rating) <= ladder.index("BBB")
            and ladder.index(s_rating) <= ladder.index("BB")
        )

        if not approve:
            case.status = "DECLINED"
            case.decision_notes = (
                f"Declined: buyer={b_rating}/seller={s_rating} below underwriting cutoff."
            )
            invoice.status = "REJECTED"
            invoice.decision_reason = case.decision_notes
            log_event(
                db,
                NAME,
                "UNDERWRITING_DECLINED",
                case.decision_notes,
                severity="DECISION",
                invoice_id=invoice.id,
            )
            return None

        program_limit = max(case.requested_limit_usd * 4, invoice.amount_usd * 5)
        program = models.Program(
            name=f"{seller.name} → {buyer.name} ({invoice.product})",
            buyer_id=buyer.id,
            seller_id=seller.id,
            product=invoice.product,
            credit_limit_usd=round(program_limit, 2),
            base_currency=invoice.currency,
            grace_period_days=invoice.grace_period_days or 5,
            status="ACTIVE",
        )
        db.add(program)
        db.flush()

        case.status = "APPROVED"
        case.decision_notes = (
            f"Approved program {program.id}; new bilateral limit ${program.credit_limit_usd:,.0f}."
        )
        invoice.program_id = program.id

        # Make sure each party has product-level credit lines.
        CreditLimitAgent.ensure_product_limit(db, buyer, invoice.product)
        CreditLimitAgent.ensure_product_limit(db, seller, invoice.product)

        log_event(
            db,
            NAME,
            "PROGRAM_CREATED",
            f"Created program {program.name} with ${program.credit_limit_usd:,.0f} bilateral limit.",
            severity="DECISION",
            invoice_id=invoice.id,
            program_id=program.id,
        )
        return program
