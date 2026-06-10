import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BackIcon } from "../../../common/BackIcon";
import { Building2, Save, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../../hooks/useAuth";
import { Permission } from "../../../../types";
import { PanelHeader } from "../../../common/PanelHeader";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ChannelConfigSkeleton } from "../../../skeletons";
import { EditorSidebar } from "../../../common/EditorSidebar";
import { ConfirmDialog } from "../../../common/ConfirmDialog";
import { channelApi } from "../../../../services/api/channel";
import { WECOM_DEFAULTS } from "./constants";
import { WeComPanelForm } from "./WeComPanelForm";
import type {
  WeComConfigResponse,
  WeComConfigStatus,
  WeComPanelProps,
} from "./types";

export function WeComPanel({
  instanceId,
  initialConfig,
  initialStatus,
  isLoading: externalIsLoading,
  onClose,
}: WeComPanelProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const navigate = useNavigate();

  const canWrite = hasPermission(Permission.CHANNEL_WRITE);
  const canDelete = hasPermission(Permission.CHANNEL_DELETE);

  // State
  const [, setConfig] = useState<WeComConfigResponse | null>(null);
  const [status, setStatus] = useState<WeComConfigStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  // Form state
  const [instanceName, setInstanceName] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [botId, setBotId] = useState("");
  const [secret, setSecret] = useState("");
  const [groupPolicy, setGroupPolicy] = useState<"open" | "mention">("mention");
  const [streamReply, setStreamReply] = useState(true);
  const [sendThinkingMessage, setSendThinkingMessage] = useState(true);
  const [segmentedReply, setSegmentedReply] = useState<boolean>(WECOM_DEFAULTS.segmentedReply);
  const [sessionTtlHours, setSessionTtlHours] = useState<number>(WECOM_DEFAULTS.sessionTtlHours);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [teamId, setTeamId] = useState<string | null>(null);
  const [personaPresetId, setPersonaPresetId] = useState<string | null>(null);

  // Track if config exists
  const [hasExistingConfig, setHasExistingConfig] = useState(false);

  // Delete confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Load config - use external data if provided, otherwise fetch from API
  useEffect(() => {
    if (externalIsLoading) {
      return;
    }

    if (initialConfig || initialStatus) {
      initializeFromExternalData();
      return;
    }

    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalIsLoading, initialConfig, initialStatus]);

  const initializeFromExternalData = () => {
    if (initialConfig) {
      const wecomConfig = initialConfig.config as unknown as
        | WeComConfigResponse
        | undefined;
      setConfig(wecomConfig ?? null);
      setHasExistingConfig(true);
      setInstanceName(initialConfig.name || "");
      setEnabled(initialConfig.enabled);
      setBotId(wecomConfig?.bot_id || "");
      setGroupPolicy(wecomConfig?.group_policy || "mention");
      setStreamReply(wecomConfig?.stream_reply ?? true);
      setSendThinkingMessage(wecomConfig?.send_thinking_message ?? true);
      setSegmentedReply(wecomConfig?.segmented_reply ?? WECOM_DEFAULTS.segmentedReply);
      setSessionTtlHours(wecomConfig?.session_ttl_hours ?? WECOM_DEFAULTS.sessionTtlHours);
      const initialAgentId = initialConfig.agent_id || null;
      setAgentId(initialAgentId);
      setModelId(initialConfig.model_id || null);
      setTeamId(
        initialAgentId === "team" ? initialConfig.team_id || null : null,
      );
      setPersonaPresetId(
        initialAgentId === "team"
          ? null
          : initialConfig.persona_preset_id || null,
      );
    } else {
      setHasExistingConfig(false);
      setInstanceName("");
      setEnabled(false);
      setBotId("");
      setSecret("");
      setGroupPolicy("mention");
      setStreamReply(true);
      setSendThinkingMessage(true);
      setSegmentedReply(WECOM_DEFAULTS.segmentedReply);
      setSessionTtlHours(WECOM_DEFAULTS.sessionTtlHours);
      setAgentId(null);
      setModelId(null);
      setTeamId(null);
      setPersonaPresetId(null);
    }

    if (initialStatus) {
      setStatus(initialStatus as WeComConfigStatus);
    }
    setIsLoading(false);
  };

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      if (instanceId === "new") {
        setHasExistingConfig(false);
        setEnabled(false);
        setInstanceName("");
        setBotId("");
        setSecret("");
        setGroupPolicy("mention");
        setStreamReply(true);
        setSendThinkingMessage(true);
        setSegmentedReply(WECOM_DEFAULTS.segmentedReply);
        setSessionTtlHours(WECOM_DEFAULTS.sessionTtlHours);
        setStatus(null);
        setAgentId(null);
        setModelId(null);
        setTeamId(null);
        setPersonaPresetId(null);
        setIsLoading(false);
        return;
      }

      const [configResponse, statusResponse] = await Promise.all([
        channelApi.get("wecom", instanceId!),
        channelApi.getStatus("wecom", instanceId!),
      ]);

      if (configResponse) {
        const wecomConfig = configResponse.config as WeComConfigResponse;
        setConfig(wecomConfig);
        setHasExistingConfig(true);
        setInstanceName(configResponse.name || "");
        setEnabled(configResponse.enabled);
        setBotId(wecomConfig.bot_id || "");
        setGroupPolicy(wecomConfig.group_policy || "mention");
        setStreamReply(wecomConfig.stream_reply ?? true);
        setSendThinkingMessage(wecomConfig.send_thinking_message ?? true);
        setSegmentedReply(wecomConfig.segmented_reply ?? WECOM_DEFAULTS.segmentedReply);
        setSessionTtlHours(wecomConfig.session_ttl_hours ?? WECOM_DEFAULTS.sessionTtlHours);
        const loadedAgentId = configResponse.agent_id || null;
        setAgentId(loadedAgentId);
        setModelId(configResponse.model_id || null);
        setTeamId(
          loadedAgentId === "team" ? configResponse.team_id || null : null,
        );
        setPersonaPresetId(
          loadedAgentId === "team"
            ? null
            : configResponse.persona_preset_id || null,
        );
      } else {
        setHasExistingConfig(false);
        setInstanceName("");
        setEnabled(false);
        setBotId("");
        setSecret("");
        setGroupPolicy("mention");
        setStreamReply(true);
        setSendThinkingMessage(true);
        setSegmentedReply(WECOM_DEFAULTS.segmentedReply);
        setSessionTtlHours(WECOM_DEFAULTS.sessionTtlHours);
        setAgentId(null);
        setModelId(null);
        setTeamId(null);
        setPersonaPresetId(null);
      }

      setStatus(statusResponse);
    } catch (error) {
      console.error("Failed to load WeCom config:", error);
      toast.error(t("wecom.loadError", "加载企业微信配置失败"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleAgentIdChange = (value: string | null) => {
    setAgentId(value);
    if (value === "team") {
      setPersonaPresetId(null);
    } else {
      setTeamId(null);
    }
  };

  const handleSave = async () => {
    if (!hasExistingConfig && !instanceName.trim()) {
      toast.error(
        t("wecom.instanceNameRequired", "实例名称为必填项"),
      );
      return;
    }

    if (!botId.trim()) {
      toast.error(t("wecom.botIdRequired", "机器人 ID 为必填项"));
      return;
    }

    if (!hasExistingConfig && !secret.trim()) {
      toast.error(t("wecom.secretRequired", "机器人密钥为必填项"));
      return;
    }

    setIsSaving(true);
    try {
      const channelTeamId = agentId === "team" ? teamId : null;
      const channelPersonaPresetId =
        agentId === "team" ? null : personaPresetId;

      if (hasExistingConfig) {
        const updateData: Record<string, unknown> = {
          bot_id: botId,
          group_policy: groupPolicy,
          stream_reply: streamReply,
          send_thinking_message: sendThinkingMessage,
          segmented_reply: segmentedReply,
          session_ttl_hours: sessionTtlHours,
          enabled,
        };

        if (secret.trim()) {
          updateData.secret = secret;
        }

        const updated = await channelApi.update("wecom", instanceId, {
          config: updateData,
          enabled,
          agent_id: agentId,
          model_id: modelId,
          team_id: channelTeamId,
          persona_preset_id: channelPersonaPresetId,
        });
        const wecomConfig = updated.config as WeComConfigResponse;
        setConfig(wecomConfig);
        setHasExistingConfig(true);
        setSecret("");
      } else {
        const created = await channelApi.create({
          channel_type: "wecom",
          name: instanceName.trim(),
          config: {
            bot_id: botId,
            secret: secret,
            group_policy: groupPolicy,
            stream_reply: streamReply,
            send_thinking_message: sendThinkingMessage,
            segmented_reply: segmentedReply,
            session_ttl_hours: sessionTtlHours,
          },
          agent_id: agentId,
          model_id: modelId,
          team_id: channelTeamId,
          persona_preset_id: channelPersonaPresetId,
        });
        const wecomConfig = created.config as WeComConfigResponse;
        setConfig(wecomConfig);
        setHasExistingConfig(true);
        setSecret("");
        navigate(`/channels/wecom/${created.instance_id}`, { replace: true });
      }

      toast.success(t("wecom.saveSuccess", "企业微信配置已保存"));

      if (hasExistingConfig) {
        const newStatus = await channelApi.getStatus("wecom", instanceId);
        setStatus(newStatus);
      }
    } catch (error) {
      console.error("Failed to save WeCom config:", error);
      const errorMessage =
        error instanceof Error
          ? error.message
          : t("wecom.saveError", "保存企业微信配置失败");
      toast.error(errorMessage);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      await channelApi.delete("wecom", instanceId);
      setConfig(null);
      setHasExistingConfig(false);
      setEnabled(false);
      setBotId("");
      setSecret("");
      setGroupPolicy("mention");
      setStreamReply(true);
      setSendThinkingMessage(true);
      setSegmentedReply(WECOM_DEFAULTS.segmentedReply);
      setSessionTtlHours(WECOM_DEFAULTS.sessionTtlHours);
      setAgentId(null);
      setModelId(null);
      setTeamId(null);
      setPersonaPresetId(null);
      setStatus(null);
      toast.success(t("wecom.deleteSuccess", "企业微信配置已删除"));
      onClose?.();
    } catch (error) {
      console.error("Failed to delete WeCom config:", error);
      toast.error(
        t("wecom.deleteError", "删除企业微信配置失败"),
      );
    }
  };

  const handleTest = async () => {
    setIsTesting(true);
    try {
      const result = await channelApi.test("wecom", instanceId);
      if (result.success) {
        toast.success(
          result.message || t("wecom.testSuccess", "连接成功"),
        );
      } else {
        toast.error(
          result.message || t("wecom.testFailed", "连接失败"),
        );
      }
    } catch (error) {
      console.error("Failed to test WeCom connection:", error);
      toast.error(t("wecom.testError", "测试连接失败"));
    } finally {
      setIsTesting(false);
    }
  };

  if (isLoading) {
    return <ChannelConfigSkeleton />;
  }

  const formContent = (
    <WeComPanelForm
      t={t}
      hasExistingConfig={hasExistingConfig}
      status={status}
      enabled={enabled}
      isTesting={isTesting}
      instanceName={instanceName}
      botId={botId}
      secret={secret}
      groupPolicy={groupPolicy}
      streamReply={streamReply}
      sendThinkingMessage={sendThinkingMessage}
      segmentedReply={segmentedReply}
      sessionTtlHours={sessionTtlHours}
      agentId={agentId}
      modelId={modelId}
      teamId={teamId}
      personaPresetId={personaPresetId}
      setInstanceName={setInstanceName}
      setEnabled={setEnabled}
      setBotId={setBotId}
      setSecret={setSecret}
      setGroupPolicy={setGroupPolicy}
      setStreamReply={setStreamReply}
      setSendThinkingMessage={setSendThinkingMessage}
      setSegmentedReply={setSegmentedReply}
      setSessionTtlHours={setSessionTtlHours}
      setAgentId={handleAgentIdChange}
      setModelId={setModelId}
      setTeamId={setTeamId}
      setPersonaPresetId={setPersonaPresetId}
      handleTest={handleTest}
    />
  );

  // Action buttons
  const actionButtons = (
    <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:items-center sm:justify-between">
      {canDelete && (
        <button
          onClick={() => setShowDeleteConfirm(true)}
          disabled={!hasExistingConfig}
          className="btn-danger"
        >
          <Trash2 size={16} />
          {t("common.delete")}
        </button>
      )}
      {canWrite && (
        <button
          onClick={handleSave}
          disabled={isSaving || !botId.trim()}
          className="btn-primary"
        >
          {isSaving ? (
            <LoadingSpinner size="sm" color="text-white" />
          ) : (
            <Save size={16} />
          )}
          {t("common.save")}
        </button>
      )}
    </div>
  );

  const deleteDialog = (
    <ConfirmDialog
      isOpen={showDeleteConfirm}
      title={t("wecom.deleteTitle", "删除企业微信配置")}
      message={t(
        "wecom.deleteConfirmMessage",
        "确定要删除此企业微信配置吗？此操作无法撤销。",
      )}
      confirmText={t("common.delete", "Delete")}
      cancelText={t("common.cancel", "Cancel")}
      variant="danger"
      onConfirm={() => {
        setShowDeleteConfirm(false);
        handleDelete();
      }}
      onCancel={() => setShowDeleteConfirm(false)}
    />
  );

  // Sidebar mode: render inside EditorSidebar
  if (onClose) {
    return (
      <>
        <EditorSidebar
          open={true}
          onClose={onClose}
          title={
            hasExistingConfig
              ? instanceName || t("wecom.title", "企业微信")
              : t("wecom.newInstance", "新建企业微信实例")
          }
          subtitle={t("wecom.description", "连接您的企业微信机器人，接收和发送消息")}
          icon={
            <Building2
              size={20}
              className="text-[#07c160] dark:text-[#4ad892]"
            />
          }
          footer={actionButtons}
        >
          {formContent}
        </EditorSidebar>
        {deleteDialog}
      </>
    );
  }

  // Full-page mode (backward compatible)
  return (
    <>
      <div className="glass-shell flex h-full flex-col min-h-0">
        <PanelHeader
          title={t("wecom.title", "企业微信")}
          subtitle={t("wecom.description", "连接您的企业微信机器人，接收和发送消息")}
          icon={
            <Building2
              size={20}
              className="text-[#07c160] dark:text-[#4ad892]"
            />
          }
          actions={
            <button
              onClick={() => navigate("/channels")}
              className="btn-secondary"
            >
              <BackIcon size={16} />
              <span className="hidden sm:inline">{t("common.back")}</span>
            </button>
          }
        />
        <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
          {formContent}
        </div>
        <div className="border-t border-[var(--theme-border)] px-3 py-3 sm:px-4">
          {actionButtons}
        </div>
      </div>
      {deleteDialog}
    </>
  );
}
