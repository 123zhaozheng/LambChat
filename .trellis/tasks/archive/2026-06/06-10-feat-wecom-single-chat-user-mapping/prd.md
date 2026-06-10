# feat: WeCom 单聊用户映射

## Goal

当企业微信单聊用户给机器人发消息时，产生的 session 应归属于该发送者（员工），而非机器人实例创建者。这样员工登录 LambChat 后能在 Web 端看到自己在企业微信的聊天记录。

## What I Already Know

* 当前 WeCom handler 收到消息时，`user_id` = 创建机器人实例的人的 LambChat ID（来自 `self.config.user_id`，不一定是系统管理员，任何创建了 WeCom 实例的用户都是 instance owner）
* 企业微信单聊中，`chat_id` = 发送者的 userid（如 `zhangsan`），群聊中 `chat_id` = 群聊 ID
* 用户确认：**企业微信单聊用户 ID 与 LambChat 账号 ID 一致**
* `list_sessions` 按 `user.sub` 过滤，普通用户只能看自己的 session
* `verify_session_ownership` 严格比对 `session.user_id == user.sub`，不匹配则 403
* session 由 `task_manager.submit(user_id=...)` 创建，user_id 写入 MongoDB session 记录
* `UserManager.get_user(user_id)` 返回 `Optional[User]`，可用于验证用户是否存在

* **handler 中 user_id 的用途分为两类**：
  - **归属类**（应该用 sender_id）：session 创建、task submit、cancel、executor 上下文
  - **配置类**（应该继续用 instance_owner_id）：channel config 查询、persona preset 访问、project 访问、WeCom client 查找（_find_channel）

## Assumptions

* 仅单聊场景需要映射；群聊仍归属 instance owner（用户已确认）
* 企业微信 userid 与 LambChat user_id 完全一致，无需额外映射表
* 员工在 LambChat 不存在时，session fallback 到 instance owner（用户已确认：先验证再写入）

## Open Questions

(none — all resolved)

## Requirements

* 单聊场景：session 的 user_id 应设为 sender_id（= LambChat 账号 ID），而非 instance owner ID
* 单聊场景：task_manager.submit/cancel 使用 sender_id 作为 user_id
* 单聊场景：如果 sender_id 在 LambChat 用户表中不存在，fallback 到 instance owner ID
* 单聊场景：channel config、persona preset 仍使用 instance owner ID
* 单聊场景：project 使用 `get_or_create_by_name(session_owner_id, channel_name)` 自动创建，忽略 channel config 中手动配置的 project_id
* 群聊场景：project 行为不变（仍使用 instance owner ID 查询/创建）
* WeComResponseCollector 的 user_id（用于 _find_channel）保持使用 instance owner ID
* 群聊场景：行为不变，session 仍归 instance owner
* 员工登录 LambChat 后，能在 session 列表中看到自己的企业微信聊天 session
* instance owner 能查看/管理通过自己实例产生的所有 session（包括归属给 sender 的）
* session metadata 增加 `authorized_viewers` (list[str]) 字段，记录有权查看/管理该 session 的用户 ID 列表（不包含 session.user_id 本身）
* 员工能查看企业微信 session 的聊天记录（events/runs）
* 现有功能不受影响：流式回复、分段、thinking placeholder、/new、cancel-then-new、TTL

## Acceptance Criteria

* [ ] 单聊消息产生的 session，其 user_id 等于 sender_id（当 sender 在 LambChat 存在时）
* [ ] 单聊 sender_id 在 LambChat 不存在时，session user_id fallback 到 instance owner ID
* [ ] 该员工登录 LambChat 后，list_sessions 能返回此 session
* [ ] 该员工能访问此 session 的 events/runs（verify_session_ownership 通过）
* [ ] session.metadata 包含 `authorized_viewers: [instance_owner_id]`，instance owner 能看到和管理此 session
* [ ] instance owner 在 list_sessions 时也能看到 authorized_viewers 包含自己 ID 的 session
* [ ] channel config / persona / _find_channel 仍使用 instance owner ID
* [ ] project 查询/创建使用 session_owner_id，单聊忽略手动 project_id
* [ ] 群聊 session 归属不变（仍为 instance owner）
* [ ] 现有 handler 功能（流式、分段、cancel-new、TTL）不受影响
* [ ] 回归测试覆盖单聊 user_id 映射路径

## Definition of Done

* 测试覆盖单聊 user_id 映射（含 sender 存在 / 不存在两条路径）
* 受影响的既有测试更新通过
* Lint / typecheck 通过
* 不引入 unrelated 变更

## Decision (ADR-lite)

**Context**: WeCom 单聊用户在企业微信和机器人对话产生的 session 归属不正确——所有 session 都挂在实例创建者名下，员工无法在 Web 端查看自己的聊天记录。

**Decision**: 在 handler 内部区分 `session_owner_id` 和 `instance_owner_id`。单聊场景下，先查 `UserManager.get_user(sender_id)` 验证用户是否存在，存在则用 sender_id 作为 session 归属，否则 fallback 到 instance owner ID。群聊不变。

**Consequences**: 最小改动，只影响 handler 内部的 user_id 分发逻辑，不改 BaseChannel 接口。多一次 DB 查询（用户验证），但对 WeCom 消息频率来说开销可忽略。

## Out of Scope

* 企业微信 userid 与 LambChat user_id 的映射表（用户已确认 ID 一致）
* 已有旧 session 的 user_id 迁移（不迁移，旧 session 保持在 instance owner 名下，新消息走新逻辑）
* 群聊 session 归属变更
* 飞书 channel 的类似映射
* 前端 UI 变更

## Technical Approach

在 `create_wecom_message_handler` 的 `wecom_message_handler` 内部，handler 收到 `user_id`（= instance owner ID）后：

1. 从 metadata 获取 `chat_type` 和 `sender_id`
2. 如果 `chat_type == "single"`：
   - 调用 `UserManager.get_user(sender_id)` 验证用户是否存在
   - 存在 → `session_owner_id = sender_id`
   - 不存在 → `session_owner_id = user_id`（原 instance owner）
3. 如果 `chat_type == "group"`：
   - `session_owner_id = user_id`（不变）
4. 后续代码中：
   - `task_manager.cancel(session_id, user_id=session_owner_id)`
   - `task_manager.submit(user_id=session_owner_id, ...)`
   - 单聊场景：project 跳过手动 project_id 验证，改用 `get_or_create_by_name(session_owner_id, channel_name)` 自动创建
   - channel config / persona / collector 仍用原 `user_id`（instance owner）
5. 当 `session_owner_id != user_id`（即 session 归 sender，不是 instance owner）：
   - submit 后，通过 `SessionManager().update_session()` 在 session.metadata 中设置 `authorized_viewers: [user_id]`（instance owner ID）
6. 修改 `list_sessions`：除了 `user_id == filter_user_id` 的 session，还返回 `metadata.authorized_viewers` 包含 `filter_user_id` 的 session
7. 修改 `verify_session_ownership`：除了 `session.user_id == user.sub`，还允许 `user.sub in session.metadata.get("authorized_viewers", [])`

## Technical Notes

* 主要修改文件：`src/infra/channel/wecom/handler.py`
* 辅助查询：`src/infra/user/manager.py` → `UserManager.get_user(user_id)`
* `BaseChannel._handle_message(user_id=self.user_id, ...)` 是 user_id 进入 handler 的入口，不改
* `WeComResponseCollector.__init__(user_id=...)` 保持使用 instance owner ID（用于 _find_channel）
