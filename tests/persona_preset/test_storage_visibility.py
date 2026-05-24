from src.infra.persona_preset.storage import PersonaPresetStorage


def test_admin_visibility_query_keeps_user_presets_owner_scoped() -> None:
    query = PersonaPresetStorage._build_visible_query(
        user_id="admin-1",
        include_admin=True,
    )

    assert query == {
        "$or": [
            {"scope": "user", "owner_user_id": "admin-1"},
            {"scope": "global"},
        ]
    }


def test_admin_visibility_query_combines_scope_filter_with_owner_visibility() -> None:
    query = PersonaPresetStorage._build_visible_query(
        user_id="admin-1",
        include_admin=True,
        scope="user",
    )

    assert query == {
        "$or": [
            {"scope": "user", "owner_user_id": "admin-1"},
            {"scope": "global"},
        ],
        "scope": "user",
    }


def test_visible_query_splits_multi_word_search_into_keyword_terms() -> None:
    query = PersonaPresetStorage._build_visible_query(
        user_id="user-1",
        q="素材 内容 创意 设计",
    )

    search_clause = query["$and"][0]["$or"]
    assert search_clause[0]["$or"][0]["name"]["$regex"] != "素材 内容 创意 设计"
    terms = {list(item["$or"][0].values())[0]["$regex"] for item in search_clause}
    assert terms == {"素材", "内容", "创意", "设计"}
