"""Agentic Intake Request Application — FastAPI backend.

Production-aware reference implementation of the PRD. The three agents
(validation, justification, documentation) are orchestrated by a LangGraph-style
state machine. The OpenAI model sits behind a swappable adapter and is optional:
with no API key the agents run a transparent, deterministic engine so the whole
service is runnable offline and in CI.
"""

__version__ = "1.0.0"
