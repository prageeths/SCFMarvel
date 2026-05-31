"""LLM adapter behind an interface (PRD §4.2, §15.2).

The model provider is swappable. With no OPENAI_API_KEY the DeterministicLLM is
used and the agents fall back to their rule-based logic. With a key (and
langchain-openai installed) the OpenAIAdapter is selected. Enterprise gateways
(Azure OpenAI / Bedrock) can be added by implementing LLMAdapter.
"""

from __future__ import annotations

from typing import Protocol

from ..config import settings


class LLMAdapter(Protocol):
    enabled: bool

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        ...


class DeterministicLLM:
    """No-op adapter: returns empty so callers use their deterministic path."""

    enabled = False

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:  # noqa: ARG002
        return ""


class OpenAIAdapter:
    enabled = True

    def __init__(self) -> None:
        # Imported lazily so the package is optional.
        from langchain_openai import ChatOpenAI  # type: ignore

        self._ChatOpenAI = ChatOpenAI

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        llm = self._ChatOpenAI(
            model=model or settings.reasoning_model,
            api_key=settings.openai_api_key,
            temperature=0.2,
        )
        resp = llm.invoke([("system", system), ("human", user)])
        return getattr(resp, "content", "") or ""


_cached: LLMAdapter | None = None


def get_llm() -> LLMAdapter:
    global _cached
    if _cached is not None:
        return _cached
    if settings.llm_enabled:
        try:
            _cached = OpenAIAdapter()
            return _cached
        except Exception:
            # langchain-openai not installed or misconfigured — fall back safely.
            pass
    _cached = DeterministicLLM()
    return _cached
