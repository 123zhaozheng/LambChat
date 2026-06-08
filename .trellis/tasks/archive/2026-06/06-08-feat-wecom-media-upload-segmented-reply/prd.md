# feat-wecom-media-upload-segmented-reply

## Goal

补全 WeCom (企业微信) 渠道的三个缺失功能：文件上传发送、语音消息简化、长消息分段回复，使 Agent 产出的图片/文件能自动发送到企业微信，超长回复自动分段显示。

## What I already know

* 企业微信 AI Bot 长连接模式下，语音消息**已由企微服务端自动转文字**推送给机器人（`voice` msgtype 附带转写文本），无需额外 ASR
* 发送媒体文件流程：`upload_media(file_data, type, filename)` → 返回 `media_id` → `reply_media(frame, media_type, media_id)` 或 `send_media_message(chatid, media_type, media_id)`
* 当前 `WeComChannel.send_image()`/`send_file()` API 签名有 bug：直接传 `image_path`/`file_path` 给 `reply_media`/`send_media_message`，但 SDK 要求先 `upload_media()` 获取 `media_id`
* 飞书 handler 已有完整的 `upload_and_send_files()` 模式：S3 → NamedTemporaryFile → upload → send，WeCom handler 的 `_process_events` 对 `EVENT_TOOL_RESULT` 只有 `logger.debug` 占位
* openclaw-wechat 实现了按 UTF-8 字节边界精确分割长消息（2048 字节限制），通过 `aibot_send_msg` 逐条推送多气泡
* PicoClaw 的流式回复最小发送间隔为 500ms，最大持续时长 5.5 分钟

## Assumptions (resolved)

* `wecom-aibot-sdk>=1.0.7` 已安装且支持 `upload_media()`、`reply_media()`、`send_media_message()`
* 企微 AI Bot 被动回复（`aibot_respond_msg`）每个用户消息只能产生一个气泡，多气泡需用 `aibot_send_msg`（主动推送）
* 长消息分段限制为 2048 字节（UTF-8 编码），企微 markdown 消息的实际限制

## Requirements

### 1. 文件上传发送 (高优先级)
- handler.py `_process_events` 中处理 `EVENT_TOOL_RESULT`，提取 Agent 产出的文件信息
- 复用飞书 handler_helpers 中的 `_extract_tool_media_files()`、`_media_file_info_from_entry()` 等工具函数
- WeComResponseCollector 添加 `upload_and_send_files()` 方法：S3 → temp file → `upload_media()` → `send_media_message()`
- 修复 WeComChannel `send_image()`/`send_file()` 的 API 签名：先 upload 获取 media_id，再 reply/send

### 2. 语音消息简化 (低优先级)
- `_on_voice_message` 中读取 `body.voice.content`（企微已转写的文字）作为消息内容
- **移除** `auto_transcribe_audio` 和 `audio_transcribe_prompt` 配置字段（企微已内置转写）
- 移除 schemas/wecom.py 中的相关字段，前端配置表单也移除对应 UI
- 语音消息始终将企微转写文本作为内容传递给 Agent

### 3. 长消息分段回复 (中优先级)
- WeComConfig 新增 `segmented_reply: bool = True` 配置字段
- 超过 2048 UTF-8 字节的回复自动分段，通过 `aibot_send_msg` 逐条推送
- 按 UTF-8 字节边界精确分割（不截断多字节字符）
- 分段功能在流式回复 finalize 后和非流式回复中均需支持
- `segmented_reply=False` 时超长内容仍在单气泡中（企微自动截断）

## Acceptance Criteria

- [ ] Agent 产出的图片文件能自动上传并发送到企业微信（单聊和群聊）
- [ ] Agent 产出的代码文件/文档能自动上传并发送到企业微信
- [ ] 用户发送语音消息后，机器人收到企微已转写的文字内容（不再附加 audio_transcribe_prompt）
- [ ] `auto_transcribe_audio` 和 `audio_transcribe_prompt` 配置字段已移除
- [ ] `segmented_reply=True` 时，超过 2048 UTF-8 字节的回复被正确分段发送，每段独立气泡
- [ ] `segmented_reply=False` 时，超长内容在单气泡中发送
- [ ] 短回复（< 2048 字节）不受分段影响，正常单气泡发送
- [ ] 流式回复超时回退时也能正确分段
- [ ] 前端 WeComPanelForm 显示分段回复开关，移除语音转写相关 UI

## Definition of Done

* 文件发送和分段回复在单聊和群聊场景下均可用
* Lint / typecheck 通过
* 现有功能不受影响（流式回复、欢迎语、思考占位等继续正常工作）
* 已移除的配置字段不影响已有配置的加载（向后兼容）

## Decision (ADR-lite)

**Context**: 需要决定分段回复是否可配置、语音转写配置是否保留
**Decision**:
1. 分段回复为可选配置（`segmented_reply` 字段，默认 true），用户可在前端关闭
2. 移除 `auto_transcribe_audio` 和 `audio_transcribe_prompt`，因为企微已内置语音转文字
**Consequences**: 用户可控制分段行为；语音处理更简洁但失去配置灵活性（后续如需云端 ASR 增强需重新加回配置）

## Out of Scope (explicit)

* 云端 ASR 增强（百炼 qwen3-asr-flash 等）— 企微已内置转写，后续可扩展
* 视频/语音媒体回复（Agent 产出视频/音频发送到企微）— 降级为文件发送
* 接收端语音/视频的下载和转交给 Agent 分析 — 当前已以 `[voice]`/`[video]` 占位

## Technical Notes

* 关键文件：`src/infra/channel/wecom/handler.py`、`src/infra/channel/wecom/channel.py`、`src/kernel/schemas/wecom.py`
* 复用飞书模式：`src/infra/channel/feishu/handler_helpers.py` 中的 `_extract_tool_media_files()`、`_download_storage_object_to_file()`
* SDK API：`wecom-aibot-sdk>=1.0.7` 的 `upload_media(file_data, type, filename)` → `reply_media(frame, media_type, media_id)` / `send_media_message(chatid, media_type, media_id)`
* 企微媒体类型：`image`、`file`、`voice`、`video`
* 参考 openclaw-wechat 的 UTF-8 字节分割实现：二分查找确保不截断多字节字符
* 前端文件：`frontend/src/components/panels/channel/wecom/WeComPanelForm.tsx`、`types.ts`、`constants.ts`、i18n 文件
