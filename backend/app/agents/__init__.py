"""Agent swarm for the supply-chain finance platform.

Every agent is a deterministic, transparent rules-engine designed to look and
feel like an LLM-driven autonomous agent: each one logs structured events with
its own persona ("OrchestrationAgent", "TransactionAgent", ...), reasons over
the shared state in the database, and hands off work to the next agent when it
hits the boundary of its responsibility.

This makes the system AI-Native in spirit (multi-agent orchestration, role
separation, rich event log) without requiring a network-connected LLM call,
which keeps the demo fully offline and reproducible.
"""

from .orchestration import OrchestrationAgent  # noqa: F401
from .transaction import TransactionAgent  # noqa: F401
from .underwriter import UnderwriterAgent  # noqa: F401
from .credit_limit import CreditLimitAgent  # noqa: F401
from .review import ReviewAgent  # noqa: F401
