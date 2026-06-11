# feat: WeCom 点赞点踩与 LambChat 反馈系统打通

## Goal

将企业微信智能机器人的点赞/点踩功能与 LambChat 的反馈系统打通。用户在企业微信中点赞/点踩机器人回复时，自动同步写入 LambChat 的 feedback 记录，与 Web 端点赞/点踩逻辑一致。

## What I Already Know

### WeCom 侧
- SDK 已原生支持 `event.feedback_event` 回调（bot.py:180 已注册）
- 当前 `_on_feedback_event` 是空壳，仅记录日志
- **关键前提**：回复时必须设置 `feedback={"id": "xxx"}`，否则用户点击赞/踩无回调
- SDK 的 `reply_stream()` 支持 `feedback: ReplyFeedback | None` 参数
- `ReplyFeedback` = `{"id": str}`，此 id 回调时原样返回，用于关联原始回复

### Feedback Event 数据
- `feedback_event.id` = 回复时设的 feedback.id
- `feedback_event.type`: 1=点赞, 2=点踩, 3=取消
- `feedback_event.content`: 用户文字反馈（仅 type=2）
- `feedback_event.inaccurate_reason_list`: 点踩原因码（仅 type=2）
- `from.userid`: 点赞/踩的用户 ID（= 员工工号）

### LambChat 反馈系统
- `FeedbackCreate(session_id, run_id, rating: "up"|"down", comment?)`
- 唯一约束: `(user_id, session_id, run_id)` 一人一轮一条
- `FeedbackManager.submit_feedback(user_id, username, data)` 是内部入口
- 无原生"取消"API，WeCom type=3 需删除已有记录
- 删除: `FeedbackStorage.delete()` 或通过 `FeedbackManager`

### 映射关系
| WeCom | LambChat |
|---|---|
| `feedback.id` | `run_id`（回复时 `feedback={"id": run_id}`） |
| `type=1` | `rating="up"` |
| `type=2` | `rating="down"` |
| `type=3` | 删除已有 feedback 记录 |
| `from.userid` | `UserStorage.get_by_username()` → `user_id` |
| `content` (type=2) | `comment` 字段 |

### run_id 可获取性
- `run_id` 在 `task_manager.submit()` 返回（handler.py:369）
- collector 在 submit 之前创建，需要后续设置 run_id
- session_id 格式为 `wecom_{chat_id}`

## Assumptions

- WeCom feedback.id 设为 run_id，回调时用此 id 反查 session
- run_id 全局唯一，可直接作为 feedback.id，无需额外映射表
- 用户取消（type=3）时直接删除已有反馈记录
- 点踩原因码（inaccurate_reason_list）暂不映射，追加到 comment 中作为文字描述
- WeCom handler 走内部调用（FeedbackManager），不走 HTTP API，无需权限检查

## Open Questions

(none)

## Requirements

### R1: 回复时设置 feedback.id
- collector 首次 reply_stream 时传入 `feedback={"id": run_id}`
- 仅在流式的**第一帧**（非 thinking placeholder）设置 feedback
- thinking placeholder 不设 feedback（因为 placeholder 时 run_id 尚未生成）

### R2: 实现 _on_feedback_event 处理逻辑
- 解析 feedback_event 数据：id(=run_id), type, content, from.userid
- 映射 type → rating: 1→"up", 2→"down"
- type=3 时查找并删除已有反馈记录
- from.userid 通过 UserStorage.get_by_username() 映射为 LambChat user_id
- 映射失败时 fallback 使用 from.userid 作为 user_id（与消息 handler 一致）
- 通过 feedback.id(=run_id) 反查 session_id（从 session metadata 的 current_run_id 匹配）

### R3: Feedback 写入
- type=1/2: 调用 `FeedbackManager.submit_feedback(user_id, username, FeedbackCreate(...))`
- session_id 通过 run_id 反查 session 获取
- type=2 的 content 映射为 comment，inaccurate_reason_list 转文字追加
- 重复提交场景：先查已有记录，如已存在且 rating 相同则跳过，rating 不同则先删再建

### R4: 取消反馈（type=3）
- 通过 `FeedbackStorage` 查找 `(user_id, session_id, run_id)` 对应的记录
- 找到则删除，未找到则忽略（幂等）

## Acceptance Criteria

- [ ] WeCom 机器人回复的消息在企业微信中显示点赞/点踩按钮
- [ ] 用户在企业微信点赞后，LambChat feedback 表中出现对应 rating="up" 记录
- [ ] 用户在企业微信点踩后，LambChat feedback 表中出现对应 rating="down" 记录，comment 含用户文字反馈
- [ ] 用户取消赞/踩后，LambChat feedback 记录被删除
- [ ] 同一用户对同一回复重复操作（先赞后踩），最终记录正确（先删除旧的，创建新的）
- [ ] Web 端查看该 session 历史时，能看到企业微信侧提交的反馈
- [ ] sender_id 映射失败时仍能写入反馈（fallback 到 raw sender_id）
- [ ] thinking placeholder 不设 feedback（不影响点赞功能）
- [ ] 不影响现有流式回复、分段、cancel-then-new、TTL 等功能

## Definition of Done

- 代码修改仅涉及 WeCom 相关文件（bot.py, collector.py, handler.py）
- FeedbackManager/Storage 的使用方式与 Web 端一致
- Lint / typecheck 通过
- 不引入 unrelated 变更

## Decision (ADR-lite)

**Context**: 企业微信智能机器人支持点赞/点踩回调，但需要回复时设置 feedback.id 才能触发。LambChat 已有完整的反馈系统，需要打通两者。

**Decision**: 将 run_id 作为 feedback.id 传入 WeCom 回复，回调时用此 id 反查 session 和写入反馈。collector 在流式首帧（非 thinking placeholder）时设置 feedback。_on_feedback_event 解析回调数据，通过 UserStorage 映射用户，通过 session 查询反查 session_id，调用 FeedbackManager 写入。

**Consequences**: 最小改动，复用已有反馈系统。run_id 全局唯一保证 feedback.id 不冲突。额外增加一次 session 查询（feedback 回调时反查），频率低可忽略。

## Out of Scope

- 点踩原因码的专门存储（inaccurate_reason_list 追加到 comment）
- 前端 UI 变更（Web 端已支持反馈展示）
- Web 端反馈同步回企业微信（企业微信 SDK 不支持主动设置赞/踩状态）
- 反馈统计面板变更

## Technical Approach

### 步骤 1: bot.py — reply_stream 增加 feedback 参数透传

在 `WeComBot.reply_stream()` 方法增加 `feedback: dict | None = None` 参数，透传给 SDK 的 `client.reply_stream(feedback=feedback)`。

### 步骤 2: collector.py — 流式首帧设置 feedback

1. 给 `WeComResponseCollector.__init__` 增加 `run_id: str | None = None` 参数
2. 增加 `set_run_id(run_id: str)` 方法（run_id 在 collector 创建后才从 submit 获取）
3. 修改 `send_thinking_placeholder()`: **不设** feedback（因为 run_id 尚未生成）
4. 修改 `append_stream_chunk()` 首帧逻辑：如果 `self._run_id` 存在，传 `feedback={"id": self._run_id}`
5. 修改 `finalize_stream_message()` 和 `_stream_update_worker()` 中的 `reply_stream` 调用：后续帧不传 feedback

### 步骤 3: handler.py — submit 后设置 run_id 到 collector

在 `task_manager.submit()` 返回 `run_id` 后，调用 `collector.set_run_id(run_id)`。

### 步骤 4: bot.py — 实现 _on_feedback_event

```python
async def _on_feedback_event(self, frame: Any) -> None:
    """Handle user feedback event from WeCom."""
    self._update_activity_time()
    body = _frame_body(frame)
    event = body.get("event", {})
    feedback_event = event.get("feedback_event", {})
    
    feedback_id = feedback_event.get("id", "")  # = run_id
    feedback_type = feedback_event.get("type", 0)  # 1=like, 2=dislike, 3=cancel
    feedback_content = feedback_event.get("content", "")
    inaccurate_reasons = feedback_event.get("inaccurate_reason_list", [])
    
    sender_id = _frame_from_userid(body)
    aibotid = body.get("aibotid", "") or self.aibotid
    
    if not feedback_id or not sender_id:
        logger.warning("[WeCom] Incomplete feedback event, skipping")
        return
    
    # 通过 message_handler 回调（新增 feedback 回调签名）
    # 或直接在此处理
```

### 步骤 5: handler.py — 新增 feedback 回调处理

在 `create_wecom_message_handler` 中增加对 feedback event 的处理逻辑：
- 映射 sender_id → user_id（复用现有 UserStorage.get_by_username()）
- 通过 run_id 查 session（遍历 session 的 current_run_id metadata）
- type=1/2: 构建 FeedbackCreate 并调用 FeedbackManager.submit_feedback()
- type=3: 查找并删除已有记录
- 重复提交处理：先查已有，rating 相同跳过，不同先删后建

### 关键文件

| 文件 | 修改内容 |
|---|---|
| `src/infra/agent/wecom/bot.py` | reply_stream 增加 feedback 参数；_on_feedback_event 实现解析+回调 |
| `src/infra/agent/wecom/collector.py` | 增加 run_id 支持；首帧 reply_stream 传 feedback |
| `src/infra/agent/wecom/handler.py` | submit 后 set_run_id；新增 feedback event 处理函数 |
