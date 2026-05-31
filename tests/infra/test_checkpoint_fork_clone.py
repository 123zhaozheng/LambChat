from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

import src.infra.storage.checkpoint as checkpoint_mod
from src.infra.storage.checkpoint import build_messages_from_trace_events


class _State(TypedDict):
    messages: Annotated[list, add_messages]


def _reply_node(state: _State):
    last = state["messages"][-1]
    return {"messages": [AIMessage(content=f"reply to {last.content}")]}


@pytest.mark.asyncio
async def test_clone_checkpoints_for_fork_copies_assistant_turn(monkeypatch: pytest.MonkeyPatch):
    builder = StateGraph(_State)
    builder.add_node("reply", _reply_node)
    builder.add_edge(START, "reply")
    builder.add_edge("reply", END)

    source_saver = InMemorySaver()
    target_saver = InMemorySaver()
    graph = builder.compile(checkpointer=source_saver)
    config = {"configurable": {"thread_id": "source-thread"}}

    graph.invoke({"messages": [HumanMessage(content="one")]}, config)
    graph.invoke({"messages": [HumanMessage(content="two")]}, config)

    async def _fake_get_async_checkpointer(thread_id: str | None = None):
        if thread_id == "source-thread":
            return source_saver
        if thread_id == "target-thread":
            return target_saver
        raise AssertionError(f"unexpected thread_id {thread_id}")

    monkeypatch.setattr(checkpoint_mod, "get_async_checkpointer", _fake_get_async_checkpointer)

    copied = await checkpoint_mod.clone_checkpoints_for_fork(
        "source-thread",
        "target-thread",
        turn_index=1,
        target_type="assistant",
    )

    assert copied > 0

    checkpoints = [
        item async for item in target_saver.alist({"configurable": {"thread_id": "target-thread"}})
    ]
    latest_messages = checkpoints[0].checkpoint["channel_values"]["messages"]
    assert [type(message).__name__ for message in latest_messages] == ["HumanMessage", "AIMessage"]
    assert latest_messages[0].content == "one"
    assert latest_messages[1].content == "reply to one"


@pytest.mark.asyncio
async def test_clone_checkpoints_for_fork_only_lists_default_namespace(
    monkeypatch: pytest.MonkeyPatch,
):
    source_saver = InMemorySaver()
    target_saver = InMemorySaver()

    first_config = {"configurable": {"thread_id": "source-thread", "checkpoint_ns": ""}}
    first_checkpoint = {
        "v": 1,
        "id": "0001",
        "ts": "2026-01-01T00:00:00+00:00",
        "channel_values": {"messages": [HumanMessage(content="one")]},
        "channel_versions": {"messages": "0001"},
        "versions_seen": {},
    }
    second_config = await source_saver.aput(
        first_config,
        first_checkpoint,
        {},
        first_checkpoint["channel_versions"],
    )
    second_checkpoint = {
        **first_checkpoint,
        "id": "0002",
        "channel_values": {"messages": [HumanMessage(content="one"), AIMessage(content="reply")]},
        "channel_versions": {"messages": "0002"},
    }
    await source_saver.aput(
        second_config,
        second_checkpoint,
        {},
        second_checkpoint["channel_versions"],
    )

    list_calls: list[tuple[dict, dict]] = []
    original_alist = source_saver.alist

    async def _recording_alist(config, *args, **kwargs):
        list_calls.append((config, kwargs))
        async for item in original_alist(config, *args, **kwargs):
            yield item

    source_saver.alist = _recording_alist  # type: ignore[method-assign]

    async def _fake_get_async_checkpointer(thread_id: str | None = None):
        if thread_id == "source-thread":
            return source_saver
        if thread_id == "target-thread":
            return target_saver
        raise AssertionError(f"unexpected thread_id {thread_id}")

    monkeypatch.setattr(checkpoint_mod, "get_async_checkpointer", _fake_get_async_checkpointer)

    await checkpoint_mod.clone_checkpoints_for_fork(
        "source-thread",
        "target-thread",
        turn_index=1,
        target_type="assistant",
    )

    assert [config for config, _ in list_calls] == [
        {"configurable": {"thread_id": "source-thread", "checkpoint_ns": ""}}
    ]
    assert list_calls[0][1]["limit"] == 25


def test_build_messages_from_trace_events_preserves_user_and_assistant_text() -> None:
    messages = build_messages_from_trace_events(
        [
            {
                "events": [
                    {"event_type": "user:message", "data": {"content": "hello"}},
                    {"event_type": "thinking", "data": {"content": "private reasoning"}},
                    {"event_type": "message:chunk", "data": {"content": "hi"}},
                    {"event_type": "message:chunk", "data": {"content": " there"}},
                    {"event_type": "done", "data": {"status": "completed"}},
                ]
            }
        ]
    )

    assert [type(message).__name__ for message in messages] == ["HumanMessage", "AIMessage"]
    assert messages[0].content == "hello"
    assert messages[1].content == "hi there"


@pytest.mark.asyncio
async def test_delete_checkpoints_for_thread_uses_checkpointer_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Saver:
        def __init__(self) -> None:
            self.deleted_threads: list[str] = []

        async def adelete_thread(self, thread_id: str) -> None:
            self.deleted_threads.append(thread_id)

    saver = _Saver()

    async def _fake_get_async_checkpointer(thread_id: str | None = None):
        assert thread_id == "session-1"
        return saver

    monkeypatch.setattr(checkpoint_mod, "get_async_checkpointer", _fake_get_async_checkpointer)

    await checkpoint_mod.delete_checkpoints_for_thread("session-1")

    assert saver.deleted_threads == ["session-1"]


@pytest.mark.asyncio
async def test_delete_checkpoints_for_thread_skips_when_checkpoint_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail_get_async_checkpointer(thread_id: str | None = None):
        raise AssertionError(f"should not initialize checkpointer for {thread_id}")

    monkeypatch.setattr(checkpoint_mod.settings, "CHECKPOINT_BACKEND", "none")
    monkeypatch.setattr(checkpoint_mod, "get_async_checkpointer", _fail_get_async_checkpointer)

    await checkpoint_mod.delete_checkpoints_for_thread("session-1")
