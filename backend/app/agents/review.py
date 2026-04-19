"""Review Agent: decides whether a one-off limit overage is acceptable."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from .base import log_event

NAME = "ReviewAgent"


class ReviewAgent:
    @staticmethod
    def decide_overage(
        db: Session,
        invoice: models.Invoice,
        program: Optional[models.Program],
        overage_usd: float,
    ) -> models.ReviewCase:
        case = models.ReviewCase(
            invoice_id=invoice.id,
            program_id=program.id if program else None,
            overage_usd=round(overage_usd, 2),
            decision="PENDING",
        )
        db.add(case)
        db.flush()

        # Decision rules:
        #   * Buyer & Seller both rated BBB or better -> approve temp increase
        #   * Overage <= 15% of program limit -> approve temp increase
        #   * Else -> deny
        ladder = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]
        b_rp = invoice.buyer.risk_profile
        s_rp = invoice.seller.risk_profile
        ratings_ok = (
            b_rp is not None and s_rp is not None
            and ladder.index(b_rp.rating) <= ladder.index("BBB")
            and ladder.index(s_rp.rating) <= ladder.index("BBB")
        )
        threshold = (program.credit_limit_usd * 0.15) if program else 0.0
        within_tolerance = overage_usd <= threshold

        if ratings_ok or within_tolerance:
            case.decision = "TEMP_INCREASE"
            case.reason = (
                f"Approved temporary increase of ${overage_usd:,.0f}: ratings_ok={ratings_ok}, "
                f"within_15pct={within_tolerance}."
            )
            if program is not None:
                # Bump bilateral limit by the overage on a one-off basis.
                program.credit_limit_usd = round(program.credit_limit_usd + overage_usd, 2)
            log_event(
                db,
                NAME,
                "TEMP_INCREASE_APPROVED",
                case.reason,
                severity="DECISION",
                invoice_id=invoice.id,
                program_id=program.id if program else None,
            )
        else:
            case.decision = "DENIED"
            case.reason = (
                f"Denied temporary increase: overage ${overage_usd:,.0f} > "
                f"15% of program limit (${threshold:,.0f}) and ratings below BBB."
            )
            invoice.status = "REJECTED"
            invoice.decision_reason = case.reason
            log_event(
                db,
                NAME,
                "TEMP_INCREASE_DENIED",
                case.reason,
                severity="DECISION",
                invoice_id=invoice.id,
                program_id=program.id if program else None,
            )
        return case
