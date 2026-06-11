# Research: WeCom vs Feishu WebSocket Architecture Comparison for LambChat

- **Query**: Key differences between WeCom's WebSocket approach vs Feishu's lark-oapi WebSocket approach, with implementation implications
- **Scope**: Mixed (external API comparison + internal Feishu codebase analysis)
- **Date**: 2026-06-08

## Findings

### Connection Lifecycle Comparison

#### Feishu (lark-oapi) Flow

1. `lark.Client.builder().app_id().app_secret().build()` -- creates HTTP client
2. `EventDispatcherHandler.builder(encrypt_key, verification_token).register_p2_im_message_receive_v1(handler).build()` -- creates event handler
3. `lark.ws.Client(app_id, app_secret, event_handler=event_handler, auto_reconnect=True)` -- creates WS client
4. SDK internally: connects WS -> authenticates -> receives events -> dispatches to handlers
5. **Sending replies**: Separate HTTP API calls via `client.im.v1.message.create()` etc.
6. Process-global loop shared by all tenants (`_lark_ws_client.loop`)

Key implementation detail from `src/infra/channel/feishu/channel.py`:
- Uses `_ensure_feishu_ws_loop()` to create a dedicated thread with shared asyncio event loop
- Patches SDK's private `_lark_ws_client.loop` to point to this shared loop
- Calls private SDK methods: `_connect()`, `_ping_loop()`, `_disconnect()`
- Override SDK defaults: `_reconnect_interval=10` (default 120s), `_reconnect_nonce=5` (default 30s)

#### WeCom (wecom-aibot-sdk) Flow

1. `WSClient(bot_id="...", secret="...")` -- creates WS client
2. `client.on("message.text", handler)` -- registers event handlers
3. `await client.connect()` -- connects WS, auto-sends `aibot_subscribe`, auto-starts heartbeat
4. SDK internally: connects WS -> authenticates via `aibot_subscribe` -> receives callbacks -> emits events
5. **Sending replies**: On the SAME WebSocket connection via `aibot_respond_msg`
6. Each WSClient has its own connection; no process-global loop

### Architectural Mapping: Feishu -> WeCom

| Feishu Component | WeCom Equivalent | Notes |
|---|---|---|
| `FeishuConfig(app_id, app_secret, encrypt_key, verification_token)` | `WeComConfig(bot_id, secret)` | Simpler: no encrypt_key/verification_token |
| `lark.Client.builder().build()` | N/A | WeCom sends on WS, no separate HTTP client needed |
| `lark.ws.Client()` | `WSClient()` | Different API but same concept |
| `EventDispatcherHandler.builder().register_p2_im_message_receive_v1()` | `client.on("message", handler)` | WeCom uses EventEmitter pattern |
| `client.im.v1.message.create()` (HTTP) | `client.reply(frame, body)` (WS) | WeCom sends on same WS connection |
| `FeishuSenderMixin` (HTTP API sends) | Not needed | WeCom replies on WS |
| `FeishuMarkdownAdapter` | Direct Markdown string | WeCom supports Markdown natively in `aibot_respond_msg` |
| CardKit streaming (create/update/finalize card) | `reply_stream(frame, stream_id, content, finish=False/True)` | WeCom native streaming is much simpler |
| `lark.register_app()` QR registration | N/A | No equivalent; manual bot creation only |
| `FeishuChannelManager` with Redis leases | `WeComChannelManager` with Redis leases | Same pattern applicable |
| `_ensure_feishu_ws_loop()` shared thread | Each WSClient has own connection | May want shared loop for efficiency |
| `_add_reaction(message_id, emoji)` | No reaction support in AI Bot API | WeCom AI Bot does not have reactions |
| Health check with `_is_connection_healthy()` | SDK has built-in heartbeat monitoring | Less need for custom health check |

### Streaming Implementation Comparison

#### Feishu Streaming (Current Implementation)

```python
# From src/infra/channel/feishu/handler.py
# 1. Create streaming card
card_id = await client.create_stream_card(initial_content)
# 2. Send card as message
sent, message_id = await client.send_card_by_id(chat_id, card_id)
# 3. Update card with new content (debounced)
success = await client.update_stream_card(card_id, content, sequence)
# 4. Finalize card
success = await client.finalize_stream_card(card_id, final_content, final_sequence)
```

This is a 4-step process involving HTTP API calls for each step.

#### WeCom Streaming (Simpler)

```python
# Direct on WebSocket
# 1. Initial streaming chunk (satisfies 5s deadline)
await client.reply_stream(frame, stream_id, "Processing...", finish=False)
# 2. Subsequent chunks
await client.reply_stream(frame, stream_id, chunk_text, finish=False)
# 3. Final chunk
await client.reply_stream(frame, stream_id, final_text, finish=True)
```

This is a single method call per chunk, all on the WebSocket connection. No card creation, no debouncing needed (though debouncing still recommended for performance).

### Config Schema Comparison

#### FeishuConfig (existing)

```python
class FeishuConfigBase(BaseModel):
    instance_id: str = ""
    app_id: str          # Required
    app_secret: str      # Required
    encrypt_key: str     # Optional
    verification_token: str  # Optional
    react_emoji: str     # "THUMBSUP"
    group_policy: FeishuGroupPolicy  # "open" | "mention"
    stream_reply: bool    # True
    auto_transcribe_audio: bool  # True
    audio_transcribe_prompt: str
    enabled: bool
```

#### Proposed WeComConfig (based on research)

```python
class WeComConfigBase(BaseModel):
    instance_id: str = ""
    bot_id: str           # Required (was app_id)
    secret: str           # Required (was app_secret)
    # No encrypt_key or verification_token needed
    # No react_emoji (WeCom AI Bot doesn't support reactions)
    group_policy: WeComGroupPolicy  # "open" | "mention"
    stream_reply: bool     # True
    auto_transcribe_audio: bool  # True
    audio_transcribe_prompt: str
    enabled: bool
    # WeCom-specific additions:
    send_thinking_message: bool  # Send placeholder within 5s
    # websocket_url override for private deployments
    websocket_url: str = "wss://openws.work.weixin.qq.com"
```

### ChannelType Addition Needed

```python
# src/kernel/schemas/channel.py currently has:
class ChannelType(str, Enum):
    FEISHU = "feishu"
    # WECHAT = "wechat"  # <-- commented out, needs to be added

# Should become:
class ChannelType(str, Enum):
    FEISHU = "feishu"
    WECOM = "wecom"
```

### Capabilities Comparison

| Capability | Feishu | WeCom |
|---|---|---|
| WEBSOCKET | Yes | Yes |
| WEBHOOK | Yes | Yes (different mode) |
| SEND_MESSAGE | Yes (HTTP) | Yes (WS) |
| SEND_IMAGE | Yes (HTTP upload) | Yes (WS + AES decrypt or upload) |
| SEND_FILE | Yes (HTTP upload) | Yes (WS + media upload) |
| REACTIONS | Yes | No (AI Bot doesn't support) |
| GROUP_CHAT | Yes | Yes |
| DIRECT_MESSAGE | Yes | Yes |
| STREAMING | Yes (CardKit) | Yes (native WS streaming) |
| WELCOME_MSG | No (no dedicated API) | Yes (aibot_respond_welcome_msg) |
| TEMPLATE_CARDS | Yes (CardKit) | Yes (native) |
| PROACTIVE_PUSH | Limited | Yes (aibot_send_msg) |

### Implementation Complexity Estimate

Compared to the Feishu implementation, a WeCom implementation would be:

- **Simpler**: No separate HTTP sender mixin, no CardKit streaming protocol, no encryption/verification, no registration flow
- **Similar**: Same BaseChannel/UserChannelManager pattern, same Redis lease coordination, same message deduplication, same group policy handling
- **Additional**: 5-second callback deadline handling, 6-minute stream timeout with fallback, thinking message placeholder

Estimated file structure (matching Feishu pattern):

```
src/infra/channel/wecom/
    __init__.py
    channel.py        # WeComChannel(BaseChannel)
    manager.py        # WeComChannelManager(UserChannelManager)
    handler.py        # WeComResponseCollector + message handler
    state.py          # ConnectionState (reuse from feishu or shared)
    sender.py         # Likely not needed (replies on WS)
```

## Caveats / Not Found

- WeCom AI Bot does not support message reactions (emoji reactions), so the `react_emoji` config field and reaction add/delete logic from Feishu has no WeCom equivalent. A "thinking message" (streaming placeholder) replaces the reaction-based processing indicator.
- The `userid` in WeCom AI Bot callbacks is an encrypted `open_userid` by default, requiring an additional API call to convert to plaintext if needed.
- No programmatic bot registration flow exists for WeCom (unlike Feishu's `register_app`), so the registration module is not needed.
- The official Python SDK is in "Beta" status (v1.0.2). API stability is not guaranteed.
- WeCom AI Bot streaming has a hard 6-minute timeout that requires explicit fallback logic.
