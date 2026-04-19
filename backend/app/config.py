"""Global configuration for the supply-chain finance platform."""
from __future__ import annotations

import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite DB path (override with SCF_DB_URL env var if needed)
DEFAULT_DB_PATH = DATA_DIR / "scf.db"
DATABASE_URL = os.environ.get("SCF_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")

# Today's quoted base rate (annualised, decimal form). 2% per the spec.
BASE_RATE = float(os.environ.get("SCF_BASE_RATE", "0.02"))

# Supported invoice currencies and approximate FX rates -> USD (snapshot)
SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "CAD", "MXN", "BRL", "COP", "JPY"]
FX_TO_USD = {
    "USD": 1.00,
    "EUR": 1.08,
    "GBP": 1.27,
    "CAD": 0.74,
    "MXN": 0.058,
    "BRL": 0.20,
    "COP": 0.00025,
    "JPY": 0.0067,
}

# Allowed tenors (days)
ALLOWED_TENORS = [30, 60, 90]

# Product families
PRODUCT_FACTORING = "FACTORING"
PRODUCT_REVERSE_FACTORING = "REVERSE_FACTORING"
PRODUCTS = [PRODUCT_FACTORING, PRODUCT_REVERSE_FACTORING]
