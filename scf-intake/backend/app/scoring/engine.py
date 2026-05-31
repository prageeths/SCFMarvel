"""Transparent, config-driven ROI scoring engine (PRD §7.3).

No hidden heuristics: every factor contribution is returned for display, and
the hard-gate override rules are evaluated before the weighted score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..config import ScoringWeights, settings
from ..schemas import (
    BacklogItem,
    BenefitType,
    IntakeRequest,
    PriorityRecommendation,
    ROIAssessment,
    Urgency,
)

EFFORT_INVERSE = {"S": 100, "M": 70, "L": 40, "XL": 15}
CONFIDENCE_FACTOR = {"Low": 0.4, "Medium": 0.7, "High": 1.0}
EFFORT_MONTHS = {"S": 1, "M": 3, "L": 6, "XL": 12}


def format_usd(n: float) -> str:
    if not n:
        return "$0"
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 1_000_000:
        return f"{sign}${a / 1_000_000:.{0 if a >= 10_000_000 else 1}f}M"
    if a >= 1_000:
        return f"{sign}${a / 1_000:.0f}k"
    return f"{sign}${a:.0f}"


def _normalize_value(annual: float, one_time: float) -> int:
    total = max(0.0, annual) + max(0.0, one_time) * 0.3
    if total <= 0:
        return 0
    score = (math.log10(total) - 3) * 25
    return max(0, min(100, round(score)))


def _strategic(r: IntakeRequest) -> int:
    s = 40
    if r.org and r.org.value == "Leadership":
        s += 30
    if r.org and r.org.value in ("Regulatory", "Risk & Compliance"):
        s += 15
    if r.impact_scope and r.impact_scope.value == "Platform-wide":
        s += 20
    elif r.impact_scope and r.impact_scope.value == "Multi-team":
        s += 10
    elif r.impact_scope and r.impact_scope.value == "External":
        s += 15
    if r.sponsor and r.sponsor.strip():
        s += 10
    return max(0, min(100, s))


def _urgency(r: IntakeRequest) -> int:
    base = {"Low": 20, "Medium": 50, "High": 75, "Critical": 100}
    s = base.get(r.urgency.value if r.urgency else "Low", 20)
    if r.hard_deadline_consequence and r.hard_deadline_consequence.strip():
        s = min(100, s + 10)
    return s


def _risk_compliance(r: IntakeRequest) -> int:
    s = 20
    org = r.org.value if r.org else ""
    if org == "Regulatory":
        s = 95
    elif org == "Risk & Compliance":
        s = 85
    bt = r.financial.benefit_type.value
    if bt == "Loss avoidance":
        s = max(s, 80)
    if bt == "Risk reduction":
        s = max(s, 70)
    if r.regulatory_citation and r.regulatory_citation.strip():
        s = max(s, 90)
    return min(100, s)


def band_from_score(score: int) -> str:
    if score >= 80:
        return "P0"
    if score >= 65:
        return "P1"
    if score >= 45:
        return "P2"
    if score >= 30:
        return "P3"
    return "Defer"


def _band_rank(b: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "Defer": 4}[b]


@dataclass
class ScoreResult:
    roi: ROIAssessment
    priority: PriorityRecommendation
    force_human: bool


def score_request(
    r: IntakeRequest,
    backlog: list[BacklogItem],
    weights: ScoringWeights | None = None,
) -> ScoreResult:
    w = weights or settings.weights
    annual = r.financial.estimated_annual_value or 0.0
    one_time = r.financial.one_time_value or 0.0
    conf = CONFIDENCE_FACTOR.get(
        r.financial.confidence.value if r.financial.confidence else "Medium", 0.7
    )

    raw = {
        "Financial value": _normalize_value(annual, one_time),
        "Effort / cost to deliver": EFFORT_INVERSE.get(
            r.financial.effort_size.value if r.financial.effort_size else "M", 70
        ),
        "Strategic alignment": _strategic(r),
        "Urgency & deadline": _urgency(r),
        "Risk / compliance": _risk_compliance(r),
        "Confidence": round(conf * 100),
    }
    weight_map = w.as_dict()
    breakdown: dict[str, int] = {}
    roi_score = 0
    for factor, value in raw.items():
        contribution = round(value * weight_map[factor])
        breakdown[factor] = contribution
        roi_score += contribution
    roi_score = max(0, min(100, round(roi_score)))

    flags: list[str] = []
    if annual > 0 and len(r.financial.basis_of_estimate.strip()) < 15:
        flags.append("Financial value asserted without a documented basis of estimate.")
    if annual >= 5_000_000 and (
        not r.financial.confidence or r.financial.confidence.value == "Low"
    ):
        flags.append(
            "Very large annual value combined with Low confidence — treat as speculative."
        )
    if r.financial.benefit_type != BenefitType.none and annual == 0 and one_time == 0:
        flags.append("Benefit type declared but no quantified value provided.")

    confidence_adjusted = round((annual + one_time * 0.3) * conf)
    annual_conf = annual * conf
    total_cost = EFFORT_MONTHS.get(
        r.financial.effort_size.value if r.financial.effort_size else "M", 3
    ) * 25000 + max(0.0, -annual)
    payback = round(total_cost / annual_conf * 12, 1) if annual_conf > 0 else None

    # ---- override rules ----
    override = None
    min_band = None
    force_human = False
    is_reg = (r.org and r.org.value == "Regulatory") or bool(
        r.regulatory_citation and r.regulatory_citation.strip()
    )
    has_hard = r.needed_by_is_hard is True or bool(
        r.hard_deadline_consequence and r.hard_deadline_consequence.strip()
    )
    if is_reg and has_hard:
        override = (
            "Regulatory mandate with a hard deadline → minimum priority band High; "
            "cannot be auto-deferred."
        )
        min_band = "P1"
    elif r.org and r.org.value == "Risk & Compliance" and (
        r.financial.benefit_type == BenefitType.loss_avoidance
        or (r.compliance_reference and r.compliance_reference.strip())
    ):
        override = (
            "Documented loss-avoidance / control gap from Risk & Compliance → "
            "escalate to human triage."
        )
        force_human = True
        min_band = "P2"
    if r.urgency == Urgency.critical:
        override = (override + " " if override else "") + (
            "Critical urgency → always routed to human review, never auto-deferred."
        )
        force_human = True
        min_band = min_band or "P2"

    band = band_from_score(roi_score)
    if min_band and _band_rank(min_band) < _band_rank(band):
        band = min_band

    if roi_score >= 65:
        desirability = "high"
    elif roi_score >= 40:
        desirability = "medium"
    else:
        desirability = "low"
    if override and desirability == "low":
        desirability = "medium"

    higher = len([b for b in backlog if b.roi_score > roi_score])
    rank = higher + 1
    neighbor = next(
        (b for b in sorted(backlog, key=lambda x: -x.roi_score) if b.roi_score <= roi_score),
        None,
    )
    comparison = _comparison_notes(roi_score, band, rank, len(backlog), neighbor)
    rationale = _rationale(r, roi_score, breakdown, desirability, override, payback)

    return ScoreResult(
        roi=ROIAssessment(
            roi_score=roi_score,
            factor_breakdown=breakdown,
            estimated_annual_value=annual,
            payback_period_months=payback,
            confidence_adjusted_value=confidence_adjusted,
            plausibility_flags=flags,
            desirability=desirability,  # type: ignore[arg-type]
            rationale=rationale,
        ),
        priority=PriorityRecommendation(
            recommended_band=band,  # type: ignore[arg-type]
            rank_in_backlog=rank,
            override_applied=override,
            comparison_notes=comparison,
        ),
        force_human=force_human,
    )


def _comparison_notes(score, band, rank, total, neighbor) -> str:
    parts = [
        f"Scores {score}/100, ranking #{rank} of {total + 1} against the current intake queue."
    ]
    if neighbor:
        parts.append(
            f'Ranks just below "{neighbor.title}" ({neighbor.roi_score}/100, {neighbor.band}).'
        )
    if band == "Defer":
        parts.append(
            "Falls below the threshold where the platform team can commit capacity "
            "ahead of higher-value work."
        )
    return " ".join(parts)


def _rationale(r, score, breakdown, desirability, override, payback) -> str:
    top = [k.lower() for k, _ in sorted(breakdown.items(), key=lambda kv: -kv[1])[:2]]
    annual = r.financial.estimated_annual_value or 0
    lines = [
        f"Composite ROI score of {score}/100 ({desirability} desirability), "
        f"driven primarily by {' and '.join(top)}."
    ]
    if annual > 0:
        conf = r.financial.confidence.value if r.financial.confidence else "unknown"
        lines.append(
            f"Requestor estimates {format_usd(annual)} annual "
            f"{r.financial.benefit_type.value.lower()} at {conf} confidence."
        )
    else:
        lines.append("No quantified annual financial benefit was provided.")
    if payback is not None:
        lines.append(f"Estimated payback period ≈ {payback} months (confidence-adjusted).")
    if override:
        lines.append(f"Override: {override}")
    return " ".join(lines)
