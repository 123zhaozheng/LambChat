"""WeCom (企业微信) AI Bot channel configuration schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.infra.utils.datetime import utc_now

DEFAULT_AUDIO_TRANSCRIBE_PROMPT = (
    "Please transcribe and understand this voice message. "
    "Use the audio_transcribe tool for the attached audio when needed."
)


class WeComGroupPolicy(str, Enum):
    """Group message handling policy."""

    OPEN = "open"  # Respond to all group messages
    MENTION = "mention"  # Respond only when @mentioned


class WeComConfigBase(BaseModel):
    """Base WeCom configuration schema."""

    instance_id: str = Field("", description="多实例支持的实例 ID")
    bot_id: str = Field(..., description="企业微信机器人 ID")
    secret: str = Field(..., description="企业微信机器人密钥")
    group_policy: WeComGroupPolicy = Field(
        WeComGroupPolicy.MENTION, description="群聊消息策略"
    )
    stream_reply: bool = Field(True, description="通过 WebSocket 流式回复")
    send_thinking_message: bool = Field(
        True, description="在 5 秒回调期限内发送思考占位消息"
    )
    auto_transcribe_audio: bool = Field(
        True, description="让 Agent 转写接收到的语音附件"
    )
    audio_transcribe_prompt: str = Field(
        DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
        description="收到语音消息时发送给 Agent 的提示词",
    )
    websocket_url: str = Field(
        "wss://openws.work.weixin.qq.com",
        description="私有化部署的 WebSocket 地址",
    )
    enabled: bool = Field(True, description="是否启用此渠道")


class WeComConfigCreate(WeComConfigBase):
    """Schema for creating WeCom configuration."""

    pass


class WeComConfigUpdate(BaseModel):
    """Schema for updating WeCom configuration."""

    model_config = ConfigDict(extra="forbid")

    bot_id: Optional[str] = None
    secret: Optional[str] = None
    group_policy: Optional[WeComGroupPolicy] = None
    stream_reply: Optional[bool] = None
    send_thinking_message: Optional[bool] = None
    auto_transcribe_audio: Optional[bool] = None
    audio_transcribe_prompt: Optional[str] = None
    websocket_url: Optional[str] = None
    enabled: Optional[bool] = None


class WeComConfig(WeComConfigBase):
    """WeCom configuration model (database view)."""

    user_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Config:
        from_attributes = True


class WeComConfigResponse(BaseModel):
    """WeCom configuration response (masked sensitive fields)."""

    user_id: str
    bot_id: str  # Can show bot_id (not sensitive)
    has_secret: bool  # Only show if secret is set
    group_policy: WeComGroupPolicy = WeComGroupPolicy.MENTION
    stream_reply: bool = True
    send_thinking_message: bool = True
    auto_transcribe_audio: bool = True
    audio_transcribe_prompt: str = DEFAULT_AUDIO_TRANSCRIBE_PROMPT
    websocket_url: str = "wss://openws.work.weixin.qq.com"
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WeComConfigStatus(BaseModel):
    """WeCom connection status."""

    enabled: bool
    connected: bool = False
    error_message: Optional[str] = None
    last_connected_at: Optional[datetime] = None
