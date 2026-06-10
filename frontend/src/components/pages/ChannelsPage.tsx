/**
 * Channels Page - Renders WeCom channel configuration.
 *
 * After removing the generic multi-channel framework, only WeCom remains.
 * This page directly renders the WeCom panel for the selected instance.
 */
import { useParams } from "react-router-dom";
import { WeComPanel } from "../panels/channel/wecom/WeComPanel";

export function ChannelsPage() {
  const { instanceId } = useParams<{ channelType?: string; instanceId?: string }>();

  if (instanceId && instanceId !== "new") {
    return <WeComPanel instanceId={instanceId} />;
  }

  return <WeComPanel instanceId="new" />;
}
