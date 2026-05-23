"""Tests for team storage."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.infra.team.storage import TeamStorage


def _make_fake_collection():
    """Build a fake Motor collection backed by an in-memory list."""
    store: list[dict] = []
    counter = {"value": 0}

    def _next_id():
        counter["value"] += 1
        return str(counter["value"])

    async def insert_one(doc: dict):
        doc = dict(doc)
        fake_id = MagicMock()
        fake_id.__str__ = lambda self: _next_id()
        # Use a deterministic id for test assertions
        from bson import ObjectId

        oid = ObjectId()
        doc["_id"] = oid
        store.append(doc)
        result = MagicMock()
        result.inserted_id = oid
        return result

    async def find_one(query: dict):
        filter_id = query.get("_id")
        owner = query.get("owner_user_id")
        for doc in store:
            if filter_id is not None and doc.get("_id") != filter_id:
                continue
            if owner is not None and doc.get("owner_user_id") != owner:
                continue
            return dict(doc)
        return None

    async def count_documents(query: dict):
        owner = query.get("owner_user_id")
        return sum(1 for d in store if d.get("owner_user_id") == owner)

    class _Cursor:
        def __init__(self, docs):
            self._docs = list(docs)

        def sort(self, *a, **kw):
            return self

        def skip(self, n):
            self._docs = self._docs[n:]
            return self

        def limit(self, n):
            self._docs = self._docs[:n]
            return self

        async def __aiter__(self):
            for doc in self._docs:
                yield doc

    def find(query: dict):
        owner = query.get("owner_user_id")
        matches = [dict(d) for d in store if d.get("owner_user_id") == owner]
        return _Cursor(matches)

    async def delete_one(query: dict):
        filter_id = query.get("_id")
        owner = query.get("owner_user_id")
        for i, doc in enumerate(store):
            if doc.get("_id") == filter_id and doc.get("owner_user_id") == owner:
                store.pop(i)
                result = MagicMock()
                result.deleted_count = 1
                return result
        result = MagicMock()
        result.deleted_count = 0
        return result

    async def insert_many(docs: list[dict]):
        inserted = []
        for doc in docs:
            doc = dict(doc)
            from bson import ObjectId

            oid = ObjectId()
            doc["_id"] = oid
            store.append(doc)
            inserted.append(oid)
        result = MagicMock()
        result.inserted_ids = inserted
        return result

    coll = MagicMock()
    coll.insert_one = insert_one
    coll.find_one = find_one
    coll.find = find
    coll.count_documents = count_documents
    coll.delete_one = delete_one
    coll.insert_many = insert_many
    return coll, store


@pytest.fixture
def storage():
    s = TeamStorage()
    coll, store = _make_fake_collection()
    s._collection = coll
    return s, store


@pytest.mark.asyncio
async def test_create_team(storage):
    s, store = storage
    team = await s.create_team(
        owner_user_id="user-1",
        name="Test Team",
        description="A test team",
        members=[
            {"persona_preset_id": "preset-1", "role_instructions": "Be helpful"},
        ],
    )
    assert team.name == "Test Team"
    assert team.owner_user_id == "user-1"
    assert len(team.members) == 1
    assert team.members[0].persona_preset_id == "preset-1"
    assert team.members[0].member_id.startswith("m-")
    assert team.visibility.value == "private"


@pytest.mark.asyncio
async def test_get_team_not_found(storage):
    s, store = storage
    result = await s.get_team("nonexistent-id", owner_user_id="user-1")
    assert result is None


@pytest.mark.asyncio
async def test_list_teams_paginated(storage):
    s, store = storage
    await s.create_team(owner_user_id="user-1", name="Team A")
    await s.create_team(owner_user_id="user-1", name="Team B")
    await s.create_team(owner_user_id="user-2", name="Team C")

    teams, total = await s.list_teams(owner_user_id="user-1", skip=0, limit=10)
    assert total == 2
    assert len(teams) == 2
    names = {t.name for t in teams}
    assert names == {"Team A", "Team B"}


@pytest.mark.asyncio
async def test_delete_team(storage):
    s, store = storage
    team = await s.create_team(owner_user_id="user-1", name="To Delete")
    deleted = await s.delete_team(team.id, owner_user_id="user-1")
    assert deleted is True
    result = await s.get_team(team.id, owner_user_id="user-1")
    assert result is None


@pytest.mark.asyncio
async def test_delete_team_wrong_owner(storage):
    s, store = storage
    team = await s.create_team(owner_user_id="user-1", name="Owned")
    deleted = await s.delete_team(team.id, owner_user_id="user-2")
    assert deleted is False


@pytest.mark.asyncio
async def test_clone_team(storage):
    s, store = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        members=[
            {"persona_preset_id": "preset-1"},
        ],
    )
    cloned = await s.clone_team(original.id, owner_user_id="user-1")
    assert cloned is not None
    assert cloned.name == "Original (copy)"
    assert cloned.id != original.id
    assert len(cloned.members) == 1
    assert cloned.members[0].member_id != original.members[0].member_id
