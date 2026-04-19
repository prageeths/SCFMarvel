"""Common helpers shared across agents."""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models


def log_event(
    db: Session,
    agent: str,
    action: str,
    message: str,
    *,
    severity: str = "INFO",
    invoice_id: Optional[int] = None,
    company_id: Optional[int] = None,
    program_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> models.AgentEvent:
    event = models.AgentEvent(
        timestamp=_dt.datetime.utcnow(),
        agent=agent,
        action=action,
        severity=severity,
        message=message,
        invoice_id=invoice_id,
        company_id=company_id,
        program_id=program_id,
        payload_json=json.dumps(payload, default=str) if payload else None,
    )
    db.add(event)
    db.flush()
    return event


def ancestor_chain(company: models.Company) -> List[models.Company]:
    """Return [company, parent, grand-parent, ... root]."""
    chain: List[models.Company] = []
    cursor = company
    seen = set()
    while cursor is not None and cursor.id not in seen:
        chain.append(cursor)
        seen.add(cursor.id)
        cursor = cursor.parent
    return chain


def descendant_ids(db: Session, company_id: int) -> List[int]:
    """All descendant IDs (excluding the root)."""
    out: List[int] = []
    frontier = [company_id]
    while frontier:
        children = (
            db.query(models.Company.id)
            .filter(models.Company.parent_id.in_(frontier))
            .all()
        )
        ids = [c[0] for c in children]
        if not ids:
            break
        out.extend(ids)
        frontier = ids
    return out
