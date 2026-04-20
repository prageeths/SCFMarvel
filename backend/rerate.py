"""Re-rate every company in the database using the current UnderwriterAgent
policy (no re-seed required — invoices and programs are preserved).

Usage:
    python -m backend.rerate
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from backend.app import models  # noqa: E402
from backend.app.agents.underwriter import UnderwriterAgent  # noqa: E402
from backend.app.agents.base import log_event  # noqa: E402
from backend.app.database import SessionLocal  # noqa: E402


def _ensure_micro_demo_suppliers(db: Session) -> int:
    """Insert a handful of <$5M revenue suppliers so the small-cap floor is visible."""
    demo = [
        ("Cedar & Sons Roastery LLC", "Food & Beverage", 1_200_000),
        ("Brookline Artisan Snacks Co", "Food & Beverage", 3_400_000),
        ("Pinecrest Family Bakery LLC", "Food & Beverage", 850_000),
        ("Harborlight Spices Inc", "Ingredients", 2_100_000),
        ("Sunset Hill Tea Company", "Food & Beverage", 4_700_000),
        ("Mountain Edge Watch Works", "Watches & Accessories", 950_000),
        ("Riverwood Chocolate Co", "Food & Beverage", 4_200_000),
        ("Highland Press Packaging LLC", "Packaging", 3_800_000),
    ]
    inserted = 0
    for name, industry, revenue in demo:
        if db.query(models.Company).filter(models.Company.name == name).first():
            continue
        c = models.Company(
            name=name,
            legal_name=name,
            country="US",
            industry=industry,
            role="SELLER",
            tax_id=f"EIN-{abs(hash(name)) % 99999999:08d}",
            website=f"https://{name.lower().split()[0]}.example.com",
            founded_year=2018,
            employees=max(5, int(revenue / 220_000)),
            annual_revenue_usd=float(revenue),
            description=f"{name} — micro-cap supplier under the platform's $5M small-cap policy.",
        )
        db.add(c)
        inserted += 1
    if inserted:
        db.flush()
    return inserted


def main() -> None:
    db: Session = SessionLocal()
    try:
        added = _ensure_micro_demo_suppliers(db)
        if added:
            print(f"[rerate] Added {added} micro-cap demo suppliers (<$5M revenue).")
        companies = db.query(models.Company).all()
        print(f"[rerate] Re-rating {len(companies)} companies...")
        # Two passes: build_risk_profile reads parent.annual_revenue_usd via
        # _max_revenue_in_tree, so a single pass is enough; but we collect
        # diffs for reporting.
        before = {c.id: (c.risk_profile.rating if c.risk_profile else None) for c in companies}

        # Sort root → leaf so ancestors are evaluated first (not strictly
        # required for the policy, but produces a cleaner event log).
        companies.sort(key=lambda c: (c.parent_id is not None, c.id))

        for c in companies:
            UnderwriterAgent.build_risk_profile(db, c)

        db.flush()

        diffs = {}
        for c in companies:
            new_rating = c.risk_profile.rating if c.risk_profile else None
            old_rating = before.get(c.id)
            if new_rating != old_rating:
                diffs[c.id] = (c.name, old_rating, new_rating)

        # Refresh credit_spread + fee on existing invoices so the dashboard's
        # historical data reflects the new ratings.
        from backend.app.config import BASE_RATE
        spread_by_company = {
            c.id: (c.risk_profile.credit_spread if c.risk_profile else 0.02)
            for c in companies
        }
        invoices = db.query(models.Invoice).all()
        for inv in invoices:
            spread = round(
                (
                    spread_by_company.get(inv.buyer_id, 0.02)
                    + spread_by_company.get(inv.seller_id, 0.02)
                )
                / 2.0,
                4,
            )
            period = (inv.tenor_days + (inv.grace_period_days or 0)) / 360.0
            inv.credit_spread = spread
            inv.base_rate = BASE_RATE
            if inv.status in ("FUNDED", "APPROVED", "PAID"):
                inv.fee_usd = round(inv.amount_usd * (BASE_RATE + spread) * period, 2)
                inv.funded_amount_usd = round(inv.amount_usd - inv.fee_usd, 2)

        log_event(
            db,
            "UnderwriterAgent",
            "BULK_RERATE",
            f"Re-rated {len(companies)} companies; {len(diffs)} ratings changed; "
            f"re-priced {len(invoices)} invoices.",
            severity="INFO",
            payload={"changed_count": len(diffs), "invoices_repriced": len(invoices)},
        )
        db.commit()

        if diffs:
            print(f"[rerate] {len(diffs)} ratings changed:")
            for cid, (name, old, new) in sorted(diffs.items()):
                print(f"  · {name:50s}  {old or '—':>4s}  →  {new}")
        else:
            print("[rerate] No rating changes.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
