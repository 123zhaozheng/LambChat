# refactor: WeCom 从"渠道实例"模型重构为"角色入口"模型

## Goal

将企业微信从独立的"渠道实例"模型彻底重构为角色（agent）的一个可选入口通道。删除整个通用渠道框架（ChannelStorage、ChannelType、ChannelCoordinator、ChannelPanel）和飞书渠道，只将企业微信 SDK 的对接逻辑搬运到角色智能体体系下。员工在企业微信和角色对话时，session 自然归属于该员工，所有权限逻辑与 Web 端完全一致。

## What I Already Know

### 当前架构（全部删除）

* **通用渠道框架**：ChannelStorage、ChannelType 枚举、ChannelCoordinator、ChannelPanel、channel API routes
* **飞书渠道**：15 个后端文件 + 6 个前端文件 + 7 个测试文件，全部删除
* **WeCom 实例模型**：WeComPanel / WeComPanelForm、instance_id 体系、WeComConfig schema、channel_storage WeCom 存储
* session 归属实例创建者，不是发送者

### 目标架构（要建成的）

* 企业微信是角色的可选入口，不是独立对象
* 管理员在角色配置页增加"企业微信"配置区域（可配置可不配）
* `role_wecom_config` 集合（参考 `role_models` 模式），存 aibotid、corpid、secret、stream_reply 等
* `/api/agent/config/roles/{role_id}/wecom` API 路由
* 前端 RolesPanel EditorSidebar 增加 WeCom 配置 section
* 员工在企业微信和某个角色对话时，session 归 sender_id，和 Web 端完全一致
* 角色本身已有的 agent_id、model_id、project_id、persona 配置直接复用

### 企业微信 SDK 对接逻辑（搬运保留）

* WS 连接管理（WeComChannel → 重命名为 WeComBot 或类似）
* 消息收发（text/image/file/voice/video/mixed）
* 流式回复（WeComResponseCollector）
* 分段回复
* thinking placeholder
* cancel-then-new 中断处理
* session TTL
* 媒体文件下载/上传

### 共享依赖（飞书删除前需迁移）

1. `ConnectionState` enum — 当前在 `src/infra/channel/feishu/state.py`，WeCom 在用 → 迁移到 WeCom 模块内
2. `_download_storage_object_to_file` — 当前在 `src/infra/channel/feishu/handler_helpers.py`，WeCom handler 在用 → 迁移到 WeCom 模块内

### 现有角色配置体系

* `AgentConfigStorage` 管理 role_agents / role_models 配置（独立 MongoDB collection）
* `role_models` 模式是最佳参考：集合 + Pydantic schema + API routes + 前端 API + TypeScript types
* 前端 RolesPanel EditorSidebar 有 permissions、limits、upload settings 等 section
* RBAC 权限体系

## Assumptions

* 一个角色最多连接一个企业微信机器人（aibotid:agent_id = 1:1）
* 每个 aibotid 需要独立 WS 连接（企业微信 SDK 机制）
* 多个角色可以共享同一个 corpid，但用不同 aibotid
* 不做旧 session 数据迁移

## Decisions (resolved during grill-me)

1. **aibotid → agent_id 映射存角色配置里** — 启动时扫一遍建内存 dict，O(1) 查询
2. **WS 连接按 aibotid 1:1** — 一个 aibotid 一条 WS 连接，对应一个角色
3. **WeComBot 不再绑定 user_id** — 改为 agent_id + aibotid 定位
4. **飞书渠道整个删除** — 不保留任何飞书代码
5. **通用渠道框架整个删除** — ChannelStorage/ChannelType/ChannelCoordinator/ChannelPanel 全删
6. **WeCom 实例模型整个删除** — 只搬运 SDK 对接逻辑到角色体系
7. **严格删除旧代码** — 该删的删，不留垃圾
8. **role_models 模式复用** — 新建 role_wecom_config 集合，走完整链路

## Open Questions

* 前端角色配置页的 WeCom 区域具体长什么样？
* WeComConfig 精简后保留哪些字段？
* WeComChannelManager 的启动/停止逻辑如何适配？改为按角色启动？
* 飞书的 `_on_feedback_event` / template_card 功能是否在新模型中保留？

## Requirements

### 删除

* 删除整个通用渠道框架：ChannelStorage、ChannelType、ChannelCoordinator、BaseChannel、ChannelPanel、channel API routes
* 删除整个飞书渠道：所有 feishu 文件、测试、前端组件、i18n key
* 删除 WeCom 实例模型：WeComPanel / WeComPanelForm、instance_id 体系、channel_storage WeCom 存储、WeComConfig schema
* 迁移共享依赖：ConnectionState、_download_storage_object_to_file

### 新建

* `role_wecom_config` MongoDB 集合 + Pydantic schema
* `/api/agent/config/roles/{role_id}/wecom` API 路由（GET/PUT/DELETE）
* 前端 RolesPanel EditorSidebar WeCom 配置 section
* WeCom Bot 管理器：启动时加载角色 WeCom 配置，建 aibotid→agent_id 映射，按 aibotid 建 WS 连接
* WeCom handler：收到消息按 aibotid 路由到角色，session 归 sender_id

### 保留（搬运）

* WeCom SDK 对接逻辑：WS 连接、消息收发、流式回复、分段、thinking、cancel-new、TTL、媒体下载

## Acceptance Criteria

* [ ] 角色配置中可以开启/配置企业微信入口（aibotid、corpid、secret 等）
* [ ] 企业微信消息到达后，handler 按 aibotid 路由到正确的角色
* [ ] session 归属 sender_id，员工登录后能看到
* [ ] 通用渠道框架代码完全删除
* [ ] 飞书渠道代码完全删除
* [ ] WeCom 实例模型代码完全删除
* [ ] 共享依赖（ConnectionState、download helper）已迁移
* [ ] 现有 Web 端角色功能不受影响
* [ ] 企业微信功能（流式、分段、thinking、/new、cancel-new、TTL）正常工作

## Definition of Done

* 旧代码完全删除（渠道框架 + 飞书 + WeCom 实例）
* 新链路测试覆盖
* 前后端 lint/typecheck 通过
* 无 unrelated 变更

## Out of Scope

* 旧 session 数据迁移
* 前端 UI 大改（风格保持现有前端风格）
* 其他渠道（钉钉、Slack 等）的接入

## Research References

* [`research/feishu-deletion-scope.md`](research/feishu-deletion-scope.md) — 飞书渠道完整删除范围 + 2 个共享依赖需迁移
* [`research/wecom-instance-scope.md`](research/wecom-instance-scope.md) — WeCom 实例模型范围：9 删除 + 20 重构，核心 SDK 逻辑保留
* [`research/role-config-system.md`](research/role-config-system.md) — 角色配置体系：role_models 模式可复用，前端加在 RolesPanel EditorSidebar

## Implementation Plan (7 subtasks, sequential)

### Task 1: 迁移共享依赖
将 `ConnectionState` 和 `_download_storage_object_to_file` 从飞书模块迁移到 WeCom 模块内，确保 WeCom 不再依赖飞书代码。

### Task 2: 删除飞书渠道
删除所有飞书相关代码：backend (15 files) + frontend (6 files) + tests (7 files) + i18n keys + shared references (ChannelType.FEISHU 等)。验证 WeCom 仍能运行。

### Task 3: 删除通用渠道框架
删除 ChannelStorage、ChannelType、ChannelCoordinator、BaseChannel、channel API routes、前端 ChannelPanel/ChannelsPage。WeCom 对接逻辑暂时保留在 `src/infra/channel/wecom/` 但不再依赖框架基类。

### Task 4: 新建角色 WeCom 配置
新建 `role_wecom_config` 集合 + Pydantic schema + `/api/agent/config/roles/{role_id}/wecom` API 路由（GET/PUT/DELETE）+ 权限控制（manage_channels）+ 前端 RolesPanel EditorSidebar WeCom section（折叠展开式）。

### Task 5: 重构 WeCom 对接逻辑
将 WeCom SDK 对接逻辑从 `src/infra/channel/wecom/` 搬运到 `src/infra/agent/wecom/`。handler 从实例模型改为角色路由（aibotid → role_id），manager 从 instance_id 改为 aibotid。session 归属 sender_id。启动时从 role_wecom_config 加载配置建映射。

### Task 6: 删除 WeCom 实例模型残余
删除 WeComPanel/WeComPanelForm、WeComConfig schema（旧）、channel_storage WeCom 部分、frontend channel types、i18n 中旧的 WeCom 实例相关 key。清理所有对 instance_id 的引用。

### Task 7: 验证与清理
运行全量测试，lint/typecheck，确认无残留无用代码，无 dead import，无孤立文件。

* 主要新增代码：角色 WeCom 配置存储 + API + 前端
* 主要搬运代码：WeCom SDK 对接逻辑（handler/collector/WS 管理）
* 主要删除代码：渠道框架 + 飞书 + WeCom 实例模型
* 迁移优先：先迁移 ConnectionState + download helper → 再删飞书 → 再删渠道框架 → 再删 WeCom 实例
