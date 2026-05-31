"""Runtime configuration and the transparent, tunable ROI scoring weights.

Everything here is intentionally explicit so prioritization is explainable to
leadership (PRD §7.3 / §12 explainability). Override via environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class ScoringWeights:
    financial_value: float = 0.30
    effort: float = 0.20
    strategic_alignment: float = 0.15
    urgency: float = 0.15
    risk_compliance: float = 0.15
    confidence: float = 0.05

    def as_dict(self) -> dict[str, float]:
        return {
            "Financial value": self.financial_value,
            "Effort / cost to deliver": self.effort,
            "Strategic alignment": self.strategic_alignment,
            "Urgency & deadline": self.urgency,
            "Risk / compliance": self.risk_compliance,
            "Confidence": self.confidence,
        }


@dataclass(frozen=True)
class Settings:
    app_name: str = "SCF Agentic Intake"
    database_url: str = _env("SCF_INTAKE_DB_URL", "sqlite:///./data/scf_intake.db")

    # LLM adapter — optional. With no key the deterministic engine is used.
    openai_api_key: str = _env("OPENAI_API_KEY", "")
    validation_model: str = _env("SCF_VALIDATION_MODEL", "gpt-4o-mini")
    reasoning_model: str = _env("SCF_REASONING_MODEL", "gpt-4o")

    # Jira adapter — draft/stub unless an MCP endpoint is configured.
    jira_project_key: str = _env("SCF_JIRA_PROJECT", "SCF")
    jira_mcp_url: str = _env("SCF_JIRA_MCP_URL", "")

    max_clarification_rounds: int = int(_env("SCF_MAX_ROUNDS", "8"))
    weights: ScoringWeights = field(default_factory=ScoringWeights)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
