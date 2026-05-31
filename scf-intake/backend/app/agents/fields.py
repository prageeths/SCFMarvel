"""Intake field specs, conditional rules and completeness scoring (PRD §3).

Single source of truth used by the validation agent and the API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..schemas import BenefitType, IntakeRequest

_EMAIL_RE = re.compile(r".+@.+\..+")
_VAGUE = [
    re.compile(r"^we just need it", re.I),
    re.compile(r"^because$", re.I),
    re.compile(r"^idk", re.I),
    re.compile(r"^n/?a$", re.I),
    re.compile(r"^needed$", re.I),
]


def is_vague(text: str) -> bool:
    t = text.strip()
    if len(t) < 25:
        return True
    return any(p.match(t) for p in _VAGUE)


def _has(s: str | None, n: int = 1) -> bool:
    return bool(s) and len(s.strip()) >= n  # type: ignore[arg-type]


@dataclass
class FieldSpec:
    key: str
    label: str
    weight: int
    required: Callable[[IntakeRequest], bool]
    is_complete: Callable[[IntakeRequest], bool]


def _has_value(r: IntakeRequest) -> bool:
    return (
        r.financial.benefit_type == BenefitType.none
        or r.financial.estimated_annual_value is not None
    )


FIELD_SPECS: list[FieldSpec] = [
    FieldSpec("title", "Title", 6, lambda r: True, lambda r: _has(r.title, 4)),
    FieldSpec("requestor_name", "Requestor name", 5, lambda r: True, lambda r: _has(r.requestor_name, 2)),
    FieldSpec(
        "requestor_email", "Requestor email", 5, lambda r: True,
        lambda r: bool(_EMAIL_RE.match(r.requestor_email.strip())),
    ),
    FieldSpec("org", "Originating org", 6, lambda r: True, lambda r: r.org is not None),
    FieldSpec(
        "business_justification", "Business justification", 12, lambda r: True,
        lambda r: _has(r.business_justification, 25) and not is_vague(r.business_justification),
    ),
    FieldSpec("impact", "Impact", 10, lambda r: True, lambda r: _has(r.impact, 20)),
    FieldSpec("impact_scope", "Impact scope", 5, lambda r: True, lambda r: r.impact_scope is not None),
    FieldSpec(
        "financial.benefit_type", "Benefit type", 6, lambda r: True,
        lambda r: r.financial.benefit_type is not None,
    ),
    FieldSpec(
        "financial.estimated_annual_value", "Estimated annual value", 8,
        lambda r: r.financial.benefit_type != BenefitType.none, _has_value,
    ),
    FieldSpec(
        "financial.effort_size", "Effort to deliver", 5, lambda r: True,
        lambda r: r.financial.effort_size is not None,
    ),
    FieldSpec(
        "financial.confidence", "Estimate confidence", 4,
        lambda r: r.financial.benefit_type != BenefitType.none,
        lambda r: r.financial.benefit_type == BenefitType.none or r.financial.confidence is not None,
    ),
    FieldSpec(
        "financial.basis_of_estimate", "Basis of estimate", 6,
        lambda r: r.financial.benefit_type != BenefitType.none,
        lambda r: r.financial.benefit_type == BenefitType.none or _has(r.financial.basis_of_estimate, 15),
    ),
    FieldSpec(
        "alternative_approach", "Alternative approach", 8, lambda r: True,
        lambda r: _has(r.alternative_approach, 15),
    ),
    FieldSpec("needed_by", "Timeline / needed-by", 5, lambda r: True, lambda r: _has(r.needed_by, 3)),
    FieldSpec("urgency", "Urgency", 5, lambda r: True, lambda r: r.urgency is not None),
    # conditional
    FieldSpec(
        "regulatory_citation", "Regulatory citation", 5,
        lambda r: r.org is not None and r.org.value == "Regulatory",
        lambda r: not (r.org and r.org.value == "Regulatory") or _has(r.regulatory_citation, 4),
    ),
    FieldSpec(
        "compliance_reference", "Compliance / control reference", 4,
        lambda r: r.org is not None and r.org.value == "Risk & Compliance",
        lambda r: not (r.org and r.org.value == "Risk & Compliance") or _has(r.compliance_reference, 3),
    ),
    FieldSpec(
        "hard_deadline_consequence", "Hard deadline & consequence", 5,
        lambda r: (r.urgency is not None and r.urgency.value == "Critical")
        or (r.org is not None and r.org.value == "Regulatory"),
        lambda r: not (
            (r.urgency and r.urgency.value == "Critical") or (r.org and r.org.value == "Regulatory")
        )
        or _has(r.hard_deadline_consequence, 10),
    ),
    FieldSpec(
        "affected_systems", "Affected systems / legacy refs", 4,
        lambda r: r.org is not None and r.org.value == "Legacy platform",
        lambda r: not (r.org and r.org.value == "Legacy platform") or _has(r.affected_systems, 4),
    ),
]

FIELD_LABEL = {f.key: f.label for f in FIELD_SPECS}


def required_fields(r: IntakeRequest) -> list[FieldSpec]:
    return [f for f in FIELD_SPECS if f.required(r)]


def missing_fields(r: IntakeRequest) -> list[str]:
    return [f.key for f in required_fields(r) if not f.is_complete(r)]


def completeness_score(r: IntakeRequest) -> int:
    req = required_fields(r)
    total = sum(f.weight for f in req)
    if total == 0:
        return 0
    got = sum(f.weight for f in req if f.is_complete(r))
    return round(got / total * 100)
