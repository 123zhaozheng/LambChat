"""WeCom (企业微信) AI Bot role-entry configuration schemas.

The old instance-model schemas (WeComConfigBase, WeComConfig, etc.) have been
removed as part of the WeCom instance-to-role refactoring.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WeComGroupPolicy(str, Enum):
    """Group message handling policy."""

    OPEN = "open"  # Respond to all group messages
    MENTION = "mention"  # Respond only when @mentioned


# ============================================
# Role WeCom Config Schemas
# ============================================


class RoleWeComConfigBase(BaseModel):
    """Base schema for role-level WeCom configuration."""

    aibotid: str = Field(..., description="企业微信机器人 bot_id")
    secret: str = Field(..., description="企业微信机器人密钥")
    stream_reply: bool = Field(True, description="通过 WebSocket 流式回复")
    send_thinking_message: bool = Field(
        True, description="在 5 秒回调期限内发送思考占位消息"
    )
    segmented_reply: bool = Field(True, description="超长回复自动分段发送")
    session_ttl_hours: int = Field(24, description="会话 TTL 小时数，0 表示永不过期")


class RoleWeComConfigCreate(RoleWeComConfigBase):
    """Schema for creating role-level WeCom configuration."""

    pass


class RoleWeComConfigUpdate(BaseModel):
    """Schema for updating role-level WeCom configuration."""

    model_config = ConfigDict(extra="forbid")

    aibotid: Optional[str] = None
    secret: Optional[str] = None
    stream_reply: Optional[bool] = None
    send_thinking_message: Optional[bool] = None
    segmented_reply: Optional[bool] = None
    session_ttl_hours: Optional[int] = None


class RoleWeComConfig(BaseModel):
    """Role-level WeCom configuration (database view)."""

    role_id: str
    aibotid: str
    has_secret: bool = True
    stream_reply: bool = True
    send_thinking_message: bool = True
    segmented_reply: bool = True
    session_ttl_hours: int = 24
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
