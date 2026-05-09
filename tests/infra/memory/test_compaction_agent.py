import pytest
from langgraph.errors import GraphRecursionError

from src.infra.memory.compaction_agent import (
    _COMPACTION_SYSTEM_PROMPT,
    MemoryCompactionAgent,
)


@pytest.fixture(autouse=True)
def _redis_cooldown_clear(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    async def fake_get_cooldown_state(_user_id: str) -> str:
        return "clear"

    async def fake_mark_cooldown(_user_id: str, _ttl_seconds: int) -> str:
        return "marked"

    monkeypatch.setattr(
        compaction_module,
        "get_compaction_cooldown_state",
        fake_get_cooldown_state,
    )
    monkeypatch.setattr(
        compaction_module,
        "mark_compaction_cooldown",
        fake_mark_cooldown,
    )


class _CountCursor:
    def __init__(self, docs):
        self._docs = docs
        self._skip = 0

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def skip(self, value):
        self._skip = value
        return self

    async def to_list(self, length):
        return self._docs[self._skip : self._skip + length]


class _Collection:
    def __init__(self, counts: dict[str, int]):
        self.counts = counts
        self.docs: list[dict] = []

    async def count_documents(self, query):
        self.last_count_query = query
        return self.counts.get(query["user_id"], 0)

    def find(self, *_args, **_kwargs):
        return _CountCursor(self.docs)

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if doc.get("user_id") == query.get("user_id") and doc.get("memory_id") == query.get(
                "memory_id"
            ):
                return doc
        return None

    def aggregate(self, _pipeline):
        return _CountCursor(
            [{"_id": user_id, "count": count} for user_id, count in self.counts.items()]
        )


class _Backend:
    def __init__(self, counts: dict[str, int], docs: list[dict] | None = None):
        self._collection = _Collection(counts)
        self._collection.docs = docs or []
        self.compacted: list[str] = []

    async def consolidate_memories(self, user_id: str):
        self.compacted.append(user_id)
        return {"merged": 1, "pruned": 0, "total_before": 10, "total_after": 9}

    @staticmethod
    async def _get_memory_model():
        return "fake-model"

    async def retain(self, *_args, **_kwargs):
        return {"success": True}

    async def delete(self, *_args, **_kwargs):
        return {"success": True}


class _CompactionCapableBackend:
    def __init__(self, counts: dict[str, int]):
        self._collection = _Collection(counts)

    @staticmethod
    async def _get_memory_model():
        return "fake-model"

    async def retain(self, *_args, **_kwargs):
        return {"success": True}

    async def delete(self, *_args, **_kwargs):
        return {"success": True}


@pytest.mark.asyncio
async def test_maybe_compact_after_write_skips_when_disabled():
    backend = _Backend({"u1": 100})
    agent = MemoryCompactionAgent(enabled=False, threshold=50)

    result = await agent.maybe_compact_after_write(backend, "u1")

    assert result == {"triggered": False, "reason": "disabled"}
    assert backend.compacted == []


@pytest.mark.asyncio
async def test_maybe_compact_after_write_skips_below_threshold():
    backend = _Backend({"u1": 49})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)

    result = await agent.maybe_compact_after_write(backend, "u1")

    assert result == {"triggered": False, "reason": "below_threshold", "count": 49}
    assert backend.compacted == []


@pytest.mark.asyncio
async def test_maybe_compact_after_write_counts_only_non_manual_memories():
    backend = _Backend({"u1": 49})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)

    await agent.maybe_compact_after_write(backend, "u1")

    assert backend._collection.last_count_query == {
        "user_id": "u1",
        "source": {"$ne": "manual"},
    }


@pytest.mark.asyncio
async def test_maybe_compact_after_write_triggers_at_threshold():
    backend = _Backend({"u1": 50})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)

    async def fake_compact(_backend, user_id: str):
        backend.compacted.append(user_id)
        return {"agent": "deepagent", "checked": 3}

    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.maybe_compact_after_write(backend, "u1")

    assert result["triggered"] is True
    assert result["reason"] == "threshold_reached"
    assert result["count"] == 50
    assert result["result"]["agent"] == "deepagent"
    assert backend.compacted == ["u1"]


@pytest.mark.asyncio
async def test_maybe_compact_after_write_does_not_require_legacy_consolidate_method():
    backend = _CompactionCapableBackend({"u1": 50})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)
    seen: list[str] = []

    async def fake_compact(_backend, user_id: str):
        seen.append(user_id)
        return {"agent": "deepagent", "checked": 3}

    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.maybe_compact_after_write(backend, "u1")

    assert result["triggered"] is True
    assert seen == ["u1"]


@pytest.mark.asyncio
async def test_maybe_compact_after_write_runs_deepagent_compactor(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    created: dict[str, object] = {}
    docs = [
        {
            "memory_id": "m1",
            "user_id": "u1",
            "content": "User prefers DuckDB for local analytics.",
            "summary": "Prefers DuckDB.",
            "title": "DuckDB",
            "memory_type": "user",
            "source": "auto_retained",
        },
        {
            "memory_id": "m2",
            "user_id": "u1",
            "content": "User prefers DuckDB because it works offline.",
            "summary": "DuckDB works offline.",
            "title": "DuckDB offline",
            "memory_type": "user",
            "source": "auto_retained",
        },
        {
            "memory_id": "m3",
            "user_id": "u1",
            "content": "User likes raw SQL for analytics.",
            "summary": "Likes raw SQL.",
            "title": "SQL",
            "memory_type": "user",
            "source": "auto_retained",
        },
    ]
    backend = _Backend({"u1": 80}, docs=docs)

    class FakeGraph:
        async def ainvoke(self, payload, config):
            created["payload"] = payload
            created["config"] = config
            return {"messages": []}

    def fake_create_deep_agent(**kwargs):
        created.update(kwargs)
        return FakeGraph()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        return None

    monkeypatch.setattr(compaction_module, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(compaction_module, "acquire_consolidation_lock", fake_acquire)
    monkeypatch.setattr(compaction_module, "release_consolidation_lock", fake_release)
    agent = MemoryCompactionAgent(enabled=True, threshold=50, min_interval_seconds=0)

    async def fake_get_compaction_model():
        return "fake-compaction-model"

    agent._get_compaction_model = fake_get_compaction_model  # type: ignore[method-assign]

    result = await agent.maybe_compact_after_write(backend, "u1")

    assert result["triggered"] is True
    assert result["result"]["agent"] == "deepagent"
    assert created["model"] == "fake-compaction-model"
    tool_names = {tool.name for tool in created["tools"]}
    assert tool_names == {
        "memory_compaction_list",
        "memory_compaction_update",
        "memory_compaction_delete",
    }
    assert "80 automatic cross-session memories" in str(created["payload"])
    assert "User prefers DuckDB" not in str(created["payload"])
    assert created["config"]["recursion_limit"] > 40
    assert "every memory has been considered" in str(created["payload"])


def test_compaction_prompt_does_not_embed_memory_content():
    prompt = MemoryCompactionAgent._build_compaction_prompt(memory_count=42)

    assert "42 automatic cross-session memories" in prompt
    assert "memory_compaction_list" in prompt
    assert "memory_compaction_update" in prompt
    assert "memory_compaction_delete" in prompt
    assert "every memory has been considered" in prompt
    assert "list all memory metadata pages" in prompt
    assert "identify candidate groups" in prompt
    assert "fetch candidate content through memory_compaction_list" in prompt
    assert "update canonical memories" in prompt
    assert "delete only redundant or non-durable memories" in prompt
    assert "JSON array below" not in prompt


def test_compaction_system_prompt_defines_strict_sop():
    prompt = _COMPACTION_SYSTEM_PROMPT

    assert "Follow this SOP exactly" in prompt
    assert "Phase 1: Inventory" in prompt
    assert "Do not update or delete anything during inventory" in prompt
    assert (
        "If metadata is enough to decide something is unique and durable, leave it alone" in prompt
    )
    assert "Phase 2: Candidate selection" in prompt
    assert "Phase 3: Fetch candidate content before mutation" in prompt
    assert "memory_compaction_list(memory_ids=" in prompt
    assert "Phase 4: Edit / merge" in prompt
    assert "Phase 5: Delete" in prompt
    assert "Phase 6: Stop condition" in prompt
    assert "memory_compaction_update on the canonical memory" in prompt
    assert "Only delete a memory after its durable facts are preserved" in prompt


@pytest.mark.asyncio
async def test_compaction_model_uses_admin_model_config_id(monkeypatch):
    from src.infra.llm.client import LLMClient
    from src.infra.memory import compaction_agent as compaction_module

    calls: list[dict] = []

    async def fake_get_model(**kwargs):
        calls.append(kwargs)
        return "configured-compaction-model"

    monkeypatch.setattr(
        compaction_module.settings,
        "NATIVE_MEMORY_COMPACTION_MODEL_ID",
        "model-config-123",
    )
    monkeypatch.setattr(LLMClient, "get_model", fake_get_model)

    model = await MemoryCompactionAgent()._get_compaction_model()

    assert model == "configured-compaction-model"
    assert calls == [{"model_id": "model-config-123", "temperature": 0.1}]


@pytest.mark.asyncio
async def test_deepagent_compactor_returns_error_on_recursion_limit(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    backend = _Backend(
        {"u1": 80},
        docs=[
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "a",
                "source": "auto_retained",
            },
            {
                "memory_id": "m2",
                "user_id": "u1",
                "content": "b",
                "source": "auto_retained",
            },
            {
                "memory_id": "m3",
                "user_id": "u1",
                "content": "c",
                "source": "auto_retained",
            },
        ],
    )
    events: list[tuple[str, str]] = []

    class FakeGraph:
        async def ainvoke(self, _payload, _config):
            raise GraphRecursionError("recursion limit reached")

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(compaction_module, "create_deep_agent", lambda **_kwargs: FakeGraph())
    monkeypatch.setattr(compaction_module, "acquire_consolidation_lock", fake_acquire)
    monkeypatch.setattr(compaction_module, "release_consolidation_lock", fake_release)

    result = await MemoryCompactionAgent(
        enabled=True,
        threshold=50,
        min_interval_seconds=0,
    ).compact_user_memories(backend, "u1")

    assert result["agent"] == "deepagent"
    assert result["skipped"] is True
    assert result["reason"] == "recursion_limit"
    assert result["checked"] == 80
    assert events == [("acquire", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_compaction_list_can_include_content_for_candidate_ids():
    backend = _Backend(
        {"u1": 80},
        docs=[
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "User prefers careful memory review before deletion.",
                "summary": "Prefers careful memory review.",
                "title": "Memory review",
                "memory_type": "user",
                "source": "auto_retained",
                "tags": ["memory"],
                "context": "feedback_rule",
            }
        ],
    )
    metrics = {"updated": 0, "deleted": 0}
    tools = MemoryCompactionAgent()._build_compaction_tools(backend, "u1", metrics)
    tool_by_name = {tool.name: tool for tool in tools}

    result = await tool_by_name["memory_compaction_list"].ainvoke(
        {"memory_ids": ["m1"], "include_content": True}
    )

    assert result["success"] is True
    assert result["memories"][0]["memory_id"] == "m1"
    assert result["memories"][0]["content"] == "User prefers careful memory review before deletion."
    assert metrics == {"updated": 0, "deleted": 0}


@pytest.mark.asyncio
async def test_compaction_tools_list_metadata_without_full_content():
    backend = _Backend(
        {"u1": 80},
        docs=[
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "Sensitive full content should not appear in list.",
                "summary": "Safe summary.",
                "title": "Safe title",
                "memory_type": "user",
                "source": "auto_retained",
                "tags": ["memory"],
                "context": "feedback_rule",
            }
        ],
    )
    tools = MemoryCompactionAgent()._build_compaction_tools(backend, "u1")
    tool_by_name = {tool.name: tool for tool in tools}

    result = await tool_by_name["memory_compaction_list"].ainvoke({"offset": 0, "limit": 10})

    assert result["success"] is True
    assert result["total"] == 80
    assert result["memories"][0]["memory_id"] == "m1"
    assert result["memories"][0]["summary"] == "Safe summary."
    assert "content" not in result["memories"][0]


@pytest.mark.asyncio
async def test_maybe_compact_after_write_does_not_cool_down_when_lock_not_acquired(
    monkeypatch,
):
    from src.infra.memory import compaction_agent as compaction_module

    backend = _Backend(
        {"u1": 80},
        docs=[
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "a",
                "source": "auto_retained",
            },
            {
                "memory_id": "m2",
                "user_id": "u1",
                "content": "b",
                "source": "auto_retained",
            },
            {
                "memory_id": "m3",
                "user_id": "u1",
                "content": "c",
                "source": "auto_retained",
            },
        ],
    )
    attempts = 0

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        nonlocal attempts
        attempts += 1
        return "not_acquired"

    monkeypatch.setattr(compaction_module, "acquire_consolidation_lock", fake_acquire)

    agent = MemoryCompactionAgent(enabled=True, threshold=50, min_interval_seconds=900)
    first = await agent.maybe_compact_after_write(backend, "u1")
    second = await agent.maybe_compact_after_write(backend, "u1")

    assert first["triggered"] is False
    assert second["triggered"] is False
    assert first["reason"] == "lock_not_acquired"
    assert second["reason"] == "lock_not_acquired"
    assert attempts == 2


@pytest.mark.asyncio
async def test_maybe_compact_after_write_uses_distributed_cooldown(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    backend = _Backend({"u1": 80})
    agent = MemoryCompactionAgent(enabled=True, threshold=50, min_interval_seconds=900)
    compact_calls = 0

    async def fake_cooldown_state(user_id: str) -> str:
        return "active"

    async def fake_compact(_backend, _user_id: str):
        nonlocal compact_calls
        compact_calls += 1
        return {"agent": "deepagent", "checked": 80}

    monkeypatch.setattr(compaction_module, "get_compaction_cooldown_state", fake_cooldown_state)
    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.maybe_compact_after_write(backend, "u1")

    assert result == {"triggered": False, "reason": "cooldown", "count": 80}
    assert compact_calls == 0


@pytest.mark.asyncio
async def test_successful_after_write_marks_distributed_cooldown(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    backend = _Backend({"u1": 80})
    marked: list[tuple[str, int]] = []
    agent = MemoryCompactionAgent(enabled=True, threshold=50, min_interval_seconds=900)

    async def fake_compact(_backend, user_id: str):
        return {"agent": "deepagent", "checked": 80}

    async def fake_mark(user_id: str, ttl_seconds: int) -> str:
        marked.append((user_id, ttl_seconds))
        return "marked"

    monkeypatch.setattr(compaction_module, "mark_compaction_cooldown", fake_mark)
    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.maybe_compact_after_write(backend, "u1")

    assert result["triggered"] is True
    assert marked == [("u1", 900)]


@pytest.mark.asyncio
async def test_deepagent_compactor_uses_distributed_consolidation_lock(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    events: list[tuple[str, str]] = []
    backend = _Backend(
        {"u1": 80},
        docs=[
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "a",
                "source": "auto_retained",
            },
            {
                "memory_id": "m2",
                "user_id": "u1",
                "content": "b",
                "source": "auto_retained",
            },
            {
                "memory_id": "m3",
                "user_id": "u1",
                "content": "c",
                "source": "auto_retained",
            },
        ],
    )

    class FakeGraph:
        async def ainvoke(self, _payload, _config):
            events.append(("agent", "run"))
            return {"messages": []}

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(compaction_module, "create_deep_agent", lambda **_kwargs: FakeGraph())
    monkeypatch.setattr(compaction_module, "acquire_consolidation_lock", fake_acquire)
    monkeypatch.setattr(compaction_module, "release_consolidation_lock", fake_release)

    result = await MemoryCompactionAgent(
        enabled=True,
        threshold=50,
        min_interval_seconds=0,
    ).compact_user_memories(backend, "u1")

    assert result["agent"] == "deepagent"
    assert events == [("acquire", "u1"), ("agent", "run"), ("release", "u1")]


@pytest.mark.asyncio
async def test_deepagent_compactor_reports_successful_tool_counts(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    backend = _Backend(
        {"u1": 80},
        docs=[
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "a",
                "source": "auto_retained",
            },
            {
                "memory_id": "m2",
                "user_id": "u1",
                "content": "b",
                "source": "auto_retained",
            },
            {
                "memory_id": "m3",
                "user_id": "u1",
                "content": "c",
                "source": "auto_retained",
            },
        ],
    )

    class FakeGraph:
        def __init__(self, tools):
            self.tools = {tool.name: tool for tool in tools}

        async def ainvoke(self, _payload, _config):
            await self.tools["memory_compaction_update"].ainvoke(
                {
                    "memory_id": "m1",
                    "content": "User prefers concise durable memory.",
                    "title": "Memory style",
                    "summary": "Prefers concise durable memory.",
                    "tags": ["memory", "style"],
                    "context": "compacted",
                }
            )
            await self.tools["memory_compaction_delete"].ainvoke({"memory_id": "m2"})
            return {"messages": []}

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        return None

    monkeypatch.setattr(
        compaction_module,
        "create_deep_agent",
        lambda **kwargs: FakeGraph(kwargs["tools"]),
    )
    monkeypatch.setattr(compaction_module, "acquire_consolidation_lock", fake_acquire)
    monkeypatch.setattr(compaction_module, "release_consolidation_lock", fake_release)

    result = await MemoryCompactionAgent(
        enabled=True,
        threshold=50,
        min_interval_seconds=0,
    ).compact_user_memories(backend, "u1")

    assert result["updated"] == 1
    assert result["deleted"] == 1


@pytest.mark.asyncio
async def test_deepagent_compactor_skips_when_distributed_lock_not_acquired(
    monkeypatch,
):
    from src.infra.memory import compaction_agent as compaction_module

    events: list[tuple[str, str]] = []
    backend = _Backend(
        {"u1": 80},
        docs=[
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "a",
                "source": "auto_retained",
            },
            {
                "memory_id": "m2",
                "user_id": "u1",
                "content": "b",
                "source": "auto_retained",
            },
            {
                "memory_id": "m3",
                "user_id": "u1",
                "content": "c",
                "source": "auto_retained",
            },
        ],
    )

    class FakeGraph:
        async def ainvoke(self, _payload, _config):
            events.append(("agent", "run"))
            return {"messages": []}

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "not_acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(compaction_module, "create_deep_agent", lambda **_kwargs: FakeGraph())
    monkeypatch.setattr(compaction_module, "acquire_consolidation_lock", fake_acquire)
    monkeypatch.setattr(compaction_module, "release_consolidation_lock", fake_release)

    result = await MemoryCompactionAgent(
        enabled=True,
        threshold=50,
        min_interval_seconds=0,
    ).compact_user_memories(backend, "u1")

    assert result["skipped"] is True
    assert result["reason"] == "lock_not_acquired"
    assert events == [("acquire", "u1")]


@pytest.mark.asyncio
async def test_run_periodic_once_compacts_only_users_at_threshold(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    backend = _Backend({"small": 49, "large": 51})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)

    async def fake_acquire(instance_id: str, ttl_seconds: int) -> str:
        return "acquired"

    async def fake_compact(_backend, user_id: str):
        backend.compacted.append(user_id)
        return {"agent": "deepagent", "checked": 3}

    monkeypatch.setattr(compaction_module, "acquire_compaction_scan_lock", fake_acquire)
    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.run_periodic_once(backend)

    assert result == {"checked": 1, "triggered": 1}
    assert backend.compacted == ["large"]


@pytest.mark.asyncio
async def test_run_periodic_once_reports_skipped_lock_separately(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    backend = _Backend({"large": 51})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)

    async def fake_acquire(instance_id: str, ttl_seconds: int) -> str:
        return "acquired"

    async def fake_compact(_backend, user_id: str):
        return {
            "agent": "deepagent",
            "checked": 0,
            "skipped": True,
            "reason": "lock_not_acquired",
        }

    monkeypatch.setattr(compaction_module, "acquire_compaction_scan_lock", fake_acquire)
    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.run_periodic_once(backend)

    assert result == {"checked": 1, "triggered": 0, "skipped": 1}


@pytest.mark.asyncio
async def test_run_periodic_once_uses_distributed_scan_lock(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    events: list[tuple[str, str]] = []
    backend = _Backend({"large": 51})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)

    async def fake_acquire(instance_id: str, ttl_seconds: int) -> str:
        events.append(("acquire_scan", instance_id))
        return "acquired"

    async def fake_compact(_backend, user_id: str):
        events.append(("compact", user_id))
        return {"agent": "deepagent", "checked": 3}

    monkeypatch.setattr(compaction_module, "acquire_compaction_scan_lock", fake_acquire)
    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.run_periodic_once(backend)

    assert result == {"checked": 1, "triggered": 1}
    assert [event[0] for event in events] == ["acquire_scan", "compact"]


@pytest.mark.asyncio
async def test_run_periodic_once_skips_when_scan_lock_not_acquired(monkeypatch):
    from src.infra.memory import compaction_agent as compaction_module

    events: list[tuple[str, str]] = []
    backend = _Backend({"large": 51})
    agent = MemoryCompactionAgent(enabled=True, threshold=50)

    async def fake_acquire(instance_id: str, ttl_seconds: int) -> str:
        events.append(("acquire_scan", instance_id))
        return "not_acquired"

    async def fake_compact(_backend, user_id: str):
        events.append(("compact", user_id))
        return {"agent": "deepagent", "checked": 3}

    monkeypatch.setattr(compaction_module, "acquire_compaction_scan_lock", fake_acquire)
    agent.compact_user_memories = fake_compact  # type: ignore[method-assign]

    result = await agent.run_periodic_once(backend)

    assert result == {
        "checked": 0,
        "triggered": 0,
        "skipped": 1,
        "reason": "scan_lock_not_acquired",
    }
    assert [event[0] for event in events] == ["acquire_scan"]
