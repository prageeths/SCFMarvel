"""SQLite persistence via SQLAlchemy (PRD §11).

For the POC the full RequestRecord is stored as JSON alongside the columns the
triage dashboard needs to filter/sort (status, org, roi_score, timestamps).
The schema is intentionally Postgres-compatible — swap the URL to migrate.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import String, Integer, DateTime, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import settings
from .schemas import RequestRecord


class Base(DeclarativeBase):
    pass


class RequestRow(Base):
    __tablename__ = "requests"

    request_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    org: Mapped[Optional[str]] = mapped_column(String(48), index=True, nullable=True)
    requestor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    roi_score: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    completeness_score: Mapped[int] = mapped_column(Integer, default=0)
    jira_issue_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    payload: Mapped[str] = mapped_column(Text)  # full RequestRecord as JSON


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


def init_db() -> None:
    Base.metadata.create_all(engine)


def _to_row(rec: RequestRecord) -> RequestRow:
    return RequestRow(
        request_id=rec.request_id,
        status=rec.status,
        org=rec.fields.org.value if rec.fields.org else None,
        requestor=rec.fields.requestor_name or None,
        roi_score=rec.roi.roi_score if rec.roi else None,
        completeness_score=rec.completeness_score,
        jira_issue_key=rec.jira.issue_key if rec.jira else None,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        payload=rec.model_dump_json(),
    )


def save(rec: RequestRecord) -> None:
    with Session(engine) as s:
        row = s.get(RequestRow, rec.request_id)
        new = _to_row(rec)
        if row is None:
            s.add(new)
        else:
            row.status = new.status
            row.org = new.org
            row.requestor = new.requestor
            row.roi_score = new.roi_score
            row.completeness_score = new.completeness_score
            row.jira_issue_key = new.jira_issue_key
            row.updated_at = new.updated_at
            row.payload = new.payload
        s.commit()


def get(request_id: str) -> Optional[RequestRecord]:
    with Session(engine) as s:
        row = s.get(RequestRow, request_id)
        if row is None:
            return None
        return RequestRecord.model_validate(json.loads(row.payload))


def list_all() -> list[RequestRecord]:
    with Session(engine) as s:
        rows = s.execute(select(RequestRow).order_by(RequestRow.created_at.desc())).scalars().all()
        return [RequestRecord.model_validate(json.loads(r.payload)) for r in rows]


def save_many(recs: Iterable[RequestRecord]) -> None:
    for r in recs:
        save(r)


def count() -> int:
    with Session(engine) as s:
        return len(s.execute(select(RequestRow.request_id)).all())
