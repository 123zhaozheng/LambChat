from __future__ import annotations

import pytest

from src.api.routes.agent import model as model_routes
from src.kernel.schemas.model import ModelConfig
from src.kernel.schemas.user import TokenPayload


class _ModelStorage:
    async def list_models(self, include_disabled: bool = False) -> list[ModelConfig]:
        models = [
            ModelConfig(
                id="allowed-model",
                value="openai/gpt-allowed",
                provider="openai",
                label="Allowed",
                description="Visible",
                api_key="sk-secret-allowed",
                api_base="https://api.example.test",
                temperature=0.2,
                max_tokens=1024,
                enabled=True,
                order=1,
            ),
            ModelConfig(
                id="blocked-model",
                value="openai/gpt-blocked",
                provider="openai",
                label="Blocked",
                description="Hidden",
                api_key="sk-secret-blocked",
                api_base="https://api.hidden.test",
                temperature=0.9,
                max_tokens=2048,
                enabled=True,
                order=2,
            ),
        ]
        if include_disabled:
            return models
        return [model for model in models if model.enabled]

    async def count(self) -> dict[str, int]:
        return {"total": 2, "enabled": 2}


class _AgentConfigStorage:
    async def get_role_models(self, role_id: str) -> list[str] | None:
        if role_id == "role-user":
            return ["allowed-model"]
        if role_id == "role-empty":
            return []
        return None


class _Role:
    id = "role-user"


class _EmptyRole:
    id = "role-empty"


class _RoleManager:
    async def get_role_by_name(self, role_name: str) -> _Role | _EmptyRole | None:
        if role_name == "user":
            return _Role()
        if role_name == "empty":
            return _EmptyRole()
        return None


@pytest.mark.asyncio
async def test_list_available_models_filters_by_role_allowed_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)

    assert [model.id for model in response.models] == ["allowed-model"]
    assert response.count == 1
    assert response.enabled_count == 1


@pytest.mark.asyncio
async def test_list_available_models_returns_public_fields_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)
    payload = response.model_dump()

    assert payload["models"] == [
        {
            "id": "allowed-model",
            "value": "openai/gpt-allowed",
            "provider": "openai",
            "label": "Allowed",
            "description": "Visible",
            "profile": None,
        }
    ]
    assert payload["default_model_id"] == "allowed-model"


@pytest.mark.asyncio
async def test_list_available_models_returns_empty_when_role_allows_no_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["empty"])

    response = await model_routes.list_available_models(user)

    assert response.models == []
    assert response.count == 0
    assert response.enabled_count == 0


@pytest.mark.asyncio
async def test_list_available_models_marks_effective_admin_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    monkeypatch.setattr(
        "src.infra.llm.models_service.settings.DEFAULT_MODEL_ID",
        "blocked-model",
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)

    assert response.default_model_id == "allowed-model"
