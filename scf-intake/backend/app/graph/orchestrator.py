"""LangGraph-style orchestrator (PRD §5).

This is a faithful, dependency-light implementation of the state machine in
§5.2: start → validate → (ask_human interrupt) → justify → decision_gate →
(human_review interrupt) → document / draft_email → finalize. The node and edge
structure mirrors a LangGraph StateGraph; when langgraph + an OpenAI key are
present the same nodes can be hosted in an actual StateGraph with a SqliteSaver
checkpointer (see README). Keeping the transitions explicit here means the
service is auditable and runs with zero external dependencies.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone

from ..agents.documentation import build_story, write_to_jira
from ..agents.fields import completeness_score, missing_fields
from ..agents.justification import draft_acceptance_email, draft_deferral_email, justify
from ..agents.validation import apply_answer, parse_initial_submission, plan_next_question
from ..config import settings
from ..schemas import (
    AuditEntry,
    BacklogItem,
    ChatMessage,
    IntakeRequest,
    RequestRecord,
)

_id_counter = itertools.count(123)
_msg_counter = itertools.count(1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def next_request_id() -> str:
    return f"SCF-INTK-{next(_id_counter):06d}"


def _msg_id() -> str:
    return f"m{next(_msg_counter)}-{int(_now().timestamp() * 1000) % 100000}"


def _audit(rec: RequestRecord, actor: str, action: str, detail: str | None = None, agent: str | None = None) -> None:
    rec.audit_trail.append(AuditEntry(ts=_now_iso(), actor=actor, action=action, detail=detail, agent=agent))  # type: ignore[arg-type]


def _agent_msg(content: str, agent: str, chips=None, field=None) -> ChatMessage:
    return ChatMessage(id=_msg_id(), role="agent", agent=agent, content=content, ts=_now_iso(), chips=chips, field=field)


def _system_msg(content: str) -> ChatMessage:
    return ChatMessage(id=_msg_id(), role="system", content=content, ts=_now_iso())


# --------------------------------------------------------------------------- #
# start node
# --------------------------------------------------------------------------- #
def start_intake(initial_text: str, backlog: list[BacklogItem]) -> RequestRecord:
    rid = next_request_id()
    fields = parse_initial_submission(initial_text, IntakeRequest())
    rec = RequestRecord(
        request_id=rid,
        status="VALIDATING",
        created_at=_now(),
        updated_at=_now(),
        fields=fields,
    )
    rec.conversation.append(
        _agent_msg(
            "Hi — I'm the SCF intake assistant. I'll turn your request into a complete, "
            "structured submission and help the platform team prioritize it fairly.",
            "Validation",
        )
    )
    rec.conversation.append(ChatMessage(id=_msg_id(), role="requestor", content=initial_text, ts=_now_iso()))
    _audit(rec, "system", "Intake started", f"request_id {rid} created")
    _audit(rec, "agent", "Parsed initial submission", agent="Validation")
    return _validate_step(rec, backlog)


# --------------------------------------------------------------------------- #
# validate node (+ ask_human interrupt)
# --------------------------------------------------------------------------- #
def _validate_step(rec: RequestRecord, backlog: list[BacklogItem]) -> RequestRecord:
    rec.completeness_score = completeness_score(rec.fields)
    rec.missing_fields = missing_fields(rec.fields)
    rec.updated_at = _now()

    if not rec.missing_fields:
        rec.status = "VALIDATED"
        rec.conversation.append(
            _agent_msg(
                f"That's everything I need — your submission is {rec.completeness_score}% complete "
                "and validated. Handing off to the Business Justification agent…",
                "Validation",
            )
        )
        _audit(rec, "agent", "Validation complete", f"completeness {rec.completeness_score}", "Validation")
        return _score_step(rec, backlog)

    if rec.clarification_rounds >= settings.max_clarification_rounds:
        rec.status = "NEEDS_MORE_INFO"
        rec.conversation.append(
            _agent_msg(
                "We've gone a few rounds and a couple of required details are still missing. "
                "I'm escalating this to a human triage lead so we don't keep you waiting.",
                "Validation",
            )
        )
        _audit(rec, "agent", "Max clarification rounds reached → escalated", ", ".join(rec.missing_fields), "Validation")
        return rec

    q = plan_next_question(rec.fields)
    if q:
        rec.status = "AWAITING_REQUESTOR"
        rec.conversation.append(_agent_msg(q.prompt, "Validation", chips=q.chips, field=q.field))
        _audit(rec, "agent", "Asked clarification", f"{q.field}: {q.reason}", "Validation")
    return rec


def handle_requestor_message(rec: RequestRecord, text: str, backlog: list[BacklogItem]) -> RequestRecord:
    rec.conversation.append(ChatMessage(id=_msg_id(), role="requestor", content=text, ts=_now_iso()))
    target = None
    for m in reversed(rec.conversation):
        if m.role == "agent" and m.field:
            target = m.field
            break
    prev_completeness = completeness_score(rec.fields)
    if target:
        rec.fields, note = apply_answer(rec.fields, target, text)
        _audit(rec, "requestor", "Answered", target)
        if note:
            rec.conversation.append(_agent_msg(note, "Validation"))
            _audit(rec, "agent", "Recorded value", note, "Validation")
    else:
        rec.fields.business_justification = (rec.fields.business_justification + "\n" + text).strip()
        _audit(rec, "requestor", "Added context")

    # Only count *unproductive* rounds toward the escalation cap, so a normal
    # multi-field intake never escalates while the requestor is making progress.
    if completeness_score(rec.fields) > prev_completeness:
        rec.clarification_rounds = 0
    else:
        rec.clarification_rounds += 1
    return _validate_step(rec, backlog)


# --------------------------------------------------------------------------- #
# justify node + decision_gate
# --------------------------------------------------------------------------- #
def _score_step(rec: RequestRecord, backlog: list[BacklogItem]) -> RequestRecord:
    rec.status = "SCORING"
    result = justify(rec.fields, backlog)
    rec.roi = result.roi
    rec.priority = result.priority
    rec.decision = result.decision
    _audit(
        rec, "agent", "ROI scored",
        f"score {result.roi.roi_score}, band {result.priority.recommended_band}, "
        f"desirability {result.roi.desirability}", "Justification",
    )
    if result.priority.override_applied:
        _audit(rec, "agent", "Override applied", result.priority.override_applied, "Justification")
    for flag in result.roi.plausibility_flags:
        _audit(rec, "agent", "Plausibility flag", flag, "Justification")

    if result.decision == "needs_human":
        rec.status = "AWAITING_TRIAGE"
        rec.conversation.append(
            _agent_msg(
                f"I've scored this at {result.roi.roi_score}/100 (band {result.priority.recommended_band}). "
                f"Because it's {'flagged for mandatory review' if result.priority.override_applied else 'borderline'}, "
                "a platform triage lead will confirm the call before anything is written to Jira.",
                "Justification",
            )
        )
        _audit(rec, "agent", "Routed to human review", "decision_gate → human_review", "Justification")
        return rec
    if result.decision == "accept":
        return _document_step(rec)
    return _draft_email_step(rec)


# --------------------------------------------------------------------------- #
# human_review interrupt
# --------------------------------------------------------------------------- #
def apply_triage_decision(rec: RequestRecord, decision: str, note: str) -> RequestRecord:
    rec.triage_note = note
    _audit(rec, "human", f"Triage decision: {decision}", note or None)
    if decision == "accept":
        rec.decision = "accept"
        return _document_step(rec)
    if decision == "defer":
        rec.decision = "defer"
        return _draft_email_step(rec)
    rec.decision = "needs_human"
    rec.status = "NEEDS_MORE_INFO"
    rec.conversation.append(
        _agent_msg(
            f"The triage lead would like a bit more detail before deciding{': ' + note if note else '.'}",
            "Validation",
        )
    )
    rec.updated_at = _now()
    return rec


# --------------------------------------------------------------------------- #
# document node → Jira → finalize
# --------------------------------------------------------------------------- #
def _document_step(rec: RequestRecord, force_fail: bool = False) -> RequestRecord:
    rec.status = "DOCUMENTING"
    rec.decision = "accept"
    payload = build_story(rec.request_id, rec.fields, rec.roi, rec.priority)  # type: ignore[arg-type]
    _audit(rec, "agent", "Story composed", payload["summary"], "Documentation")
    attempt = (rec.jira.attempts if rec.jira else 0) + 1
    link = write_to_jira(rec.request_id, payload, attempt, force_fail=force_fail)
    rec.jira = link
    if link.write_status == "written":
        rec.status = "WRITTEN_TO_JIRA"
        _audit(rec, "agent", "Wrote to Jira", f"{link.issue_key} (attempt {link.attempts})", "Documentation")
        rec.email_draft = draft_acceptance_email(rec.request_id, rec.fields, rec.priority, link.issue_key)  # type: ignore[arg-type]
        _audit(rec, "agent", "Acceptance email drafted (draft-only)", rec.email_draft.subject, "Justification")
        rec.conversation.append(
            _agent_msg(
                f"Accepted and logged as {link.issue_key}. Track it in Jira: {link.url}. "
                "An acceptance note has been drafted for a human to review and send.",
                "Documentation",
            )
        )
        rec.status = "CLOSED"
        _audit(rec, "system", "Request closed", "accepted & written to Jira")
    else:
        rec.conversation.append(
            _system_msg(
                f"The Jira write failed (attempt {link.attempts}). The request is safe and a human "
                "has been notified to retry — nothing was lost."
            )
        )
        _audit(rec, "agent", "Jira write failed", f"attempt {link.attempts}; payload preserved", "Documentation")
    rec.updated_at = _now()
    return rec


def retry_jira(rec: RequestRecord) -> RequestRecord:
    _audit(rec, "human", "Manual Jira retry requested")
    return _document_step(rec, force_fail=False)


# --------------------------------------------------------------------------- #
# draft_email node (deferral) → finalize
# --------------------------------------------------------------------------- #
def _draft_email_step(rec: RequestRecord) -> RequestRecord:
    rec.decision = "defer"
    rec.status = "DEFERRED"
    rec.email_draft = draft_deferral_email(rec.request_id, rec.fields, rec.roi, rec.priority)  # type: ignore[arg-type]
    _audit(rec, "agent", "Deferral email drafted (draft-only)", rec.email_draft.subject, "Justification")
    rec.conversation.append(
        _agent_msg(
            f"After scoring this against the current backlog, it isn't one we can schedule right now "
            f"(score {rec.roi.roi_score}/100). I've drafted a respectful explanation for the team to "  # type: ignore[union-attr]
            f"review and send — this is a deferral, not a rejection. {rec.priority.comparison_notes}",  # type: ignore[union-attr]
            "Justification",
        )
    )
    _audit(rec, "system", "Request deferred", "no Jira issue created")
    rec.updated_at = _now()
    return rec
