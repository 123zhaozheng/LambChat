from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes import project as project_route


class _FakeProjectStorage:
    def __init__(self, project) -> None:
        self.project = project
        self.deleted: list[tuple[str, str]] = []
        self.delete_result = True

    async def get_by_id(self, project_id: str, user_id: str):
        if self.project and self.project.id == project_id and self.project.user_id == user_id:
            return self.project
        return None

    async def delete(self, project_id: str, user_id: str) -> bool:
        self.deleted.append((project_id, user_id))
        return self.delete_result


class _FakeSessionStorage:
    def __init__(self) -> None:
        self.clear_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []
        self.project_session_ids: list[str] = []

    async def clear_project_id(self, project_id: str, user_id: str) -> int:
        self.clear_calls.append((project_id, user_id))
        return 1

    async def delete_by_project(self, project_id: str, user_id: str) -> int:
        self.delete_calls.append((project_id, user_id))
        return 1

    async def list_ids_by_project(self, project_id: str, user_id: str) -> list[str]:
        self.delete_calls.append((project_id, user_id))
        return self.project_session_ids


class _FakeSessionManager:
    def __init__(self) -> None:
        self.deleted_sessions: list[str] = []
        self.delete_results: dict[str, bool] = {}

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return self.delete_results.get(session_id, True)


class _FakeRevealedStorage:
    async def clear_project_id(self, project_id: str) -> int:
        return 1


class _FakeDeferredTools:
    def __init__(self) -> None:
        self.cleared_sessions: list[str] = []

    async def clear_discovered_tools(self, session_id: str) -> None:
        self.cleared_sessions.append(session_id)


@pytest.mark.asyncio
async def test_delete_project_clears_session_project_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="channel")
    project_storage = _FakeProjectStorage(project)
    session_storage = _FakeSessionStorage()

    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "SessionStorage", lambda: session_storage)
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _FakeRevealedStorage(),
    )

    response = await project_route.delete_project(
        "project-1",
        delete_sessions=False,
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {"status": "deleted"}
    assert session_storage.clear_calls == [("project-1", "user-1")]


@pytest.mark.asyncio
async def test_delete_project_with_delete_sessions_uses_full_session_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="channel")
    project_storage = _FakeProjectStorage(project)
    session_storage = _FakeSessionStorage()
    session_storage.project_session_ids = ["session-a", "session-b"]
    session_manager = _FakeSessionManager()
    deferred_tools = _FakeDeferredTools()

    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "SessionStorage", lambda: session_storage)
    monkeypatch.setattr(project_route, "SessionManager", lambda: session_manager)
    monkeypatch.setattr(
        "src.infra.tool.deferred_manager.clear_discovered_tools",
        deferred_tools.clear_discovered_tools,
    )
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _FakeRevealedStorage(),
    )

    response = await project_route.delete_project(
        "project-1",
        delete_sessions=True,
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {"status": "deleted"}
    assert session_storage.delete_calls == [("project-1", "user-1")]
    assert session_manager.deleted_sessions == ["session-a", "session-b"]
    assert deferred_tools.cleared_sessions == ["session-a", "session-b"]


@pytest.mark.asyncio
async def test_delete_project_with_delete_sessions_stops_when_session_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="channel")
    project_storage = _FakeProjectStorage(project)
    session_storage = _FakeSessionStorage()
    session_storage.project_session_ids = ["session-a", "session-b"]
    session_manager = _FakeSessionManager()
    session_manager.delete_results = {"session-a": False}

    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "SessionStorage", lambda: session_storage)
    monkeypatch.setattr(project_route, "SessionManager", lambda: session_manager)

    with pytest.raises(project_route.HTTPException) as exc_info:
        await project_route.delete_project(
            "project-1",
            delete_sessions=True,
            user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "删除项目内会话失败"
    assert session_manager.deleted_sessions == ["session-a"]
    assert project_storage.deleted == []
