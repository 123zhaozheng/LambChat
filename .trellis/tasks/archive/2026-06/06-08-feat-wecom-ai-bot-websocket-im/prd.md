# feat: WeCom (企业微信) AI Bot WebSocket 长连接 IM 接入

## Goal

实现企业微信（WeCom）AI Bot 模式的 WebSocket 长连接 IM 接入，参照飞书通道实现，支持文本/图片/文件收发、流式回复、欢迎消息、模板卡片等全功能。

## Decisions (ADR-lite)

### D1: 通道类型命名 → `wecom`
**Context**: 后端注释了 `WECHAT="wechat"`，前端已含 `"wechat"` 类型。企业微信官方英文名已从 WeChat Work 改为 WeCom。
**Decision**: 使用 `wecom`，后端枚举 `WECOM='wecom'`，前端替换 `'wechat'` → `'wecom'`，API 路径 `/api/channels/wecom/`。
**Consequences**: 需修改前端 `channel.ts` 中的 `'wechat'` → `'wecom'`。与官方命名一致，避免与个人微信混淆。

### D2: 前端面板 → 独立 WeComPanel
**Context**: 飞书有独立 FeishuPanel，WeCom 配置简单（仅需 bot_id + secret），但需定制 UI（logo、提示）。
**Decision**: 创建独立 WeComPanel + WeComPanelForm + types.ts。
**Consequences**: 前端代码量增加，但用户体验更好，可添加 WeCom 特有交互逻辑。

### D3: MVP 范围 → 全功能
**Context**: WeCom AI Bot 支持多种消息类型，需权衡初版工作量与可用性。
**Decision**: 包含文本收发+流式回复、图片/文件收发、欢迎消息、模板卡片。
**Consequences**: 工作量较大，但功能完整，用户可直接使用所有核心能力。

### D4: SDK → `wecom-aibot-sdk` 社区增强版 (v1.0.7)
**Context**: 官方 SDK 缺少 upload_media；社区增强版基于官方代码增加了 upload_media/reply_media/send_media_message。
**Decision**: 使用 `wecom-aibot-sdk>=1.0.7` (mattzwang)。
**Consequences**: 非腾讯官方维护，长期稳定性有风险。开箱即用，无需自行实现媒体上传。

### D5: 架构范围 → 纯 AI Bot
**Context**: 未来可能需要自建应用模式（更多 API 能力，明文 userid）。
**Decision**: 仅实现 AI Bot 模式，不预留自建应用扩展点。
**Consequences**: 未来加自建应用时可能需要重构 WeComConfig，但 MVP 最简洁。

### D6: 流式超时策略 → 超时回退主动推送
**Context**: WeCom 流式回复硬性 6 分钟超时，但 Agent 可能仍在运行。
**Decision**: 6 分钟超时后自动通过 `aibot_send_msg` 发送完整结果。用户会看到两条消息（流式部分 + 完整结果）。
**Consequences**: 用户体验有轻微不连续性，但保证结果不丢失。实现简单。

## Requirements

### 后端

* **WeComConfig schema** (`src/kernel/schemas/wecom.py`):
  - `bot_id` (必填) — 机器人 ID
  - `secret` (必填) — 机器人密钥
  - `group_policy` — `"open"` | `"mention"`，默认 `"mention"`
  - `stream_reply` — 是否流式回复，默认 `True`
  - `send_thinking_message` — 5秒内发送思考占位消息，默认 `True`
  - `auto_transcribe_audio` — 自动音频转写，默认 `True`
  - `audio_transcribe_prompt` — 音频转写提示词
  - `websocket_url` — WS 地址覆盖，默认 `wss://openws.work.weixin.qq.com`
  - `enabled` — 是否启用
* **WeComChannel** (`src/infra/channel/wecom/channel.py`):
  - 继承 `BaseChannel`，使用 `wecom-aibot-sdk` WSClient
  - WebSocket 长连接 + 自动重连 + 心跳（SDK 内建）
  - 消息接收（text/image/file/voice/video/mixed）
  - 消息去重（msgid）
  - 群聊/私聊策略（group_policy: open/mention）
  - ConnectionState 状态跟踪
  - 欢迎消息处理（enter_chat 事件 → aibot_respond_welcome_msg）
* **WeComChannelManager** (`src/infra/channel/wecom/manager.py`):
  - 继承 `UserChannelManager`
  - Redis lease 分布式协调（复用 Feishu 模式）
  - 多租户连接管理
  - 配置热重载
* **WeComResponseCollector** (`src/infra/channel/wecom/handler.py`):
  - 流式回复处理（reply_stream + 防抖）
  - 5 秒回调截止时间（异步发送 thinking 占位消息）
  - 6 分钟流式超时回退（aibot_send_msg）
  - 模板卡片回复 + 按钮事件处理
  - 图片/文件发送（upload_media + reply_media）
* **ChannelType 枚举** 新增 `WECOM = "wecom"`
* **API routes** 扩展支持 wecom 通道 CRUD + status

### 前端

* `channel.ts`: `'wechat'` → `'wecom'`
* 新增 `WeComPanel` + `WeComPanelForm` + `types.ts`
* 通道列表/创建/编辑 UI 支持 wecom 类型

### 依赖

* `pyproject.toml` 新增 `wecom-aibot-sdk>=1.0.7`

## Acceptance Criteria

* [ ] 用户可在 UI 中创建企业微信通道配置（输入 bot_id + secret）
* [ ] 配置保存后自动建立 WebSocket 长连接
* [ ] 企业微信用户发文本消息后，LambChat Agent 接收并流式回复
* [ ] 群聊中 @机器人 触发回复（mention 策略），open 策略下所有消息触发回复
* [ ] 5 秒内发送 thinking 占位消息（配置开关）
* [ ] 长时间 Agent 任务超过 6 分钟后回退到 aibot_send_msg 主动推送
* [ ] 用户进入对话时收到欢迎消息
* [ ] 可发送模板卡片回复，用户点击按钮后收到事件回调
* [ ] 可接收图片/文件消息，Agent 可回复图片/文件（upload_media）
* [ ] 连接断开后自动重连（SDK 内建指数退避）
* [ ] 分布式部署下使用 Redis lease 协调（单 bot_id 只被一个实例持有）
* [ ] 消息去重（msgid），不重复处理
* [ ] 前端 WeComPanel 正确渲染配置表单和状态

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope

* WeCom 自建应用模式（corp_id + corp_secret + HTTP callback）— 未来可扩展
* 一键注册流程（WeCom 无此 API）
* 消息 Reactions（WeCom AI Bot 不支持）
* 音频转写（初版不含，可后续迭代添加）
* open_userid 转明文 userid（需额外自建应用 API）
* 并发消息排队/限流（3 条限制由 WeCom 侧控制）

## Technical Notes

### 参考文件
* `src/infra/channel/base.py` — BaseChannel / UserChannelManager 抽象层
* `src/infra/channel/feishu/channel.py` — FeishuChannel 实现（主要参考）
* `src/infra/channel/feishu/manager.py` — FeishuChannelManager + Redis lease
* `src/infra/channel/feishu/handler.py` — FeishuResponseCollector + CardKit 流式
* `src/infra/channel/feishu/state.py` — ConnectionState 枚举
* `src/kernel/schemas/channel.py` — ChannelType / ChannelCapability 枚举
* `src/kernel/schemas/feishu.py` — FeishuConfig schema（模板）
* `frontend/src/types/channel.ts` — 前端 ChannelType 类型
* `frontend/src/components/panels/channel/feishu/` — FeishuPanel 前端组件

### 研究文件
* [research/wecom-websocket-integration.md](../../research/wecom-websocket-integration.md) — WeCom AI Bot WS 协议、SDK、开源项目参考
* [research/wecom-vs-feishu-comparison.md](../../research/wecom-vs-feishu-comparison.md) — WeCom vs 飞书架构对比及实现映射

### 关键架构差异（vs 飞书）
| 方面 | 飞书 | 企业微信 |
|---|---|---|
| 回复机制 | HTTP API (`/im/v1/messages`) | 同一 WS 连接 (`aibot_respond_msg`) |
| 流式回复 | CardKit (4步) | 原生 WS 流式 (`reply_stream`) |
| 发送器 | 需要 FeishuSenderMixin (HTTP) | 不需要单独 Sender (WS 直发) |
| 加密 | encrypt_key + verification_token | 不需要 (wss://) |
| 注册 | register_app 一键注册 | 无（手动创建）|
| Reactions | 支持 | 不支持 |
| 心跳 | 手动 _ping_loop | SDK 内建 |
| 5s 截止 | 无 | 有（需 thinking 占位）|
| 6min 流式超时 | 无硬限制 | 有硬限制 |

### 预估文件结构
```
src/infra/channel/wecom/
    __init__.py
    channel.py        # WeComChannel(BaseChannel) - WS连接+消息收发
    manager.py        # WeComChannelManager(UserChannelManager) - Redis lease
    handler.py        # WeComResponseCollector - 流式+超时+卡片处理
src/kernel/schemas/wecom.py  # WeComConfig schema
frontend/src/components/panels/channel/wecom/
    WeComPanel.tsx
    WeComPanelForm.tsx
    types.ts
```

### Implementation Plan (小 PR 拆分)

**PR1: 后端骨架 + 基础连接**
* 新增 `WeComConfig` schema
* ChannelType 新增 `WECOM`
* 新增 `WeComChannel` 骨架（start/stop/connect）
* 新增 `WeComChannelManager` 骨架（Redis lease）
* pyproject.toml 添加依赖
* 基础消息收发（text only）
* 单元测试

**PR2: 流式回复 + 超时处理**
* `WeComResponseCollector` 实现
* 流式回复（reply_stream + 防抖）
* 5 秒 thinking 占位消息
* 6 分钟超时回退（aibot_send_msg）
* 集成 Agent stream 事件驱动

**PR3: 图片/文件/卡片/欢迎消息**
* upload_media + reply_media 实现
* 模板卡片回复 + 按钮事件处理
* 欢迎消息（enter_chat → aibot_respond_welcome_msg）
* 前端 WeComPanel + WeComPanelForm
* 集成测试
