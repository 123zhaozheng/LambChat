/**
 * WeCom API - WeCom channel configuration service
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  WeComConfigResponse,
  WeComConfigStatus,
} from "../../components/panels/channel/wecom/types";

// WeCom instance config response from the backend
interface WeComInstanceResponse {
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

export const wecomApi = {
  /**
   * Get a WeCom instance configuration
   */
  async get(instanceId: string): Promise<WeComInstanceResponse | null> {
    return authFetch<WeComInstanceResponse | null>(
      `${API_BASE}/api/channels/wecom/${instanceId}`,
    );
  },

  /**
   * Get WeCom connection status for an instance
   */
  async getStatus(instanceId: string): Promise<WeComConfigStatus> {
    return authFetch<WeComConfigStatus>(
      `${API_BASE}/api/channels/wecom/${instanceId}/status`,
    );
  },

  /**
   * Create a WeCom instance
   */
  async create(data: {
    name: string;
    config: Record<string, unknown>;
    agent_id?: string | null;
    model_id?: string | null;
    team_id?: string | null;
    persona_preset_id?: string | null;
  }): Promise<WeComInstanceResponse> {
    return authFetch<WeComInstanceResponse>(
      `${API_BASE}/api/channels/wecom`,
      {
        method: "POST",
        body: JSON.stringify({
          channel_type: "wecom",
          ...data,
        }),
      },
    );
  },

  /**
   * Update a WeCom instance
   */
  async update(
    instanceId: string,
    data: {
      config: Record<string, unknown>;
      enabled?: boolean;
      agent_id?: string | null;
      model_id?: string | null;
      team_id?: string | null;
      persona_preset_id?: string | null;
    },
  ): Promise<WeComInstanceResponse> {
    return authFetch<WeComInstanceResponse>(
      `${API_BASE}/api/channels/wecom/${instanceId}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Delete a WeCom instance
   */
  async delete(instanceId: string): Promise<{ message: string }> {
    return authFetch<{ message: string }>(
      `${API_BASE}/api/channels/wecom/${instanceId}`,
      {
        method: "DELETE",
      },
    );
  },

  /**
   * Test WeCom connection for an instance
   */
  async test(instanceId: string): Promise<{ success: boolean; message: string }> {
    return authFetch<{ success: boolean; message: string }>(
      `${API_BASE}/api/channels/wecom/${instanceId}/test`,
      {
        method: "POST",
      },
    );
  },
};
