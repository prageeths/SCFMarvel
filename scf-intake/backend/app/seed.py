"""Synthetic intake backlog for prioritization comparison (PRD §16.2).

Synthetic only — no real customer / account / PII data.
"""

from __future__ import annotations

from .schemas import BacklogItem, OriginatingOrg

SEED_BACKLOG: list[BacklogItem] = [
    BacklogItem(request_id="SCF-INTK-000101", title="Real-time supplier early-payment APR transparency", org=OriginatingOrg.business_line, roi_score=84, band="P0"),
    BacklogItem(request_id="SCF-INTK-000102", title="OFAC sanctioned-party screening on counterparty onboarding", org=OriginatingOrg.risk_compliance, roi_score=81, band="P0"),
    BacklogItem(request_id="SCF-INTK-000103", title="Basel III RWA reporting field for receivables financing", org=OriginatingOrg.regulatory, roi_score=78, band="P1"),
    BacklogItem(request_id="SCF-INTK-000104", title="Automated reconciliation of buyer remittance files", org=OriginatingOrg.accounting, roi_score=71, band="P1"),
    BacklogItem(request_id="SCF-INTK-000105", title="Dynamic discounting offer engine for mid-market buyers", org=OriginatingOrg.leadership, roi_score=68, band="P1"),
    BacklogItem(request_id="SCF-INTK-000106", title="Decommission COBOL FX-rate batch feed (legacy LIMITS)", org=OriginatingOrg.legacy_platform, roi_score=57, band="P2"),
    BacklogItem(request_id="SCF-INTK-000107", title="Multi-currency invoice upload via CSV template", org=OriginatingOrg.business_line, roi_score=52, band="P2"),
    BacklogItem(request_id="SCF-INTK-000108", title="Configurable email cadence for program utilization alerts", org=OriginatingOrg.business_line, roi_score=44, band="P3"),
    BacklogItem(request_id="SCF-INTK-000109", title="Dark-mode theme for the relationship-manager console", org=OriginatingOrg.business_line, roi_score=28, band="Defer"),
    BacklogItem(request_id="SCF-INTK-000110", title="Custom emoji reactions on agent decision feed", org=OriginatingOrg.business_line, roi_score=16, band="Defer"),
]


def get_backlog() -> list[BacklogItem]:
    return list(SEED_BACKLOG)
