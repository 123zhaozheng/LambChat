from __future__ import annotations

import pytest

from src.infra.llm import models_service
from src.kernel.config import settings


@pytest.fixture(autouse=True)
def clear_model_caches() -> None:
    models_service.clear_memory_cache()
    models_service.clear_api_key_cache()


@pytest.mark.asyncio
async def test_get_default_model_prefers_admin_default_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_MODEL_ID", "model-b", raising=False)

    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.get_default_model() == "anthropic/claude-b"
    assert await models_service.get_default_model_id() == "model-b"


@pytest.mark.asyncio
async def test_get_default_model_falls_back_when_admin_default_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_MODEL_ID", "missing-model", raising=False)

    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.get_default_model() == "openai/gpt-a"
    assert await models_service.get_default_model_id() == "model-a"


@pytest.mark.asyncio
async def test_get_default_model_respects_allowed_models_before_admin_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_MODEL_ID", "model-b", raising=False)

    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.get_default_model(["model-a"]) == "openai/gpt-a"
    assert await models_service.get_default_model_id(["model-a"]) == "model-a"
