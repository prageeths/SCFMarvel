"""Funding Agent — the last-word fund/no-fund decision for every invoice."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..config import llm_enabled
from ..context import company_context, program_context, relevant_human_overrides
from ..llm import (
    FundingDecision, LLMUnavailable, SYSTEM_FUNDING_AGENT,
    facts_block, structured_call,
)
from ._common import log_event


def tool_decide_funding(db: Session, *, invoice_id: int) -> dict:
    """Ask the Funding Agent LLM whether to FUND or DO_NOT_FUND this invoice.

    Strict mode — if the LLM can't be called, :class:`LLMUnavailable` is
    raised and the API returns 503 "Couldn't call the OpenAI API …".
    """
    inv = db.query(models.Invoice).get(invoice_id)
    if inv is None:
        return {"ok": False, "error": f"Unknown invoice {invoice_id}"}
    if not llm_enabled():
        raise LLMUnavailable("funding_agent")

    program = db.query(models.Program).get(inv.program_id) if inv.program_id else None
    overrides = relevant_human_overrides(
        db, buyer_id=inv.buyer_id, seller_id=inv.seller_id,
        product=inv.product, limit=8,
    )

    facts = {
        "invoice": {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "amount_usd": inv.amount_usd,
            "currency": inv.currency,
            "amount_native": inv.amount,
            "product": inv.product,
            "tenor_days": inv.tenor_days,
            "grace_period_days": inv.grace_period_days,
            "status_at_funding_check": inv.status,
            "decision_reason_so_far": inv.decision_reason,
            "fee_usd": inv.fee_usd,
            "funded_amount_usd": inv.funded_amount_usd,
            "credit_spread": inv.credit_spread,
            "base_rate": inv.base_rate,
        },
        "buyer": company_context(db, inv.buyer),
        "seller": company_context(db, inv.seller),
        "program": program_context(db, program) if program else None,
        "relevant_human_overrides": overrides,
    }

    result: FundingDecision = structured_call(
        SYSTEM_FUNDING_AGENT,
        (
            "Decide FUND or DO_NOT_FUND for this invoice. Respect absolute "
            "rules in the system prompt: if STATUS=REJECTED you MUST return "
            "DO_NOT_FUND. If there are relevant human overrides, cite them.\n\n"
            + facts_block(facts)
        ),
        FundingDecision,
        label="funding_agent",
    )

    log_event(
        db, agent="funding_agent", action=f"FUNDING_{result.decision}",
        node="funding_agent", severity="DECISION",
        message=f"Funding Agent: {result.decision}. {result.rationale}",
        invoice_id=inv.id, program_id=inv.program_id,
        payload={
            "decision": result.decision,
            "rationale": result.rationale,
            "precedent_cited": result.precedent_cited,
            "n_relevant_overrides": len(overrides),
        },
    )
    return {
        "decision": result.decision,
        "rationale": result.rationale,
        "precedent_cited": result.precedent_cited,
    }
