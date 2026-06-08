"""
WeCom (企业微信) 消息处理器模块

处理 WeCom 消息的 Agent 执行和响应。
支持流式回复（原生 WebSocket 流式）、5 秒思考占位、6 分钟超时回退。
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from typing import Any, AsyncGenerator, Callable, Optional, cast

from src.infra.channel.wecom.channel import WeComChannel
from src.infra.channel.wecom.manager import WeComChannelManager
from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────

# Redis key prefix for WeCom chat→session mapping
WECOM_SESSION_KEY_PREFIX = "wecom:session:"

# 流式更新防抖间隔（秒）。WeCom 原生 WS 流式比飞书 CardKit 更轻量，
# 可以稍微长一点的防抖间隔以减少 WS 帧数量。
WECOM_STREAM_UPDATE_DEBOUNCE_SECONDS = 1.0

# WeCom 流式回复硬性超时：6 分钟。
# 超时后流式消息会被 finalize，完整结果通过 aibot_send_msg 主动推送。
WECOM_STREAM_TIMEOUT_SECONDS = 360

# 首次推送的最小字符数，让用户尽快看到内容。
WECOM_STREAM_FIRST_PAINT_CHARS = 50

# 思考占位消息（5 秒回调截止时间内发送）
WECOM_THINKING_MESSAGE = "思考中..."

# 事件类型（与 agent stream 事件一致）
EVENT_MESSAGE_CHUNK = "message:chunk"
EVENT_THINKING = "thinking"
EVENT_TOOL_START = "tool:start"
EVENT_TOOL_RESULT = "tool:result"
EVENT_DONE = "done"

_STREAM_UPDATE_SIGNAL = object()


# ── Session 辅助函数 ──────────────────────────────────────────────────


async def _get_wecom_session_id(chat_id: str) -> str:
    """获取 WeCom 聊天对应的当前 session ID，如果不存在则创建默认的"""
    from src.infra.storage.redis import RedisStorage

    storage = RedisStorage()
    key = f"{WECOM_SESSION_KEY_PREFIX}{chat_id}"
    session_id = await storage.get(key)

    if session_id is None:
        # 默认使用 chat_id 作为 session ID（兼容旧数据）
        session_id = f"wecom_{chat_id}"
        await storage.set(key, session_id)

    return session_id


async def _create_new_wecom_session(chat_id: str) -> str:
    """为 WeCom 聊天创建新的 session ID"""
    from src.infra.storage.redis import RedisStorage

    storage = RedisStorage()
    key = f"{WECOM_SESSION_KEY_PREFIX}{chat_id}"

    # 使用时间戳生成唯一的 session ID
    timestamp = int(time.time())
    session_id = f"wecom_{chat_id}_{timestamp}"

    # 存储到 Redis，不设置过期时间
    await storage.set(key, session_id)

    logger.info(f"[WeCom] Created new session for chat {chat_id}: {session_id}")
    return session_id


# ── 长消息分段 ────────────────────────────────────────────────────────

WECOM_MESSAGE_BYTE_LIMIT = 2048  # UTF-8 byte limit per WeCom markdown message


def _split_by_utf8_byte_limit(text: str, byte_limit: int = WECOM_MESSAGE_BYTE_LIMIT) -> list[str]:
    """Split text into chunks that don't exceed byte_limit UTF-8 bytes.

    Uses binary search to find safe split points that don't break multi-byte characters.
    Tries to split on paragraph breaks (\\n\\n), then line breaks (\\n), then character boundaries.
    """
    if not text:
        return []

    encoded = text.encode("utf-8")
    if len(encoded) <= byte_limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        encoded = remaining.encode("utf-8")
        if len(encoded) <= byte_limit:
            chunks.append(remaining)
            break

        # Binary search for the maximum prefix that fits in byte_limit
        lo, hi = 0, len(remaining)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(remaining[:mid].encode("utf-8")) <= byte_limit:
                lo = mid
            else:
                hi = mid - 1

        # Try to split on paragraph break within the prefix
        split_pos = lo
        last_para = remaining.rfind("\n\n", 0, lo)
        if last_para > 0:
            split_pos = last_para + 2
        else:
            last_line = remaining.rfind("\n", 0, lo)
            if last_line > 0:
                split_pos = last_line + 1

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:]

    return chunks


# ── WeComResponseCollector ────────────────────────────────────────────


class WeComResponseCollector:
    """
    WeCom 响应收集器

    收集 Agent 响应内容，通过 WeCom WebSocket 流式回复。
    与飞书不同：
    - WeCom 在同一 WebSocket 连接上发送回复（aibot_respond_msg），无需单独的 HTTP sender
    - WeCom 支持原生流式（reply_stream），无需 CardKit 的 4 步流程
    - WeCom 有 5 秒回调截止时间，需发送思考占位消息
    - WeCom 有 6 分钟流式超时，需回退到 aibot_send_msg 主动推送
    """

    def __init__(
        self,
        manager: WeComChannelManager,
        user_id: str,
        chat_id: str,
        reply_to_msgid: str | None = None,
        sender_id: str | None = None,
        chat_type: str | None = None,
        stream_reply: bool = True,
        send_thinking_message: bool = True,
        segmented_reply: bool = True,
        instance_id: str | None = None,
    ):
        self.manager = manager
        self.user_id = user_id
        self.chat_id = chat_id
        self.reply_to_msgid = reply_to_msgid
        self.sender_id = sender_id
        self.chat_type = chat_type
        self.stream_reply = stream_reply
        self.send_thinking_message = send_thinking_message
        self.segmented_reply = segmented_reply
        self.instance_id = instance_id

        # 内容收集
        self.text_parts: list[str] = []
        self.tools_used: list[str] = []
        self.files_to_reveal: list[dict] = []
        self._sent_file_keys: set[str] = set()

        # 流式状态
        self._stream_id: str | None = None
        self._stream_started = False
        self._stream_finalized = False
        self._stream_failed = False
        self._stream_timed_out = False
        self._stream_lock = asyncio.Lock()
        self._stream_update_queue: asyncio.Queue[object | None] = asyncio.Queue(maxsize=1)
        self._stream_update_task: asyncio.Task | None = None
        self._stream_last_pushed_content = ""
        self._stream_start_time: float = 0.0

    # ── 内容管理 ──────────────────────────────────────────────────

    def _current_stream_content(self) -> str:
        """获取当前累积的文本内容"""
        return "".join(self.text_parts)

    def _queue_latest_stream_update(self) -> None:
        """将流式更新信号排入队列（仅保留最新一个信号）"""
        while True:
            try:
                pending = self._stream_update_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if pending is None:
                self._stream_update_queue.put_nowait(None)
                return
        self._stream_update_queue.put_nowait(_STREAM_UPDATE_SIGNAL)

    def append_text(self, chunk: str) -> None:
        """追加文本内容"""
        self.text_parts.append(chunk)

    async def append_stream_chunk(self, chunk: str) -> None:
        """追加一个响应 chunk 并在流式回复启用时推送更新"""
        self.append_text(chunk)
        if not self.stream_reply or self._stream_failed or self._stream_finalized:
            return

        # 流式已启动：仅排队更新
        if self._stream_started:
            self._ensure_stream_update_worker()
            self._queue_latest_stream_update()
            return

        # 第一个 chunk：启动流式消息
        content = self._current_stream_content()
        initial_content = self._first_paint_content(content)
        async with self._stream_lock:
            if self._stream_failed or self._stream_finalized:
                return
            client = self._get_client()
            if not client:
                self._stream_failed = True
                return

            stream_id = self._stream_id or uuid.uuid4().hex[:16]
            self._stream_id = stream_id
            success = await client.reply_stream(
                self.chat_id, stream_id, initial_content, finish=False
            )
            if not success:
                self._stream_failed = True
                return
            self._stream_started = True
            self._stream_start_time = time.time()
            self._stream_last_pushed_content = initial_content

        self._ensure_stream_update_worker()
        if initial_content != content:
            self._queue_latest_stream_update()

    def _first_paint_content(self, content: str) -> str:
        """返回精简的首次推送内容，让用户尽快看到内容渲染"""
        stripped = content.strip()
        if not stripped:
            return content
        if len(stripped) <= WECOM_STREAM_FIRST_PAINT_CHARS:
            return content
        return stripped[:WECOM_STREAM_FIRST_PAINT_CHARS]

    # ── 5 秒回调截止：思考占位消息 ────────────────────────────────

    async def send_thinking_placeholder(self) -> bool:
        """发送思考占位消息，满足 WeCom 5 秒回调截止要求。

        WeCom 要求在收到消息后 5 秒内发送初始回复。
        如果 Agent 处理较慢，此方法确保截止要求被满足。

        Returns:
            True if thinking placeholder was sent successfully.
        """
        if not self.send_thinking_message or not self.stream_reply:
            return False
        if self._stream_started or self._stream_failed or self._stream_finalized:
            return False

        client = self._get_client()
        if not client:
            return False

        stream_id = uuid.uuid4().hex[:16]
        self._stream_id = stream_id

        success = await client.reply_stream(
            self.chat_id, stream_id, WECOM_THINKING_MESSAGE, finish=False
        )
        if success:
            self._stream_started = True
            self._stream_start_time = time.time()
            self._stream_last_pushed_content = WECOM_THINKING_MESSAGE
            return True

        logger.warning("[WeCom] Failed to send thinking placeholder")
        self._stream_failed = True
        return False

    # ── 流式更新 worker（防抖）──────────────────────────────────

    def _ensure_stream_update_worker(self) -> None:
        """启动防抖的流式更新 worker（如果尚未运行）"""
        if self._stream_update_task and not self._stream_update_task.done():
            return
        self._stream_update_task = asyncio.create_task(self._stream_update_worker())
        self._stream_update_task.add_done_callback(self._on_stream_update_task_done)

    def _on_stream_update_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as e:
            self._stream_failed = True
            logger.warning("[WeCom] Stream update worker failed: %s", e, exc_info=True)

    async def _stream_update_worker(self) -> None:
        """防抖 worker：定期推送流式更新到 WeCom 客户端。

        使用 debounce 机制避免频繁发送 WS 帧。
        同时检测 6 分钟超时，超时时自动 finalize 并回退。
        """
        first_update = True
        while True:
            marker = await self._stream_update_queue.get()
            if marker is None:
                return

            # Debounce：等待一段时间再处理，期间丢弃中间信号
            if not first_update:
                await asyncio.sleep(WECOM_STREAM_UPDATE_DEBOUNCE_SECONDS)
                while True:
                    try:
                        next_marker = self._stream_update_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if next_marker is None:
                        return
            first_update = False

            # 检测 6 分钟超时
            if self._stream_start_time > 0:
                elapsed = time.time() - self._stream_start_time
                if elapsed >= WECOM_STREAM_TIMEOUT_SECONDS:
                    logger.warning(
                        "[WeCom] Stream timeout (%ds) reached for chat %s",
                        WECOM_STREAM_TIMEOUT_SECONDS,
                        self.chat_id,
                    )
                    self._stream_timed_out = True
                    await self._finalize_stream_with_timeout()
                    return

            content = self._current_stream_content()
            if content == self._stream_last_pushed_content:
                continue

            async with self._stream_lock:
                if self._stream_failed or self._stream_finalized or not self._stream_id:
                    return
                client = self._get_client()
                if not client:
                    self._stream_failed = True
                    return

                success = await client.reply_stream(
                    self.chat_id, self._stream_id, content, finish=False
                )
                if not success:
                    self._stream_failed = True
                    return
                self._stream_last_pushed_content = content

    async def _finalize_stream_with_timeout(self) -> None:
        """因超时 finalize 流式消息（发送当前已有的内容）。"""
        async with self._stream_lock:
            if self._stream_finalized or self._stream_failed:
                return
            client = self._get_client()
            if not client:
                self._stream_failed = True
                return

            content = self._current_stream_content()
            if not content.strip():
                content = "(处理超时，请稍后查看完整回复)"

            if not self._stream_id:
                self._stream_failed = True
                return
            success = await client.reply_stream(
                self.chat_id, self._stream_id, content, finish=True
            )
            if success:
                self._stream_finalized = True
                logger.info(
                    "[WeCom] Stream finalized due to timeout for chat %s",
                    self.chat_id,
                )
            else:
                self._stream_failed = True

    async def _cancel_stream_update_worker(self) -> None:
        """取消流式更新 worker 任务"""
        task = self._stream_update_task
        if not task or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # ── 其他内容收集 ──────────────────────────────────────────────

    def add_tool(self, tool_name: str) -> None:
        """添加使用的工具"""
        if tool_name:
            self.tools_used.append(tool_name)

    def add_file_to_reveal(self, file_info: dict) -> None:
        """添加待展示的文件"""
        self.files_to_reveal.append(file_info)

    async def upload_and_send_files(self) -> None:
        """上传文件并发送到 WeCom。

        从 S3 storage 下载文件到临时文件，通过 upload_media 上传获取 media_id，
        再通过 send_media_message 主动推送到 WeCom。
        """
        from src.infra.channel.feishu.handler_helpers import (
            FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE,
            _download_storage_object_to_file,
        )
        from src.infra.storage.s3.service import get_or_init_storage

        if not self.files_to_reveal:
            return

        client = self._get_client()
        if not client:
            return

        if not hasattr(client, "_ws_client") or not hasattr(
            client._ws_client, "upload_media"
        ):
            logger.warning(
                "[WeCom] SDK does not support upload_media (requires wecom-aibot-sdk>=1.0.7)"
            )
            return

        try:
            storage = await get_or_init_storage()
        except Exception as e:
            logger.error("[WeCom] Failed to init storage: %s", e)
            return

        backend = storage._get_backend()

        for file_info in self.files_to_reveal:
            try:
                file_name = file_info.get("name", "unknown")
                file_key = file_info.get("key", "")

                if not file_key:
                    logger.warning("[WeCom] No key for file %s", file_name)
                    continue
                if file_key in self._sent_file_keys:
                    continue

                logger.info(
                    "[WeCom] Reading file %s from storage, key=%s",
                    file_name,
                    file_key,
                )

                safe_suffix = os.path.basename(file_name) or "file"
                with NamedTemporaryFile(
                    prefix="lambchat-wecom-", suffix=f"-{safe_suffix}"
                ) as tmp:
                    size = await _download_storage_object_to_file(
                        backend,
                        file_key,
                        tmp,
                        chunk_size=FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE,
                    )
                    if size <= 0:
                        logger.warning(
                            "[WeCom] File not found or empty: %s", file_key
                        )
                        continue

                    logger.info(
                        "[WeCom] Downloaded file %s, size: %d bytes",
                        file_name,
                        size,
                    )

                    # Read file bytes from temp file
                    tmp.seek(0)
                    file_bytes = tmp.read()

                # Map file type to WeCom media type
                file_type = str(file_info.get("type") or "").lower()
                mime_type = str(file_info.get("mime_type") or "").lower()
                if file_type == "image" or mime_type.startswith("image/"):
                    media_type = "image"
                else:
                    media_type = "file"

                # Step 1: Upload to get media_id
                upload_result = await client._ws_client.upload_media(
                    file_bytes, type=media_type, filename=file_name
                )
                media_id = upload_result["media_id"]

                # Step 2: Send via send_media_message (proactive, frame may be gone)
                if hasattr(client._ws_client, "send_media_message"):
                    await client._ws_client.send_media_message(
                        self.chat_id, media_type, media_id
                    )
                    self._sent_file_keys.add(file_key)
                    logger.info("[WeCom] Sent %s: %s", media_type, file_name)
                else:
                    logger.warning(
                        "[WeCom] SDK does not support send_media_message "
                        "(requires wecom-aibot-sdk>=1.0.7)"
                    )

            except Exception as e:
                logger.error(
                    "[WeCom] Failed to upload file %s: %s",
                    file_info.get("name"),
                    e,
                )

    def _get_client(self) -> WeComChannel | None:
        """获取当前用户的 WeComChannel 实例"""
        base_client = self.manager._find_channel(self.user_id, self.instance_id)
        if not base_client:
            logger.warning("[WeCom] No client for user %s", self.user_id)
            return None
        return cast(WeComChannel, base_client)

    # ── 最终发送 ──────────────────────────────────────────────────

    async def finalize_stream_message(self) -> bool:
        """关闭流式消息。返回 True 表示流式回复已成功发送。

        如果流式因超时已 finalize，此方法会额外通过 aibot_send_msg
        发送完整结果作为新消息（用户会看到两条消息）。
        """
        if not self._stream_started or self._stream_failed:
            return False

        await self._cancel_stream_update_worker()
        async with self._stream_lock:
            if not self._stream_started or self._stream_failed:
                return False

            if self._stream_finalized:
                # 已 finalize（可能因超时）
                if self._stream_timed_out:
                    # 超时回退：通过 aibot_send_msg 发送完整结果
                    await self._send_timeout_fallback()
                return True  # 流式回复已使用

            # 正常 finalize
            client = self._get_client()
            if not client:
                return False

            if not self._stream_id:
                return False
            final_content = self._current_stream_content()
            final_text = final_content.strip() or " "

            success = await client.reply_stream(
                self.chat_id, self._stream_id, final_text, finish=True
            )
            if success:
                self._stream_finalized = True
            return success

    async def _send_timeout_fallback(self) -> bool:
        """超时后通过 aibot_send_msg 主动推送完整结果。

        流式消息已因 6 分钟超时被 finalize（包含当时已有的内容）。
        此方法发送完整的最终结果作为新消息。
        如果 segmented_reply 启用且内容超过字节限制，自动分段发送。
        """
        client = self._get_client()
        if not client:
            return False

        final_content = self._current_stream_content()
        final_text = final_content.strip() or " "

        # 分段发送：超过字节限制时自动拆分
        if self.segmented_reply and len(final_text.encode("utf-8")) > WECOM_MESSAGE_BYTE_LIMIT:
            chunks = _split_by_utf8_byte_limit(final_text)
            all_success = True
            for i, chunk in enumerate(chunks):
                success = await client.send_proactive_message(self.chat_id, chunk)
                if not success:
                    all_success = False
                    logger.warning(
                        "[WeCom] Failed to send timeout fallback part %d/%d for chat %s",
                        i + 1, len(chunks), self.chat_id,
                    )
            if all_success:
                logger.info(
                    "[WeCom] Sent timeout fallback (%d parts) to chat %s",
                    len(chunks), self.chat_id,
                )
            return all_success

        success = await client.send_proactive_message(self.chat_id, final_text)
        if success:
            logger.info(
                "[WeCom] Sent timeout fallback message to chat %s",
                self.chat_id,
            )
        else:
            logger.warning(
                "[WeCom] Failed to send timeout fallback for chat %s",
                self.chat_id,
            )
        return success

    async def send_message(self) -> bool:
        """发送非流式回复（完整消息）。

        用于流式回复失败或被禁用时的回退方案。
        如果 segmented_reply 启用且内容超过字节限制，自动分段发送。
        """
        if self._stream_finalized:
            return True

        client = self._get_client()
        if not client:
            return False

        content = self._current_stream_content()
        if not content.strip():
            content = "(无内容)"
        else:
            content = content.strip()

        # 添加工具和文件元数据
        metadata_parts = []
        if self.tools_used:
            unique_tools = list(dict.fromkeys(self.tools_used))
            tool_badges = " ".join(f"`{t}`" for t in unique_tools)
            metadata_parts.append(f"🔧 {tool_badges}")
        if self.files_to_reveal:
            file_names = [f.get("name", "未知文件") for f in self.files_to_reveal]
            metadata_parts.append(f"📎 {', '.join(file_names)}")
        if metadata_parts:
            content += "\n\n---\n" + " · ".join(metadata_parts)

        # 分段发送：超过字节限制时自动拆分
        if self.segmented_reply and len(content.encode("utf-8")) > WECOM_MESSAGE_BYTE_LIMIT:
            chunks = _split_by_utf8_byte_limit(content)
            all_success = True
            for i, chunk in enumerate(chunks):
                success = await client.send_proactive_message(self.chat_id, chunk)
                if not success:
                    all_success = False
                    logger.warning(
                        "[WeCom] Failed to send segmented message part %d/%d to %s",
                        i + 1, len(chunks), self.chat_id,
                    )
            if all_success:
                reply_info = (
                    f" (reply to {self.reply_to_msgid})" if self.reply_to_msgid else ""
                )
                logger.info(
                    "[WeCom] Segmented message (%d parts) sent to %s%s",
                    len(chunks), self.chat_id, reply_info,
                )
            return all_success

        success = await client.reply_message(self.chat_id, content)
        if success:
            reply_info = (
                f" (reply to {self.reply_to_msgid})" if self.reply_to_msgid else ""
            )
            logger.info(f"[WeCom] Message sent to {self.chat_id}{reply_info}")
        else:
            logger.warning("[WeCom] Failed to send message")
        return success


# ── Agent 执行 ────────────────────────────────────────────────────────


async def execute_wecom_agent(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter: Optional[Any] = None,
    disabled_tools: list[str] | None = None,
    agent_options: dict | None = None,
    attachments: list[dict] | None = None,
    disabled_skills: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    persona_system_prompt: str | None = None,
    disabled_mcp_tools: list[str] | None = None,
    team_id: str | None = None,
    active_goal: dict | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """执行 Agent 并生成事件流"""
    from src.agents.core.base import AgentFactory
    from src.infra.task.exceptions import TaskInterruptedError

    agent = await AgentFactory.get(agent_id)
    run_id = presenter.run_id if presenter else None

    started_at: str | None = None
    if active_goal is not None:
        started_at = datetime.now(timezone.utc).isoformat()
        yield {"event": "goal:start", "data": {"goal": active_goal, "started_at": started_at}}

    try:
        async for event in agent.stream(
            message,
            session_id,
            user_id=user_id,
            presenter=presenter,
            disabled_tools=disabled_tools,
            agent_options=agent_options,
            attachments=attachments,
            disabled_skills=disabled_skills,
            enabled_skills=enabled_skills,
            persona_system_prompt=persona_system_prompt,
            disabled_mcp_tools=disabled_mcp_tools,
            team_id=team_id,
            active_goal=active_goal,
            goal_started_at=started_at,
        ):
            yield event
    except (asyncio.CancelledError, TaskInterruptedError):
        if run_id:
            await agent.close(run_id)
        if active_goal is not None:
            ended_at = datetime.now(timezone.utc).isoformat()
            yield {
                "event": "goal:end",
                "data": {"goal": active_goal, "started_at": started_at, "ended_at": ended_at},
            }
        raise


# ── 消息处理器工厂 ────────────────────────────────────────────────────


def create_wecom_message_handler(
    manager: WeComChannelManager,
    default_agent: str,
    show_tools: bool = True,
) -> Callable:
    """
    创建 WeCom 消息处理器

    Args:
        manager: WeCom 渠道管理器
        default_agent: 默认 Agent ID
        show_tools: 是否显示工具调用
    """
    from src.infra.task.manager import get_task_manager

    async def wecom_message_handler(
        user_id: str,
        sender_id: str,
        chat_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        """处理 WeCom 消息"""
        original_message_id = metadata.get("message_id")
        instance_id = metadata.get("instance_id")
        delivery_chat_id = chat_id

        try:
            logger.info(
                f"[WeCom] Processing message from {sender_id} for user {user_id}: {content[:50]}..."
            )

            sender_id_from_msg = metadata.get("sender_id")
            chat_type_from_msg = metadata.get("chat_type")
            reply_to_msgid = original_message_id

            # Resolve agent, model & project: use per-channel config if available
            agent_to_use = default_agent
            model_id: str | None = None
            project_id: str | None = None
            team_id: str | None = None
            persona_preset_id: str | None = None
            enabled_skills: list[str] | None = None
            persona_system_prompt: str | None = None
            persona_metadata: dict[str, Any] | None = None
            channel_name: str | None = None
            stream_reply = True
            send_thinking_message = True
            segmented_reply = True
            ch_storage = None

            if instance_id:
                from src.infra.channel.channel_storage import ChannelStorage
                from src.kernel.schemas.channel import ChannelType

                ch_storage = ChannelStorage()
                ch_config = await ch_storage.get_config(user_id, ChannelType.WECOM, instance_id)
                if ch_config:
                    if ch_config.get("agent_id"):
                        agent_to_use = ch_config["agent_id"]
                        logger.info(
                            f"[WeCom] Using channel agent: {agent_to_use} for instance {instance_id}"
                        )
                    model_id = ch_config.get("model_id")
                    project_id = ch_config.get("project_id")
                    team_id = ch_config.get("team_id")
                    persona_preset_id = (
                        None if agent_to_use == "team" else ch_config.get("persona_preset_id")
                    )
                    channel_name = ch_config.get("name")
                    stream_reply = bool(ch_config.get("stream_reply", True))
                    send_thinking_message = bool(ch_config.get("send_thinking_message", True))
                    segmented_reply = bool(ch_config.get("segmented_reply", True))

            # Persona preset resolution
            if persona_preset_id:
                try:
                    from src.infra.persona_preset.manager import PersonaPresetManager

                    snapshot = await PersonaPresetManager().use_preset(
                        persona_preset_id,
                        user_id=user_id,
                        is_admin=False,
                    )
                    persona_system_prompt = snapshot.system_prompt
                    enabled_skills = snapshot.skill_names or None
                    persona_metadata = {
                        "persona_preset_id": snapshot.preset_id,
                        "persona_preset_name": snapshot.name,
                        "persona_snapshot": snapshot.model_dump(),
                        "enabled_skills": enabled_skills,
                    }
                    if snapshot.avatar:
                        persona_metadata["persona_avatar"] = snapshot.avatar
                    logger.info(
                        f"[WeCom] Using channel persona: {snapshot.name} "
                        f"({persona_preset_id}) for instance {instance_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[WeCom] Ignoring unavailable channel persona {persona_preset_id}: {e}"
                    )

            # Project resolution
            if project_id:
                try:
                    from src.infra.folder.storage import get_project_storage

                    proj_storage = get_project_storage()
                    project = await proj_storage.get_by_id(project_id, user_id)
                    if not project:
                        logger.warning(
                            f"[WeCom] Ignoring missing channel project_id {project_id} "
                            f"for user {user_id}"
                        )
                        if ch_storage and instance_id:
                            await ch_storage.clear_config_project_id(
                                user_id, ChannelType.WECOM, instance_id
                            )
                        project_id = None
                except Exception as e:
                    logger.warning(f"[WeCom] Failed to validate channel project_id: {e}")
                    project_id = None

            # Auto-create project by channel name if not manually configured
            if not project_id and channel_name:
                try:
                    from src.infra.folder.storage import get_project_storage

                    proj_storage = get_project_storage()
                    project = await proj_storage.get_or_create_by_name(user_id, channel_name)
                    project_id = project.id
                except Exception as e:
                    logger.warning(f"[WeCom] Failed to auto-create project: {e}")

            # Build agent_options with model_id if configured
            wecom_agent_options: dict | None = None
            if model_id:
                wecom_agent_options = {"model_id": model_id}

            # 处理 /new 命令 - 严格匹配
            if content.strip() == "/new":
                new_session_id = await _create_new_wecom_session(chat_id)
                await manager.send_message(
                    user_id,
                    delivery_chat_id,
                    "✅ 已创建新对话，请发送消息开始",
                    instance_id,
                )
                logger.info(f"[WeCom] New session created for chat {chat_id}: {new_session_id}")
                return

            # 获取当前 session ID
            session_id = await _get_wecom_session_id(chat_id)
            task_manager = get_task_manager()

            # Cancel any previous running task for this session
            # This matches Web UI behavior where sending a new message cancels the previous run
            previous_run_cancelled = False
            try:
                cancel_result = await task_manager.cancel(session_id, user_id=user_id)
                if cancel_result.get("success") or cancel_result.get("cancelled_locally"):
                    previous_run_cancelled = True
                    logger.info(
                        "[WeCom] Cancelled previous run for session %s: %s",
                        session_id,
                        cancel_result.get("message", ""),
                    )
            except Exception as e:
                logger.debug("[WeCom] No previous run to cancel for session %s: %s", session_id, e)

            # When a previous run is cancelled, create a fresh session so the
            # new message is processed from a clean checkpoint.  Otherwise the
            # agent inherits the cancelled run's partial assistant response from
            # the LangGraph checkpointer and treats the new user message as a
            # follow-up rather than a fresh request.
            if previous_run_cancelled:
                session_id = await _create_new_wecom_session(chat_id)

            collector = WeComResponseCollector(
                manager=manager,
                user_id=user_id,
                chat_id=delivery_chat_id,
                reply_to_msgid=reply_to_msgid,
                sender_id=sender_id_from_msg,
                chat_type=chat_type_from_msg,
                stream_reply=stream_reply,
                send_thinking_message=send_thinking_message,
                segmented_reply=segmented_reply,
                instance_id=instance_id,
            )

            # 立即发送思考占位消息（满足 5 秒回调截止要求）
            if stream_reply and send_thinking_message:
                await collector.send_thinking_placeholder()

            async def executor(
                session_id: str,
                agent_id: str,
                message: str,
                user_id: str,
                presenter=None,
                disabled_tools=None,
                agent_options=None,
                attachments=None,
                disabled_skills=None,
                enabled_skills=None,
                persona_system_prompt=None,
                disabled_mcp_tools=None,
                team_id=None,
                active_goal=None,
            ):
                async for event in execute_wecom_agent(
                    session_id=session_id,
                    agent_id=agent_id,
                    message=message,
                    user_id=user_id,
                    presenter=presenter,
                    disabled_tools=disabled_tools,
                    agent_options=agent_options,
                    attachments=attachments,
                    disabled_skills=disabled_skills,
                    enabled_skills=enabled_skills,
                    persona_system_prompt=persona_system_prompt,
                    disabled_mcp_tools=disabled_mcp_tools,
                    team_id=team_id,
                    active_goal=active_goal,
                ):
                    yield event

            # Use time-based session title for WeCom
            session_title = utc_now().strftime("%Y-%m-%d %H:%M")

            run_id, _ = await task_manager.submit(
                session_id=session_id,
                agent_id=agent_to_use,
                message=content,
                user_id=user_id,
                executor=executor,
                project_id=project_id,
                agent_options=wecom_agent_options,
                session_name=session_title,
                enabled_skills=enabled_skills,
                persona_system_prompt=persona_system_prompt,
                team_id=team_id if agent_to_use == "team" else None,
            )

            if persona_metadata:
                try:
                    from src.infra.session.manager import SessionManager
                    from src.kernel.schemas.session import SessionUpdate

                    await SessionManager().update_session(
                        session_id,
                        SessionUpdate(metadata=persona_metadata),
                    )
                except Exception as e:
                    logger.warning(f"[WeCom] Failed to persist persona metadata: {e}")

            logger.info(f"[WeCom] Task submitted: session={session_id}, run_id={run_id}")

            await _process_events(
                collector=collector,
                session_id=session_id,
                run_id=run_id,
                show_tools=show_tools,
            )

            # Check if this run is still the active run for the session.
            # If a newer message arrived and cancelled this run, skip sending
            # the reply to avoid duplicate/conflicting messages.
            current_session = await task_manager.storage.get_by_session_id(session_id)
            current_run_id = (
                current_session.metadata.get("current_run_id")
                if current_session and current_session.metadata
                else None
            )
            if current_run_id and current_run_id != run_id:
                logger.info(
                    "[WeCom] Run %s superseded by %s, skipping reply for chat %s",
                    run_id, current_run_id, chat_id,
                )
                return

            streamed = await collector.finalize_stream_message()
            if not streamed:
                await collector.send_message()

            await collector.upload_and_send_files()

            logger.info(f"[WeCom] Message processing completed for {chat_id}")

        except Exception as e:
            logger.error(f"[WeCom] Error handling message: {e}", exc_info=True)
            try:
                await manager.send_message(
                    user_id,
                    delivery_chat_id,
                    f"❌ 处理消息时发生错误: {str(e)[:200]}",
                    instance_id,
                )
            except Exception:
                pass

    return wecom_message_handler


# ── 事件处理 ──────────────────────────────────────────────────────────


async def _process_events(
    collector: WeComResponseCollector,
    session_id: str,
    run_id: str,
    show_tools: bool,
) -> None:
    """处理事件流并收集响应"""
    from src.infra.session.dual_writer import get_dual_writer

    dual_writer = get_dual_writer()

    try:
        async for event in dual_writer.read_from_redis(session_id, run_id):
            event_type = event.get("event_type", "")
            data = event.get("data", {})

            if event_type == EVENT_MESSAGE_CHUNK:
                chunk = data.get("content", "")
                if chunk:
                    await collector.append_stream_chunk(chunk)

            elif event_type == EVENT_TOOL_START and show_tools:
                tool_name = data.get("tool", "")
                if tool_name:
                    collector.add_tool(tool_name)

            elif event_type == EVENT_TOOL_RESULT:
                tool_name = data.get("tool", "")
                result = data.get("result", {})
                if isinstance(result, dict):
                    from src.infra.channel.feishu.handler_helpers import (
                        _extract_tool_media_files,
                    )

                    file_infos = _extract_tool_media_files(result)

                    # Also handle reveal_file direct result format:
                    # {"key": "...", "url": "...", "name": "...", "type": "image", ...}
                    # This format has no "images" or "blocks" wrapper, so
                    # _extract_tool_media_files returns [] for it.
                    if not file_infos and "key" in result and "url" in result:
                        file_type = str(result.get("type") or "").lower()
                        mime_type = str(result.get("mime_type") or "").lower()
                        if file_type in {"image", "file", "audio", "video", "document"} or mime_type:
                            media_type = file_type
                            if file_type == "document":
                                media_type = "file"
                            elif mime_type.startswith("image/"):
                                media_type = "image"
                            elif mime_type.startswith("audio/"):
                                media_type = "audio"
                            elif mime_type.startswith("video/"):
                                media_type = "video"
                            file_infos.append({
                                "key": result["key"],
                                "name": result.get("name", "unknown"),
                                "type": media_type,
                                "mime_type": mime_type or "application/octet-stream",
                                "url": result.get("url", ""),
                            })

                    for fi in file_infos:
                        collector.add_file_to_reveal(fi)
                        logger.info(
                            "[WeCom] Added tool media file to reveal: %s",
                            fi.get("name"),
                        )

            elif event_type in ("done", "complete", "error"):
                break

        logger.info(f"[WeCom] Event processing completed for session={session_id}")

    except Exception as e:
        logger.error(f"[WeCom] Event processing error: {e}", exc_info=True)


# ── Handler 设置入口 ──────────────────────────────────────────────────


async def setup_wecom_handler(
    default_agent: str,
    show_tools: bool = True,
) -> None:
    """
    设置 WeCom 消息处理器

    Args:
        default_agent: 默认 Agent ID
        show_tools: 是否显示工具调用
    """
    from src.infra.channel.wecom import get_wecom_channel_manager, start_wecom_channels

    manager = get_wecom_channel_manager()
    handler = create_wecom_message_handler(
        manager=manager,
        default_agent=default_agent,
        show_tools=show_tools,
    )

    await start_wecom_channels(handler)
    logger.info("WeCom channels started")
