# refactor: WeCom 对接逻辑从实例模型改为角色入口

## Goal

将 WeCom SDK 对接逻辑从实例模型搬运到 `src/infra/agent/wecom/`，改为角色入口模型。handler 按 aibotid 路由到角色，session 归 sender_id。

## Requirements

### 搬运与重构

* 将 WeCom SDK 对接逻辑从 `src/infra/channel/wecom/` 搬运到 `src/infra/agent/wecom/`
* 保留：WS 连接管理、消息收发、流式回复（WeComResponseCollector）、分段、thinking placeholder、cancel-new、TTL、媒体下载
* 删除：instance_id 引用、BaseChannel 继承、UserChannelManager 继承

### WeCom Bot 管理器

* 新建 `WeComBotManager`（放在 `src/infra/agent/wecom/`）
* 启动时：从 `role_wecom_config` 加载配置 → 建 `aibotid → (role_id, config)` 内存映射
* 按 aibotid 建 WS 连接，每个 aibotid 对应一条连接
* 角色配置变更时：通过 pubsub 刷新缓存，动态增减 WS 连接

### Handler

* 收到消息按 aibotid 查内存映射 → 获取 role_id 和配置
* 从角色配置获取 agent_id、model_id、project_id 等（复用角色体系）
* `task_manager.submit(user_id=sender_id, agent_id=角色agent_id, ...)` — session 归 sender
* `task_manager.cancel(session_id, user_id=sender_id)` — 和 Web 端一致
* project 使用 `get_or_create_by_name(sender_id, channel_name)` 自动创建
* sender 不存在于 LambChat 时：fallback session 到系统默认（或跳过）

### Session 行为

* 单聊：session_id = `wecom_{sender_id}` 或 `wecom_{sender_id}_{timestamp}`
* session.user_id = sender_id
* 不需要 authorized_viewers，不需要 instance_owner_id 分离
* 和 Web 端完全一致

## Acceptance Criteria

* [ ] WeCom SDK 对接逻辑在 `src/infra/agent/wecom/` 下
* [ ] 启动时从 role_wecom_config 加载配置建映射
* [ ] handler 按 aibotid 路由到角色
* [ ] session 归属 sender_id
* [ ] 流式回复、分段、thinking、/new、cancel-new、TTL 正常
* [ ] `src/infra/channel/wecom/` 目录可安全删除

## Technical Notes

* 这是核心重构任务，依赖 Task 4（角色 WeCom 配置）已完成
* sender_id fallback：如果 sender 不存在 LambChat 用户表，可参考原有 user_id 参数逻辑
