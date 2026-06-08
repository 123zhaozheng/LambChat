"""
WeCom (企业微信) channel manager for managing multiple user bot connections.
"""

import asyncio
import hashlib
import uuid
from typing import Any, Callable, Optional

from redis.asyncio import Redis

from src.infra.channel.base import UserChannelManager
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.wecom.channel import WECOM_AVAILABLE, WeComChannel
from src.infra.logging import get_logger
from src.infra.storage.redis import create_redis_client
from src.kernel.schemas.channel import ChannelType
from src.kernel.schemas.wecom import (
    WeComConfig,
    WeComGroupPolicy,
)

logger = get_logger(__name__)
_WECOM_LEASE_PREFIX = "wecom:lease"
_WECOM_NODE_PREFIX = "wecom:nodes"
_WECOM_LEASE_TTL_SECONDS = 60
_WECOM_NODE_TTL_SECONDS = 60
_WECOM_LEASE_REFRESH_INTERVAL = 20
_WECOM_REBALANCE_INTERVAL = 20
_RELEASE_LEASE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""
_REFRESH_LEASE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("EXPIRE", KEYS[1], ARGV[2])
else
    return 0
end
"""


class WeComChannelManager(UserChannelManager):
    """
    Manager for all user WeCom channels.

    Manages multiple WeCom AI Bot connections, one per user.
    Uses Redis lease-based distributed coordination to ensure
    each bot_id is only connected from one instance.
    """

    channel_type = ChannelType.WECOM
    config_class = WeComConfig

    def __init__(self, message_handler: Optional[Callable] = None):
        super().__init__(message_handler)
        self._storage = ChannelStorage()
        self._message_handler: Optional[Callable] = message_handler
        # Track active bot_ids to prevent duplicate bot connections
        self._active_bot_ids: dict[str, str] = {}  # bot_id -> channel_key
        self._instance_id = uuid.uuid4().hex
        self._lease_tasks: dict[str, asyncio.Task] = {}
        self._lease_redis: Redis | None = None
        self._rebalance_task: asyncio.Task | None = None

    @classmethod
    def get_instance(cls) -> "WeComChannelManager":
        """Get the singleton instance, consistent with get_wecom_channel_manager()."""
        return get_wecom_channel_manager()

    def _dict_to_config(
        self,
        user_id: str,
        config_dict: dict[str, Any],
        instance_id: Optional[str] = None,
    ) -> WeComConfig:
        """Convert a config dict to WeComConfig."""
        resolved_instance_id = instance_id or config_dict.get("instance_id") or ""
        return WeComConfig(
            user_id=user_id,
            instance_id=resolved_instance_id,
            bot_id=config_dict.get("bot_id") or "",
            secret=config_dict.get("secret") or "",
            group_policy=WeComGroupPolicy(config_dict.get("group_policy") or "mention"),
            stream_reply=config_dict.get("stream_reply", True),
            send_thinking_message=config_dict.get("send_thinking_message", True),
            segmented_reply=config_dict.get("segmented_reply", True),
            websocket_url=config_dict.get("websocket_url") or "wss://openws.work.weixin.qq.com",
            enabled=config_dict.get("enabled", True),
        )

    async def start(self) -> None:
        """Start all enabled WeCom channels."""
        if not WECOM_AVAILABLE:
            logger.warning("WeCom SDK not installed. Run: pip install wecom-aibot-sdk")
            return

        self._running = True

        started, skipped = await self._reconcile_enabled_configs()
        self._ensure_rebalance_task()
        logger.info(
            "WeCom startup processed enabled configurations: started=%s skipped=%s",
            started,
            skipped,
        )

    async def stop(self) -> None:
        """Stop all WeCom channels."""
        self._running = False
        await self._cancel_rebalance_task()

        for user_id, client in list(self._channels.items()):
            try:
                await client.stop()
            except Exception as e:
                logger.error(f"Error stopping WeCom client for user {user_id}: {e}")

        await self._release_all_leases()
        await self._unregister_node()
        await self._close_lease_redis()
        self._channels.clear()
        self._active_bot_ids.clear()
        await self._storage.close()

    async def _reconcile_enabled_configs(self) -> tuple[int, int]:
        """Start only configs assigned to this node and stop unassigned local channels."""
        if not await self._refresh_node_membership():
            return 0, 0

        node_ids = await self._list_active_node_ids()
        if self._instance_id not in node_ids:
            node_ids.append(self._instance_id)
            node_ids.sort()

        started = 0
        skipped = 0
        desired_local_keys: set[str] = set()

        async for config_dict in self._storage.iter_enabled_configs(ChannelType.WECOM):
            try:
                user_id = config_dict.get("user_id")
                if not user_id:
                    logger.warning("Skipping config without user_id")
                    skipped += 1
                    continue

                bot_id = config_dict.get("bot_id") or ""
                secret = config_dict.get("secret") or ""

                if not bot_id or not secret:
                    logger.warning(
                        f"Skipping WeCom config for user {user_id}: "
                        "missing bot_id or secret (decryption may have failed). "
                        "Please re-save the channel configuration."
                    )
                    skipped += 1
                    continue

                channel_key = self._channel_key(
                    user_id,
                    config_dict.get("instance_id") or "",
                )
                if self._preferred_owner(bot_id, node_ids) != self._instance_id:
                    await self._stop_channel_by_key(channel_key)
                    skipped += 1
                    continue

                desired_local_keys.add(channel_key)
                config = self._dict_to_config(user_id, config_dict)
                if await self._start_user_client(config, replace_existing=False):
                    started += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(
                    f"Failed to reconcile WeCom client for user {config_dict.get('user_id')}: {e}"
                )
                skipped += 1

        for channel_key in list(self._channels.keys()):
            if channel_key not in desired_local_keys:
                await self._stop_channel_by_key(channel_key)

        return started, skipped

    async def _refresh_node_membership(self) -> bool:
        try:
            redis = self._get_lease_redis()
            await redis.set(
                self._node_key(self._instance_id),
                self._instance_id,
                ex=_WECOM_NODE_TTL_SECONDS,
            )
            return True
        except Exception as e:
            logger.warning("[WeCom] Failed to refresh node membership: %s", e)
            return False

    async def _list_active_node_ids(self) -> list[str]:
        redis = self._get_lease_redis()
        pattern = self._node_key("*")
        cursor: int | str = 0
        node_ids: set[str] = set()
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                key_text = key.decode() if isinstance(key, bytes) else str(key)
                node_id = key_text.rsplit(":", 1)[-1]
                if node_id:
                    node_ids.add(node_id)
            if int(cursor) == 0:
                return sorted(node_ids)

    async def _unregister_node(self) -> None:
        try:
            redis = self._get_lease_redis()
            await redis.delete(self._node_key(self._instance_id))
        except Exception as e:
            logger.warning("[WeCom] Failed to unregister node membership: %s", e)

    def _ensure_rebalance_task(self) -> None:
        if self._rebalance_task and not self._rebalance_task.done():
            return
        self._rebalance_task = asyncio.create_task(self._rebalance_loop())

    async def _rebalance_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(_WECOM_REBALANCE_INTERVAL)
                await self._reconcile_enabled_configs()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[WeCom] Rebalance loop stopped unexpectedly: %s", e)
        finally:
            self._rebalance_task = None

    async def _cancel_rebalance_task(self) -> None:
        task = self._rebalance_task
        self._rebalance_task = None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    @staticmethod
    def _node_key(instance_id: str) -> str:
        return f"{_WECOM_NODE_PREFIX}:{instance_id}"

    @staticmethod
    def _channel_key(user_id: str, instance_id: str | None = None) -> str:
        return f"{user_id}:{instance_id}" if instance_id else user_id

    @staticmethod
    def _preferred_owner(bot_id: str, node_ids: list[str]) -> str | None:
        if not node_ids:
            return None
        return max(
            node_ids,
            key=lambda node_id: hashlib.sha256(f"{bot_id}:{node_id}".encode()).hexdigest(),
        )

    async def _start_user_client(
        self,
        config: WeComConfig,
        *,
        replace_existing: bool = True,
    ) -> bool:
        """Start a user's WeCom client."""
        channel_key = self._channel_key(config.user_id, config.instance_id)

        existing_channel = self._channels.get(channel_key)
        existing_bot_id = (
            getattr(existing_channel.config, "bot_id", None) if existing_channel else None
        )
        existing_running = bool(
            getattr(existing_channel, "is_running", getattr(existing_channel, "_running", False))
        )
        if (
            existing_channel
            and not replace_existing
            and existing_bot_id == config.bot_id
            and existing_running
        ):
            existing_channel.message_handler = self._message_handler
            self._active_bot_ids[config.bot_id] = channel_key
            self._ensure_lease_refresh_task(config.bot_id)
            return True

        # Prevent duplicate bot connections: same bot_id should only have one active channel
        bot_id = config.bot_id
        if bot_id in self._active_bot_ids:
            existing_key = self._active_bot_ids[bot_id]
            if existing_key != channel_key and existing_key in self._channels:
                logger.warning(
                    f"[WeCom] Duplicate bot detected: bot_id={bot_id} already active "
                    f"as '{existing_key}', skipping '{channel_key}'"
                )
                return False

        if not await self._acquire_lease(bot_id):
            logger.info(
                "[WeCom] Lease for bot_id=%s is held by another instance, skipping '%s'",
                bot_id,
                channel_key,
            )
            return False

        try:
            if channel_key in self._channels:
                await self._channels[channel_key].stop()
                old_bot_id = getattr(self._channels[channel_key].config, "bot_id", None)
                if old_bot_id and old_bot_id in self._active_bot_ids:
                    del self._active_bot_ids[old_bot_id]

            client = WeComChannel(config, self._message_handler)
            success = await client.start()

            if success:
                self._channels[channel_key] = client
                self._active_bot_ids[bot_id] = channel_key
                self._ensure_lease_refresh_task(bot_id)
                return True
            await self._release_lease(bot_id)
            return False
        except BaseException:
            await self._release_lease(bot_id)
            raise

    async def reload_user(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        """Reload a user's WeCom configuration and restart the client.

        Args:
            user_id: The user ID
            instance_id: Optional specific instance ID to reload. If None, reloads all instances.
        """
        if instance_id:
            channel_key = self._channel_key(user_id, instance_id)
            if channel_key in self._channels:
                await self._stop_channel_by_key(channel_key)
                logger.info(f"Stopped WeCom client for {channel_key}")

            config_dict = await self._storage.get_config(user_id, ChannelType.WECOM, instance_id)
            if config_dict and config_dict.get("enabled", True):
                if await self._refresh_node_membership():
                    nodes = await self._list_active_node_ids()
                    if self._instance_id not in nodes:
                        nodes.append(self._instance_id)
                    bot_id = config_dict.get("bot_id") or ""
                    if self._preferred_owner(bot_id, sorted(nodes)) != self._instance_id:
                        return True
                config = self._dict_to_config(user_id, config_dict, instance_id)
                return await self._start_user_client(config)
            return True

        # Legacy behavior: reload all instances for user
        wecom_configs = await self._storage.list_user_configs_by_type(user_id, ChannelType.WECOM)

        for key in list(self._channels.keys()):
            if key.startswith(user_id):
                await self._stop_channel_by_key(key)

        for config_dict in wecom_configs:
            if config_dict.get("enabled", True):
                inst_id = config_dict.get("instance_id")
                bot_id = config_dict.get("bot_id") or ""
                if await self._refresh_node_membership():
                    nodes = await self._list_active_node_ids()
                    if self._instance_id not in nodes:
                        nodes.append(self._instance_id)
                    if self._preferred_owner(bot_id, sorted(nodes)) != self._instance_id:
                        continue
                config = self._dict_to_config(user_id, config_dict, inst_id)
                await self._start_user_client(config)

        return True

    def _find_channel(
        self, user_id: str, instance_id: Optional[str] = None
    ) -> Optional[WeComChannel]:
        """Find a channel by user_id, with fallback to prefix match."""
        if instance_id:
            channel = self._channels.get(f"{user_id}:{instance_id}")
            if channel:
                return channel  # type: ignore[return-value]

        channel = self._channels.get(user_id)
        if channel:
            return channel  # type: ignore[return-value]

        # Fallback: find first channel whose key starts with "user_id:"
        prefix = f"{user_id}:"
        for key, ch in self._channels.items():
            if key.startswith(prefix):
                logger.debug(
                    f"[WeCom] _find_channel fallback: matched key '{key}' for user '{user_id}'"
                )
                return ch  # type: ignore[return-value]

        return None

    async def send_message(
        self,
        user_id: str,
        chat_id: str,
        content: str,
        instance_id: Optional[str] = None,
    ) -> bool:
        """Send a message through a user's WeCom bot."""
        client = self._find_channel(user_id, instance_id)
        if not client:
            logger.warning(f"No WeCom client for user {user_id}, instance {instance_id}")
            return False

        return await client.send_message(chat_id, content)

    def is_connected(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        """Check if a user's WeCom bot is connected."""
        channel = self._find_channel(user_id, instance_id)
        return channel is not None and channel._running

    async def is_connected_distributed(
        self, user_id: str, instance_id: Optional[str] = None
    ) -> bool:
        """Check whether a WeCom bot is connected anywhere in the cluster."""
        if self.is_connected(user_id, instance_id):
            return True

        if instance_id:
            config = await self._storage.get_config(user_id, ChannelType.WECOM, instance_id)
            return await self._has_cluster_lease(config)

        configs = await self._storage.list_user_configs_by_type(user_id, ChannelType.WECOM)
        for config in configs:
            if not config.get("enabled", True):
                continue
            config_instance_id = config.get("instance_id")
            if config_instance_id and self.is_connected(user_id, config_instance_id):
                return True
            if await self._has_cluster_lease(config):
                return True
        return False

    async def _stop_channel_by_key(self, channel_key: str) -> None:
        channel = self._channels.pop(channel_key, None)
        if not channel:
            return

        old_bot_id = getattr(channel.config, "bot_id", None)
        if old_bot_id and self._active_bot_ids.get(old_bot_id) == channel_key:
            del self._active_bot_ids[old_bot_id]

        try:
            await channel.stop()
        except Exception as e:
            logger.error(f"Error stopping WeCom client {channel_key}: {e}")

        if old_bot_id:
            await self._release_lease(old_bot_id)

    async def _has_cluster_lease(self, config: dict[str, Any] | None) -> bool:
        if not config or not config.get("enabled", True):
            return False
        bot_id = config.get("bot_id") or ""
        if not bot_id:
            return False
        try:
            redis = self._get_lease_redis()
            return bool(await redis.get(self._lease_key(bot_id)))
        except Exception as e:
            logger.warning("[WeCom] Failed to read lease for bot_id=%s: %s", bot_id, e)
            return False

    @staticmethod
    def _lease_key(bot_id: str) -> str:
        return f"{_WECOM_LEASE_PREFIX}:{bot_id}"

    async def _acquire_lease(self, bot_id: str) -> bool:
        try:
            redis = self._get_lease_redis()
            claimed = await redis.set(
                self._lease_key(bot_id),
                self._instance_id,
                nx=True,
                ex=_WECOM_LEASE_TTL_SECONDS,
            )
            return bool(claimed)
        except Exception as e:
            logger.warning("[WeCom] Failed to acquire lease for bot_id=%s: %s", bot_id, e)
            return False

    def _ensure_lease_refresh_task(self, bot_id: str) -> None:
        if bot_id in self._lease_tasks:
            return

        async def _refresh() -> None:
            try:
                redis = self._get_lease_redis()
                while True:
                    await asyncio.sleep(_WECOM_LEASE_REFRESH_INTERVAL)
                    if bot_id not in self._active_bot_ids:
                        return
                    refreshed = await redis.eval(
                        _REFRESH_LEASE_LUA,
                        1,
                        self._lease_key(bot_id),
                        self._instance_id,
                        _WECOM_LEASE_TTL_SECONDS,
                    )
                    if not refreshed:
                        logger.warning(
                            "[WeCom] Lost lease refresh for bot_id=%s on instance=%s",
                            bot_id,
                            self._instance_id,
                        )
                        await self._stop_channel_after_lost_lease(bot_id)
                        return
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("[WeCom] Lease refresh failed for bot_id=%s: %s", bot_id, e)
                await self._stop_channel_after_lost_lease(bot_id)
            finally:
                self._lease_tasks.pop(bot_id, None)

        self._lease_tasks[bot_id] = asyncio.create_task(_refresh())

    async def _stop_channel_after_lost_lease(self, bot_id: str) -> None:
        channel_key = self._active_bot_ids.pop(bot_id, None)
        if not channel_key:
            return

        channel = self._channels.pop(channel_key, None)
        if not channel:
            return

        try:
            await channel.stop()
            logger.warning(
                "[WeCom] Stopped local channel '%s' after losing lease for bot_id=%s",
                channel_key,
                bot_id,
            )
        except Exception as e:
            logger.error(
                "[WeCom] Failed to stop channel '%s' after losing lease for bot_id=%s: %s",
                channel_key,
                bot_id,
                e,
            )

    async def _release_lease(self, bot_id: str) -> None:
        task = self._lease_tasks.pop(bot_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            redis = self._get_lease_redis()
            await redis.eval(_RELEASE_LEASE_LUA, 1, self._lease_key(bot_id), self._instance_id)
        except Exception as e:
            logger.warning("[WeCom] Failed to release lease for bot_id=%s: %s", bot_id, e)

    def _cancel_all_lease_tasks(self) -> None:
        for bot_id in list(self._lease_tasks.keys()):
            task = self._lease_tasks.pop(bot_id, None)
            if task and not task.done():
                task.cancel()

    async def _release_all_leases(self) -> None:
        for bot_id in list(self._active_bot_ids.keys()):
            await self._release_lease(bot_id)

    def _get_lease_redis(self):
        if self._lease_redis is None:
            self._lease_redis = create_redis_client(isolated_pool=True)
        return self._lease_redis

    async def _close_lease_redis(self) -> None:
        if self._lease_redis is None:
            return
        try:
            await self._lease_redis.aclose()
        except Exception as e:
            logger.warning("[WeCom] Failed to close lease redis client: %s", e)
        finally:
            self._lease_redis = None


# Global instance
_wecom_channel_manager: Optional[WeComChannelManager] = None


def get_wecom_channel_manager() -> WeComChannelManager:
    """Get the global WeCom channel manager instance."""
    global _wecom_channel_manager
    if _wecom_channel_manager is None:
        _wecom_channel_manager = WeComChannelManager()
    return _wecom_channel_manager


async def start_wecom_channels(message_handler=None) -> None:
    """Start the WeCom channel manager with all enabled user bots."""
    manager = get_wecom_channel_manager()
    manager._message_handler = message_handler
    await manager.start()


async def stop_wecom_channels() -> None:
    """Stop the WeCom channel manager."""
    global _wecom_channel_manager
    if _wecom_channel_manager:
        await _wecom_channel_manager.stop()
        _wecom_channel_manager = None
