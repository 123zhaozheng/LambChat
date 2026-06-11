# LambChat 反馈系统调研

## 1. 数据模型

### 1.1 Schema 层 (`src/kernel/schemas/feedback.py`)

| Schema | 字段 | 用途 |
|---|---|---|
| `RatingValue` | `Literal["up", "down"]` | 点赞/踩类型别名 |
| `FeedbackBase` | `rating`, `comment?` (max 1000) | 基础模型 |
| `FeedbackCreate` | + `session_id`, `run_id` | 创建请求 |
| `Feedback` | + `id`, `user_id`, `username`, `session_id`, `run_id`, `created_at` | 响应模型 |
| `FeedbackInDB` | 同 Feedback | DB 文档模型 |
| `FeedbackStats` | `total_count`, `up_count`, `down_count`, `up_percentage` | 统计 |
| `FeedbackListResponse` | `items`, `total`, `stats` | 分页列表 |

**唯一约束**: `(user_id, session_id, run_id)` — 每人每轮只允许一条反馈。

### 1.2 存储层 (`src/infra/feedback/storage.py`)

- MongoDB collection: `"feedback"`
- 索引: `(user_id, session_id, run_id)` unique, `(session_id, run_id)`, `(rating)`, `(created_at DESC)`
- `create()` 方法先查 `get_user_feedback_for_run()`，已有则抛 `ValueError("您已经对该对话提交过反馈")`

### 1.3 Manager 层 (`src/infra/feedback/manager.py`)

薄层包装 Storage，核心方法：

```python
async def submit_feedback(self, user_id: str, username: str, data: FeedbackCreate) -> Feedback
```

直接委托 `storage.create()`。

## 2. API 路由 (`src/api/routes/feedback.py`)

挂载于 `/api/feedback`。

| 端点 | 方法 | 权限 | 说明 |
|---|---|---|---|
| `/api/feedback/` | POST | `feedback:write` | 提交反馈，重复提交返回 400 |
| `/api/feedback/` | GET | `feedback:read` | 列表（分页） |
| `/api/feedback/stats` | GET | `feedback:read` | 统计 |
| `/api/feedback/my/by-run/{session_id}/{run_id}` | GET | `feedback:write` | 当前用户对某 run 的反馈 |
| `/api/feedback/by-run/{session_id}/{run_id}` | GET | `feedback:read` | 某 run 的所有反馈 |
| `/api/feedback/stats/{session_id}/{run_id}` | GET | `feedback:read` | 某 run 的统计 |
| `/api/feedback/{feedback_id}` | DELETE | `feedback:admin` | 删除反馈记录 |

## 3. 前端集成

### 3.1 FeedbackButtons (`frontend/src/components/chat/ChatMessage/FeedbackButtons.tsx`)

- 在 assistant 消息上渲染 👍/👎 按钮
- 点击后打开 `FeedbackDialog`（可选填写 comment）
- 提交调用 `feedbackApi.submit({ rating, comment, session_id, run_id })`
- 已提交后显示已选中的图标

### 3.2 反馈加载流程 (`useAgent.ts`)

1. 加载 session 历史时，并行调用 `feedbackApi.list(0, 100, ..., sessionId)`
2. 构建 `feedbackMap: Map<run_id, {feedback, feedbackId}>`
3. 将反馈状态映射到对应消息的 `message.feedback` 和 `message.feedbackId`

### 3.3 Message 类型中的反馈字段

```typescript
interface Message {
  runId?: string;       // run ID，feedback 关联键
  feedback?: RatingValue; // 当前用户的反馈
  feedbackId?: string;    // 反馈记录 ID
}
```

## 4. 关键发现 — 供 WeCom 打通用

1. **FeedbackManager.submit_feedback(user_id, username, data)** 是入口，WeCom handler 应直接调用此方法
2. **重复提交限制**：同一 `(user_id, session_id, run_id)` 只能一条。WeCom 场景下，用户可能先点👍再改👎（即 type=3 取消再 type=2），需要先删再建
3. **FeedbackCreate 需要 session_id**：WeCom handler 中 session_id 已有（wecom_{chat_id}），可直接用
4. **FeedbackCreate 需要 run_id**：这是关键——需要将 run_id 作为 feedback.id 传给 WeCom，回调时再拿回来反查
5. **无"取消"API**：LambChat 只有 POST 创建和 DELETE 删除，没有"切换"操作。WeCom type=3 需要调用 delete
6. **删除需 feedback:admin 权限**：WeCom handler 走内部调用，不经过 API，直接用 FeedbackStorage.delete() 即可
