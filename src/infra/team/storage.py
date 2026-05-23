"""Team storage."""

import uuid
from typing import Any, Optional

from bson import ObjectId

from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.team import (
    TeamMemberResponse,
    TeamResponse,
    TeamVisibility,
)


class TeamStorage:
    """MongoDB storage for teams."""

    def __init__(self) -> None:
        self._collection = None

    @property
    def collection(self):
        """Lazy MongoDB collection."""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["teams"]
        return self._collection

    # ── Document conversion ──

    @staticmethod
    def _doc_to_response(doc: dict[str, Any]) -> TeamResponse:
        """Convert a MongoDB document to a TeamResponse."""
        result = dict(doc)
        if "_id" in result:
            result["id"] = str(result.pop("_id"))

        members_raw = result.pop("members", [])
        members = []
        for m in members_raw:
            members.append(
                TeamMemberResponse(
                    member_id=m.get("member_id", ""),
                    persona_preset_id=m.get("persona_preset_id", ""),
                    role_name=m.get("role_name", ""),
                    role_avatar=m.get("role_avatar"),
                    role_tags=m.get("role_tags", []),
                    role_instructions=m.get("role_instructions", ""),
                    position=m.get("position", 0),
                    enabled=m.get("enabled", True),
                )
            )
        result["members"] = members
        result.setdefault("description", "")
        result.setdefault("default_member_id", None)
        result.setdefault("team_instructions", "")
        result.setdefault("visibility", TeamVisibility.PRIVATE.value)
        return TeamResponse(**result)

    # ── CRUD ──

    async def create_team(
        self,
        *,
        owner_user_id: str,
        name: str,
        description: str = "",
        members: list[dict[str, Any]] | None = None,
        default_member_id: str | None = None,
        team_instructions: str = "",
    ) -> TeamResponse:
        """Create a new team."""
        now = utc_now()
        members_docs = []
        for m in members or []:
            members_docs.append(
                {
                    "member_id": f"m-{uuid.uuid4().hex[:12]}",
                    "persona_preset_id": m.get("persona_preset_id", ""),
                    "role_name": m.get("role_name", ""),
                    "role_avatar": m.get("role_avatar"),
                    "role_tags": m.get("role_tags", []),
                    "role_instructions": m.get("role_instructions", ""),
                    "position": m.get("position", 0),
                    "enabled": m.get("enabled", True),
                }
            )
        doc: dict[str, Any] = {
            "owner_user_id": owner_user_id,
            "name": name,
            "description": description,
            "members": members_docs,
            "default_member_id": default_member_id,
            "team_instructions": team_instructions,
            "visibility": TeamVisibility.PRIVATE.value,
            "created_at": now,
            "updated_at": now,
        }
        insert_result = await self.collection.insert_one(doc)
        doc["_id"] = insert_result.inserted_id
        return self._doc_to_response(doc)

    async def get_team(
        self,
        team_id: str,
        *,
        owner_user_id: str,
    ) -> Optional[TeamResponse]:
        """Get a team by ID, scoped to owner."""
        try:
            query_id = ObjectId(team_id)
        except Exception:
            return None
        doc = await self.collection.find_one({"_id": query_id, "owner_user_id": owner_user_id})
        if not doc:
            return None
        return self._doc_to_response(doc)

    async def list_teams(
        self,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[TeamResponse], int]:
        """List teams for an owner, paginated. Returns (teams, total)."""
        query: dict[str, Any] = {"owner_user_id": owner_user_id}
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        docs = [doc async for doc in cursor]
        teams = [self._doc_to_response(doc) for doc in docs]
        return teams, total

    async def update_team(
        self,
        team_id: str,
        *,
        owner_user_id: str,
        update: dict[str, Any],
    ) -> Optional[TeamResponse]:
        """Update a team by ID, scoped to owner."""
        try:
            query_id = ObjectId(team_id)
        except Exception:
            return None

        update = {k: v for k, v in update.items() if v is not None}
        update["updated_at"] = utc_now()

        # Full replacement semantics for members: regenerate member_ids
        if "members" in update:
            new_members = []
            for m in update["members"]:
                new_members.append(
                    {
                        "member_id": f"m-{uuid.uuid4().hex[:12]}",
                        "persona_preset_id": m.get("persona_preset_id", ""),
                        "role_name": m.get("role_name", ""),
                        "role_avatar": m.get("role_avatar"),
                        "role_tags": m.get("role_tags", []),
                        "role_instructions": m.get("role_instructions", ""),
                        "position": m.get("position", 0),
                        "enabled": m.get("enabled", True),
                    }
                )
            update["members"] = new_members

        if not update:
            return await self.get_team(team_id, owner_user_id=owner_user_id)

        doc = await self.collection.find_one_and_update(
            {"_id": query_id, "owner_user_id": owner_user_id},
            {"$set": update},
            return_document=True,
        )
        if not doc:
            return None
        return self._doc_to_response(doc)

    async def delete_team(
        self,
        team_id: str,
        *,
        owner_user_id: str,
    ) -> bool:
        """Delete a team by ID, scoped to owner."""
        try:
            query_id = ObjectId(team_id)
        except Exception:
            return False
        result = await self.collection.delete_one({"_id": query_id, "owner_user_id": owner_user_id})
        return result.deleted_count > 0

    async def clone_team(
        self,
        team_id: str,
        *,
        owner_user_id: str,
        new_name: str | None = None,
    ) -> Optional[TeamResponse]:
        """Clone a team for the same owner."""
        original = await self.get_team(team_id, owner_user_id=owner_user_id)
        if not original:
            return None

        # Serialize members back to dicts with new member_ids
        members_data = []
        for m in original.members:
            members_data.append(
                {
                    "persona_preset_id": m.persona_preset_id,
                    "role_name": m.role_name,
                    "role_avatar": m.role_avatar,
                    "role_tags": m.role_tags,
                    "role_instructions": m.role_instructions,
                    "position": m.position,
                    "enabled": m.enabled,
                }
            )

        return await self.create_team(
            owner_user_id=owner_user_id,
            name=new_name or f"{original.name} (copy)",
            description=original.description,
            members=members_data,
            default_member_id=original.default_member_id,
            team_instructions=original.team_instructions,
        )
