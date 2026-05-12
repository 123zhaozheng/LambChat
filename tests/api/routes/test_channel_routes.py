from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.routes import channels as channels_route
from src.kernel.schemas.channel import ChannelConfigCreate, ChannelConfigUpdate, ChannelType


class _FakeChannelClass:
    @staticmethod
    def get_metadata() -> dict:
        return {"config_fields": [], "capabilities": []}


class _FakeRegistry:
    def __init__(self, manager_class=None) -> None:
        self._manager_class = manager_class

    def get_channel_class(self, channel_type: ChannelType):
        return _FakeChannelClass

    def get_manager_class(self, channel_type: ChannelType):
        return self._manager_class


class _FakeStorage:
    def __init__(self) -> None:
        self.create_calls = 0
        self.update_calls = 0

    async def create_config(self, **kwargs):
        self.create_calls += 1
        return {"instance_id": "instance-1"}

    async def get_config(self, user_id: str, channel_type: ChannelType, instance_id: str):
        return {"app_id": "app-1", "enabled": True}

    async def update_config(self, **kwargs):
        self.update_calls += 1
        return {"instance_id": "instance-1"}

    async def get_response(
        self, user_id: str, channel_type: ChannelType, instance_id: str, metadata
    ):
        return SimpleNamespace(instance_id=instance_id)

    async def get_status(self, user_id: str, channel_type: ChannelType, instance_id: str):
        return SimpleNamespace(channel_type=channel_type, enabled=True, connected=False)


class _FakeManager:
    def __init__(self) -> None:
        self.reload_calls: list[tuple[str, str]] = []
        self.connected = False

    def is_connected(self, user_id: str, instance_id: str) -> bool:
        return self.connected

    async def reload_user(self, user_id: str, instance_id: str) -> bool:
        self.reload_calls.append((user_id, instance_id))
        self.connected = True
        return True


class _FakeProjectStorage:
    async def get_by_id(self, project_id: str, user_id: str):
        return None


@pytest.mark.asyncio
async def test_create_channel_rejects_unknown_project_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: _FakeProjectStorage(),
    )
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.create_channel_instance(
            ChannelType.FEISHU,
            ChannelConfigCreate(
                channel_type=ChannelType.FEISHU,
                name="Feishu",
                config={},
                project_id="missing-project",
            ),
            user=SimpleNamespace(sub="user-1", roles=[]),
            storage=storage,
        )

    assert exc_info.value.status_code == 400
    assert storage.create_calls == 0


@pytest.mark.asyncio
async def test_update_channel_rejects_unknown_project_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: _FakeProjectStorage(),
    )
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.update_channel_instance(
            ChannelType.FEISHU,
            "instance-1",
            ChannelConfigUpdate(config={}, project_id="missing-project"),
            user=SimpleNamespace(sub="user-1", roles=[]),
            storage=storage,
        )

    assert exc_info.value.status_code == 400
    assert storage.update_calls == 0


@pytest.mark.asyncio
async def test_status_starts_enabled_channel_when_manager_is_disconnected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    manager = _FakeManager()
    manager_class = type(
        "_StatusManagerClass",
        (),
        {"get_instance": classmethod(lambda cls: manager)},
    )
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry(manager_class))

    status = await channels_route.get_channel_instance_status(
        ChannelType.FEISHU,
        "instance-1",
        user=SimpleNamespace(sub="user-1", roles=[]),
        storage=storage,
    )

    assert manager.reload_calls == [("user-1", "instance-1")]
    assert status.connected is True


async def _async_noop(*args, **kwargs) -> None:
    return None
