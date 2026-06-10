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
  segmented_reply?: boolean;
  session_ttl_hours?: number;
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
