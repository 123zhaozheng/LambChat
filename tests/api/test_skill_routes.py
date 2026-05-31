from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.routes import skill as skill_route
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["skill:read"],
    )


class _FakeUserDoc:
    metadata = {
        "disabled_skills": ["archived"],
        "pinned_skill_names": ["planner"],
        "favorite_skill_names": ["writer"],
    }


class _FakeUserStorage:
    async def get_by_id(self, user_id: str):
        assert user_id == "user-1"
        return _FakeUserDoc()


class _ChunkedUpload:
    def __init__(
        self,
        *,
        filename: str,
        data: bytes,
        chunk_size: int = 64 * 1024,
        content_type: str | None = None,
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self._data = data
        self._chunk_size = chunk_size
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._data):
            return b""
        if size is None or size < 0:
            size = len(self._data) - self._offset
        size = min(size, self._chunk_size)
        start = self._offset
        self._offset = min(len(self._data), self._offset + size)
        return self._data[start : self._offset]


@pytest.mark.asyncio
async def test_list_user_skills_returns_paginated_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def list_user_skills(
            self,
            user_id: str,
            skip: int = 0,
            limit: int = 100,
            disabled_skills=None,
            pinned_skill_names=None,
            favorite_skill_names=None,
            q: str | None = None,
            tags=None,
        ):
            assert user_id == "user-1"
            assert skip == 20
            assert limit == 10
            assert disabled_skills == ["archived"]
            assert pinned_skill_names == ["planner"]
            assert favorite_skill_names == ["writer"]
            assert q == "plan"
            assert tags == ["planning"]
            return [
                {
                    "skill_name": "planner",
                    "enabled": True,
                    "file_count": 1,
                    "file_paths": ["SKILL.md"],
                    "installed_from": "manual",
                    "published_marketplace_name": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                    "is_pinned": True,
                    "is_favorite": False,
                }
            ]

        async def count_user_skills(self, user_id: str, q: str | None = None, tags=None):
            assert user_id == "user-1"
            assert q == "plan"
            assert tags == ["planning"]
            return 37

        async def count_disabled_user_skills(
            self,
            user_id: str,
            disabled_skills,
            q: str | None = None,
            tags=None,
        ):
            assert user_id == "user-1"
            assert disabled_skills == ["archived"]
            assert q == "plan"
            assert tags == ["planning"]
            return 0

        async def list_user_skill_tags(self, user_id: str):
            assert user_id == "user-1"
            return ["planning"]

        async def batch_get_skill_md_contents(self, skill_names, user_id: str):
            assert skill_names == ["planner"]
            assert user_id == "user-1"
            return {"planner": "---\nname: planner\ndescription: Plan work\ntags:\n- planning\n---"}

    class _FakeMarketplace:
        async def get_user_published_skills(self, user_id: str):
            assert user_id == "user-1"
            return {}

    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[skill_route.get_marketplace_storage] = lambda: _FakeMarketplace()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/skills/?skip=20&limit=10&q=plan&tags=planning")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 37
    assert payload["skip"] == 20
    assert payload["limit"] == 10
    assert payload["enabled_count"] == 37
    assert payload["available_tags"] == ["planning"]
    assert [skill["skill_name"] for skill in payload["skills"]] == ["planner"]
    assert payload["skills"][0]["is_pinned"] is True
    assert payload["skills"][0]["is_favorite"] is False


@pytest.mark.asyncio
async def test_preview_zip_rejects_oversized_upload_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StorageShouldNotBeCalled:
        async def list_user_skills(self, user_id: str):
            raise AssertionError("storage should not be called for oversized uploads")

    monkeypatch.setattr(skill_route.settings, "S3_ENABLED", False, raising=False)
    monkeypatch.setattr(skill_route.settings, "FILE_UPLOAD_MAX_SIZE_DOCUMENT", 1, raising=False)
    monkeypatch.setattr(
        skill_route,
        "_parse_zip_skills",
        lambda _content: (_ for _ in ()).throw(
            AssertionError("oversized upload should not be parsed")
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await skill_route.preview_zip_skills(
            file=_ChunkedUpload(filename="skills.zip", data=b"x" * (1024 * 1024 + 1)),
            user=_fake_user(),
            storage=_StorageShouldNotBeCalled(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Failed to read file content"


def test_skill_upload_size_treats_string_false_as_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_route.settings, "S3_ENABLED", "false", raising=False)
    monkeypatch.setattr(skill_route.settings, "S3_MAX_FILE_SIZE", 99 * 1024 * 1024, raising=False)
    monkeypatch.setattr(skill_route.settings, "FILE_UPLOAD_MAX_SIZE_DOCUMENT", 1, raising=False)

    assert skill_route._get_skill_upload_max_size() == (1024 * 1024, 1)


@pytest.mark.asyncio
async def test_update_skill_preference_returns_updated_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def list_skill_file_paths(self, skill_name: str, user_id: str):
            assert skill_name == "planner"
            assert user_id == "user-1"
            return ["SKILL.md"]

        async def update_user_preference(self, *, user_id: str, skill_name: str, update):
            assert user_id == "user-1"
            assert skill_name == "planner"
            assert update == {"is_favorite": True, "is_pinned": None}
            return {"is_favorite": True, "is_pinned": False}

    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/api/skills/planner/preference",
            json={"is_favorite": True},
        )

    assert response.status_code == 200
    assert response.json() == {
        "skill_name": "planner",
        "is_favorite": True,
        "is_pinned": False,
    }
