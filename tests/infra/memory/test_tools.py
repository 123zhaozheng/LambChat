import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest


def test_all_memory_tools_excludes_consolidation_tool():
    from src.infra.memory import tools as memory_tools

    tool_names = {tool.name for tool in memory_tools.get_all_memory_tools()}

    assert "memory_retain" in tool_names
    assert "memory_recall" in tool_names
    assert "memory_delete" in tool_names
    assert "memory_consolidate" not in tool_names


def test_native_memory_guide_does_not_advertise_consolidation_tool():
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE

    assert "memory_consolidate" not in NATIVE_MEMORY_GUIDE


@pytest.mark.asyncio
async def test_auto_memory_capture_serializes_per_user(monkeypatch):
    from src.infra.memory import tools as memory_tools

    state = {"active": 0, "max_active": 0, "calls": 0}
    release = asyncio.Event()

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            state["calls"] += 1
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            if state["calls"] == 1:
                await release.wait()
            state["active"] -= 1

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        return None

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    t1 = asyncio.create_task(memory_tools._auto_retain_user_memory("u1", "first"))
    await asyncio.sleep(0)
    t2 = asyncio.create_task(memory_tools._auto_retain_user_memory("u1", "second"))
    await asyncio.sleep(0.05)

    assert state["calls"] == 1
    assert state["max_active"] == 1

    release.set()
    await asyncio.gather(t1, t2)

    assert state["calls"] == 2
    assert state["max_active"] == 1


@pytest.mark.asyncio
async def test_auto_memory_capture_uses_distributed_lock(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            events.append(("retain", user_id))

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1"), ("retain", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_auto_memory_capture_notifies_compaction_agent_after_store(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> dict[str, int]:
            events.append(("retain", user_id))
            return {"stored": 1}

    class FakeCompactionAgent:
        async def maybe_compact_after_write(self, backend, user_id: str):
            assert isinstance(backend, FakeBackend)
            events.append(("compact", user_id))
            return {"triggered": True}

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1"), ("retain", "u1"), ("compact", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_auto_memory_capture_detaches_langsmith_parent(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, object]] = []

    @contextmanager
    def fake_tracing_context(**kwargs):
        events.append(("trace_kwargs", kwargs))
        yield

    async def fake_auto_retain(user_id: str, user_input: str) -> None:
        events.append(("retain", (user_id, user_input)))

    monkeypatch.setattr(memory_tools, "tracing_context", fake_tracing_context)
    monkeypatch.setattr(memory_tools, "_auto_retain_user_memory", fake_auto_retain)

    await memory_tools._auto_retain_user_memory_detached("u1", "hello")

    assert events == [
        ("trace_kwargs", {"parent": False}),
        ("retain", ("u1", "hello")),
    ]


@pytest.mark.asyncio
async def test_auto_memory_capture_skips_compaction_when_nothing_stored(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> dict[str, int]:
            events.append(("retain", user_id))
            return {"stored": 0}

    class FakeCompactionAgent:
        async def maybe_compact_after_write(self, backend, user_id: str):
            events.append(("compact", user_id))
            return {"triggered": True}

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1"), ("retain", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_auto_memory_capture_skips_when_distributed_lock_not_acquired(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            events.append(("retain", user_id))

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "not_acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1")]


def test_start_memory_compaction_agent_registers_unified_scheduler_job(monkeypatch):
    from src.infra.memory import tools as memory_tools

    registered = []

    class FakeScheduler:
        def register_interval_job(self, job):
            registered.append(job)

    class FakeCompactionAgent:
        def is_periodic_enabled(self) -> bool:
            return True

        def get_periodic_interval_seconds(self) -> int:
            return 123

    monkeypatch.setattr(
        memory_tools,
        "settings",
        SimpleNamespace(ENABLE_MEMORY=True),
    )
    monkeypatch.setattr(memory_tools, "get_runtime_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    memory_tools.start_memory_compaction_agent()

    assert len(registered) == 1
    job = registered[0]
    assert job.id == "memory.compaction"
    assert job.enabled() is True
    assert job.interval_seconds() == 123
    assert job.run_on_start is False


@pytest.mark.asyncio
async def test_scheduled_memory_compaction_runs_periodic_once(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events = []

    class FakeBackend:
        pass

    class FakeCompactionAgent:
        async def run_periodic_once(self, backend):
            assert isinstance(backend, FakeBackend)
            events.append("run")
            return {"checked": 1, "triggered": 1}

    async def fake_get_backend():
        return FakeBackend()

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools,
        "get_memory_compaction_agent",
        lambda: FakeCompactionAgent(),
        raising=False,
    )

    result = await memory_tools.run_scheduled_memory_compaction()

    assert result == {"checked": 1, "triggered": 1}
    assert events == ["run"]
