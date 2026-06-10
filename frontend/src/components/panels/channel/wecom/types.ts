/**
 * WeCom-specific types.
 * Self-contained — no longer depends on the deleted generic channel types.
 */

export type WeComConfigResponse = {
  bot_id: string;
  has_secret?: boolean;
  group_policy: "open" | "mention";
  stream_reply?: boolean;
  send_thinking_message?: boolean;
  segmented_reply?: boolean;
  session_ttl_hours?: number;
  websocket_url?: string;
  secret?: string;
  enabled?: boolean;
};

export type WeComConfigStatus = {
  enabled: boolean;
  connected: boolean;
  error_message?: string;
  last_connected_at?: string;
};

/**
 * Full channel instance response from the backend.
 * Used when loading a WeCom instance config via the API.
 */
export interface WeComInstanceResponse {
  instance_id: string;
  name: string;
  user_id: string;
  enabled: boolean;
  config: WeComConfigResponse;
  agent_id?: string | null;
  model_id?: string | null;
  project_id?: string | null;
  team_id?: string | null;
  persona_preset_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface WeComPanelProps {
  instanceId: string;
  initialConfig?: WeComInstanceResponse | null;
  initialStatus?: WeComConfigStatus | null;
  isLoading?: boolean;
  onClose?: () => void;
}
