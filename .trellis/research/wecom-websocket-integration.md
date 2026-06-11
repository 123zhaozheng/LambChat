# Research: WeCom (企业微信) WebSocket Long Connection Integration

- **Query**: WeCom "长连接" (WebSocket) approach for receiving messages, Python SDK, API docs, open-source integrations, and comparison with Feishu/lark-oapi
- **Scope**: Mixed (external API/SDK research + internal Feishu codebase analysis)
- **Date**: 2026-06-08

## Findings

### WeCom Has Two Distinct Bot Architectures

WeCom provides **two completely different bot types**, each with different APIs, authentication, and message flows:

| Aspect | AI Bot (智能机器人) | Self-built App (自建应用) |
|---|---|---|
| **Creation** | Admin Console -> App Management -> AI Bot | Admin Console -> App Management -> Create App |
| **Credentials** | `bot_id` + `secret` | `corp_id` + `corp_secret` + `agent_id` |
| **WebSocket** | YES - `wss://openws.work.weixin.qq.com` | NO - requires HTTP webhook callback URL |
| **Streaming** | YES - native `aibot_respond_msg` streaming | NO - only complete message replies |
| **Message Format** | JSON over WebSocket frames | XML over HTTP POST (AES encrypted) |
| **Encryption** | NOT needed (wss:// transport encryption) | REQUIRED - AES-256-CBC with EncodingAESKey |
| **Heartbeat** | App-level `ping` every 30s | N/A (HTTP callback) |
| **Public IP** | NOT required | REQUIRED for callback URL |
| **Group Chat** | YES (user @mentions bot) | Limited |
| **Proactive Send** | YES (`aibot_send_msg`) | YES (via HTTP API with `access_token`) |
| **Official Doc** | https://developer.work.weixin.qq.com/document/path/101463 | https://developer.work.weixin.qq.com/document/path/90238 |

**Key Decision**: The AI Bot (智能机器人) mode with WebSocket long connection is the right choice for LambChat -- it matches the Feishu pattern (no public IP needed, streaming support, WebSocket-based).

### WebSocket Long Connection Protocol (AI Bot Mode)

#### Connection Flow

```
Developer Server                    WeCom Server
     |                                  |
     |--- 1. WebSocket connect -------->|  wss://openws.work.weixin.qq.com
     |<-- 2. WebSocket handshake OK ----|
     |--- 3. aibot_subscribe ---------->|  { bot_id, secret }
     |<-- 4. Subscribe result ----------|  success/failure
     |                                  |
     |--- 5. ping (every 30s) --------->|  Heartbeat keep-alive
     |<-- 6. pong ----------------------|  ACK
     |                                  |
     |<-- 7. aibot_msg_callback --------|  User sent a message
     |--- 8. aibot_respond_msg -------->|  Reply (streaming or complete)
     |                                  |
     |<-- 9. aibot_event_callback ------|  Enter chat / card click / feedback
     |--- 10. aibot_respond_welcome_msg>|  Welcome message (5s deadline)
```

#### Key WebSocket Commands (Frames)

| Command | Direction | Description |
|---|---|---|
| `aibot_subscribe` | Developer -> WeCom | Authentication with `bot_id` + `secret` |
| `aibot_msg_callback` | WeCom -> Developer | Inbound user message |
| `aibot_event_callback` | WeCom -> Developer | Inbound event (enter_chat, template_card_event, feedback_event, disconnected_event) |
| `aibot_respond_msg` | Developer -> WeCom | Reply to message (streaming, markdown, card, file, voice, image, video) |
| `aibot_respond_welcome_msg` | Developer -> WeCom | Welcome message reply (5s deadline) |
| `aibot_respond_update_msg` | Developer -> WeCom | Update template card (5s deadline) |
| `aibot_send_msg` | Developer -> WeCom | Proactive push message (no callback needed) |
| `ping` | Developer -> WeCom | Heartbeat |
| `pong` | WeCom -> Developer | Heartbeat ACK |

#### Message Callback Payload Structure (aibot_msg_callback)

```json
{
  "cmd": "aibot_msg_callback",
  "frame_id": "unique-frame-id",
  "req_id": "unique-request-id",
  "msgid": "unique-message-id",
  "aibotid": "bot-id",
  "chatid": "chat-id",
  "chattype": "single|group",
  "from": {
    "userid": "encrypted-user-id",
    "name": "User Display Name"
  },
  "msgtype": "text|image|voice|video|file|mixed|link",
  "text": { "content": "message text" },
  "image": { "aes_key": "...", "md5": "...", "pic_url": "..." },
  "voice": { "aes_key": "...", "md5": "...", "voice_url": "..." },
  "file": { "aes_key": "...", "md5": "...", "file_url": "...", "file_name": "..." },
  "quote": { ... }  // Quoted message context
}
```

#### Streaming Reply Protocol

Long connection mode does NOT use the "stream-refresh" polling mechanism from the webhook mode. Instead, the developer actively pushes stream updates:

```python
# Stream chunk (finish=False means more coming)
await client.reply_stream(frame, stream_id, "partial content", finish=False)

# Final chunk (finish=True ends the stream)
await client.reply_stream(frame, stream_id, "final content", finish=True)
```

- Streaming timeout: 6 minutes from first stream send
- Must send initial reply within 5 seconds of receiving callback
- If streaming times out, fall back to `aibot_send_msg` (24-hour validity)

### Python SDKs for WeCom AI Bot WebSocket

#### 1. Official: `wecom-aibot-python-sdk` (WecomTeam on GitHub)

**Package**: `pip install wecom-aibot-python-sdk` (v1.0.2)
**Repo**: https://github.com/WecomTeam/wecom-aibot-python-sdk
**Also available as**: `pip install wecom-aibot-sdk` (v1.0.7, by mattzwang, same codebase)

This is the official Python SDK from Tencent's WeCom team, a port of the Node.js `@wecom/aibot-node-sdk`.

**Dependencies**: `websockets>=12.0`, `pyee>=11.0`, `pycryptodome>=42.0`, `certifi>=2023.1.0`

**Usage Pattern**:
```python
import asyncio
from wecom_aibot_sdk import WSClient

async def main():
    client = WSClient(
        bot_id="your-bot-id",
        secret="your-bot-secret",
    )

    # Event listeners
    client.on("message.text", lambda frame: print(f"Text: {frame}"))
    client.on("message.image", lambda frame: print(f"Image: {frame}"))
    client.on("event.enter_chat", lambda frame: ...)

    # Connect
    await client.connect()

    # In message handler: streaming reply
    # await client.reply_stream(frame, stream_id, "chunk", finish=False)

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await client.disconnect()

asyncio.run(main())
```

**WSClient API**:

| Method | Description | Returns |
|---|---|---|
| `await connect()` | Establish WS + auto-authenticate | `WSClient` (chainable) |
| `disconnect()` | Close connection | `None` |
| `on(event, handler)` | Register event listener (sync/async) | `WSClient` (chainable) |
| `off(event, handler?)` | Remove event listener | `WSClient` |
| `await reply(frame, body, cmd?)` | Generic reply | `WsFrame` |
| `await reply_stream(frame, stream_id, content, finish?, msg_item?, feedback?)` | Streaming text reply (Markdown) | `WsFrame` |
| `await reply_welcome(frame, body)` | Welcome reply (5s deadline) | `WsFrame` |
| `await reply_template_card(frame, template_card, feedback?)` | Template card reply | `WsFrame` |
| `await reply_stream_with_card(frame, stream_id, content, finish?, ...)` | Stream + card combo | `WsFrame` |
| `await update_template_card(frame, template_card, userids?)` | Update card (5s deadline) | `WsFrame` |
| `await send_message(chatid, body)` | Proactive push (Markdown/card) | `WsFrame` |
| `await download_file(url, aes_key?)` | Download + optional AES decrypt | `tuple[bytes, str?]` |
| `run()` | Convenience: create event loop + connect | `None` |

**Supported Events**:

| Event | Callback Data | Description |
|---|---|---|
| `connected` | - | WS connection established |
| `authenticated` | - | Auth success |
| `disconnected` | `reason: str` | Connection lost |
| `reconnecting` | `attempt: int` | Reconnecting attempt N |
| `error` | `error: Exception` | Error occurred |
| `message` | `frame: WsFrame` | Any message type |
| `message.text` | `frame: WsFrame` | Text message |
| `message.image` | `frame: WsFrame` | Image message |
| `message.mixed` | `frame: WsFrame` | Mixed content message |
| `message.voice` | `frame: WsFrame` | Voice message |
| `message.file` | `frame: WsFrame` | File message |
| `message.video` | `frame: WsFrame` | Video message |
| `event` | `frame: WsFrame` | Any event |
| `event.enter_chat` | `frame: WsFrame` | User entered chat |
| `event.template_card_event` | `frame: WsFrame` | Card button clicked |
| `event.feedback_event` | `frame: WsFrame` | User feedback |
| `event.disconnected_event` | `frame: WsFrame` | Server disconnected (new connection replaced) |

**Built-in Features**:
- Auto heartbeat (ping every 30s)
- Exponential backoff reconnection (1s -> 2s -> 4s -> ... -> 30s max)
- Auto authentication on connect
- Message deduplication via `msgid`
- File download with AES-256-CBC decryption

#### 2. Community: `wecom-aibot-sdk-python` (v0.1.7)

**Package**: `pip install wecom-aibot-sdk-python`
**Repo**: https://github.com/chengyongru/wecom_aibot_sdk

Additional features over official SDK:
- `upload_media(file_path)` - 3-step WS media upload
- `reply_media(frame, file_path)` - Upload + media reply
- `send_media_message(chatid, file_path)` - Upload + proactive media send

#### 3. Community: `wecom-ws-channel` (v1.0.0)

**Package**: `pip install wecom-ws-channel`

Standalone implementation with:
- HTTP/HTTPS proxy support
- Simplified callback API (`channel.on_message = lambda msg: ...`)
- `send_text`, `send_image`, `send_file`, `send_mixed` convenience methods
- `encoding_aes_key` for message encryption
- Custom heartbeat interval

#### 4. Other WeCom SDKs (NOT for AI Bot WebSocket)

| Package | Description | Relevance |
|---|---|---|
| `wechatpy` (v1.8.14, 4.2K stars) | WeChat/WeCom general SDK | Supports self-built app API but NOT AI Bot WebSocket |
| `wecomkit` (v0.1.0) | Async httpx-based SDK | corp_id/corp_secret API only, no WS |
| `wecom_sdk` (v1.0.0) | Basic SDK | HTTP API only, no WS |
| `wecom-doc-sdk` (v0.6.0) | Document SDK | Not relevant |

### Open Source Projects Integrating WeCom AI Bot with Chatbots

#### 1. PicoClaw (26K stars, Go)

**Repo**: https://github.com/sipeed/picoclaw
**Docs**: https://docs.picoclaw.io/docs/channels/wecom/

Unified WeCom channel using AI Bot WebSocket API. Consolidated three legacy modes (wecom/wecom_app/wecom_aibot) into one `channels.wecom` config.

**Config model**:
```json
{
  "channels": {
    "wecom": {
      "enabled": true,
      "bot_id": "YOUR_BOT_ID",
      "secret": "YOUR_SECRET",
      "websocket_url": "wss://openws.work.weixin.qq.com",
      "send_thinking_message": true,
      "allow_from": [],
      "reasoning_channel_id": ""
    }
  }
}
```

Key features: QR-based onboarding, streaming replies, media upload/download, proactive push, sender allowlist.

#### 2. OpenClaw WeCom Plugin (Node.js, official by Tencent WeCom team)

**Package**: `@wecom/wecom-openclaw-plugin`
**Repo**: https://github.com/WecomTeam/wecom-openclaw-plugin

Dual-mode: Bot (WebSocket/Webhook) + Agent (HTTP API). Bot-first with Agent fallback for media/timeout.

**Config**:
```yaml
channels:
  wecom:
    botId: "your-bot-id"
    secret: "your-bot-secret"
    websocketUrl: "wss://openws.work.weixin.qq.com"
    sendThinkingMessage: true
    connectionMode: websocket  # or webhook
    # Agent mode (optional):
    corpId: "ww..."
    agentId: 1000002
    corpSecret: "..."
```

#### 3. OpenClaw Community WeCom Plugin (@sunnoy/wecom)

Enhanced community plugin with: multi-account management, dynamic Agent isolation, MCP document/smart-table capabilities, command whitelist, quota awareness.

#### 4. CodeBuddy (CLI)

Uses WeCom AI Bot WebSocket for remote code editing. Streaming reply with 5-minute timeout and `aibot_send_msg` fallback.

#### 5. Hermes Adapter

Python adapter using WeCom AI Bot WebSocket. Configurable DM/group policies, per-group sender whitelists, AES media decryption, auto-reconnect.

### WeCom WebSocket vs Feishu lark-oapi WebSocket: Key Differences

| Aspect | WeCom AI Bot WS | Feishu lark-oapi WS |
|---|---|---|
| **SDK** | `wecom-aibot-sdk` (standalone) | `lark-oapi` (monolithic, includes WS) |
| **Connection URL** | `wss://openws.work.weixin.qq.com` | `wss://open.larkoffice.com` (SDK handles) |
| **Auth Credentials** | `bot_id` + `secret` | `app_id` + `app_secret` |
| **Auth Command** | `aibot_subscribe` frame | SDK internal `_connect()` method |
| **Event Handler Registration** | `.on("message.text", handler)` pattern | `EventDispatcherHandler.builder().register_p2_im_message_receive_v1(handler)` |
| **Message Callback** | `aibot_msg_callback` frame | `p2_im_message_receive_v1` event |
| **Reply Mechanism** | `aibot_respond_msg` frame on same WS | Separate HTTP API call (not on WS) |
| **Streaming Reply** | Native via `aibot_respond_msg` with `finish=false/true` | NOT native on WS; uses CardKit streaming (separate HTTP API) |
| **Proactive Send** | `aibot_send_msg` on WS connection | HTTP API `im/v1/messages` with `access_token` |
| **Heartbeat** | App-level `ping` every 30s (developer responsibility) | SDK internal `_ping_loop()` |
| **Message Format** | JSON in WS frames | Protobuf/binary in WS, JSON parsed by SDK |
| **Encryption** | NOT needed (wss:// TLS) | Optional `encrypt_key` + `verification_token` |
| **File Download** | URL + AES key for decryption | SDK helper via HTTP API |
| **Welcome Message** | `aibot_respond_welcome_msg` (5s deadline) | No dedicated welcome; `im.message.receive_v1` handles |
| **Template Cards** | Native support + button events | CardKit (different protocol) |
| **Multi-tenant** | One WSClient = one bot, separate connections | Shared event loop, multiple tenants on same loop |
| **SDK Architecture** | Clean async, `websockets` + `pyee` | Heavy SDK, uses private `_connect()`/`_disconnect()` APIs |
| **Callback Timeout** | 5 seconds to send initial reply | No explicit timeout (webhook-style) |
| **Stream Timeout** | 6 minutes max | No hard limit (CardKit streaming) |

**Critical Architectural Difference**: In WeCom, replies go back ON THE SAME WebSocket connection (`aibot_respond_msg`). In Feishu, replies are sent via SEPARATE HTTP API calls (`/im/v1/messages`). This means:
- WeCom: lower latency, simpler (one connection for bidirectional)
- Feishu: more decoupled, but requires HTTP API for sending

**Streaming Architecture Difference**: WeCom has native streaming in the WebSocket protocol itself (`aibot_respond_msg` with `finish=false`/`true`). Feishu streaming uses CardKit, a completely separate HTTP-based streaming card update system (create card -> send card -> update card -> finalize card).

### Internal Project Files Found

| File Path | Description |
|---|---|
| `src/infra/channel/base.py` | BaseChannel abstract class and UserChannelManager -- WeCom channel should extend these |
| `src/infra/channel/feishu/channel.py` | FeishuChannel implementation with lark-oapi WS -- primary reference for WeCom implementation |
| `src/infra/channel/feishu/manager.py` | FeishuChannelManager with lease-based distributed coordination |
| `src/infra/channel/feishu/handler.py` | FeishuResponseCollector with CardKit streaming -- WeCom uses different streaming approach |
| `src/infra/channel/feishu/registration.py` | Feishu one-click app registration (lark.register_app) -- no WeCom equivalent |
| `src/infra/channel/feishu/sender.py` | FeishuSenderMixin for HTTP API sends -- WeCom sends on WS directly |
| `src/infra/channel/feishu/state.py` | ConnectionState enum -- reusable for WeCom |
| `src/kernel/schemas/channel.py` | ChannelType enum (has FEISHU, needs WECOM) |
| `src/kernel/schemas/feishu.py` | FeishuConfig schema -- template for WeComConfig |
| `pyproject.toml` | Dependencies (has `lark-oapi>=1.5.3,<1.7`, needs `wecom-aibot-sdk`) |

### WeCom-Specific Considerations for LambChat Implementation

1. **SDK Choice**: Use `wecom-aibot-sdk` (official WecomTeam Python SDK). It is clean async, well-maintained, and matches the project's asyncio architecture.

2. **No Registration Flow**: Unlike Feishu's `lark.register_app()` QR-based registration, WeCom AI Bot does not offer a programmatic registration flow. Users must manually create the bot in WeCom admin console and input `bot_id` + `secret`.

3. **Reply on Same Connection**: WeCom replies go through the WS connection, not a separate HTTP API. This simplifies the sender architecture (no need for a separate FeishuSenderMixin equivalent).

4. **Streaming is Simpler**: WeCom native streaming via `aibot_respond_msg` is simpler than Feishu CardKit streaming. No need for card creation/update/finalize cycle.

5. **File Handling**: Media files come with `aes_key` for AES-256-CBC decryption. The SDK provides `download_file(url, aes_key)` for this.

6. **5-Second Callback Deadline**: Must send initial reply (even a streaming placeholder) within 5 seconds of receiving a message callback.

7. **6-Minute Stream Timeout**: Streaming replies have a 6-minute maximum. Need fallback to `aibot_send_msg` for long-running tasks.

8. **No Encrypt Key / Verification Token**: Unlike Feishu, WeCom WS mode does not need `encrypt_key` or `verification_token`. This simplifies the config schema.

9. **Group Message Policy**: Similar to Feishu -- bots are @mentioned in groups. The `group_policy` concept (open/mention) maps directly.

10. **Multi-Tenant**: Each WSClient is one bot with its own connection. Unlike lark-oapi which shares a process-global loop, wecom-aibot-sdk creates independent connections. Each tenant needs its own WSClient instance.

## Caveats / Not Found

- The WeCom AI Bot WebSocket API is relatively new (docs dated 2026-05-18). The official Python SDK (`wecom-aibot-python-sdk`) is at v1.0.2 with "Beta" status on PyPI.
- There are multiple PyPI packages with confusingly similar names: `wecom-aibot-python-sdk` (official), `wecom-aibot-sdk` (community fork with extras), `wecom-aibot-sdk-python` (another community fork). The official one is from WecomTeam on GitHub.
- The WeCom AI Bot `userid` field is an "encrypted userid" (`open_userid`) by default, unless the bot creator is a super admin. Converting to plaintext requires a self-built app API call (`openuserid_to_userid`), which is a separate integration path.
- WeCom AI Bot does NOT support the "one-click registration" flow that Feishu provides via `lark.register_app()`. Users must manually configure the bot in the admin console.
- The streaming timeout (6 minutes) is a hard limit. For long-running AI tasks, the implementation must include a fallback to `aibot_send_msg` proactive push.
- WeCom AI Bot currently only supports up to 3 concurrent messages per user per bot.
