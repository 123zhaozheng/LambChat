# WeCom AI Bot 点赞点踩 (Feedback Event) 调研

## 1. SDK 事件支持

`wecom-aibot-sdk` 已原生支持 feedback 事件，无需额外安装。

### 1.1 事件注册

SDK 通过 `client.on("event.feedback_event", handler)` 注册回调。项目中 `bot.py:180` 已注册：

```python
client.on("event.feedback_event", self._on_feedback_event)
```

当前 `_on_feedback_event`（bot.py:679）是空壳，只记录日志。

### 1.2 事件分发机制

SDK 的 `message_handler.py` 处理 `aibot_event_callback` 命令：

```python
def _handle_event_callback(self, frame, emitter):
    body = frame.get("body") or {}
    event = body.get("event") or {}
    event_type = event.get("eventtype", "")
    if event_type:
        emitter.emit(f"event.{event_type}", frame)
```

当 `eventtype = "feedback_event"` 时，触发 `event.feedback_event` 事件。

## 2. 回复时设置 feedback（前置条件）

**关键约束**：只有回复中设置了 `feedback.id` 的消息，用户才能点赞/点踩。未设置 feedback 的回复，点击赞/踩无任何回调。

### 2.1 SDK reply_stream 签名

```python
async def reply_stream(
    self,
    frame: WsFrame | dict[str, Any],
    stream_id: str,
    content: str,
    finish: bool = False,
    msg_item: list[ReplyMsgItem] | None = None,
    feedback: ReplyFeedback | None = None,  # ← 此参数
) -> WsFrame:
```

### 2.2 ReplyFeedback 类型

```python
class ReplyFeedback(TypedDict):
    """回复消息中的反馈信息"""
    id: str
```

只需 `{"id": "xxx"}`，此 `id` 用于后续 feedback_event 回调时关联原始回复。

### 2.3 何时设置

- **仅在首次流式回复时设置**（finish=False 的第一帧）
- 后续流式帧不需要再传 feedback
- `reply_stream_non_blocking` 和 `reply_stream_with_card` 也支持 feedback 参数

## 3. Feedback Event 数据结构

用户点赞/点踩后，SDK 收到如下结构的 WsFrame：

```json
{
  "cmd": "aibot_event_callback",
  "headers": {"req_id": "..."},
  "body": {
    "msgid": "CAIQ16HMjQYY/NGagIOAgAMgq4KM0AI=",
    "create_time": 1700000000,
    "aibotid": "AIBOTID",
    "chatid": "CHATID",
    "chattype": "single",
    "from": {
      "userid": "USERID"
    },
    "msgtype": "event",
    "event": {
      "eventtype": "feedback_event",
      "feedback_event": {
        "id": "FEEDBACKID",
        "type": 2,
        "content": "能再详细一些么",
        "inaccurate_reason_list": [2, 4]
      }
    }
  }
}
```

### 3.1 字段详解

| 字段 | 位置 | 说明 |
|---|---|---|
| `body.msgid` | body | 事件唯一 ID，可用于去重 |
| `body.create_time` | body | 事件时间戳 |
| `body.aibotid` | body | 机器人 ID |
| `body.chatid` | body | 群聊 ID（单聊无此字段） |
| `body.chattype` | body | `"single"` / `"group"` |
| `body.from.userid` | body | 点赞/踩的用户 ID |
| `body.event.feedback_event.id` | event | 对应回复时设的 `feedback.id` |
| `body.event.feedback_event.type` | event | **1=点赞，2=点踩，3=取消** |
| `body.event.feedback_event.content` | event | 用户文字反馈（仅 type=2） |
| `body.event.feedback_event.inaccurate_reason_list` | event | 点踩原因码（仅 type=2） |

### 3.2 点踩原因码

| 值 | 含义 |
|---|---|
| 1 | 与问题无关 |
| 2 | 内容不完整 |
| 3 | 内容错误 |
| 4 | 数据分析错误 |

## 4. 约束与注意事项

1. **feedback.id 必须在回复时设置**，否则用户点击无回调
2. **feedback_event 只支持空 ack 回复**，不能在回调中发送新消息或更新卡片
3. 单聊无 `chatid` 字段，用 `body.from.userid` 作为 chat target
4. `type=3`（取消）表示用户撤回之前的点赞/踩

## 5. 与 LambChat 反馈系统的映射

| WeCom | LambChat |
|---|---|
| `feedback.id` | 设为 `run_id`（回复时 `feedback={"id": run_id}`） |
| `type=1` (like) | `rating="up"` |
| `type=2` (dislike) | `rating="down"`，`content` → `comment` |
| `type=3` (cancel) | 删除对应 feedback 记录 |
| `from.userid` | username → `UserStorage.get_by_username()` → LambChat `user_id` |
| `session_id` | 需从 `run_id` 反查 session，或在 reply 时记录 run_id→session_id 映射 |

### 5.1 LambChat 反馈系统关键信息

- **Schema**: `FeedbackCreate(session_id, run_id, rating: "up"|"down", comment?)`
- **唯一约束**: `(user_id, session_id, run_id)` 一人一轮只能一条反馈
- **API**: `POST /api/feedback/` 需 `feedback:write` 权限
- **Manager**: `FeedbackManager.submit_feedback(user_id, username, data)`
- **删除**: `FeedbackStorage.delete(feedback_id)` 需 `feedback:admin` 权限，或直接通过 MongoDB
- **取消逻辑**: LambChat 无原生"取消"操作，WeCom type=3 时需删除已有记录

## 6. 官方文档

- 企业微信智能机器人开发文档: `https://developer.work.weixin.qq.com/document/path/101027`
- SDK 源码位置: `.venv/Lib/site-packages/wecom_aibot_sdk/`
