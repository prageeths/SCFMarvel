"""FastAPI routes — the API surface from PRD §9."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..graph import (
    apply_triage_decision,
    handle_requestor_message,
    retry_jira,
    start_intake,
)
from ..schemas import (
    BacklogItem,
    DecisionBody,
    EmailDraft,
    MessageBody,
    RequestRecord,
    StartIntakeBody,
)
from ..seed import get_backlog

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "requests": db.count()}


@router.get("/backlog", response_model=list[BacklogItem])
def backlog() -> list[BacklogItem]:
    return get_backlog()


@router.post("/intake", response_model=RequestRecord)
def create_intake(body: StartIntakeBody) -> RequestRecord:
    text = body.text.strip()
    if len(text) < 8:
        raise HTTPException(400, "Please describe the request in a sentence or two.")
    rec = start_intake(text, get_backlog())
    if body.requestor_name and not rec.fields.requestor_name:
        rec.fields.requestor_name = body.requestor_name
    if body.requestor_email and not rec.fields.requestor_email:
        rec.fields.requestor_email = body.requestor_email
    db.save(rec)
    return rec


@router.post("/intake/{request_id}/message", response_model=RequestRecord)
def post_message(request_id: str, body: MessageBody) -> RequestRecord:
    rec = db.get(request_id)
    if rec is None:
        raise HTTPException(404, "Request not found")
    if rec.status not in ("AWAITING_REQUESTOR", "VALIDATING", "NEEDS_MORE_INFO"):
        raise HTTPException(409, f"Request is not awaiting requestor input (status {rec.status}).")
    rec = handle_requestor_message(rec, body.text, get_backlog())
    db.save(rec)
    return rec


@router.get("/intake/{request_id}", response_model=RequestRecord)
def get_intake(request_id: str) -> RequestRecord:
    rec = db.get(request_id)
    if rec is None:
        raise HTTPException(404, "Request not found")
    return rec


@router.get("/requests", response_model=list[RequestRecord])
def list_requests(status: str | None = None, org: str | None = None) -> list[RequestRecord]:
    rows = db.list_all()
    if status:
        rows = [r for r in rows if r.status == status]
    if org:
        rows = [r for r in rows if r.fields.org and r.fields.org.value == org]
    return rows


@router.get("/requests/{request_id}", response_model=RequestRecord)
def get_request(request_id: str) -> RequestRecord:
    return get_intake(request_id)


@router.post("/requests/{request_id}/decision", response_model=RequestRecord)
def decide(request_id: str, body: DecisionBody) -> RequestRecord:
    rec = db.get(request_id)
    if rec is None:
        raise HTTPException(404, "Request not found")
    if rec.status != "AWAITING_TRIAGE":
        raise HTTPException(409, f"Request is not awaiting triage (status {rec.status}).")
    if not body.note.strip():
        raise HTTPException(400, "A decision note is required (captured in the audit trail).")
    rec = apply_triage_decision(rec, body.decision, body.note.strip())
    db.save(rec)
    return rec


@router.get("/requests/{request_id}/email-draft", response_model=EmailDraft)
def email_draft(request_id: str) -> EmailDraft:
    rec = db.get(request_id)
    if rec is None:
        raise HTTPException(404, "Request not found")
    if rec.email_draft is None:
        raise HTTPException(404, "No email draft for this request.")
    return rec.email_draft


@router.post("/requests/{request_id}/retry-jira", response_model=RequestRecord)
def retry_jira_write(request_id: str) -> RequestRecord:
    rec = db.get(request_id)
    if rec is None:
        raise HTTPException(404, "Request not found")
    rec = retry_jira(rec)
    db.save(rec)
    return rec
