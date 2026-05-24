"""Validation helpers for chat routes."""

from src.kernel.schemas.agent import AgentRequest


def validate_team_agent_request(_agent_id: str, _request: AgentRequest) -> None:
    """Validate team-agent-specific request requirements before dispatch."""
    return None
