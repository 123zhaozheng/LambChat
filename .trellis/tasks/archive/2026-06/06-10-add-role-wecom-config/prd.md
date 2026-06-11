# feat: 角色配置增加企业微信入口

## Goal

在角色配置体系中增加企业微信入口配置，包括后端存储、API 路由、前端 UI。

## Requirements

### 后端

* 新建 `role_wecom_config` MongoDB 集合，字段：
  - `role_id` (str, 唯一索引)
  - `aibotid` (str, 企业微信机器人 bot_id)
  - `secret` (str, 加密存储)
  - `stream_reply` (bool, 默认 true)
  - `send_thinking_message` (bool, 默认 true)
  - `segmented_reply` (bool, 默认 true)
  - `session_ttl_hours` (int, 默认 24)
  - `created_at` / `updated_at`
* 新建 Pydantic schema：`RoleWeComConfig`、`RoleWeComConfigCreate`、`RoleWeComConfigUpdate`
* 在 `AgentConfigStorage` 或新建存储类中增加 WeCom 配置 CRUD 方法
* 新建 API 路由 `/api/agent/config/roles/{role_id}/wecom`（GET/PUT/DELETE）
* 权限控制：需要 `manage_channels` 权限

### 前端

* 在 RolesPanel EditorSidebar 增加"企业微信入口" section
* 默认折叠，展开后显示配置项
* 配置项：aibotid、secret（敏感字段 mask）、stream_reply、send_thinking_message、segmented_reply、session_ttl_hours
* 风格保持现有前端风格
* 只对有 `manage_channels` 权限的用户显示配置区域
* 新建前端 API service 方法
* 新增 i18n key

## Acceptance Criteria

* [ ] GET `/api/agent/config/roles/{role_id}/wecom` 返回 WeCom 配置（或 404）
* [ ] PUT 创建/更新 WeCom 配置
* [ ] DELETE 删除 WeCom 配置
* [ ] 无 `manage_channels` 权限的用户无法配置
* [ ] 前端 EditorSidebar 显示折叠式 WeCom section
* [ ] 配置项可编辑保存
* [ ] secret 字段返回时 mask

## Technical Notes

* 参考 `role_models` 模式实现全链路
* 参考 `research/role-config-system.md` 获取角色配置体系详情
