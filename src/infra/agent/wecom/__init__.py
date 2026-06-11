"""
WeCom (企业微信) role-based bot module.

Provides WeCom AI Bot integration with WebSocket long connection support.
Each aibotid maps to one role; messages are routed by aibotid to the
corresponding role's agent. Sessions belong to the WeCom sender_id.
"""

from src.infra.agent.wecom.bot import WECOM_AVAILABLE, WeComBot
from src.infra.agent.wecom.collector import WeComResponseCollector
from src.infra.agent.wecom.handler import (
    create_wecom_message_handler,
    setup_wecom_handler,
)
from src.infra.agent.wecom.manager import (
    WeComBotManager,
    get_wecom_bot_manager,
    start_wecom_bots,
    stop_wecom_bots,
)

__all__ = [
    # Bot
    "WECOM_AVAILABLE",
    "WeComBot",
    # Manager
    "WeComBotManager",
    "get_wecom_bot_manager",
    "start_wecom_bots",
    "stop_wecom_bots",
    # Handler
    "WeComResponseCollector",
    "create_wecom_message_handler",
    "setup_wecom_handler",
]
