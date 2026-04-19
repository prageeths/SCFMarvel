"""Seed the database with a realistic dataset.

Run:  python -m backend.seed
"""
from __future__ import annotations

import datetime as _dt
import random
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow running both as `python -m backend.seed` and `python backend/seed.py`
sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from backend.app.agents.credit_limit import CreditLimitAgent  # noqa: E402
from backend.app.agents.underwriter import UnderwriterAgent  # noqa: E402
from backend.app.config import (  # noqa: E402
    BASE_RATE,
    FX_TO_USD,
    PRODUCT_FACTORING,
    PRODUCT_REVERSE_FACTORING,
    SUPPORTED_CURRENCIES,
)
from backend.app.database import Base, SessionLocal, engine  # noqa: E402
from backend.app import models  # noqa: E402

RNG_SEED = 42
random.seed(RNG_SEED)


# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

# Hierarchical buyers (Walmart-style trees + others). Each entry is
# (parent_path_or_None, name, country, industry, role, revenue)
BUYER_HIERARCHIES = [
    # Walmart
    ("Walmart", "Walmart Global", None, "Retail", "BOTH", 611_000_000_000),
    ("Walmart", "Walmart US", "US", "Retail", "BOTH", 420_000_000_000),
    ("Walmart", "Walmart Canada", "CA", "Retail", "BUYER", 22_000_000_000),
    ("Walmart", "Walmart LATAM", None, "Retail", "BUYER", 40_000_000_000),
    ("Walmart", "Walmart Mexico", "MX", "Retail", "BUYER", 30_000_000_000),
    ("Walmart", "Walmart Brazil", "BR", "Retail", "BUYER", 5_000_000_000),
    ("Walmart", "Walmart Colombia", "CO", "Retail", "BUYER", 3_000_000_000),
    ("Walmart", "Walmart East Coast", "US", "Retail", "BUYER", 110_000_000_000),
    ("Walmart", "Walmart Midwest", "US", "Retail", "BUYER", 95_000_000_000),
    ("Walmart", "Walmart West Coast", "US", "Retail", "BUYER", 130_000_000_000),
    ("Walmart", "Walmart South", "US", "Retail", "BUYER", 85_000_000_000),

    # Target
    ("Target", "Target Corporation", "US", "Retail", "BUYER", 109_000_000_000),
    ("Target", "Target East", "US", "Retail", "BUYER", 35_000_000_000),
    ("Target", "Target West", "US", "Retail", "BUYER", 38_000_000_000),
    ("Target", "Target South", "US", "Retail", "BUYER", 22_000_000_000),
    ("Target", "Target Midwest", "US", "Retail", "BUYER", 14_000_000_000),

    # Kroger
    ("Kroger", "Kroger Co", "US", "Retail", "BUYER", 148_000_000_000),
    ("Kroger", "Kroger Mid-Atlantic", "US", "Retail", "BUYER", 22_000_000_000),
    ("Kroger", "Kroger Southwest", "US", "Retail", "BUYER", 25_000_000_000),
    ("Kroger", "Kroger Central", "US", "Retail", "BUYER", 30_000_000_000),
    ("Kroger", "Kroger Delta", "US", "Retail", "BUYER", 18_000_000_000),

    # Albertsons / Jewel-Osco family
    ("Albertsons", "Albertsons Companies", "US", "Retail", "BUYER", 79_000_000_000),
    ("Albertsons", "Jewel-Osco", "US", "Retail", "BUYER", 6_500_000_000),
    ("Albertsons", "Safeway", "US", "Retail", "BUYER", 38_000_000_000),
    ("Albertsons", "Vons", "US", "Retail", "BUYER", 5_400_000_000),

    # Best Buy
    ("BestBuy", "Best Buy Co", "US", "Consumer Electronics", "BUYER", 46_000_000_000),
    ("BestBuy", "Best Buy US", "US", "Consumer Electronics", "BUYER", 42_000_000_000),
    ("BestBuy", "Best Buy Canada", "CA", "Consumer Electronics", "BUYER", 4_000_000_000),

    # Costco
    ("Costco", "Costco Wholesale", "US", "Retail", "BUYER", 242_000_000_000),
    ("Costco", "Costco US", "US", "Retail", "BUYER", 180_000_000_000),
    ("Costco", "Costco Canada", "CA", "Retail", "BUYER", 25_000_000_000),
    ("Costco", "Costco Mexico", "MX", "Retail", "BUYER", 6_000_000_000),

    # CVS / Walgreens (drug stores)
    ("CVS", "CVS Health", "US", "Pharmaceuticals", "BUYER", 357_000_000_000),
    ("CVS", "CVS Pharmacy", "US", "Pharmaceuticals", "BUYER", 110_000_000_000),
    ("Walgreens", "Walgreens Boots Alliance", "US", "Pharmaceuticals", "BUYER", 139_000_000_000),
    ("Walgreens", "Walgreens US", "US", "Pharmaceuticals", "BUYER", 110_000_000_000),

    # Whole Foods (Amazon)
    ("Amazon", "Amazon", "US", "Retail", "BUYER", 575_000_000_000),
    ("Amazon", "Whole Foods Market", "US", "Retail", "BUYER", 22_000_000_000),
    ("Amazon", "Amazon Fresh", "US", "Retail", "BUYER", 10_000_000_000),

    # Publix, Wegmans, Trader Joe's, Aldi, HEB
    ("Publix", "Publix Super Markets", "US", "Retail", "BUYER", 57_000_000_000),
    ("Wegmans", "Wegmans Food Markets", "US", "Retail", "BUYER", 12_000_000_000),
    ("TraderJoes", "Trader Joe's", "US", "Retail", "BUYER", 16_000_000_000),
    ("Aldi", "Aldi US", "US", "Retail", "BUYER", 35_000_000_000),
    ("HEB", "H-E-B", "US", "Retail", "BUYER", 38_000_000_000),
    ("Meijer", "Meijer", "US", "Retail", "BUYER", 21_000_000_000),
    ("WinnDixie", "Winn-Dixie", "US", "Retail", "BUYER", 4_000_000_000),
]

# Maps "group_key" -> root index in BUYER_HIERARCHIES (the first row for that group)
# used to set parent pointers below.

# Well-known seller brands. A subset of these are real, the rest will be
# generated via Faker. role=SELLER unless otherwise noted.
KNOWN_SELLERS = [
    # Cereal / Snack
    ("Kellogg Company", "Food & Beverage", "US", 14_000_000_000),
    ("Quaker Oats Company", "Food & Beverage", "US", 2_500_000_000),
    ("General Mills", "Food & Beverage", "US", 20_000_000_000),
    ("Post Holdings", "Food & Beverage", "US", 6_500_000_000),
    ("Mondelez International", "Food & Beverage", "US", 36_000_000_000),
    ("Nestle USA", "Food & Beverage", "US", 28_000_000_000),
    ("Kraft Heinz", "Food & Beverage", "US", 27_000_000_000),
    ("Conagra Brands", "Food & Beverage", "US", 12_000_000_000),
    ("Tyson Foods", "Food & Beverage", "US", 53_000_000_000),
    ("Hormel Foods", "Food & Beverage", "US", 12_400_000_000),
    ("Campbell Soup Company", "Food & Beverage", "US", 9_400_000_000),
    ("Hershey Company", "Food & Beverage", "US", 10_000_000_000),
    ("Mars Incorporated", "Food & Beverage", "US", 45_000_000_000),

    # Beverages
    ("The Coca-Cola Company", "Food & Beverage", "US", 45_000_000_000),
    ("PepsiCo", "Food & Beverage", "US", 91_000_000_000),
    ("Keurig Dr Pepper", "Food & Beverage", "US", 14_800_000_000),
    ("Monster Beverage", "Food & Beverage", "US", 7_000_000_000),
    ("Red Bull North America", "Food & Beverage", "US", 5_000_000_000),
    ("Anheuser-Busch", "Food & Beverage", "US", 16_000_000_000),
    ("Molson Coors Beverage Co", "Food & Beverage", "US", 11_000_000_000),
    ("Constellation Brands", "Food & Beverage", "US", 9_400_000_000),
    ("Brown-Forman", "Food & Beverage", "US", 4_000_000_000),

    # OTC Pharma / health
    ("Reckitt Benckiser (Delsym)", "Pharmaceuticals", "US", 16_000_000_000),
    ("Pfizer Consumer Health (Advil)", "Pharmaceuticals", "US", 4_000_000_000),
    ("Johnson & Johnson Consumer", "Pharmaceuticals", "US", 15_000_000_000),
    ("Bayer Consumer Health", "Pharmaceuticals", "US", 5_000_000_000),
    ("GSK Consumer Healthcare", "Pharmaceuticals", "US", 11_000_000_000),
    ("Procter & Gamble Health", "Pharmaceuticals", "US", 6_000_000_000),
    ("Sanofi Consumer Healthcare", "Pharmaceuticals", "US", 5_500_000_000),
    ("Haleon", "Pharmaceuticals", "US", 12_000_000_000),

    # Houseware / consumer goods
    ("Thermos LLC", "Home Goods", "US", 600_000_000),
    ("OXO International", "Home Goods", "US", 350_000_000),
    ("Newell Brands", "Home Goods", "US", 8_500_000_000),
    ("Tupperware Brands", "Home Goods", "US", 1_200_000_000),
    ("Hamilton Beach", "Home Goods", "US", 700_000_000),

    # Tech / electronics
    ("HP Inc", "Consumer Electronics", "US", 53_000_000_000),
    ("Dell Technologies", "Consumer Electronics", "US", 102_000_000_000),
    ("Lenovo USA", "Consumer Electronics", "US", 14_000_000_000),
    ("Logitech Inc", "Consumer Electronics", "US", 4_500_000_000),
    ("Bose Corporation", "Consumer Electronics", "US", 3_700_000_000),
    ("Garmin International", "Consumer Electronics", "US", 5_200_000_000),
    ("Sonos", "Consumer Electronics", "US", 1_700_000_000),
    ("Roku", "Consumer Electronics", "US", 3_500_000_000),
    ("GoPro", "Consumer Electronics", "US", 1_000_000_000),

    # Watches
    ("Fossil Group", "Watches & Accessories", "US", 1_200_000_000),
    ("Movado Group", "Watches & Accessories", "US", 700_000_000),
    ("Timex Group USA", "Watches & Accessories", "US", 800_000_000),
    ("Citizen Watch America", "Watches & Accessories", "US", 600_000_000),
    ("Bulova Corporation", "Watches & Accessories", "US", 250_000_000),
    ("Shinola Detroit", "Watches & Accessories", "US", 100_000_000),
    ("Skagen Designs", "Watches & Accessories", "US", 80_000_000),

    # Apparel
    ("Levi Strauss & Co", "Apparel", "US", 6_200_000_000),
    ("VF Corporation", "Apparel", "US", 11_600_000_000),
    ("PVH Corp", "Apparel", "US", 9_200_000_000),
    ("Hanesbrands", "Apparel", "US", 6_200_000_000),
    ("Under Armour", "Apparel", "US", 5_700_000_000),
    ("Carter's Inc", "Apparel", "US", 3_000_000_000),
    ("Columbia Sportswear", "Apparel", "US", 3_500_000_000),
    ("Crocs Inc", "Apparel", "US", 3_900_000_000),
    ("Skechers USA", "Apparel", "US", 7_500_000_000),

    # Pet care
    ("Blue Buffalo", "Food & Beverage", "US", 1_400_000_000),
    ("Spectrum Brands Pet", "Food & Beverage", "US", 900_000_000),

    # Cleaning / personal care
    ("Clorox Company", "Home Goods", "US", 7_400_000_000),
    ("Church & Dwight", "Home Goods", "US", 5_400_000_000),
    ("Energizer Holdings", "Home Goods", "US", 2_900_000_000),
    ("Edgewell Personal Care", "Home Goods", "US", 2_300_000_000),
]

# Tier-2 suppliers (companies that sell to the sellers above) — packaging,
# ingredients, logistics, etc. Faker generates many of these too.
TIER2_INDUSTRIES = ["Packaging", "Ingredients", "Logistics", "Industrial"]
TIER2_SAMPLE = [
    ("Sealed Air Corporation", "Packaging", "US", 5_500_000_000),
    ("Berry Global", "Packaging", "US", 12_700_000_000),
    ("Sonoco Products", "Packaging", "US", 7_200_000_000),
    ("WestRock Company", "Packaging", "US", 21_000_000_000),
    ("Packaging Corp of America", "Packaging", "US", 8_400_000_000),
    ("ADM (Archer Daniels Midland)", "Ingredients", "US", 102_000_000_000),
    ("Ingredion Incorporated", "Ingredients", "US", 8_200_000_000),
    ("Cargill Inc", "Ingredients", "US", 165_000_000_000),
    ("Bunge Limited", "Ingredients", "US", 67_000_000_000),
    ("International Flavors & Fragrances", "Ingredients", "US", 12_400_000_000),
    ("Givaudan US", "Ingredients", "US", 7_000_000_000),
    ("Symrise US", "Ingredients", "US", 4_700_000_000),
    ("J.B. Hunt Transport Services", "Logistics", "US", 14_800_000_000),
    ("XPO Logistics", "Logistics", "US", 7_700_000_000),
    ("Old Dominion Freight Line", "Logistics", "US", 5_900_000_000),
    ("C.H. Robinson Worldwide", "Logistics", "US", 24_700_000_000),
    ("Schneider National", "Logistics", "US", 5_500_000_000),
]


def _seed_companies(db: Session) -> Dict[str, models.Company]:
    """Create the company hierarchy and named brands.

    Returns a dict mapping name -> Company (already persisted with IDs).
    """
    by_name: Dict[str, models.Company] = {}

    # 1. Buyers — first pass create rows; second pass attach parents.
    # The first row of each group_key is the root; subsequent rows are children
    # of that root.
    group_root: Dict[str, models.Company] = {}

    for group_key, name, country, industry, role, revenue in BUYER_HIERARCHIES:
        c = models.Company(
            name=name,
            legal_name=name,
            country=country,
            industry=industry,
            role=role,
            tax_id=f"EIN-{random.randint(10000000, 99999999)}",
            website=f"https://www.{name.lower().replace(' ', '').replace('-', '').replace(',','')[:20]}.com",
            founded_year=random.randint(1900, 2010),
            employees=int(max(100, revenue / random.uniform(150_000, 600_000))),
            annual_revenue_usd=float(revenue),
            description=f"{name} — {industry} buyer.",
        )
        db.add(c)
        db.flush()
        by_name[name] = c
        if group_key not in group_root:
            group_root[group_key] = c
        else:
            # Two-level Walmart-style nesting: detect intermediate roots
            # (LATAM, US, etc.) and parent the rest beneath them where appropriate.
            parent = group_root[group_key]
            # Walmart special routing
            if group_key == "Walmart":
                if name in ("Walmart Mexico", "Walmart Brazil", "Walmart Colombia"):
                    parent = by_name.get("Walmart LATAM", parent)
                elif name in (
                    "Walmart East Coast", "Walmart Midwest",
                    "Walmart West Coast", "Walmart South",
                ):
                    parent = by_name.get("Walmart US", parent)
                elif name == "Walmart US":
                    parent = by_name.get("Walmart Global", parent)
                elif name == "Walmart Canada":
                    parent = by_name.get("Walmart Global", parent)
                elif name == "Walmart LATAM":
                    parent = by_name.get("Walmart Global", parent)
            # Target / Kroger / Best Buy / Costco simple two-level
            elif group_key in ("Target", "Kroger", "BestBuy", "Costco"):
                parent = group_root[group_key]
            elif group_key == "Albertsons":
                parent = by_name.get("Albertsons Companies", parent)
            elif group_key == "CVS":
                parent = by_name.get("CVS Health", parent)
            elif group_key == "Walgreens":
                parent = by_name.get("Walgreens Boots Alliance", parent)
            elif group_key == "Amazon":
                parent = by_name.get("Amazon", parent)
            c.parent_id = parent.id
            db.flush()

    # 2. Known sellers (no parents).
    for name, industry, country, revenue in KNOWN_SELLERS + TIER2_SAMPLE:
        c = models.Company(
            name=name,
            legal_name=name,
            country=country,
            industry=industry,
            role="SELLER" if (name, industry, country, revenue) in KNOWN_SELLERS else "BOTH",
            tax_id=f"EIN-{random.randint(10000000, 99999999)}",
            website=f"https://www.{name.lower().split()[0]}.com",
            founded_year=random.randint(1900, 2015),
            employees=int(max(50, revenue / random.uniform(150_000, 800_000))),
            annual_revenue_usd=float(revenue),
            description=f"{name} — {industry}.",
        )
        db.add(c)
        db.flush()
        by_name[name] = c

    return by_name


def _generate_extra_sellers(db: Session, by_name: Dict[str, models.Company], n_target: int) -> None:
    """Top up the seller roster to >= 500 US-based companies via Faker."""
    try:
        from faker import Faker
    except ImportError:  # pragma: no cover
        print("WARN: faker not installed; using deterministic fallback names.")
        Faker = None

    industries = [
        "Food & Beverage", "Pharmaceuticals", "Consumer Electronics",
        "Apparel", "Home Goods", "Watches & Accessories", "Packaging",
        "Ingredients", "Logistics", "Industrial",
    ]
    fake = Faker("en_US") if Faker else None
    if fake:
        Faker.seed(RNG_SEED)

    suffixes = ["Inc", "LLC", "Corp", "Co", "Holdings", "Group", "Brands", "Industries"]
    descriptors = [
        "Foods", "Beverages", "Snacks", "Naturals", "Organics", "Pharma",
        "Health", "Tech", "Electronics", "Apparel", "Wearables", "Home",
        "Goods", "Packaging", "Ingredients", "Logistics", "Distribution",
        "Bakery", "Dairy", "Coffee", "Tea", "Spirits", "Brewing", "Snack Co",
    ]

    existing_seller_names = {
        c.name for c in by_name.values() if c.role in ("SELLER", "BOTH")
    }
    sellers_needed = max(0, n_target - len(existing_seller_names))
    print(f"[seed] Generating {sellers_needed} synthetic sellers...")

    created = 0
    attempts = 0
    while created < sellers_needed and attempts < sellers_needed * 5:
        attempts += 1
        if fake:
            base = fake.last_name() + " " + random.choice(descriptors)
        else:
            base = f"Acme {random.choice(descriptors)}-{attempts}"
        candidate = f"{base} {random.choice(suffixes)}"
        if candidate in by_name:
            continue
        industry = random.choice(industries)
        revenue = random.choice(
            [random.uniform(2e7, 5e8), random.uniform(5e8, 5e9), random.uniform(5e9, 2e10)]
        )
        c = models.Company(
            name=candidate,
            legal_name=candidate,
            country="US",
            industry=industry,
            role="SELLER",
            tax_id=f"EIN-{random.randint(10000000, 99999999)}",
            website=f"https://{candidate.lower().split()[0]}.example.com",
            founded_year=random.randint(1950, 2020),
            employees=int(max(20, revenue / random.uniform(200_000, 800_000))),
            annual_revenue_usd=float(revenue),
            description=f"{candidate} — {industry} supplier.",
        )
        db.add(c)
        db.flush()
        by_name[candidate] = c
        created += 1
    print(f"[seed] Synthetic sellers created: {created}")


def _profile_all(db: Session) -> None:
    print("[seed] Profiling companies and setting credit limits...")
    rng = random.Random(RNG_SEED)
    companies = db.query(models.Company).all()
    for c in companies:
        UnderwriterAgent.build_risk_profile(db, c, rng=rng)
        CreditLimitAgent.ensure_global_limit(db, c)
        CreditLimitAgent.ensure_product_limit(db, c, PRODUCT_FACTORING)
        CreditLimitAgent.ensure_product_limit(db, c, PRODUCT_REVERSE_FACTORING)
    db.commit()
    print(f"[seed] Profiled {len(companies)} companies.")


def _build_programs(
    db: Session,
    buyer_pool: List[models.Company],
    seller_pool: List[models.Company],
    target_count: int,
) -> List[models.Program]:
    print(f"[seed] Building ~{target_count} programs...")
    programs: List[models.Program] = []
    seen: set = set()
    rng = random.Random(RNG_SEED + 1)
    while len(programs) < target_count:
        buyer = rng.choice(buyer_pool)
        seller = rng.choice(seller_pool)
        if buyer.id == seller.id:
            continue
        product = rng.choice([PRODUCT_FACTORING, PRODUCT_REVERSE_FACTORING])
        key = (buyer.id, seller.id, product)
        if key in seen:
            continue
        seen.add(key)
        # Bilateral limit: roughly the smaller of the two parties' product limit
        buyer_cl = next(cl for cl in buyer.credit_limits if cl.product == product)
        seller_cl = next(cl for cl in seller.credit_limits if cl.product == product)
        limit = round(min(buyer_cl.limit_usd, seller_cl.limit_usd) * rng.uniform(0.05, 0.25), 2)
        program = models.Program(
            name=f"{seller.name} -> {buyer.name} ({product})",
            buyer_id=buyer.id,
            seller_id=seller.id,
            product=product,
            credit_limit_usd=max(250_000.0, limit),
            base_currency=rng.choice(["USD", "USD", "USD", "EUR", "CAD", "MXN", "BRL"]),
            grace_period_days=rng.choice([0, 3, 5, 7, 10]),
            status="ACTIVE",
        )
        db.add(program)
        programs.append(program)
    db.flush()
    print(f"[seed] Programs created: {len(programs)}")
    return programs


def _make_invoice_number(idx: int) -> str:
    return f"INV-{idx:08d}-{uuid.uuid4().hex[:6].upper()}"


def _seed_invoices(
    db: Session,
    programs: List[models.Program],
    n_invoices: int,
) -> None:
    print(f"[seed] Generating {n_invoices} invoices over the last 2 years...")
    rng = random.Random(RNG_SEED + 2)

    today = _dt.datetime.utcnow()
    two_years_ago = today - _dt.timedelta(days=730)

    # Cache risk profiles for fast lookup
    rp_by_company: Dict[int, models.RiskProfile] = {
        rp.company_id: rp for rp in db.query(models.RiskProfile).all()
    }

    # Index programs for sampling
    program_index = list(range(len(programs)))

    statuses_pool = [
        ("FUNDED", 0.55),
        ("APPROVED", 0.10),
        ("PAID", 0.20),
        ("REVIEW", 0.05),
        ("UNDERWRITING", 0.04),
        ("REJECTED", 0.04),
        ("PENDING", 0.02),
    ]
    status_choices, status_weights = zip(*statuses_pool)

    batch = []
    BATCH_SIZE = 1000
    for i in range(n_invoices):
        program = programs[rng.choice(program_index)]
        buyer = program.buyer
        seller = program.seller
        product = program.product
        currency = rng.choice(SUPPORTED_CURRENCIES)
        amount = round(rng.uniform(2_000, 750_000), 2)
        amount_usd = round(amount * FX_TO_USD[currency], 2)
        tenor = rng.choice([30, 60, 90])
        grace = rng.choice([0, 3, 5, 7])

        # Random issue date in the last 2 years.
        offset = rng.randint(0, 730)
        issue = two_years_ago + _dt.timedelta(days=offset, hours=rng.randint(0, 23))
        due = issue + _dt.timedelta(days=tenor)

        spread = (
            (rp_by_company[buyer.id].credit_spread + rp_by_company[seller.id].credit_spread)
            / 2.0
        )
        period = (tenor + grace) / 360.0
        fee_usd = round(amount_usd * (BASE_RATE + spread) * period, 2)
        funded_usd = round(amount_usd - fee_usd, 2)

        status = rng.choices(status_choices, weights=status_weights, k=1)[0]
        if status == "REJECTED":
            decision_reason = "Limit exceeded or risk threshold breached."
            funded_usd = 0.0
            fee_usd = 0.0
        elif status == "UNDERWRITING":
            decision_reason = "Routed to underwriting (no program / new pair)."
            funded_usd = 0.0
            fee_usd = 0.0
        elif status == "REVIEW":
            decision_reason = "Program limit exceeded; awaiting Review Agent."
        elif status == "PAID":
            decision_reason = f"Buyer paid invoice on {due.date().isoformat()}."
        elif status == "FUNDED":
            decision_reason = f"Funded ${funded_usd:,.2f} at {(BASE_RATE+spread):.2%}."
        elif status == "APPROVED":
            decision_reason = "Approved; awaiting funding."
        else:
            decision_reason = "Pending evaluation."

        invoice = models.Invoice(
            invoice_number=_make_invoice_number(i + 1),
            seller_id=seller.id,
            buyer_id=buyer.id,
            program_id=program.id,
            product=product,
            amount=amount,
            currency=currency,
            amount_usd=amount_usd,
            tenor_days=tenor,
            grace_period_days=grace,
            issue_date=issue,
            due_date=due,
            base_rate=BASE_RATE,
            credit_spread=round(spread, 4),
            fee_usd=fee_usd,
            funded_amount_usd=funded_usd,
            status=status,
            decision_reason=decision_reason,
        )
        batch.append(invoice)

        # Update utilisation for funded/approved invoices to keep limits realistic
        if status in ("FUNDED", "APPROVED"):
            program.utilised_usd = round(program.utilised_usd + amount_usd, 2)
            for company in (buyer, seller):
                for cl in company.credit_limits:
                    if cl.product in ("GLOBAL", product):
                        cl.utilised_usd = round(cl.utilised_usd + amount_usd, 2)

        if len(batch) >= BATCH_SIZE:
            db.add_all(batch)
            db.flush()
            batch = []
            if (i + 1) % 2000 == 0:
                print(f"  ...{i+1} invoices generated")

    if batch:
        db.add_all(batch)
        db.flush()
    db.commit()
    print(f"[seed] Done: {n_invoices} invoices.")


def _summary_events(db: Session) -> None:
    """Add a handful of high-level platform events so the console isn't empty."""
    from backend.app.agents.base import log_event
    log_event(
        db, "OrchestrationAgent", "PLATFORM_BOOT",
        f"Seeded platform with {db.query(models.Company).count()} companies, "
        f"{db.query(models.Program).count()} programs, "
        f"{db.query(models.Invoice).count()} invoices.",
        severity="INFO",
    )
    db.commit()


def main(n_invoices: int = 12_000, n_sellers_target: int = 520) -> None:
    print("[seed] (Re)creating schema...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        by_name = _seed_companies(db)
        db.commit()
        _generate_extra_sellers(db, by_name, n_target=n_sellers_target)
        db.commit()

        _profile_all(db)

        # Reload from DB for fresh state with relationships
        sellers = (
            db.query(models.Company)
            .filter(models.Company.role.in_(["SELLER", "BOTH"]))
            .all()
        )
        # Buyer pool: only the LEAF buyer entities (no children) plus a few mids.
        all_buyers = (
            db.query(models.Company)
            .filter(models.Company.role.in_(["BUYER", "BOTH"]))
            .all()
        )
        leaf_buyers = [b for b in all_buyers if not b.children]
        buyer_pool = leaf_buyers if len(leaf_buyers) > 5 else all_buyers
        print(f"[seed] {len(sellers)} sellers, {len(buyer_pool)} buyer leaves.")

        programs = _build_programs(
            db, buyer_pool, sellers, target_count=min(2500, len(sellers) * 3)
        )
        db.commit()

        _seed_invoices(db, programs, n_invoices=n_invoices)
        _summary_events(db)
    finally:
        db.close()
    print("[seed] Complete.")


if __name__ == "__main__":
    n = 12_000
    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
        except ValueError:
            pass
    main(n_invoices=n)
