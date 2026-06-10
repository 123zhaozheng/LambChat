"""Channel infrastructure module.

Provides WeCom chat platform integration.
"""

from src.infra.channel.wecom import (
    WeComChannelManager,
    WeComConfigStorage,
    WeComResponseCollector,
    create_wecom_message_handler,
    get_wecom_channel_manager,
    setup_wecom_handler,
    start_wecom_channels,
    stop_wecom_channels,
)

__all__ = [
    # WeCom
    "WeComChannelManager",
    "WeComConfigStorage",
    "WeComResponseCollector",
    "create_wecom_message_handler",
    "get_wecom_channel_manager",
    "setup_wecom_handler",
    "start_wecom_channels",
    "stop_wecom_channels",
]
