from __future__ import annotations

import json

import pytest

from src.infra.channel.pubsub import (
    CHANNEL_CONFIG_CHANNEL,
    ChannelConfigPubSub,
    publish_channel_config_changed,
)


class _FakeHub:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, object]] = []
        self.unsubscribed: list[str] = []
        self.start_calls = 0
        self.stop_if_idle_calls = 0

    def subscribe(self, channel: str, handler) -> str:
        token = f"token-{len(self.subscriptions) + 1}"
        self.subscriptions.append((channel, handler))
        return token

    def unsubscribe(self, token: str) -> None:
        self.unsubscribed.append(token)

    async def start(self) -> None:
        self.start_calls += 1

    async def stop_if_idle(self) -> None:
        self.stop_if_idle_calls += 1


class _FakeRedisClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


class _FakeManager:
    def __init__(self) -> None:
        self.reload_calls: list[tuple[str, str | None]] = []

    async def reload_user(self, user_id: str, instance_id: str | None = None) -> bool:
        self.reload_calls.append((user_id, instance_id))
        return True


class _FakeManagerClass:
    _instance = _FakeManager()

    @classmethod
    def get_instance(cls) -> _FakeManager:
        return cls._instance


class _FakeRegistry:
    def __init__(self, manager_cls) -> None:
        self._manager_cls = manager_cls

    def get_manager_class(self, channel_type):
        return self._manager_cls


@pytest.mark.asyncio
async def test_channel_config_pubsub_subscribes_to_shared_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.channel.pubsub.get_pubsub_hub", lambda: fake_hub)

    pubsub = ChannelConfigPubSub()
    await pubsub.start_listener()

    assert fake_hub.start_calls == 1
    assert fake_hub.subscriptions[0][0] == CHANNEL_CONFIG_CHANNEL

    await pubsub.stop_listener()
    assert fake_hub.unsubscribed == ["token-1"]


@pytest.mark.asyncio
async def test_channel_config_pubsub_reloads_foreign_instance_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _FakeRegistry(_FakeManagerClass)
    monkeypatch.setattr("src.infra.channel.pubsub.get_registry", lambda: registry)

    pubsub = ChannelConfigPubSub()
    pubsub._instance_id = "instance-a"

    await pubsub._handle_message(
        {
            "data": json.dumps(
                {
                    "instance_id": "instance-b",
                    "user_id": "user-1",
                    "channel_type": "wecom",
                    "channel_instance_id": "chan-1",
                    "action": "updated",
                }
            )
        }
    )

    assert _FakeManagerClass.get_instance().reload_calls == [("user-1", "chan-1")]


@pytest.mark.asyncio
async def test_publish_channel_config_changed_broadcasts_instance_scoped_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.channel.pubsub.get_redis_client", lambda: fake_redis)

    pubsub = ChannelConfigPubSub()
    pubsub._instance_id = "instance-a"
    monkeypatch.setattr("src.infra.channel.pubsub.get_channel_config_pubsub", lambda: pubsub)

    await publish_channel_config_changed(
        user_id="user-1",
        channel_type="wecom",
        channel_instance_id="chan-1",
        action="deleted",
    )

    assert fake_redis.published == [
        (
            CHANNEL_CONFIG_CHANNEL,
            json.dumps(
                {
                    "instance_id": "instance-a",
                    "user_id": "user-1",
                    "channel_type": "wecom",
                    "channel_instance_id": "chan-1",
                    "action": "deleted",
                }
            ),
        )
    ]
