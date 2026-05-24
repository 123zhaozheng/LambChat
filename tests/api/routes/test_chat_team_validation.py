from __future__ import annotations

from src.api.routes.chat_validation import validate_team_agent_request
from src.kernel.schemas.agent import AgentRequest


def test_validate_team_agent_request_allows_missing_team_id_for_fallback() -> None:
    request = AgentRequest(message="hello")

    validate_team_agent_request("team", request)


def test_validate_team_agent_request_allows_team_id() -> None:
    request = AgentRequest(message="hello", team_id="team-1")

    validate_team_agent_request("team", request)


def test_validate_team_agent_request_ignores_other_agents() -> None:
    request = AgentRequest(message="hello")

    validate_team_agent_request("search", request)


def test_conversation_metadata_scopes_team_id_to_team_agent() -> None:
    from pathlib import Path

    source = Path("src/api/routes/chat.py").read_text()

    assert 'if agent_id == "team" and request.team_id:' in source
