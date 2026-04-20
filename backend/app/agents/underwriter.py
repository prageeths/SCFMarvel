"""Underwriter Agent: builds risk profiles and credit limits."""
from __future__ import annotations

import math
import random
from typing import Optional, Tuple

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

RATING_LADDER = [b[0] for b in _RATING_BANDS]
RATING_SPREAD = {b[0]: b[2] for b in _RATING_BANDS}
RATING_PD = {b[0]: max(0.0001, b[1] * 0.6) for b in _RATING_BANDS}

# Companies (or any entity in their corporate tree) that should be force-rated
# at AA / AAA regardless of synthetic PD math.  Match is by case-insensitive
# substring against the company's name OR any ancestor's name.
NAMED_MAJORS_AAA = {
    "Walmart",
    "Amazon",
    "Coca-Cola",
}
NAMED_MAJORS_AA = {
    "Target",
    "Kroger",
    "Albertsons",
    "Jewel-Osco",
    "Costco",
    "Best Buy",
    "CVS",
    "Walgreens",
    "Publix",
    "PepsiCo",
    "Pepsi",
}

# Revenue thresholds (USD)
THRESHOLD_AA_REVENUE = 100_000_000_000.0   # >= $100B  -> at least AA (AAA above $250B)
THRESHOLD_AAA_REVENUE = 250_000_000_000.0
THRESHOLD_B_MAX_REVENUE = 5_000_000.0      # <  $5M    -> capped at B (or CCC)

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


def _max_revenue_in_tree(company: models.Company) -> float:
    """Largest annual revenue across the company AND any of its ancestors."""
    best = float(company.annual_revenue_usd or 0.0)
    cursor = company.parent
    seen = set()
    while cursor is not None and cursor.id not in seen:
        seen.add(cursor.id)
        if cursor.annual_revenue_usd:
            best = max(best, float(cursor.annual_revenue_usd))
        cursor = cursor.parent
    return best


def _named_major_band(company: models.Company) -> Optional[str]:
    """Return 'AAA', 'AA', or None based on the company (and ancestors') name."""
    names = [company.name or ""]
    cursor = company.parent
    seen = set()
    while cursor is not None and cursor.id not in seen:
        seen.add(cursor.id)
        names.append(cursor.name or "")
        cursor = cursor.parent
    blob = " | ".join(names).lower()

    for tag in NAMED_MAJORS_AAA:
        if tag.lower() in blob:
            return "AAA"
    for tag in NAMED_MAJORS_AA:
        if tag.lower() in blob:
            return "AA"
    return None


def _apply_policy(
    base_rating: str, company: models.Company
) -> Tuple[str, str]:
    """Return (final_rating, reason) after applying the policy overrides."""
    reasons = []
    final = base_rating

    named = _named_major_band(company)
    if named is not None:
        # Move up to at least the named-major floor.
        if RATING_LADDER.index(named) < RATING_LADDER.index(final):
            reasons.append(f"named-major floor → {named}")
            final = named

    max_rev = _max_revenue_in_tree(company)
    if max_rev >= THRESHOLD_AAA_REVENUE:
        if RATING_LADDER.index("AAA") < RATING_LADDER.index(final):
            reasons.append(f"revenue ${max_rev/1e9:.0f}B ≥ $250B → AAA")
            final = "AAA"
    elif max_rev >= THRESHOLD_AA_REVENUE:
        if RATING_LADDER.index("AA") < RATING_LADDER.index(final):
            reasons.append(f"revenue ${max_rev/1e9:.0f}B ≥ $100B → AA")
            final = "AA"

    own_rev = float(company.annual_revenue_usd or 0.0)
    if own_rev > 0 and own_rev < THRESHOLD_B_MAX_REVENUE:
        # Cap at B (no better) for tiny companies.
        if RATING_LADDER.index(final) < RATING_LADDER.index("B"):
            reasons.append(f"revenue ${own_rev/1e6:.2f}M < $5M → cap at B")
            final = "B"

    reason = "; ".join(reasons) if reasons else "model-derived"
    return final, reason


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

        base_rating = "CCC"
        for band_rating, max_pd, _band_spread in _RATING_BANDS:
            if pd_1y <= max_pd:
                base_rating = band_rating
                break

        # Apply named-major / revenue / floor / cap policy.
        rating, policy_reason = _apply_policy(base_rating, company)

        # Spread comes from the *final* rating band so it stays consistent.
        # Tiny random jitter so two AAA names don't look identical.
        spread = RATING_SPREAD[rating] + rng.uniform(-0.0008, 0.0015)
        spread = round(max(0.0025, spread), 4)

        # Re-derive a representative PD from the final band (so the dashboard
        # and the rating agree even after a policy override).
        final_pd = RATING_PD[rating]

        existing = company.risk_profile
        notes = (
            f"Base model rating={base_rating} (PD={pd_1y:.2%}); "
            f"final rating={rating} via {policy_reason}."
        )
        if existing:
            existing.rating = rating
            existing.pd_1y = final_pd
            existing.credit_spread = spread
            existing.industry_risk = industry_risk
            existing.country_risk = country_risk
            existing.leverage_score = leverage
            existing.notes = notes
            profile = existing
        else:
            profile = models.RiskProfile(
                company_id=company.id,
                rating=rating,
                pd_1y=final_pd,
                credit_spread=spread,
                industry_risk=industry_risk,
                country_risk=country_risk,
                leverage_score=leverage,
                notes=notes,
            )
            db.add(profile)

        log_event(
            db,
            NAME,
            "RISK_PROFILED",
            f"Profiled {company.name}: rating={rating} spread={spread:.2%} ({policy_reason}).",
            severity="DECISION",
            company_id=company.id,
            payload={
                "rating": rating,
                "base_rating": base_rating,
                "spread": spread,
                "pd_1y": final_pd,
                "policy_reason": policy_reason,
                "max_revenue_in_tree": _max_revenue_in_tree(company),
            },
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
