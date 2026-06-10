# fix-wecom-interrupt-daily-session

## Goal

修复 WeCom 渠道的三个核心问题：新消息中断旧 run 后新输入无法送入 agent、日切 session 管理、回复内容过滤（仅主 agent 文本渲染），同时优化流式防抖体验。

## Requirements

### 1. 新消息中断旧 run — Cancel + Same Session Resubmit

- Cancel 旧 run 后，**不创建新 session**，同一 session 提交新 run
- Cancel 后**轮询等待**旧 run 状态变为 CANCELLED（不是固定 sleep 0.5s），确保状态一致
- 旧 run 的截断内容**静默丢弃**，不发截断回复
- 不管 LangGraph checkpointer 残留，让 agent 自己处理
- 保留 run_id superseded 检查（防止重复回复）

### 2. 日切 Session — Redis TTL 方案

- `_get_wecom_session_id` 改为给 Redis key 设 TTL：`session_ttl_hours * 3600`（默认 25h 留余量）
- Redis key 过期/不存在时自动创建新 session（`_create_new_wecom_session`）
- 新增 `session_ttl_hours` 配置项：
  - 类型：`int | None`
  - 默认：24
  - 0 或 null = 永不过期（当前行为）
  - 加入 WeComConfigBase / WeComConfigUpdate / WeComConfigResponse schema
  - 加入前端 constants / types / form / i18n

### 3. 回复内容过滤 — 仅主 agent 文本渲染

- `message:chunk` 事件：仅渲染 `depth=0`（主 agent）的文本，`depth>0`（子 agent）的 chunk 不 append 到 collector
- `tool:start` 事件：
  - depth=0 → 🔧 `tool_name`
  - depth>0 → 🤖 `agent_name`（子代理用机器人图标标识）
- `tool:result` 事件：不管 depth，照常提取文件信息并发送
- 流式 finalize 时在最终内容末尾追加工具/子代理调用徽章
- 文件/图片照常独立发送媒体消息

### 4. 流式防抖优化

- `WECOM_STREAM_UPDATE_DEBOUNCE_SECONDS` 从 1.0 降到 0.5（500ms，跟 PicoClaw 一致）

### 5. 保持不变

- 流式超时：保持 6 分钟
- 用户隔离：仅对话上下文隔离（单聊已天然实现）
- `/new` 命令行为不变

## Acceptance Criteria

- [ ] 新消息中断旧 run 后，新输入成功送入 agent 并得到回复
- [ ] 同一 session 内 cancel + resubmit，agent 看到完整对话历史 + 新消息
- [ ] Redis key `wecom:session:{chat_id}` 有 TTL（默认 25h）
- [ ] TTL 过期后首条消息自动创建新 session
- [ ] `session_ttl_hours=0` 时永不过期
- [ ] 前端 WeCom 配置面板有 session TTL 输入项
- [ ] 企微回复只含主 agent 文本，不含子 agent 中间过程
- [ ] 工具调用显示 🔧 badge，子代理调用显示 🤖 badge
- [ ] 子 agent 产出的文件仍正常发送
- [ ] 流式防抖 500ms
- [ ] ruff lint + mypy 通过

## Definition of Done

- Lint / typecheck green
- Manual test: 新消息中断 + 回复正确
- Manual test: 日切 session 正确轮换

## Technical Approach

### handler.py 改动

1. **Cancel 等待逻辑**：替换 `asyncio.sleep(0.5)` 为轮询 `task_manager.get_run_status(session_id, old_run_id)` 直到 CANCELLED，最多等 3s
2. **Session TTL**：`_get_wecom_session_id` 写入时设 TTL，`_create_new_wecom_session` 也设 TTL；handler 里读 `session_ttl_hours` 配置传入
3. **内容过滤**：`_process_events` 中对 `message:chunk` 检查 `data.get("depth", 0)` 和 `data.get("agent_id")`，`depth > 0` 时跳过 `append_stream_chunk`；对 `tool:start` 检查 depth 区分 🔧 和 🤖
4. **工具/子代理徽章**：在 `finalize_stream_message` 的最终内容末尾或 `send_message` 非流式路径追加徽章
5. **防抖**：`WECOM_STREAM_UPDATE_DEBOUNCE_SECONDS = 0.5`

### schema 改动

- `WeComConfigBase` 加 `session_ttl_hours: int = Field(24, ...)`
- `WeComConfigUpdate` 加 `session_ttl_hours: Optional[int] = None`
- `WeComConfigResponse` 加 `session_ttl_hours: int = 24`

### 前端改动

- `types.ts` 加 `session_ttl_hours?: number`
- `constants.ts` 加 `sessionTtlHours: 24`
- `WeComPanelForm.tsx` 加数字输入项
- `WeComPanel.tsx` 状态管理
- `zh.json` / `en.json` 加 i18n key

### manager.py 改动

- `_dict_to_config` 加 `session_ttl_hours` 字段

## Decision (ADR-lite)

**Context**: WeCom 渠道存在新消息中断后新输入无法送入 agent、session 无生命周期管理、子 agent 内容全部推到企微三大问题
**Decision**: Cancel + Same Session Resubmit（轮询等待旧 run 状态），Redis TTL 日切，depth 过滤子 agent 内容
**Consequences**: 不清理 checkpointer 残留（agent 自处理），TTL 不精确到零点但大致隔天轮换够用

## Out of Scope

- PicoClaw Steering 机制（注入新消息到旧 run）
- Agent 实例隔离 / 并发配额隔离
- 企微 markdown 格式适配
- LangGraph checkpointer 残留清理

## Technical Notes

- PicoClaw 参考：500ms 防抖、5.5min 超时、wecomTurn 队列 + reqIDStore 路由
- 事件 depth 信息来自 `AgentEventProcessor.SubagentEventMixin._get_agent_context()`
- `checkpoint_ns` 含 `|` 分隔符表示子 agent 层级
- `data.agent_id` 在 `message:chunk` 和 `tool:start` 事件中可用
