# Research: Feishu Deletion Scope

- **Query**: Full scope of Feishu channel code that needs to be deleted — all files, imports, references, tests, configs, schemas, frontend components, i18n keys, constants/enums
- **Scope**: Internal
- **Date**: 2026-06-10

## Findings

### 1. Backend: Feishu-Specific Files (TO DELETE ENTIRELY)

| File Path | Description |
|---|---|
| `src/infra/channel/feishu/__init__.py` | Module init — exports FeishuChannel, FeishuChannelManager, FeishuStorage, etc. |
| `src/infra/channel/feishu/channel.py` | FeishuChannel class — WS long-connection, lark-oapi SDK, dedupe, message handling |
| `src/infra/channel/feishu/handler.py` | FeishuResponseCollector, create_feishu_message_handler, execute_feishu_agent, setup_feishu_handler |
| `src/infra/channel/feishu/handler_helpers.py` | Helper functions for feishu handler (download, session link, tool media extraction) |
| `src/infra/channel/feishu/manager.py` | FeishuChannelManager — distributed lease, rebalance, per-user bot management |
| `src/infra/channel/feishu/markdown.py` | FeishuMarkdownAdapter — markdown-to-Feishu-card conversion |
| `src/infra/channel/feishu/registration.py` | One-click Feishu app registration (lark-oapi register_app) |
| `src/infra/channel/feishu/sender.py` | FeishuSenderMixin — combines sender_base, sender_messages, sender_files |
| `src/infra/channel/feishu/sender_base.py` | Base send logic (lark API client construction) |
| `src/infra/channel/feishu/sender_files.py` | File upload/send via Feishu API |
| `src/infra/channel/feishu/sender_messages.py` | Message/card send via Feishu API |
| `src/infra/channel/feishu/state.py` | ConnectionState enum (DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING) |
| `src/infra/channel/feishu/storage.py` | FeishuStorage — MongoDB config storage (legacy, pre-generic ChannelStorage) |
| `src/infra/channel/feishu/utils.py` | Message parsing utilities (extract_post_content, extract_share_card_content, MSG_TYPE_MAP) |
| `src/kernel/schemas/feishu.py` | FeishuConfigBase, FeishuConfigCreate, FeishuConfigUpdate, FeishuConfig, FeishuConfigResponse, FeishuConfigStatus, FeishuGroupPolicy, DEFAULT_AUDIO_TRANSCRIBE_PROMPT |

### 2. Backend: Test Files (TO DELETE ENTIRELY)

| File Path | Description |
|---|---|
| `tests/infra/test_feishu_storage.py` | FeishuStorage tests |
| `tests/infra/test_feishu_sender.py` | Feishu sender tests |
| `tests/infra/test_feishu_manager_leases.py` | FeishuChannelManager lease tests |
| `tests/infra/test_feishu_registration.py` | Feishu registration tests |
| `tests/infra/test_feishu_handler_executor.py` | Feishu handler/executor tests |
| `tests/infra/test_feishu_channel_dedupe.py` | Feishu message deduplication tests |
| `tests/kernel/config/test_feishu_setting_definitions.py` | FEISHU_UPLOAD_BYTES_MAX_SIZE setting test |

### 3. Frontend: Feishu-Specific Files (TO DELETE ENTIRELY)

| File Path | Description |
|---|---|
| `frontend/src/components/panels/channel/feishu/FeishuPanel.tsx` | Feishu panel component — full CRUD with QR registration |
| `frontend/src/components/panels/channel/feishu/FeishuPanelForm.tsx` | Feishu form component — credentials, behavior settings, emoji picker |
| `frontend/src/components/panels/channel/feishu/types.ts` | FeishuConfigResponse, FeishuConfigStatus, FeishuPanelProps types |
| `frontend/src/components/panels/channel/feishu/constants.ts` | PREDEFINED_EMOJIS, DEFAULT_AUDIO_TRANSCRIBE_PROMPT |
| `frontend/src/components/panels/channel/feishu/__tests__/FeishuPanelRegistrationSource.test.ts` | Feishu panel registration test |

### 4. Shared Backend Code: Feishu References to Remove/Edit

| File Path | Line(s) | What to Change |
|---|---|---|
| `src/kernel/schemas/channel.py` | 18 | `FEISHU = "feishu"` in `ChannelType` enum — remove this member |
| `src/infra/channel/__init__.py` | 9-15, 43-48 | Imports of FeishuStorage, FeishuResponseCollector, create_feishu_message_handler, execute_feishu_agent, setup_feishu_handler from feishu module; corresponding `__all__` entries |
| `src/api/routes/channels.py` | 123-164 | Three Feishu registration endpoints: `POST /feishu/registrations`, `GET /feishu/registrations/{session_id}`, `DELETE /feishu/registrations/{session_id}` |
| `src/api/main.py` | 90, 274-283, 476-489, 528 | `_LIFESPAN_BACKGROUND_TASK_NAMES` includes `"feishu_task"`; `_stop_feishu_channels_for_shutdown`; `_start_feishu` in lifespan; shutdown call to `_stop_feishu_channels_for_shutdown` |
| `src/kernel/config/definitions.py` | 274-281 | `FEISHU_UPLOAD_BYTES_MAX_SIZE` setting definition in `SettingCategory.FILE_UPLOAD` subcategory `"feishu"` |
| `src/infra/folder/storage.py` | 173 | Comment mentioning "Feishu" for auto-create project — update comment |
| `src/infra/channel/wecom/handler.py` | 449-503, 1143 | Imports from `src.infra.channel.feishu.handler_helpers` — `FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE`, etc. These are **shared constants** that WeCom reuses from Feishu. Must be moved before deleting Feishu. |
| `src/infra/channel/wecom/channel.py` | 6, 16, 877 | Imports `ConnectionState` from `src.infra.channel.feishu.state` and comments about Feishu. **Shared dependency** — ConnectionState must be moved before deleting Feishu. |

### 5. Shared Frontend Code: Feishu References to Remove/Edit

| File Path | Line(s) | What to Change |
|---|---|---|
| `frontend/src/types/channel.ts` | 6 | `"feishu"` in `ChannelType` union — remove this option |
| `frontend/src/services/api/channel.ts` | 18-26, 143-170 | `FeishuRegistrationStatus` interface; `startFeishuRegistration()`, `getFeishuRegistration()`, `cancelFeishuRegistration()` methods |
| `frontend/src/components/pages/ChannelsPage.tsx` | 15, 34, 148-165 | Import of `FeishuPanel`; `"feishu"` in `CHANNEL_ICONS` map; conditional rendering of `<FeishuPanel>` when `selectedChannel === "feishu"` |
| `frontend/src/components/landing/data.ts` | 110 | `Feishu/Lark` label in TECH_STACK array |

### 6. i18n Keys: Feishu Sections to Remove

Each of these locale files has a top-level `"feishu"` key with ~80+ translation entries (app credentials, emoji labels, setup guide, registration UI, etc.):
- `frontend/src/i18n/locales/en.json` (lines 922-1001+) — `"feishu"` key block
- `frontend/src/i18n/locales/zh.json` (line 922+) — `"feishu"` key block
- `frontend/src/i18n/locales/ja.json` (line 922+) — `"feishu"` key block
- `frontend/src/i18n/locales/ko.json` (line 922+) — `"feishu"` key block
- `frontend/src/i18n/locales/ru.json` (line 922+) — `"feishu"` key block

Also in landing/hero sections:
- All 5 locale files: `"channelsIntegrationsDesc"` mentions Feishu/Lark
- All 5 locale files: `"heroDescription"` mentions Feishu/Lark

### 7. Shared Test Code: Feishu References to Remove/Edit

| File Path | Line(s) | What to Change |
|---|---|---|
| `tests/infra/test_channel_storage_indexes.py` | 9, 97, 162, 165, 181, 184, 232, 245-246, 249, 256 | Uses `FeishuStorage`, `ChannelType.FEISHU`, `FEISHU_CONFIG_LIST_LIMIT` — must switch to WeCom or generic |
| `tests/infra/test_channel_pubsub.py` | 103, 127, 139 | Uses `"feishu"` as channel_type in pubsub tests |
| `tests/api/test_startup_warmups.py` | 192-216, 255-256 | Tests `_stop_feishu_channels_for_shutdown` and checks `"feishu_task"` in background task list |
| `tests/api/routes/test_channel_routes.py` | 9, 96, 240-243, 269, 290-293, 313-316, 339-342, 359, 364, 396, 416, 435, 460, 484, 510, 521-532 | Extensive use of `ChannelType.FEISHU`, `feishu_registration`, Feishu registration endpoints |

### 8. Registry: Auto-Discovery (No Direct Edit Needed)

`src/infra/channel/registry.py` auto-discovers channel modules by scanning the `src/infra/channel/` package directory. Once the `feishu/` directory is deleted, Feishu will no longer be discovered. No direct code change needed in the registry itself.

### 9. Build Artifact

| File Path | Description |
|---|---|
| `frontend/tsconfig.tsbuildinfo` | Contains cached file paths referencing feishu components — will be regenerated on next build |
| `src/infra/channel/feishu/__pycache__/` | All `.pyc` files — will be cleaned up when source is deleted |

### 10. Documentation References (Lower Priority)

| File Path | Line(s) | Description |
|---|---|---|
| `README.md` | 132 | Mentions "Feishu integration" in feature list |
| `CHANGELOG.md` | 11, 15, 29, 65 | Multiple Feishu-related changelog entries |

## Critical Shared Dependencies (Must Move Before Deleting Feishu)

1. **`ConnectionState` enum** (from `src/infra/channel/feishu/state.py`) — imported by `src/infra/channel/wecom/channel.py` (line 16). This must be moved to a shared location (e.g., `src/infra/channel/base.py` or `src/kernel/schemas/channel.py`) before the Feishu module is deleted.

2. **`FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE` and related download constants** (from `src/infra/channel/feishu/handler_helpers.py`) — imported by `src/infra/channel/wecom/handler.py` (lines 449-450, 503, 1143). These constants must be moved to WeCom's own module or a shared location before Feishu deletion.

3. **`_download_storage_object_to_file` function** (from `src/infra/channel/feishu/handler_helpers.py`) — used by `src/infra/channel/wecom/handler.py`. Must be copied/moved.

## Caveats / Not Found

- No `.env` or `.env.example` files were found with Feishu-specific configuration entries (settings come from MongoDB-based settings system).
- The `ConnectionState` enum currently lives inside `feishu/state.py` but is used by WeCom — this is a shared dependency that must be relocated.
- The download helpers in `feishu/handler_helpers.py` are imported by WeCom handler — these must be relocated.
- MongoDB may still contain `feishu`-typed documents in `user_channel_configs` collection — these are data-level, not code-level, and will just be inert after Feishu code is removed.
- Redis keys with `feishu:` prefix (lease, processed message dedup) will become orphaned but harmless.
