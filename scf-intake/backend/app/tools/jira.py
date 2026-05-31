"""Jira writer adapter (PRD §8). Isolates Jira auth/transport from agent logic.

Default is a stub that returns a deterministic synthetic issue key so the POC
runs without a live Jira. Set SCF_JIRA_MCP_URL to route writes through a Jira
MCP server in a real environment.
"""

from __future__ import annotations

from typing import Protocol

from ..config import settings
from ..schemas import JiraLink


class JiraWriter(Protocol):
    def create_story(self, intake_id: str, payload: dict, attempt: int) -> JiraLink:
        ...


class StubJiraWriter:
    """Synthetic, deterministic Jira writer for the POC."""

    def create_story(self, intake_id: str, payload: dict, attempt: int) -> JiraLink:  # noqa: ARG002
        digits = "".join(ch for ch in intake_id if ch.isdigit())[-4:] or "0001"
        key = f"{settings.jira_project_key}-{digits}"
        return JiraLink(
            issue_key=key,
            url=f"https://jira.example.com/browse/{key}",
            write_status="written",
            attempts=attempt,
        )


class FailingJiraWriter:
    """Used to exercise retry handling (PRD §8.5)."""

    def create_story(self, intake_id: str, payload: dict, attempt: int) -> JiraLink:  # noqa: ARG002
        return JiraLink(issue_key="", url="", write_status="failed", attempts=attempt)


def get_jira_writer() -> JiraWriter:
    # A real implementation would dispatch to the Jira MCP server here when
    # settings.jira_mcp_url is configured.
    return StubJiraWriter()
