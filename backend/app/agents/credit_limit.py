"""Credit Limit Agent: dynamically sets and enforces hierarchical limits."""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from .. import models
from ..config import PRODUCT_FACTORING, PRODUCT_REVERSE_FACTORING
from .base import ancestor_chain, descendant_ids, log_event

NAME = "CreditLimitAgent"

GLOBAL = "GLOBAL"


class CreditLimitAgent:
    # ---------- limit construction ----------
    @staticmethod
    def derive_global_limit(company: models.Company) -> float:
        """A simple model: 8% of annual revenue, floor $1M, ceiling $5B."""
        revenue = company.annual_revenue_usd or 5e7
        raw = revenue * 0.08
        return max(1_000_000.0, min(5_000_000_000.0, raw))

    @staticmethod
    def ensure_global_limit(db: Session, company: models.Company) -> models.CreditLimit:
        existing = (
            db.query(models.CreditLimit)
            .filter(
                models.CreditLimit.company_id == company.id,
                models.CreditLimit.product == GLOBAL,
            )
            .one_or_none()
        )
        if existing:
            return existing
        cl = models.CreditLimit(
            company_id=company.id,
            product=GLOBAL,
            limit_usd=round(CreditLimitAgent.derive_global_limit(company), 2),
            utilised_usd=0.0,
            set_by="UNDERWRITER_AGENT",
        )
        db.add(cl)
        db.flush()
        log_event(
            db,
            NAME,
            "GLOBAL_LIMIT_SET",
            f"Set global credit limit for {company.name} = ${cl.limit_usd:,.0f}",
            severity="DECISION",
            company_id=company.id,
            payload={"limit_usd": cl.limit_usd},
        )
        return cl

    @staticmethod
    def ensure_product_limit(
        db: Session, company: models.Company, product: str
    ) -> models.CreditLimit:
        if product not in (PRODUCT_FACTORING, PRODUCT_REVERSE_FACTORING):
            raise ValueError(f"Unknown product {product}")
        existing = (
            db.query(models.CreditLimit)
            .filter(
                models.CreditLimit.company_id == company.id,
                models.CreditLimit.product == product,
            )
            .one_or_none()
        )
        if existing:
            return existing
        global_cl = CreditLimitAgent.ensure_global_limit(db, company)
        # Split: 60% to FACTORING, 40% to REVERSE_FACTORING by default.
        share = 0.6 if product == PRODUCT_FACTORING else 0.4
        cl = models.CreditLimit(
            company_id=company.id,
            product=product,
            limit_usd=round(global_cl.limit_usd * share, 2),
            utilised_usd=0.0,
            set_by="CREDIT_LIMIT_AGENT",
        )
        db.add(cl)
        db.flush()
        log_event(
            db,
            NAME,
            "PRODUCT_LIMIT_SET",
            f"Set {product} sub-limit for {company.name} = ${cl.limit_usd:,.0f}",
            severity="DECISION",
            company_id=company.id,
            payload={"product": product, "limit_usd": cl.limit_usd},
        )
        return cl

    # ---------- hierarchical headroom checks ----------
    @staticmethod
    def _utilisation_for_subtree(
        db: Session, company: models.Company, product: Optional[str]
    ) -> float:
        """Sum of utilised_usd across this company AND all descendants."""
        ids = [company.id] + descendant_ids(db, company.id)
        q = db.query(models.CreditLimit).filter(models.CreditLimit.company_id.in_(ids))
        if product is None:
            q = q.filter(models.CreditLimit.product == GLOBAL)
        else:
            q = q.filter(models.CreditLimit.product == product)
        return sum(cl.utilised_usd for cl in q.all())

    @staticmethod
    def hierarchical_headroom(
        db: Session, company: models.Company, product: str
    ) -> Tuple[float, Dict[str, float]]:
        """Smallest available headroom across this node AND every ancestor.

        Returns (headroom_usd, breakdown_dict).  Headroom is computed both
        for the product-specific limit AND the global limit at every level —
        whichever is tightest wins.
        """
        breakdown: Dict[str, float] = {}
        worst_headroom = float("inf")

        for ancestor in ancestor_chain(company):
            CreditLimitAgent.ensure_global_limit(db, ancestor)
            CreditLimitAgent.ensure_product_limit(db, ancestor, product)

            for limit_kind in (product, GLOBAL):
                cl = next(
                    (c for c in ancestor.credit_limits if c.product == limit_kind),
                    None,
                )
                if cl is None:
                    continue
                used_subtree = CreditLimitAgent._utilisation_for_subtree(
                    db, ancestor, None if limit_kind == GLOBAL else limit_kind
                )
                headroom = max(0.0, cl.limit_usd - used_subtree)
                key = f"{ancestor.name}:{limit_kind}"
                breakdown[key] = round(headroom, 2)
                worst_headroom = min(worst_headroom, headroom)

        if worst_headroom == float("inf"):
            worst_headroom = 0.0
        return round(worst_headroom, 2), breakdown

    # ---------- utilisation updates ----------
    @staticmethod
    def reserve(
        db: Session,
        invoice: models.Invoice,
        program: Optional[models.Program],
    ) -> None:
        amount = invoice.amount_usd
        product = invoice.product
        # Bump program utilisation
        if program is not None:
            program.utilised_usd = round(program.utilised_usd + amount, 2)
            log_event(
                db,
                NAME,
                "PROGRAM_UTILISATION_BUMPED",
                f"Program {program.name}: +${amount:,.0f} (used ${program.utilised_usd:,.0f}/${program.credit_limit_usd:,.0f})",
                invoice_id=invoice.id,
                program_id=program.id,
            )
        # Bump each company's GLOBAL + product limits
        for company in (invoice.buyer, invoice.seller):
            for limit_kind in (product, GLOBAL):
                cl = next(
                    (c for c in company.credit_limits if c.product == limit_kind),
                    None,
                )
                if cl is None:
                    continue
                cl.utilised_usd = round(cl.utilised_usd + amount, 2)
        log_event(
            db,
            NAME,
            "LIMITS_RESERVED",
            f"Reserved ${amount:,.0f} against buyer/seller limits.",
            invoice_id=invoice.id,
        )
