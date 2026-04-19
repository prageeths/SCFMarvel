"""Pydantic schemas for the API surface."""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from pydantic import BaseModel, Field

from .config import ALLOWED_TENORS, PRODUCTS, SUPPORTED_CURRENCIES


# ---------------- Invoice intake ----------------


class InvoiceCreate(BaseModel):
    seller_name: str = Field(..., description="Exact seller company name")
    buyer_name: str = Field(..., description="Exact buyer company name")
    product: str
    amount: float = Field(..., gt=0)
    currency: str
    tenor_days: int
    grace_period_days: int = 0
    invoice_number: Optional[str] = None

    def normalised_product(self) -> str:
        p = self.product.strip().upper().replace(" ", "_")
        if p not in PRODUCTS:
            raise ValueError(f"product must be one of {PRODUCTS}")
        return p

    def normalised_currency(self) -> str:
        c = self.currency.strip().upper()
        if c not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {SUPPORTED_CURRENCIES}")
        return c

    def validate_tenor(self) -> int:
        if self.tenor_days not in ALLOWED_TENORS:
            raise ValueError(f"tenor_days must be one of {ALLOWED_TENORS}")
        return self.tenor_days


# ---------------- Read models ----------------


class CompanyMini(BaseModel):
    id: int
    name: str
    role: str
    country: Optional[str] = None
    industry: Optional[str] = None

    class Config:
        from_attributes = True


class CreditLimitOut(BaseModel):
    product: str
    limit_usd: float
    utilised_usd: float

    class Config:
        from_attributes = True


class RiskProfileOut(BaseModel):
    rating: str
    pd_1y: float
    credit_spread: float
    industry_risk: float
    country_risk: float
    leverage_score: float
    last_reviewed: _dt.datetime

    class Config:
        from_attributes = True


class ProgramOut(BaseModel):
    id: int
    name: str
    product: str
    buyer: CompanyMini
    seller: CompanyMini
    credit_limit_usd: float
    utilised_usd: float
    status: str
    spread_override: Optional[float] = None

    class Config:
        from_attributes = True


class CompanyDetail(BaseModel):
    id: int
    name: str
    legal_name: Optional[str]
    country: Optional[str]
    industry: Optional[str]
    role: str
    description: Optional[str]
    website: Optional[str]
    annual_revenue_usd: Optional[float]
    employees: Optional[int]
    parent: Optional[CompanyMini]
    children: List[CompanyMini]
    risk_profile: Optional[RiskProfileOut]
    credit_limits: List[CreditLimitOut]
    programs: List[ProgramOut]


class InvoiceOut(BaseModel):
    id: int
    invoice_number: str
    seller: CompanyMini
    buyer: CompanyMini
    product: str
    amount: float
    currency: str
    amount_usd: float
    tenor_days: int
    grace_period_days: int
    issue_date: _dt.datetime
    due_date: _dt.datetime
    base_rate: float
    credit_spread: float
    fee_usd: float
    funded_amount_usd: float
    status: str
    decision_reason: Optional[str]
    program_id: Optional[int]

    class Config:
        from_attributes = True


class AgentEventOut(BaseModel):
    id: int
    timestamp: _dt.datetime
    agent: str
    action: str
    severity: str
    message: str
    invoice_id: Optional[int]
    company_id: Optional[int]
    program_id: Optional[int]

    class Config:
        from_attributes = True


class DecisionResult(BaseModel):
    invoice: InvoiceOut
    events: List[AgentEventOut]
    summary: str
