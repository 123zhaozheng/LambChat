"""
WeCom (企业微信) channel module.

This module provides WeCom AI Bot integration with WebSocket long connection support.
Each user can have their own WeCom AI Bot configuration.
"""

from src.infra.channel.wecom.channel import WECOM_AVAILABLE, WeComChannel
from src.infra.channel.wecom.handler import (
    WeComResponseCollector,
    create_wecom_message_handler,
    setup_wecom_handler,
)
from src.infra.channel.wecom.manager import (
    WeComChannelManager,
    get_wecom_channel_manager,
    start_wecom_channels,
    stop_wecom_channels,
)
from src.infra.channel.wecom.storage import WeComConfigStorage

__all__ = [
    # Channel
    "WECOM_AVAILABLE",
    "WeComChannel",
    # Manager
    "WeComChannelManager",
    "get_wecom_channel_manager",
    "start_wecom_channels",
    "stop_wecom_channels",
    # Handler
    "WeComResponseCollector",
    "create_wecom_message_handler",
    "setup_wecom_handler",
    # Storage
    "WeComConfigStorage",
]
