"""
WeCom connection state management.

Migrated from src.infra.channel.wecom.state — no longer depends on the
generic channel framework.
"""

from enum import Enum


class ConnectionState(Enum):
    """WebSocket connection state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
