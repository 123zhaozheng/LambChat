"""
WeCom (企业微信) AI Bot channel implementation using wecom-aibot-sdk WebSocket long connection.

Supports per-user bot configurations - each user can have their own WeCom AI Bot.
Replies go back on the SAME WebSocket connection (aibot_respond_msg).
"""

import asyncio
import importlib.util
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

from src.infra.channel.wecom.state import ConnectionState
from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.schemas.wecom import (
    WeComConfig,
    WeComGroupPolicy,
)

logger = get_logger(__name__)

_DEFAULT_WELCOME_MESSAGE = "你好！我是 AI 助手，有什么可以帮你的吗？"

WECOM_AVAILABLE = importlib.util.find_spec("wecom_aibot_sdk") is not None
_PROCESSED_MESSAGE_TTL_SECONDS = 15 * 60
_PROCESSED_MESSAGE_CACHE_MAX = 1000


def _frame_body(frame: Any) -> dict[str, Any]:
    """Extract the message body from a WsFrame.

    The SDK's WsFrame is a dict subclass. Message callbacks carry
    message-type-specific content (text, image, file, etc.) inside ``body``.
    Metadata fields (chatid, chattype, from, msgid, aibotid) are at the
    top level of the frame dict, not inside body.
    Top-level keys also include ``cmd``, ``headers``.
    """
    if hasattr(frame, "get"):
        return frame.get("body", {}) or {}
    # Fallback: if frame IS the body (no wrapping), return as-is
    if isinstance(frame, dict):
        return frame
    return {}


def _frame_top(frame: Any, key: str, default: str = "") -> str:
    """Read a top-level key from a WsFrame (cmd, frame_id, req_id, etc.)."""
    if hasattr(frame, "get"):
        return frame.get(key, default) or default
    return default


class WeComChannel:
    """WeCom (企业微信) AI Bot channel implementation for a single user."""

    def __init__(self, config: WeComConfig, message_handler: Optional[Callable] = None):
        self.config = config
        self.message_handler = message_handler
        self._running = False
        self._ws_client: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()

        # Connection state tracking
        self._connection_state = ConnectionState.DISCONNECTED
        self._last_activity_time = 0.0

        # Store the latest frame for each chat to support reply on same WS
        self._pending_frames: dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        return self._running

    @property
    def user_id(self) -> str:
        """Get the user ID this channel belongs to."""
        return getattr(self.config, "user_id", "unknown")

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Handle an incoming message from the chat platform.

        Forwards the message to the registered message handler.
        """
        if not self.message_handler:
            logger.warning(f"No message handler registered for WeCom channel")
            return

        try:
            enriched_metadata = metadata or {}
            instance_id = getattr(self.config, "instance_id", None)
            if instance_id and "instance_id" not in enriched_metadata:
                enriched_metadata["instance_id"] = instance_id

            await self.message_handler(
                user_id=self.user_id,
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=enriched_metadata,
            )
        except Exception as e:
            logger.error(f"Error handling message on WeCom: {e}")

    # -- Connection state management --

    def _set_connection_state(self, new_state: ConnectionState) -> None:
        """Update connection state with logging."""
        old_state = self._connection_state
        if old_state != new_state:
            self._connection_state = new_state
            logger.info(
                f"WeCom connection state changed for user {self.config.user_id}: "
                f"{old_state.value} -> {new_state.value}"
            )
            if new_state == ConnectionState.CONNECTED:
                self._last_activity_time = time.time()

    def _get_connection_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._connection_state

    def _update_activity_time(self) -> None:
        """Update last activity timestamp."""
        self._last_activity_time = time.time()

    # -- Start / Stop --

    async def start(self) -> bool:
        """Start the WeCom AI Bot with WebSocket long connection."""
        if not WECOM_AVAILABLE:
            logger.error(
                f"WeCom SDK not installed for user {self.config.user_id}. "
                "Run: pip install wecom-aibot-sdk"
            )
            return False

        if not self.config.bot_id or not self.config.secret:
            logger.error(
                f"WeCom bot_id and secret not configured for user {self.config.user_id}"
            )
            return False

        self._running = True
        self._loop = asyncio.get_running_loop()
        self._set_connection_state(ConnectionState.CONNECTING)

        try:
            from wecom_aibot_sdk import WSClient

            ws_url = self.config.websocket_url or "wss://openws.work.weixin.qq.com"
            client = WSClient(
                bot_id=self.config.bot_id,
                secret=self.config.secret,
                ws_url=ws_url,
            )

            # Register event handlers
            client.on("authenticated", self._on_authenticated)
            client.on("disconnected", self._on_disconnected)
            client.on("error", self._on_error)
            client.on("message.text", self._on_text_message)
            client.on("message.image", self._on_image_message)
            client.on("message.file", self._on_file_message)
            client.on("message.voice", self._on_voice_message)
            client.on("message.video", self._on_video_message)
            client.on("message.mixed", self._on_mixed_message)
            client.on("event.enter_chat", self._on_enter_chat)
            client.on("event.template_card_event", self._on_template_card_event)
            client.on("event.feedback_event", self._on_feedback_event)

            await client.connect()
            self._ws_client = client
            self._set_connection_state(ConnectionState.CONNECTED)

            logger.info(
                f"WeCom AI Bot started for user {self.config.user_id} "
                f"with bot_id={self.config.bot_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"WeCom AI Bot failed to start for user {self.config.user_id}: {e}"
            )
            self._set_connection_state(ConnectionState.FAILED)
            self._running = False
            return False

    async def stop(self) -> None:
        """Stop the WeCom AI Bot."""
        self._running = False
        if self._ws_client is not None:
            try:
                self._ws_client.disconnect()
            except Exception as e:
                logger.warning(
                    f"Error disconnecting WeCom client for user {self.config.user_id}: {e}"
                )
            self._ws_client = None

        self._pending_frames.clear()
        self._set_connection_state(ConnectionState.DISCONNECTED)
        logger.info(f"WeCom AI Bot stopped for user {self.config.user_id}")

    # -- SDK lifecycle event handlers --

    async def _on_authenticated(self, *args: Any) -> None:
        """Handle successful authentication."""
        self._update_activity_time()
        self._set_connection_state(ConnectionState.CONNECTED)
        logger.info(
            f"WeCom bot authenticated for user {self.config.user_id}, "
            f"bot_id={self.config.bot_id}"
        )

    async def _on_disconnected(self, reason: str = "") -> None:
        """Handle disconnection event."""
        logger.warning(
            f"WeCom bot disconnected for user {self.config.user_id}: {reason}"
        )
        self._set_connection_state(ConnectionState.RECONNECTING)

    async def _on_error(self, error: Exception) -> None:
        """Handle error event from SDK."""
        logger.error(f"WeCom bot error for user {self.config.user_id}: {error}")
        self._set_connection_state(ConnectionState.FAILED)

    # -- Common frame parsing helpers --

    def _extract_common_fields(self, frame: Any) -> dict[str, Any] | None:
        """Extract common fields from a message callback frame.

        WeCom SDK WsFrame structure:
          - frame top-level: cmd, headers, body, errcode, errmsg
          - body: msgid, chattype, from, msgtype, text/image/file/voice/video, aibotid
          - chatid: present in group chats; ABSENT in single chats
          - For single chats, chatid = sender's userid (per WeCom API convention)

        Returns a dict with keys: msgid, chat_type, chat_id, sender_id, msg_type
        or None if dedup check fails.
        """
        body = _frame_body(frame)

        msgid = body.get("msgid", "")
        if not msgid:
            return None

        chat_type = body.get("chattype", "single")
        chat_id = body.get("chatid", "")

        from_info = body.get("from", {})
        sender_id = from_info.get("userid", "unknown") if isinstance(from_info, dict) else "unknown"

        # Single chats do not include chatid — use sender's userid instead
        # (per WeCom send_message API: 单聊填用户的 userid，群聊填对应群聊的 chatid)
        if not chat_id and chat_type == "single" and sender_id != "unknown":
            chat_id = sender_id

        msg_type = body.get("msgtype", "text")

        return {
            "msgid": msgid,
            "chat_type": chat_type,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "msg_type": msg_type,
        }

    # -- Message handlers --

    async def _on_text_message(self, frame: Any) -> None:
        """Handle incoming text message."""
        self._update_activity_time()
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)

        try:
            fields = self._extract_common_fields(frame)
            if not fields:
                return

            msgid = fields["msgid"]
            if not await self._mark_message_processed(msgid):
                return

            chat_type = fields["chat_type"]
            chat_id = fields["chat_id"]
            sender_id = fields["sender_id"]

            if chat_type == "group" and not self._is_group_message_for_bot(frame):
                logger.debug(
                    f"WeCom: skipping group message (not mentioned) "
                    f"for user {self.config.user_id}"
                )
                return

            body = _frame_body(frame)
            text_content = body.get("text", {}).get("content", "")
            if not text_content:
                return

            # Store frame for potential reply
            self._pending_frames[chat_id] = frame

            metadata = {
                "message_id": msgid,
                "chat_type": chat_type,
                "msg_type": "text",
                "sender_id": sender_id,
                "reply_chat_id": chat_id,
                "frame_id": _frame_top(frame, "frame_id"),
                "req_id": _frame_top(frame, "req_id"),
                "aibotid": body.get("aibotid", ""),
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=text_content,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                f"Error processing WeCom text message for user {self.config.user_id}: {e}"
            )

    async def _on_image_message(self, frame: Any) -> None:
        """Handle incoming image message."""
        self._update_activity_time()
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)

        try:
            fields = self._extract_common_fields(frame)
            if not fields:
                return

            msgid = fields["msgid"]
            if not await self._mark_message_processed(msgid):
                return

            chat_type = fields["chat_type"]
            chat_id = fields["chat_id"]
            sender_id = fields["sender_id"]

            if chat_type == "group" and not self._is_group_message_for_bot(frame):
                return

            self._pending_frames[chat_id] = frame

            body = _frame_body(frame)
            image_info = body.get("image", {})
            pic_url = image_info.get("pic_url", "") if isinstance(image_info, dict) else ""
            aes_key = image_info.get("aes_key", "") if isinstance(image_info, dict) else ""

            metadata = {
                "message_id": msgid,
                "chat_type": chat_type,
                "msg_type": "image",
                "sender_id": sender_id,
                "reply_chat_id": chat_id,
                "frame_id": _frame_top(frame, "frame_id"),
                "req_id": _frame_top(frame, "req_id"),
                "pic_url": pic_url,
                "aes_key": aes_key,
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content="[image]",
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                f"Error processing WeCom image message for user {self.config.user_id}: {e}"
            )

    async def _on_file_message(self, frame: Any) -> None:
        """Handle incoming file message."""
        self._update_activity_time()
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)

        try:
            fields = self._extract_common_fields(frame)
            if not fields:
                return

            msgid = fields["msgid"]
            if not await self._mark_message_processed(msgid):
                return

            chat_type = fields["chat_type"]
            chat_id = fields["chat_id"]
            sender_id = fields["sender_id"]

            if chat_type == "group" and not self._is_group_message_for_bot(frame):
                return

            self._pending_frames[chat_id] = frame

            body = _frame_body(frame)
            file_info = body.get("file", {})
            file_url = file_info.get("file_url", "") if isinstance(file_info, dict) else ""
            file_name = file_info.get("file_name", "") if isinstance(file_info, dict) else ""
            aes_key = file_info.get("aes_key", "") if isinstance(file_info, dict) else ""

            content = f"[file: {file_name}]" if file_name else "[file]"

            metadata = {
                "message_id": msgid,
                "chat_type": chat_type,
                "msg_type": "file",
                "sender_id": sender_id,
                "reply_chat_id": chat_id,
                "frame_id": _frame_top(frame, "frame_id"),
                "req_id": _frame_top(frame, "req_id"),
                "file_url": file_url,
                "file_name": file_name,
                "aes_key": aes_key,
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                f"Error processing WeCom file message for user {self.config.user_id}: {e}"
            )

    async def _on_voice_message(self, frame: Any) -> None:
        """Handle incoming voice message."""
        self._update_activity_time()
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)

        try:
            fields = self._extract_common_fields(frame)
            if not fields:
                return

            msgid = fields["msgid"]
            if not await self._mark_message_processed(msgid):
                return

            chat_type = fields["chat_type"]
            chat_id = fields["chat_id"]
            sender_id = fields["sender_id"]

            if chat_type == "group" and not self._is_group_message_for_bot(frame):
                return

            self._pending_frames[chat_id] = frame

            body = _frame_body(frame)
            voice_info = body.get("voice", {})
            voice_url = voice_info.get("voice_url", "") if isinstance(voice_info, dict) else ""
            aes_key = voice_info.get("aes_key", "") if isinstance(voice_info, dict) else ""

            # WeCom auto-transcribes voice messages — use the transcribed text if available
            transcribed = voice_info.get("content", "") if isinstance(voice_info, dict) else ""
            content = transcribed if transcribed else "[voice]"

            metadata = {
                "message_id": msgid,
                "chat_type": chat_type,
                "msg_type": "voice",
                "sender_id": sender_id,
                "reply_chat_id": chat_id,
                "frame_id": _frame_top(frame, "frame_id"),
                "req_id": _frame_top(frame, "req_id"),
                "voice_url": voice_url,
                "aes_key": aes_key,
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                f"Error processing WeCom voice message for user {self.config.user_id}: {e}"
            )

    async def _on_video_message(self, frame: Any) -> None:
        """Handle incoming video message."""
        self._update_activity_time()
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)

        try:
            fields = self._extract_common_fields(frame)
            if not fields:
                return

            msgid = fields["msgid"]
            if not await self._mark_message_processed(msgid):
                return

            chat_type = fields["chat_type"]
            chat_id = fields["chat_id"]
            sender_id = fields["sender_id"]

            if chat_type == "group" and not self._is_group_message_for_bot(frame):
                return

            self._pending_frames[chat_id] = frame

            metadata = {
                "message_id": msgid,
                "chat_type": chat_type,
                "msg_type": "video",
                "sender_id": sender_id,
                "reply_chat_id": chat_id,
                "frame_id": _frame_top(frame, "frame_id"),
                "req_id": _frame_top(frame, "req_id"),
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content="[video]",
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                f"Error processing WeCom video message for user {self.config.user_id}: {e}"
            )

    async def _on_mixed_message(self, frame: Any) -> None:
        """Handle incoming mixed content message."""
        self._update_activity_time()
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)

        try:
            fields = self._extract_common_fields(frame)
            if not fields:
                return

            msgid = fields["msgid"]
            if not await self._mark_message_processed(msgid):
                return

            chat_type = fields["chat_type"]
            chat_id = fields["chat_id"]
            sender_id = fields["sender_id"]

            if chat_type == "group" and not self._is_group_message_for_bot(frame):
                return

            self._pending_frames[chat_id] = frame

            # Mixed messages contain multiple content items
            body = _frame_body(frame)
            mixed_info = body.get("mixed", {})
            content_parts = []
            if isinstance(mixed_info, dict):
                items = mixed_info.get("items", [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("msgtype", "")
                    if item_type == "text":
                        text = item.get("text", {}).get("content", "")
                        if text:
                            content_parts.append(text)
                    elif item_type == "image":
                        content_parts.append("[image]")
                    else:
                        content_parts.append(f"[{item_type}]")

            content = "\n".join(content_parts) if content_parts else "[mixed]"

            metadata = {
                "message_id": msgid,
                "chat_type": chat_type,
                "msg_type": "mixed",
                "sender_id": sender_id,
                "reply_chat_id": chat_id,
                "frame_id": _frame_top(frame, "frame_id"),
                "req_id": _frame_top(frame, "req_id"),
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                f"Error processing WeCom mixed message for user {self.config.user_id}: {e}"
            )

    # -- Event handlers --

    async def _on_enter_chat(self, frame: Any) -> None:
        """Handle user entering chat event - send welcome message within 5s deadline."""
        self._update_activity_time()
        body = _frame_body(frame)
        chatid = body.get("chatid", "")
        logger.info(
            f"WeCom user entered chat for bot of user {self.config.user_id}: "
            f"chatid={chatid}"
        )

        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected, cannot send welcome for user {self.config.user_id}"
            )
            return

        try:
            welcome_body = {
                "msgtype": "markdown",
                "markdown": {"content": _DEFAULT_WELCOME_MESSAGE},
            }
            await self._ws_client.reply_welcome(frame, welcome_body)
            logger.info(
                f"WeCom welcome message sent for bot of user {self.config.user_id}, "
                f"chatid={chatid}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to send WeCom welcome message for user {self.config.user_id}: {e}"
            )

    async def _on_template_card_event(self, frame: Any) -> None:
        """Handle template card button click event - forward as user message."""
        self._update_activity_time()
        body = _frame_body(frame)
        chatid = body.get("chatid", "")

        logger.info(
            f"WeCom template card event for bot of user {self.config.user_id}: "
            f"chatid={chatid}, frame_id={_frame_top(frame, 'frame_id')}"
        )

        # Store frame for potential reply
        if chatid:
            self._pending_frames[chatid] = frame

        # Extract card action details
        card_event = body.get("template_card_event", {})
        action = card_event.get("action", {}) if isinstance(card_event, dict) else {}
        action_name = action.get("name", "") if isinstance(action, dict) else ""
        action_value = action.get("value", "") if isinstance(action, dict) else ""

        if not action_name and not action_value:
            return

        from_info = body.get("from", {})
        sender_id = from_info.get("userid", "unknown") if isinstance(from_info, dict) else "unknown"
        chat_type = body.get("chattype", "single")

        # Single chats: use sender_id as chatid for aibot_send_msg
        if not chatid and chat_type == "single" and sender_id != "unknown":
            chatid = sender_id

        content = (
            f"[card_action: {action_name}={action_value}]"
            if action_name
            else f"[card_action: {action_value}]"
        )

        metadata = {
            "message_id": body.get("msgid", ""),
            "chat_type": chat_type,
            "msg_type": "template_card_event",
            "sender_id": sender_id,
            "reply_chat_id": chatid,
            "frame_id": _frame_top(frame, "frame_id"),
            "req_id": _frame_top(frame, "req_id"),
            "card_action_name": action_name,
            "card_action_value": action_value,
        }

        await self._handle_message(
            sender_id=sender_id,
            chat_id=chatid,
            content=content,
            metadata=metadata,
        )

    async def _on_feedback_event(self, frame: Any) -> None:
        """Handle user feedback event."""
        self._update_activity_time()
        logger.info(
            f"WeCom feedback event for bot of user {self.config.user_id}: "
            f"frame_id={_frame_top(frame, 'frame_id')}"
        )

    # -- Group message policy --

    def _is_group_message_for_bot(self, frame: Any) -> bool:
        """Check if a group message should be processed by the bot."""
        if self.config.group_policy == WeComGroupPolicy.OPEN:
            return True
        # In mention mode, WeCom AI Bot only receives messages where the bot is @mentioned
        # The WeCom server filters this before sending to the WebSocket, so all received
        # messages in mention mode are already directed at the bot.
        return True

    # -- Message deduplication --

    async def _mark_message_processed(self, message_id: str) -> bool:
        """Mark a message as processed using local cache plus Redis NX dedupe."""
        if message_id in self._processed_message_ids:
            return False

        redis_claimed = True
        try:
            redis_client = get_redis_client()
            redis_claimed = bool(
                await redis_client.set(
                    f"wecom:processed:{message_id}",
                    self.config.instance_id or self.config.user_id,
                    nx=True,
                    ex=_PROCESSED_MESSAGE_TTL_SECONDS,
                )
            )
        except Exception as e:
            logger.warning(
                "WeCom distributed dedupe unavailable for message %s: %s",
                message_id,
                e,
            )

        if not redis_claimed:
            return False

        self._processed_message_ids[message_id] = None
        while len(self._processed_message_ids) > _PROCESSED_MESSAGE_CACHE_MAX:
            self._processed_message_ids.popitem(last=False)
        return True

    # -- Send message (reply on same WS) --

    async def send_message(self, chat_id: str, content: str, **kwargs: Any) -> bool:
        """Send a message through the WeCom WebSocket connection.

        WeCom replies go on the SAME WebSocket connection (aibot_respond_msg).

        Args:
            chat_id: The target chat/conversation ID.
            content: The message content (Markdown supported).
            **kwargs: Additional options (frame, body, cmd).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return False

        try:
            frame = kwargs.get("frame") or self._pending_frames.get(chat_id)
            if frame:
                body = kwargs.get(
                    "body",
                    {"msgtype": "markdown", "markdown": {"content": content}},
                )
                await self._ws_client.reply(frame, body)
                return True
            else:
                # Proactive send via aibot_send_msg (no frame needed)
                await self._ws_client.send_message(
                    chat_id,
                    {"msgtype": "markdown", "markdown": {"content": content}},
                )
                return True

        except Exception as e:
            logger.error(
                f"Error sending WeCom message for user {self.config.user_id}: {e}"
            )
            return False

    async def reply_stream(
        self,
        chat_id: str,
        stream_id: str,
        content: str,
        finish: bool = False,
    ) -> bool:
        """Send a streaming reply via the WebSocket connection.

        Uses aibot_respond_msg with streaming support. Each call replaces
        the previous content on the client side.

        Args:
            chat_id: The target chat/conversation ID.
            stream_id: Unique identifier for this streaming session.
            content: Full markdown content to display (not delta).
            finish: True to finalize the stream, False for more updates.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return False

        frame = self._pending_frames.get(chat_id)
        if not frame:
            logger.warning(
                f"No pending frame for chat {chat_id} (user {self.config.user_id})"
            )
            return False

        try:
            await self._ws_client.reply_stream(
                frame, stream_id, content, finish=finish
            )
            return True
        except Exception as e:
            logger.error(
                f"Error in WeCom stream reply for user {self.config.user_id}: {e}"
            )
            return False

    async def send_proactive_message(self, chat_id: str, content: str) -> bool:
        """Send a proactive message via aibot_send_msg.

        Used when no original frame is available (e.g. timeout fallback)
        or to push a message without a triggering callback.

        Args:
            chat_id: The target chat/conversation ID.
            content: The message content (Markdown supported).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return False

        try:
            body = {"msgtype": "markdown", "markdown": {"content": content}}
            await self._ws_client.send_message(chat_id, body)
            return True
        except Exception as e:
            logger.error(
                f"Error in WeCom proactive send for user {self.config.user_id}: {e}"
            )
            return False

    async def reply_message(
        self,
        chat_id: str,
        content: str,
        body: dict[str, Any] | None = None,
    ) -> bool:
        """Send a complete reply via the WebSocket connection (aibot_respond_msg).

        Falls back to proactive send if no pending frame is available.

        Args:
            chat_id: The target chat/conversation ID.
            content: The message content (Markdown supported).
            body: Optional pre-built message body. If None, builds markdown body.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return False

        frame = self._pending_frames.get(chat_id)
        try:
            if frame:
                if body is None:
                    body = {"msgtype": "markdown", "markdown": {"content": content}}
                await self._ws_client.reply(frame, body)
                return True
            else:
                # No frame available, fall back to proactive send
                return await self.send_proactive_message(chat_id, content)
        except Exception as e:
            logger.error(
                f"Error in WeCom reply for user {self.config.user_id}: {e}"
            )
            return False

    # -- Media sending (image/file via WS upload) --

    async def send_image(self, chat_id: str, image_path: str, **kwargs: Any) -> bool:
        """Send an image to a chat via WeCom AI Bot media upload.

        Two-step flow: upload_media(file_bytes) -> media_id,
        then reply_media(frame, media_id) or send_media_message(chatid, media_id).

        Args:
            chat_id: The target chat/conversation ID.
            image_path: Local file path of the image to send.
            **kwargs: Additional options (frame override).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return False

        if not hasattr(self._ws_client, "upload_media"):
            logger.warning(
                "WeCom SDK does not support upload_media (requires wecom-aibot-sdk>=1.0.7)"
            )
            return False

        try:
            import os

            if not os.path.isfile(image_path):
                logger.warning(f"WeCom image file not found: {image_path}")
                return False

            with open(image_path, "rb") as f:
                file_bytes = f.read()

            file_name = os.path.basename(image_path) or "image.png"

            upload_result = await self._ws_client.upload_media(
                file_bytes, type="image", filename=file_name
            )
            media_id = upload_result["media_id"]

            frame = kwargs.get("frame") or self._pending_frames.get(chat_id)
            if frame and hasattr(self._ws_client, "reply_media"):
                await self._ws_client.reply_media(frame, "image", media_id)
            else:
                if not hasattr(self._ws_client, "send_media_message"):
                    logger.warning(
                        "WeCom SDK does not support send_media_message "
                        "(requires wecom-aibot-sdk>=1.0.7)"
                    )
                    return False
                await self._ws_client.send_media_message(chat_id, "image", media_id)
            logger.info(
                f"WeCom image sent to chat {chat_id} for user {self.config.user_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error sending WeCom image for user {self.config.user_id}: {e}"
            )
            return False

    async def send_file(self, chat_id: str, file_path: str, file_name: str = "", **kwargs: Any) -> bool:
        """Send a file to a chat via WeCom AI Bot media upload.

        Two-step flow: upload_media(file_bytes) -> media_id,
        then reply_media(frame, media_id) or send_media_message(chatid, media_id).

        Args:
            chat_id: The target chat/conversation ID.
            file_path: Local file path of the file to send.
            file_name: Display name for the file.
            **kwargs: Additional options (frame override).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return False

        if not hasattr(self._ws_client, "upload_media"):
            logger.warning(
                "WeCom SDK does not support upload_media (requires wecom-aibot-sdk>=1.0.7)"
            )
            return False

        try:
            import os

            if not os.path.isfile(file_path):
                logger.warning(f"WeCom file not found: {file_path}")
                return False

            with open(file_path, "rb") as f:
                file_bytes = f.read()

            safe_name = file_name or os.path.basename(file_path) or "file.bin"

            upload_result = await self._ws_client.upload_media(
                file_bytes, type="file", filename=safe_name
            )
            media_id = upload_result["media_id"]

            frame = kwargs.get("frame") or self._pending_frames.get(chat_id)
            if frame and hasattr(self._ws_client, "reply_media"):
                await self._ws_client.reply_media(frame, "file", media_id)
            else:
                if not hasattr(self._ws_client, "send_media_message"):
                    logger.warning(
                        "WeCom SDK does not support send_media_message "
                        "(requires wecom-aibot-sdk>=1.0.7)"
                    )
                    return False
                await self._ws_client.send_media_message(chat_id, "file", media_id)
            logger.info(
                f"WeCom file sent to chat {chat_id} for user {self.config.user_id}"
                f"{f': {safe_name}' if safe_name else ''}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error sending WeCom file for user {self.config.user_id}: {e}"
            )
            return False

    # -- Template card sending --

    async def send_template_card(
        self, chat_id: str, template_card: dict[str, Any], **kwargs: Any
    ) -> bool:
        """Send a template card message.

        Uses the SDK's reply_template_card (if a pending frame exists) or
        falls back to aibot_send_msg with a card body.

        Args:
            chat_id: The target chat/conversation ID.
            template_card: The template card definition dict.
            **kwargs: Additional options (frame override, feedback).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return False

        try:
            frame = kwargs.get("frame") or self._pending_frames.get(chat_id)
            feedback = kwargs.get("feedback")

            if frame and hasattr(self._ws_client, "reply_template_card"):
                await self._ws_client.reply_template_card(frame, template_card, feedback)
            else:
                # Proactive card send via aibot_send_msg
                body = {
                    "msgtype": "template_card",
                    "template_card": template_card,
                }
                await self._ws_client.send_message(chat_id, body)

            logger.info(
                f"WeCom template card sent to chat {chat_id} for user {self.config.user_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error sending WeCom template card for user {self.config.user_id}: {e}"
            )
            return False

    async def update_template_card(
        self, chat_id: str, template_card: dict[str, Any], **kwargs: Any
    ) -> bool:
        """Update an existing template card (5s deadline from event callback).

        Args:
            chat_id: The target chat/conversation ID.
            template_card: The updated template card definition dict.
            **kwargs: Additional options (frame override, userids).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._ws_client:
            return False

        try:
            frame = kwargs.get("frame") or self._pending_frames.get(chat_id)
            userids = kwargs.get("userids")

            if frame and hasattr(self._ws_client, "update_template_card"):
                await self._ws_client.update_template_card(frame, template_card, userids)
                return True
            return False

        except Exception as e:
            logger.error(
                f"Error updating WeCom template card for user {self.config.user_id}: {e}"
            )
            return False

    # -- File download --

    async def download_media_file(
        self, url: str, aes_key: str = ""
    ) -> tuple[bytes, str | None]:
        """Download and optionally decrypt a media file from WeCom.

        Uses the SDK's download_file method which handles AES-256-CBC
        decryption when an aes_key is provided.

        Args:
            url: The media file URL from the message callback.
            aes_key: Optional AES key for decryption.

        Returns:
            Tuple of (file_bytes, md5_hash_or_none).
            Returns (b"", None) on failure.
        """
        if not self._ws_client:
            logger.warning(
                f"WeCom WS client not connected for user {self.config.user_id}"
            )
            return (b"", None)

        try:
            result = await self._ws_client.download_file(url, aes_key or None)
            return result
        except Exception as e:
            logger.error(
                f"Error downloading WeCom media file for user {self.config.user_id}: {e}"
            )
            return (b"", None)
