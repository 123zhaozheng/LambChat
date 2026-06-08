import type {
  ChannelConfigResponse,
  ChannelConfigStatus,
} from "../../../../types/channel";

export type WeComConfigResponse = ChannelConfigResponse["config"] & {
  bot_id: string;
  has_secret?: boolean;
  group_policy: "open" | "mention";
  stream_reply?: boolean;
  send_thinking_message?: boolean;
  auto_transcribe_audio?: boolean;
  audio_transcribe_prompt?: string;
  websocket_url?: string;
};

export type WeComConfigStatus = ChannelConfigStatus;

export interface WeComPanelProps {
  instanceId: string;
  initialConfig?: ChannelConfigResponse | null;
  initialStatus?: WeComConfigStatus | null;
  isLoading?: boolean;
  onClose?: () => void;
}
