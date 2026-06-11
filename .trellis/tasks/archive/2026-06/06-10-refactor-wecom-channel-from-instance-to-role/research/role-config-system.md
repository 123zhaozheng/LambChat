# Research: Role Config System

- **Query**: Understand the existing role/agent configuration system to determine where a "WeCom entry" config section should be added
- **Scope**: internal
- **Date**: 2026-06-10

## Findings

### Files Found

| File Path | Description |
|---|---|
| `src/infra/agent/config_storage.py` | AgentConfigStorage - MongoDB storage for role_agents, role_models, catalog config, user preferences |
| `src/api/routes/agent/config.py` | FastAPI routes for /api/agent/config (global, catalog, roles, models, user preference) |
| `src/api/routes/agent/__init__.py` | Agent listing and SSE streaming routes at /api/agents |
| `src/kernel/schemas/agent.py` | All agent config Pydantic schemas: AgentConfig, RoleAgentAssignment, RoleModelAssignment, etc. |
| `src/kernel/schemas/role.py` | Role schema with RoleLimits, permissions, allowed_agents |
| `src/kernel/schemas/channel.py` | Generic channel schemas: ChannelConfigCreate/Update/Response, ChannelType enum, ChannelMetadata |
| `src/kernel/schemas/wecom.py` | WeCom-specific schemas: WeComConfigBase, WeComConfigCreate/Update, WeComConfigResponse |
| `src/infra/role/storage.py` | RoleStorage - MongoDB CRUD for roles with Redis cache |
| `src/infra/role/manager.py` | RoleManager - thin business logic layer over RoleStorage |
| `src/infra/channel/channel_storage.py` | ChannelStorage - per-user channel configs in MongoDB `user_channel_configs` collection |
| `src/infra/channel/wecom/manager.py` | WeComChannelManager - manages multiple WeCom WS connections per user instance |
| `src/infra/channel/wecom/handler.py` | WeCom message handler, response collector, agent execution pipeline |
| `src/infra/channel/registry.py` | ChannelRegistry - auto-discovers channel types and managers |
| `frontend/src/components/panels/AgentPanel/AgentConfigPanel.tsx` | Main agent config panel with "global" and "roles" tabs |
| `frontend/src/components/panels/AgentPanel/tabs/RolesAgentTab.tsx` | Roles tab: select role, toggle agents per role |
| `frontend/src/components/panels/AgentPanel/tabs/GlobalAgentTab.tsx` | Global tab: enable/disable agents, edit icon/sort_order/labels |
| `frontend/src/components/panels/RolesPanel.tsx` | Full role CRUD panel (name, permissions, limits) with EditorSidebar |
| `frontend/src/services/api/agent_config.ts` | API service for agent config: getGlobalConfig, getRoleAgents, updateRoleAgents, getRoleModels, etc. |
| `frontend/src/services/api/agent.ts` | Agent list API with caching |
| `frontend/src/services/api/role.ts` | Role CRUD API |
| `frontend/src/types/agent.ts` | TypeScript types: AgentConfig, AgentCatalogConfig, RoleAgentAssignment, RoleModelAssignment |
| `frontend/src/types/auth.ts` | TypeScript types: Role, RoleLimits, Permission enum |
| `frontend/src/components/agent/agentCatalog.ts` | Agent display name/description resolution with i18n labels |
| `frontend/src/components/panels/channel/wecom/WeComPanel.tsx` | Current WeCom instance management panel (to be deleted) |
| `frontend/src/components/panels/channel/wecom/types.ts` | WeCom panel TypeScript types (to be deleted) |

### Code Patterns

#### 1. Role Config Data Model (Backend)

The **Role** schema (`src/kernel/schemas/role.py:71-82`) stores:
- `id`, `name`, `description`
- `permissions: List[Permission]` (directly on Role)
- `allowed_agents: List[str]` (directly on Role, not in separate collection)
- `limits: Optional[RoleLimits]` (max_channels, max_concurrent_chats, upload limits, etc.)
- `is_system: bool`, `created_at`, `updated_at`

The **RoleLimits** model uses `model_config = ConfigDict(extra="allow")` to allow future extensions.

Separately from the Role document, **AgentConfigStorage** (`src/infra/agent/config_storage.py`) manages:
- **role_agents** collection: `{role_id, role_name, allowed_agents: [str], updated_at}`
  - Accessed via `get_role_agents(role_id)`, `set_role_agents(role_id, role_name, agent_ids)`
  - Note: this duplicates the `allowed_agents` from Role -- the Role schema has its own `allowed_agents` field too
- **role_models** collection: `{role_id, role_name, allowed_models: [str], updated_at}`
  - Accessed via `get_role_models(role_id)`, `set_role_models(role_id, role_name, model_values)`
- **agent_catalog_config** collection: per-agent display metadata (name, description, icon, sort_order, labels, enabled)
- **user_agent_preferences** collection: per-user default agent

#### 2. Role Config API Routes

Mounted at `/api/agent/config` prefix:

| Method | Path | Purpose |
|---|---|---|
| GET | `/global` | Get global agent config |
| PUT | `/global` | Update global agent config |
| GET | `/catalog` | Get agent catalog (display metadata) |
| PUT | `/catalog` | Update agent catalog |
| GET | `/roles/{role_id}` | Get role's allowed agents |
| PUT | `/roles/{role_id}` | Set role's allowed agents |
| GET | `/roles/{role_id}/models` | Get role's allowed models |
| PUT | `/roles/{role_id}/models` | Set role's allowed models |
| GET | `/user/preference` | Get user's default agent |
| PUT | `/user/preference` | Set user's default agent |
| DELETE | `/user/preference` | Delete user's default agent |

**Pattern for adding a new role-level config section**: The `roles/{role_id}/models` route is a clear precedent. It was added as a sub-resource of the role config. A similar `roles/{role_id}/wecom` endpoint would follow this pattern.

#### 3. Frontend AgentConfigPanel Structure

`AgentConfigPanel.tsx` has two tabs:
- **"global" tab** (`GlobalAgentTab`): Enable/disable agents, edit catalog metadata (icon, sort_order, localized labels)
- **"roles" tab** (`RolesAgentTab`): Select a role via `RoleSelector`, then toggle which agents that role can access

The panel loads data in parallel:
1. `agentConfigApi.getCatalogConfig()` - all agent catalog entries
2. `roleApi.list()` - all roles
3. `agentApi.list()` - available agents
4. Per-role: `agentConfigApi.getRoleAgents(role.id)` - role-agent mappings

For the **RolesPanel** (separate component), the role editor uses `EditorSidebar` and has sections for:
- Name, description
- Max channels limit
- Concurrent chat limits
- Upload limits (collapsible)
- Permissions (grouped checkboxes)

**The WeCom entry config would most naturally fit into the RolesPanel's EditorSidebar**, alongside permissions and limits, as it's a role-level configuration. Alternatively, it could be a third tab in AgentConfigPanel, or a sub-section within the existing "roles" tab.

#### 4. Current WeCom Instance Architecture (to be replaced)

Currently WeCom is managed as independent "instances":
- **ChannelStorage** stores configs in `user_channel_configs` collection with `(user_id, channel_type, instance_id)` composite key
- Each WeCom instance has: `bot_id`, `secret`, `group_policy`, `stream_reply`, `send_thinking_message`, `segmented_reply`, `session_ttl_hours`, `websocket_url`, `enabled`, plus `agent_id`, `model_id`, `project_id`, `persona_preset_id`
- **WeComChannelManager** manages multiple WS connections keyed by `user_id:instance_id`
- Handler resolves `agent_id`, `model_id`, `project_id`, `persona_preset_id` from the instance config at message time
- Sessions belong to the instance creator, not the WeCom message sender

#### 5. Existing Pattern for Extending Role Configuration

The clearest pattern is **role_models** (`/api/agent/config/roles/{role_id}/models`):
1. New MongoDB collection (`role_models`) with `role_id` as unique index
2. New Pydantic schemas (`RoleModelAssignment`, `RoleModelAssignmentUpdate`)
3. New methods on `AgentConfigStorage` (`get_role_models`, `set_role_models`)
4. New API routes under `/api/agent/config/roles/{role_id}/models`
5. New frontend API methods in `agent_config.ts` (`getRoleModels`, `updateRoleModels`)
6. New frontend types in `agent.ts` (`RoleModelAssignment`)

This pattern can be replicated for WeCom entry config as a new sub-resource: `/api/agent/config/roles/{role_id}/wecom`.

Alternatively, the WeCom config could be embedded directly in the Role document (as `limits` is), since one role has at most one WeCom entry. The `RoleLimits` model already uses `extra="allow"` to permit future extensions, though a dedicated `wecom_config` field would be more explicit.

#### 6. Frontend API Services

`agent_config.ts` provides typed API calls to `/api/agent/config/*`:
- `getGlobalConfig()`, `updateGlobalConfig()`
- `getCatalogConfig()`, `updateCatalogConfig()`
- `getRoleAgents(roleId)`, `updateRoleAgents(roleId, allowedAgents)`
- `getRoleModels(roleId)`, `updateRoleModels(roleId, allowedModels)`
- `getUserPreference()`, `setUserPreference()`, `deleteUserPreference()`

All use `authFetch` with `API_BASE` prefix.

### Related Specs

- `.trellis/tasks/06-10-refactor-wecom-channel-from-instance-to-role/prd.md` - Full PRD with decisions, requirements, acceptance criteria

## Caveats / Not Found

1. **Dual `allowed_agents` storage**: The `Role` schema in `role.py` has an `allowed_agents` field directly on the document, but `AgentConfigStorage` also maintains a separate `role_agents` collection with the same data. The route `GET /api/agent/config/roles/{role_id}` reads from `AgentConfigStorage.get_role_agents()`, while the Role CRUD uses `RoleStorage`. This duplication may need to be resolved during the refactor.

2. **No existing "channel" or "entry point" pattern on roles**: There is currently no concept of a channel/entry point configuration attached to a role. The WeCom entry will be the first of its kind.

3. **Feishu channel deletion**: The PRD decisions note "Feishu channel entire deletion" -- the Feishu channel code should be removed as well. Feishu files exist at `src/infra/channel/feishu/` and share `ChannelStorage`.

4. **AgentModelPanel**: There appears to be a separate `AgentModelPanel` component (found in test references) for model configuration per agent/role. This is a parallel admin panel that could inform the WeCom config UI pattern.

5. **RoleLimits extensibility**: `RoleLimits` already has `extra="allow"`, which means WeCom config fields could theoretically be added there. However, this would mix channel configuration with rate limits, which is semantically wrong. A dedicated sub-document is cleaner.
