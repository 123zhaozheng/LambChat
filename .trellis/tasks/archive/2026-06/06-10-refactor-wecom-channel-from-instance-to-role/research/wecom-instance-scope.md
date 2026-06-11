# Research: WeCom Instance Model Scope

- **Query**: Full scope of current WeCom "instance" model code that needs to be refactored or deleted
- **Scope**: internal
- **Date**: 2026-06-10

## Findings

### Summary of Current "Instance" Model

The current WeCom channel follows an "instance" model where:
- Users create WeCom **instances** with a UUID `instance_id` stored in MongoDB
- Each instance is keyed by `(user_id, channel_type, instance_id)` in `ChannelStorage`
- `WeComChannelManager` tracks channels by `channel_key = f"{user_id}:{instance_id}"`
- Handler receives `instance_id` via metadata, looks up config from `ChannelStorage` to get agent_id/model_id/project_id/persona
- Frontend has dedicated `WeComPanel` / `WeComPanelForm` for instance CRUD
- API routes at `/api/channels/{channel_type}/{instance_id}` support full instance lifecycle

### Files Found

| File Path | Description | Classification |
|---|---|---|
| `src/kernel/schemas/wecom.py` | WeComConfig schema with `instance_id` field | REFACTOR |
| `src/kernel/schemas/channel.py` | ChannelType.WECOM enum, ChannelConfigCreate/Update/Response with `instance_id` | REFACTOR |
| `src/infra/channel/wecom/channel.py` | WeComChannel class, WS lifecycle, message handling | REFACTOR |
| `src/infra/channel/wecom/handler.py` | WeComResponseCollector, create_wecom_message_handler, instance_id-based config lookup | REFACTOR |
| `src/infra/channel/wecom/manager.py` | WeComChannelManager with instance_id-based channel_key, lease management | REFACTOR |
| `src/infra/channel/wecom/__init__.py` | Module exports | REFACTOR |
| `src/infra/channel/channel_storage.py` | ChannelStorage with instance_id-based MongoDB queries | DELETE (entire file) |
| `src/infra/channel/base.py` | BaseChannel._handle_message injects instance_id; UserChannelManager.reload_user(instance_id) | REFACTOR |
| `src/infra/channel/__init__.py` | Imports ChannelStorage, WeCom handler exports | REFACTOR |
| `src/infra/channel/registry.py` | Auto-discovers wecom module; registry stores channel/manager classes | REFACTOR (minor) |
| `src/infra/channel/manager.py` | ChannelCoordinator delegates to per-type managers | REFACTOR (minor) |
| `src/infra/channel/pubsub.py` | publish_channel_config_changed with channel_instance_id | REFACTOR |
| `src/api/routes/channels.py` | Full CRUD API: create/update/delete/get/list channel instances | DELETE (entire file, all instance CRUD) |
| `src/api/main.py` | Lifespan: starts/stops WeCom channels; includes channels router; init channel_storage indexes | REFACTOR |
| `src/api/routes/project.py` | Clears channel config project_id on project deletion | REFACTOR |
| `frontend/src/components/panels/channel/wecom/WeComPanel.tsx` | WeCom instance config panel (full CRUD UI) | DELETE |
| `frontend/src/components/panels/channel/wecom/WeComPanelForm.tsx` | WeCom form with instance-specific fields | DELETE |
| `frontend/src/components/panels/channel/wecom/constants.ts` | WECOM_DEFAULTS constant | DELETE |
| `frontend/src/components/panels/channel/wecom/types.ts` | WeComConfigResponse/Status/PanelProps types | DELETE |
| `frontend/src/components/pages/ChannelsPage.tsx` | Routes to WeComPanel for wecom channel type | REFACTOR |
| `frontend/src/components/panels/ChannelPanel.tsx` | Generic channel panel (fallback for unknown types) | REFACTOR |
| `frontend/src/types/channel.ts` | ChannelConfigResponse with instance_id, ChannelConfigCreate/Update | REFACTOR |
| `frontend/src/services/api/channel.ts` | channelApi CRUD (create/update/delete/get/getStatus/test) | DELETE (entire file) |
| `frontend/src/i18n/locales/en.json` | "wecom" section with instance-related keys | REFACTOR |
| `frontend/src/i18n/locales/zh.json` | "wecom" section with instance-related keys | REFACTOR |
| `tests/infra/channel/wecom/test_handler_interrupt.py` | WeCom handler interrupt tests using _FakeManager with instance_id | REFACTOR |
| `tests/infra/test_channel_storage_indexes.py` | ChannelStorage index tests | DELETE |
| `tests/api/routes/test_channel_routes.py` | Channel API route tests | DELETE |
| `tests/infra/test_channel_pubsub.py` | Channel config pub/sub tests | REFACTOR |

### Code Patterns

#### 1. instance_id as primary key throughout (DELETE pattern)

The `instance_id` UUID is generated on create (`ChannelStorage.create_config` line 138) and used everywhere:

- **MongoDB index**: `user_channel_instance_idx` on `(user_id, channel_type, instance_id)` -- unique compound index (`channel_storage.py:86-89`)
- **Channel key**: `WeComChannelManager._channel_key(user_id, instance_id)` returns `f"{user_id}:{instance_id}"` (`manager.py:255-256`)
- **Channel lookup**: `WeComChannelManager._find_channel(user_id, instance_id)` (`manager.py:382-404`)
- **Reload**: `WeComChannelManager.reload_user(user_id, instance_id)` (`manager.py:334-380`)
- **Send**: `WeComChannelManager.send_message(user_id, chat_id, content, instance_id)` (`manager.py:406-419`)
- **Distributed status**: `is_connected_distributed(user_id, instance_id)` (`manager.py:426-446`)
- **Handler metadata injection**: `BaseChannel._handle_message` injects `instance_id` from `config.instance_id` into metadata (`base.py:167-169`)
- **Handler config lookup**: `create_wecom_message_handler` reads `metadata.instance_id` to look up `ChannelStorage.get_config(user_id, ChannelType.WECOM, instance_id)` (`handler.py:842-864`)
- **WeComResponseCollector**: stores and uses `instance_id` for `_get_client()` (`handler.py:174-185, 555-561`)
- **Redis dedup**: `_mark_message_processed` uses `self.config.instance_id or self.config.user_id` as dedup value (`channel.py:851`)
- **API routes**: all endpoints use `instance_id` as path parameter (`channels.py:289, 401, 507, 556, 599`)

#### 2. WeComConfig schema fields (REFACTOR pattern)

Current `WeComConfigBase` fields (`wecom.py:19-38`):
- `instance_id: str` -- DELETE from schema (no longer instance-based)
- `bot_id: str` -- KEEP (maps to aibotid for WS connection)
- `secret: str` -- KEEP (WS auth)
- `group_policy: WeComGroupPolicy` -- KEEP (mention/open)
- `stream_reply: bool` -- KEEP
- `send_thinking_message: bool` -- KEEP
- `segmented_reply: bool` -- KEEP
- `session_ttl_hours: int` -- KEEP
- `websocket_url: str` -- KEEP
- `enabled: bool` -- KEEP (per-role toggle)

Current `WeComConfig` adds: `user_id`, `created_at`, `updated_at` -- will change to be role-owned, not user-owned.

Current `WeComConfigResponse` has: `user_id`, `bot_id`, `has_secret`, plus all behavior fields.

Current `WeComConfigUpdate` omits `instance_id` (only updatable config fields).

#### 3. WeComChannelManager start/stop/reload logic (REFACTOR pattern)

- **Startup** (`manager.py:96-110`): calls `_reconcile_enabled_configs()` which iterates `ChannelStorage.iter_enabled_configs(ChannelType.WECOM)`, checks distributed lease ownership, starts `WeComChannel` instances
- **Reconciliation** (`manager.py:130-189`): iterates all enabled configs from MongoDB, uses `_channel_key(user_id, config.instance_id)` to track channels, checks `_preferred_owner(bot_id, node_ids)` for distributed assignment
- **Reload** (`manager.py:334-380`): stops old channel by key, fetches new config from `ChannelStorage`, restarts
- **Lease management** (`manager.py:482-593`): Redis-based lease per `bot_id`, with refresh tasks; this pattern is role-based (bot_id -> role) rather than instance-based and can be adapted
- **_dict_to_config** (`manager.py:74-94`): converts storage dict to `WeComConfig`, resolves `instance_id` from dict or parameter

#### 4. Handler config resolution from instance (REFACTOR pattern)

In `handler.py:842-894`, the handler:
1. Reads `instance_id` from metadata
2. If present, calls `ChannelStorage.get_config(user_id, ChannelType.WECOM, instance_id)` 
3. Extracts: `agent_id`, `model_id`, `project_id`, `team_id`, `persona_preset_id`, `channel_name`, `stream_reply`, `send_thinking_message`, `segmented_reply`, `session_ttl_hours`
4. In the new model, these come from the role config directly (agent already has these), except for WeCom-specific behavioral settings which will be on the role's WeCom entry config.

#### 5. Frontend instance CRUD flow (DELETE pattern)

`ChannelsPage.tsx` renders:
1. Channel type list (cards with instance counts)
2. Instance list for a selected channel type (click to open sidebar)
3. Sidebar: routes to `WeComPanel` (for wecom) or `ChannelPanel` (generic fallback)

`WeComPanel.tsx`:
- Accepts `instanceId` prop
- On "new": shows empty form with `instanceName` field
- On existing: loads config via `channelApi.get("wecom", instanceId)`, populates form
- Save: `channelApi.create(...)` or `channelApi.update("wecom", instanceId, ...)`
- Delete: `channelApi.delete("wecom", instanceId)`
- Test: `channelApi.test("wecom", instanceId)`

All of this instance-centric UI will be replaced by a WeCom config section in the role/agent config panel.

#### 6. ChannelStorage as shared infrastructure (DELETE pattern)

`ChannelStorage` is a shared MongoDB-backed storage used by both Feishu and WeCom channels. With the PRD decision to delete Feishu entirely and refactor WeCom to role-based config, `ChannelStorage` becomes entirely unnecessary.

Key methods: `create_config`, `update_config`, `delete_config`, `get_config`, `list_user_configs`, `list_user_configs_by_type`, `iter_enabled_configs`, `get_response`, `get_status`, `clear_project_id`, `clear_config_project_id`.

All depend on `instance_id` as a primary key dimension alongside `user_id` and `channel_type`.

#### 7. Channel API routes (DELETE pattern)

`src/api/routes/channels.py` provides:
- `GET /api/channels/types` -- list channel type metadata
- `GET /api/channels/` -- list user's channel instances
- `GET /api/channels/{channel_type}` -- list instances by type
- `GET /api/channels/{channel_type}/{instance_id}` -- get instance
- `POST /api/channels/{channel_type}` -- create instance
- `PUT /api/channels/{channel_type}/{instance_id}` -- update instance
- `DELETE /api/channels/{channel_type}/{instance_id}` -- delete instance
- `GET /api/channels/{channel_type}/{instance_id}/status` -- get status
- `POST /api/channels/{channel_type}/{instance_id}/test` -- test connection
- `POST /api/channels/feishu/registrations` -- Feishu registration (will be deleted with Feishu)
- `GET /api/channels/feishu/registrations/{session_id}` -- poll registration
- `DELETE /api/channels/feishu/registrations/{session_id}` -- cancel registration

The entire router is instance-based. In the new model, channel config will be managed within the role config API, not as a separate channel CRUD API.

### Related Specs

- `.trellis/tasks/06-10-refactor-wecom-channel-from-instance-to-role/prd.md` -- task PRD with decisions and acceptance criteria

### Cross-references to Feishu (also being deleted per PRD decision 4)

The Feishu channel follows the same instance model. The following Feishu files will also be deleted but are out of scope for this research:
- `src/infra/channel/feishu/` (entire directory)
- `src/kernel/schemas/feishu.py`
- `frontend/src/components/panels/channel/feishu/`
- Feishu-specific API routes in channels.py

## Classification Summary

### DELETE (entire file/module)

| File | Reason |
|---|---|
| `src/infra/channel/channel_storage.py` | Instance-based MongoDB storage; no longer needed |
| `src/api/routes/channels.py` | Instance-based CRUD API; no longer needed |
| `frontend/src/components/panels/channel/wecom/WeComPanel.tsx` | Instance config panel; replaced by role config section |
| `frontend/src/components/panels/channel/wecom/WeComPanelForm.tsx` | Instance form; replaced by role config section |
| `frontend/src/components/panels/channel/wecom/constants.ts` | WeCom-specific constants; absorbed into role config |
| `frontend/src/components/panels/channel/wecom/types.ts` | WeCom instance types; replaced |
| `frontend/src/services/api/channel.ts` | Channel CRUD API client; no longer needed |
| `tests/infra/test_channel_storage_indexes.py` | Tests for deleted ChannelStorage |
| `tests/api/routes/test_channel_routes.py` | Tests for deleted channel API routes |

### REFACTOR (significant changes needed)

| File | What Changes |
|---|---|
| `src/kernel/schemas/wecom.py` | Remove `instance_id`; schema becomes role-owned config; add `aibotid` field |
| `src/kernel/schemas/channel.py` | Remove ChannelConfigCreate/Update/Response (instance schemas); keep ChannelType.WECOM; keep ChannelMetadata if still needed |
| `src/infra/channel/wecom/channel.py` | Remove `user_id` binding; use `agent_id` + `aibotid` for identity; remove instance_id from Redis dedup |
| `src/infra/channel/wecom/handler.py` | Route by aibotid->agent_id instead of instance_id->ChannelStorage; remove ChannelStorage lookup; remove instance_id from WeComResponseCollector |
| `src/infra/channel/wecom/manager.py` | Manage channels by aibotid instead of user_id:instance_id; remove ChannelStorage dependency; keep lease management per bot_id |
| `src/infra/channel/wecom/__init__.py` | Update exports |
| `src/infra/channel/base.py` | Remove instance_id injection from `_handle_message`; simplify `reload_user` signature; simplify `is_connected` |
| `src/infra/channel/__init__.py` | Remove ChannelStorage import; update WeCom exports |
| `src/infra/channel/pubsub.py` | Remove channel_instance_id from pub/sub payload; adapt to role-based config changes |
| `src/api/main.py` | Remove `_init_channel_storage` from startup; remove channels router; adapt WeCom startup to role-based |
| `src/api/routes/project.py` | Remove ChannelStorage.clear_project_id call |
| `frontend/src/components/pages/ChannelsPage.tsx` | Remove WeComPanel routing; remove instance list for WeCom; may keep as simplified channel status view |
| `frontend/src/components/panels/ChannelPanel.tsx` | Remove instance-based rendering if channel type system is simplified |
| `frontend/src/types/channel.ts` | Remove instance_id from ChannelConfigResponse; remove ChannelConfigCreate/Update or simplify |
| `frontend/src/i18n/locales/en.json` | Remove instance-related WeCom keys; add role-config WeCom keys |
| `frontend/src/i18n/locales/zh.json` | Same as en.json |
| `tests/infra/channel/wecom/test_handler_interrupt.py` | Remove instance_id from fakes; adapt to role-based routing |
| `tests/infra/test_channel_pubsub.py` | Adapt to role-based config changes |
| `src/infra/channel/registry.py` | May need to adapt if channel type system changes |
| `src/infra/channel/manager.py` | May simplify if channel coordination changes |

### KEEP (stays mostly as-is)

| File | Reason |
|---|---|
| `src/infra/channel/wecom/channel.py` (WS lifecycle, message handlers, send/reply/stream methods) | Core WeCom SDK integration logic is channel-type-specific, not instance-specific; only identity binding changes |
| `src/infra/channel/wecom/handler.py` (streaming, segmentation, thinking, /new, event processing) | WeCom-specific behavior logic stays; only config resolution changes |
| `src/infra/channel/wecom/manager.py` (lease management, rebalance, preferred_owner) | Distributed coordination pattern is sound; only key scheme changes |

## Caveats / Not Found

1. **Agent config storage**: The PRD mentions `AgentConfigStorage` as the target for storing WeCom entry config on roles. The exact schema and API for adding WeCom config to agent/role config was not researched here -- see the separate `role-config-system.md` research file.
2. **Migration path**: No research on how to migrate existing MongoDB `user_channel_configs` data to the new role-based storage. This may need a one-time migration script.
3. **Frontend role config panel**: The specific UI for WeCom config within the role/agent config panel was not researched -- needs design work.
4. **`ChannelType` enum**: The PRD has an open question about whether `ChannelType` enum and the entire generic channel framework survives. If only WeCom remains (Feishu deleted), the generic framework may be over-engineered.
5. **`ChannelPanel.tsx`**: This generic panel is currently used as fallback for unknown channel types. If the channel type system is simplified, this may become unnecessary.
6. **Startup sequence**: `main.py` calls `ChannelStorage().ensure_indexes_if_needed()` at startup. This will need to be removed or replaced.
