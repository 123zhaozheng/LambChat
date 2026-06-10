"""Tests for WeCom handler interrupt-and-new-message behavior.

Covers:
- submit passes display_message and write_user_message_immediately
- superseded old run does not send a final reply
- blank collected content does not finalize to an empty WeCom bubble
- /new still creates a fresh session
- finalize_stream_message uses nonblank fallback when no assistant content
"""
from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from src.infra.channel.wecom import handler as wecom_handler

# ── Fakes ──────────────────────────────────────────────────────────────


class _FakeWeComClient:
    """Fake WeComChannel that records all send/reply calls."""

    def __init__(self) -> None:
        self.stream_replies: list[tuple[str, str, str, bool]] = []
        self.proactive_messages: list[tuple[str, str]] = []
        self.reply_messages: list[tuple[str, str]] = []

    async def reply_stream(
        self, chat_id: str, stream_id: str, content: str, *, finish: bool = False
    ) -> bool:
        self.stream_replies.append((chat_id, stream_id, content, finish))
        return True

    async def send_proactive_message(self, chat_id: str, content: str) -> bool:
        self.proactive_messages.append((chat_id, content))
        return True

    async def reply_message(self, chat_id: str, content: str) -> bool:
        self.reply_messages.append((chat_id, content))
        return True


class _FakeManager:
    """Fake WeComChannelManager."""

    def __init__(self, client: _FakeWeComClient | None = None) -> None:
        self.sent_messages: list[tuple[str, str, str, str | None]] = []
        self._client = client or _FakeWeComClient()

    async def send_message(
        self,
        user_id: str,
        chat_id: str,
        content: str,
        instance_id: str | None = None,
    ) -> None:
        self.sent_messages.append((user_id, chat_id, content, instance_id))

    def _find_channel(self, user_id: str, instance_id: str | None = None):
        if user_id == "user-1":
            return self._client
        return None


class _FakeSessionModel:
    """Minimal session model with .metadata support."""

    def __init__(self, current_run_id: str | None = None) -> None:
        self.metadata = {"current_run_id": current_run_id}


class _FakeSessionStorage:
    """Fake SessionStorage that returns a session with current_run_id."""

    def __init__(self, current_run_id: str | None = None) -> None:
        self._current_run_id = current_run_id

    async def get_by_session_id(self, session_id: str):
        if self._current_run_id is not None:
            return _FakeSessionModel(self._current_run_id)
        return None


class _FakeTaskManager:
    """Fake BackgroundTaskManager that records cancel/submit calls."""

    def __init__(self, current_run_id: str | None = None) -> None:
        self.cancel_calls: list[dict[str, Any]] = []
        self.submit_calls: list[dict[str, Any]] = []
        self._storage = _FakeSessionStorage(current_run_id)

    async def cancel(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        self.cancel_calls.append({"session_id": session_id, "user_id": user_id})
        return {"success": True, "cancelled_locally": True, "run_id": "old-run", "message": "ok"}

    async def submit(self, **kwargs: Any) -> tuple[str, str]:
        self.submit_calls.append(kwargs)
        return "run-1", ""

    @property
    def storage(self) -> _FakeSessionStorage:
        return self._storage


def _install_fake_task_manager(
    monkeypatch: pytest.MonkeyPatch, fake_tm: _FakeTaskManager
) -> None:
    task_module = ModuleType("src.infra.task")
    manager_module = ModuleType("src.infra.task.manager")
    manager_module.get_task_manager = lambda: fake_tm  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.infra.task", task_module)
    monkeypatch.setitem(sys.modules, "src.infra.task.manager", manager_module)


async def _async_return(value: Any) -> Any:
    return value


async def _no_op_process_events(**kwargs: Any) -> None:
    return None


async def _no_op_collector_method(self, *args: Any, **kwargs: Any) -> None:
    return None


async def _no_op_upload_and_send(self) -> None:
    return None


# ── Tests: submit kwargs ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wecom_submit_passes_display_message_and_write_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WeCom submit should pass display_message=content and write_user_message_immediately=True."""
    fake_tm = _FakeTaskManager()
    fake_manager = _FakeManager()

    monkeypatch.setattr(
        wecom_handler, "_get_wecom_session_id", lambda chat_id: _async_return(f"wecom_{chat_id}")
    )
    _install_fake_task_manager(monkeypatch, fake_tm)
    monkeypatch.setattr(wecom_handler, "execute_wecom_agent", lambda **kw: _empty_async_gen())
    monkeypatch.setattr(wecom_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector,
        "send_thinking_placeholder",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector, "finalize_stream_message", lambda self: _async_return(False)
    )
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector, "send_message", lambda self: _async_return(True)
    )
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector, "upload_and_send_files", _no_op_upload_and_send
    )

    handler = wecom_handler.create_wecom_message_handler(fake_manager, default_agent="search")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="你好",
        metadata={},
    )

    assert len(fake_tm.submit_calls) == 1
    submit_kwargs = fake_tm.submit_calls[0]
    assert submit_kwargs["display_message"] == "你好"
    assert submit_kwargs["write_user_message_immediately"] is True


@pytest.mark.asyncio
async def test_wecom_submit_uses_same_session_after_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a new message arrives while a run is active, the same session_id is kept."""
    fake_tm = _FakeTaskManager()
    fake_manager = _FakeManager()
    captured_session_ids: list[str] = []

    async def _capture_get_session(chat_id: str) -> str:
        sid = f"wecom_{chat_id}"
        captured_session_ids.append(sid)
        return sid

    monkeypatch.setattr(wecom_handler, "_get_wecom_session_id", _capture_get_session)
    _install_fake_task_manager(monkeypatch, fake_tm)
    monkeypatch.setattr(wecom_handler, "execute_wecom_agent", lambda **kw: _empty_async_gen())
    monkeypatch.setattr(wecom_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector,
        "send_thinking_placeholder",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector, "finalize_stream_message", lambda self: _async_return(False)
    )
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector, "send_message", lambda self: _async_return(True)
    )
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector, "upload_and_send_files", _no_op_upload_and_send
    )

    handler = wecom_handler.create_wecom_message_handler(fake_manager, default_agent="search")

    # First message
    await handler(
        user_id="user-1", sender_id="sender-1", chat_id="chat-1", content="A", metadata={}
    )
    # Second message (interrupts first)
    await handler(
        user_id="user-1", sender_id="sender-1", chat_id="chat-1", content="B", metadata={}
    )

    # Both messages should use the same session_id (no fresh session created)
    assert captured_session_ids[0] == captured_session_ids[1] == "wecom_chat-1"
    assert fake_tm.cancel_calls  # cancel was called before second submit


# ── Tests: superseded run does not send reply ───────────────────────────


@pytest.mark.asyncio
async def test_wecom_superseded_run_does_not_send_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a run is superseded by a newer run, the old run should not finalize or send a reply."""
    fake_client = _FakeWeComClient()
    fake_manager = _FakeManager(fake_client)
    # Simulate that a newer run has replaced this run
    fake_tm = _FakeTaskManager(current_run_id="newer-run")

    monkeypatch.setattr(
        wecom_handler, "_get_wecom_session_id", lambda chat_id: _async_return(f"wecom_{chat_id}")
    )
    _install_fake_task_manager(monkeypatch, fake_tm)
    monkeypatch.setattr(wecom_handler, "execute_wecom_agent", lambda **kw: _empty_async_gen())
    monkeypatch.setattr(wecom_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector,
        "send_thinking_placeholder",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        wecom_handler.WeComResponseCollector, "upload_and_send_files", _no_op_upload_and_send
    )

    handler = wecom_handler.create_wecom_message_handler(fake_manager, default_agent="search")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="hello",
        metadata={},
    )

    # No stream replies or proactive messages should be sent for the superseded run
    assert fake_client.stream_replies == []
    assert fake_client.proactive_messages == []
    assert fake_client.reply_messages == []


# ── Tests: blank bubble guard ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wecom_finalize_no_blank_bubble_when_no_assistant_content() -> None:
    """finalize_stream_message should not finalize with whitespace-only content."""
    fake_client = _FakeWeComClient()
    fake_manager = _FakeManager(fake_client)

    collector = wecom_handler.WeComResponseCollector(
        manager=fake_manager,
        user_id="user-1",
        chat_id="chat-1",
        stream_reply=True,
        send_thinking_message=True,
    )

    # Simulate: thinking placeholder started the stream, but no assistant chunks arrived
    await collector.send_thinking_placeholder()
    result = await collector.finalize_stream_message()

    assert result is True
    # The finalized content must not be a single space or empty
    finalized_content = fake_client.stream_replies[-1][2]
    assert finalized_content.strip() != ""
    assert finalized_content != " "


@pytest.mark.asyncio
async def test_wecom_finalize_normal_content_unchanged() -> None:
    """When assistant content exists, finalize should pass it through normally."""
    fake_client = _FakeWeComClient()
    fake_manager = _FakeManager(fake_client)

    collector = wecom_handler.WeComResponseCollector(
        manager=fake_manager,
        user_id="user-1",
        chat_id="chat-1",
        stream_reply=True,
        send_thinking_message=True,
    )

    # Send thinking placeholder, then add assistant content
    await collector.send_thinking_placeholder()
    await collector.append_stream_chunk("Hello world")

    result = await collector.finalize_stream_message()
    assert result is True

    # The final reply should contain the actual content
    finalized_content = fake_client.stream_replies[-1][2]
    assert "Hello world" in finalized_content
    assert finalized_content != "(无回复内容)"


@pytest.mark.asyncio
async def test_wecom_timeout_fallback_no_blank_bubble() -> None:
    """_send_timeout_fallback should not send whitespace when no content was collected."""
    fake_client = _FakeWeComClient()
    fake_manager = _FakeManager(fake_client)

    collector = wecom_handler.WeComResponseCollector(
        manager=fake_manager,
        user_id="user-1",
        chat_id="chat-1",
        stream_reply=True,
        send_thinking_message=True,
        segmented_reply=False,
    )

    # Start stream via thinking placeholder, mark as timed out
    await collector.send_thinking_placeholder()
    collector._stream_timed_out = True
    collector._stream_finalized = True

    result = await collector._send_timeout_fallback()
    assert result is True

    # Timeout fallback should not be whitespace-only
    sent_content = fake_client.proactive_messages[-1][1]
    assert sent_content.strip() != ""
    assert sent_content != " "


# ── Tests: /new command still works ─────────────────────────────────────


@pytest.mark.asyncio
async def test_wecom_new_command_creates_fresh_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The /new command should still create a fresh WeCom session."""
    fake_manager = _FakeManager()
    created_sessions: list[str] = []

    async def _fake_create_new(chat_id: str) -> str:
        sid = f"wecom_{chat_id}_new"
        created_sessions.append(sid)
        return sid

    monkeypatch.setattr(wecom_handler, "_create_new_wecom_session", _fake_create_new)

    handler = wecom_handler.create_wecom_message_handler(fake_manager, default_agent="search")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="/new",
        metadata={},
    )

    assert created_sessions == ["wecom_chat-1_new"]
    assert any("已创建新对话" in msg[2] for msg in fake_manager.sent_messages)


# ── Helper ──────────────────────────────────────────────────────────────


async def _empty_async_gen():
    """Yields nothing — simulates an executor that produces no events."""
    return
    yield  # type: ignore[unreachable]  # makes this an async generator
