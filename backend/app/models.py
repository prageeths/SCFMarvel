"""Domain models for the AI-Native Supply Chain Finance platform.

Concepts modelled:
  * Companies form a tree (Walmart Global -> LATAM -> Brazil etc.).
  * Each node can hold a global credit limit AND product-scoped sub-limits
    (Factoring vs Reverse Factoring).
  * A Program is a buyer/seller relationship plus product type, with its
    own bilateral credit limit.
  * Invoices reference a buyer and a seller and (when one exists) a Program.
  * Risk profiles drive the credit spread used in fee computation.
  * AgentEvents log every decision the agent swarm makes.
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from .database import Base


# ---------------------------------------------------------------------------
# Companies and hierarchy
# ---------------------------------------------------------------------------


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    legal_name = Column(String(255))
    country = Column(String(64))
    industry = Column(String(128))
    role = Column(String(32), nullable=False)  # BUYER / SELLER / SUPPLIER / BOTH
    parent_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    tax_id = Column(String(64))
    website = Column(String(255))
    founded_year = Column(Integer)
    employees = Column(Integer)
    annual_revenue_usd = Column(Float)
    description = Column(Text)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    parent = relationship("Company", remote_side=[id], backref="children")
    risk_profile = relationship(
        "RiskProfile", uselist=False, back_populates="company", cascade="all, delete-orphan"
    )
    credit_limits = relationship(
        "CreditLimit", back_populates="company", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Company {self.id} {self.name}>"


# ---------------------------------------------------------------------------
# Risk profiles (built/updated by Underwriter Agent)
# ---------------------------------------------------------------------------


class RiskProfile(Base):
    __tablename__ = "risk_profiles"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, unique=True)
    rating = Column(String(8), nullable=False)  # AAA, AA, A, BBB, BB, B, CCC
    pd_1y = Column(Float, nullable=False)        # 1-year probability of default
    credit_spread = Column(Float, nullable=False)  # decimal, e.g. 0.0125 = 1.25%
    industry_risk = Column(Float, default=0.0)
    country_risk = Column(Float, default=0.0)
    leverage_score = Column(Float, default=0.0)
    notes = Column(Text)
    last_reviewed = Column(DateTime, default=_dt.datetime.utcnow)

    company = relationship("Company", back_populates="risk_profile")


# ---------------------------------------------------------------------------
# Credit limits (global + per-product, hierarchical)
# ---------------------------------------------------------------------------


class CreditLimit(Base):
    __tablename__ = "credit_limits"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    product = Column(String(32), nullable=False, default="GLOBAL")  # GLOBAL/FACTORING/REVERSE_FACTORING
    limit_usd = Column(Float, nullable=False)
    utilised_usd = Column(Float, nullable=False, default=0.0)
    set_by = Column(String(64), default="UNDERWRITER_AGENT")
    last_updated = Column(DateTime, default=_dt.datetime.utcnow, onupdate=_dt.datetime.utcnow)

    company = relationship("Company", back_populates="credit_limits")

    __table_args__ = (
        UniqueConstraint("company_id", "product", name="uq_credit_limit_company_product"),
    )


# ---------------------------------------------------------------------------
# Programs (buyer / seller / product) and their bilateral credit limit
# ---------------------------------------------------------------------------


class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    buyer_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    product = Column(String(32), nullable=False)  # FACTORING / REVERSE_FACTORING
    credit_limit_usd = Column(Float, nullable=False)
    utilised_usd = Column(Float, nullable=False, default=0.0)
    base_currency = Column(String(8), default="USD")
    grace_period_days = Column(Integer, default=5)
    status = Column(String(32), default="ACTIVE")  # ACTIVE / SUSPENDED / TERMINATED
    spread_override = Column(Float, nullable=True)  # optional bilateral spread override
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    buyer = relationship("Company", foreign_keys=[buyer_id])
    seller = relationship("Company", foreign_keys=[seller_id])

    __table_args__ = (
        UniqueConstraint("buyer_id", "seller_id", "product", name="uq_program_pair_product"),
        Index("ix_program_pair", "buyer_id", "seller_id"),
    )


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(64), unique=True, nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    buyer_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True, index=True)

    product = Column(String(32), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    amount_usd = Column(Float, nullable=False)

    tenor_days = Column(Integer, nullable=False)
    grace_period_days = Column(Integer, default=0)

    issue_date = Column(DateTime, default=_dt.datetime.utcnow)
    due_date = Column(DateTime, nullable=False)

    base_rate = Column(Float, nullable=False)
    credit_spread = Column(Float, nullable=False)
    fee_usd = Column(Float, nullable=False, default=0.0)
    funded_amount_usd = Column(Float, nullable=False, default=0.0)

    status = Column(String(32), nullable=False, default="PENDING")
    # PENDING -> APPROVED / REVIEW / UNDERWRITING / REJECTED / FUNDED / PAID
    decision_reason = Column(Text)

    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    updated_at = Column(DateTime, default=_dt.datetime.utcnow, onupdate=_dt.datetime.utcnow)

    seller = relationship("Company", foreign_keys=[seller_id])
    buyer = relationship("Company", foreign_keys=[buyer_id])
    program = relationship("Program")
    events = relationship("AgentEvent", back_populates="invoice", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Underwriting / review queues
# ---------------------------------------------------------------------------


class UnderwritingCase(Base):
    __tablename__ = "underwriting_cases"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    product = Column(String(32), nullable=False)
    requested_limit_usd = Column(Float, nullable=False)
    status = Column(String(32), default="OPEN")  # OPEN / APPROVED / DECLINED
    decision_notes = Column(Text)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class ReviewCase(Base):
    __tablename__ = "review_cases"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    overage_usd = Column(Float, nullable=False)
    decision = Column(String(32), default="PENDING")  # PENDING / TEMP_INCREASE / DENIED
    reason = Column(Text)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Agent activity log – powers the "console"
# ---------------------------------------------------------------------------


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=_dt.datetime.utcnow, index=True)
    agent = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True, index=True)
    severity = Column(String(16), default="INFO")  # INFO / WARN / DECISION / ERROR
    message = Column(Text, nullable=False)
    payload_json = Column(Text)

    invoice = relationship("Invoice", back_populates="events")
