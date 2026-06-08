import {
  Check,
  Unplug,
  RefreshCw,
} from "lucide-react";
import type { TFunction } from "i18next";
import { ChannelAgentSelect } from "../ChannelAgentSelect";
import { ChannelModelSelect } from "../ChannelModelSelect";
import { ChannelPersonaSelect } from "../ChannelPersonaSelect";
import { ChannelTeamSelect } from "../ChannelTeamSelect";
import { DEFAULT_AUDIO_TRANSCRIBE_PROMPT } from "./constants";
import type { WeComConfigStatus } from "./types";

interface WeComPanelFormProps {
  t: TFunction;
  hasExistingConfig: boolean;
  status: WeComConfigStatus | null;
  enabled: boolean;
  isTesting: boolean;
  instanceName: string;
  botId: string;
  secret: string;
  groupPolicy: "open" | "mention";
  streamReply: boolean;
  sendThinkingMessage: boolean;
  autoTranscribeAudio: boolean;
  audioTranscribePrompt: string;
  agentId: string | null;
  modelId: string | null;
  teamId: string | null;
  personaPresetId: string | null;
  setInstanceName: (value: string) => void;
  setEnabled: (value: boolean) => void;
  setBotId: (value: string) => void;
  setSecret: (value: string) => void;
  setGroupPolicy: (value: "open" | "mention") => void;
  setStreamReply: (value: boolean) => void;
  setSendThinkingMessage: (value: boolean) => void;
  setAutoTranscribeAudio: (value: boolean) => void;
  setAudioTranscribePrompt: (value: string) => void;
  setAgentId: (value: string | null) => void;
  setModelId: (value: string | null) => void;
  setTeamId: (value: string | null) => void;
  setPersonaPresetId: (value: string | null) => void;
  handleTest: () => void;
}

function WeComToggle({
  checked,
  onChange,
  ariaLabel,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50 ${
        checked
          ? "bg-amber-500 shadow-sm shadow-amber-500/25"
          : "bg-stone-200 dark:bg-stone-700"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-[18px]" : "translate-x-[3px]"
        }`}
      />
    </button>
  );
}

export function WeComPanelForm({
  t,
  hasExistingConfig,
  status,
  enabled,
  isTesting,
  instanceName,
  botId,
  secret,
  groupPolicy,
  streamReply,
  sendThinkingMessage,
  autoTranscribeAudio,
  audioTranscribePrompt,
  agentId,
  modelId,
  teamId,
  personaPresetId,
  setInstanceName,
  setEnabled,
  setBotId,
  setSecret,
  setGroupPolicy,
  setStreamReply,
  setSendThinkingMessage,
  setAutoTranscribeAudio,
  setAudioTranscribePrompt,
  setAgentId,
  setModelId,
  setTeamId,
  setPersonaPresetId,
  handleTest,
}: WeComPanelFormProps) {
  return (
    <div className="es-form">
      {/* Status Callout */}
      {hasExistingConfig && status && (
        <div
          className={`es-callout ${
            status.connected ? "es-callout--success" : "es-callout--danger"
          }`}
        >
          <div className="es-callout-icon">
            {status.connected ? <Check size={14} /> : <Unplug size={14} />}
          </div>
          <div className="es-callout-body">
            <div className="es-callout-title">
              <span
                className={`es-status-dot ${
                  status.connected ? "" : "opacity-40"
                }`}
              />
              {status.connected
                ? t("wecom.connected", "已连接")
                : t("wecom.disconnected", "未连接")}
            </div>
            {status.error_message && (
              <div className="es-callout-desc">{status.error_message}</div>
            )}
          </div>
          <button
            onClick={handleTest}
            disabled={isTesting || !enabled}
            className="btn-secondary btn-sm ml-auto flex-shrink-0"
          >
            {isTesting ? (
              <span className="animate-spin inline-block">⟳</span>
            ) : (
              <RefreshCw size={14} />
            )}
            {t("wecom.testConnection", "测试")}
          </button>
        </div>
      )}

      {/* Instance Name */}
      {!hasExistingConfig && (
        <div className="es-field">
          <label className="es-label">
            {t("wecom.instanceName", "实例名称")}
            <span className="es-required">*</span>
          </label>
          <input
            type="text"
            value={instanceName}
            onChange={(e) => setInstanceName(e.target.value)}
            placeholder={t("wecom.instanceNamePlaceholder", "我的企业微信机器人")}
            className="glass-input es-input"
          />
        </div>
      )}

      {/* Enable Toggle */}
      <div className="es-section">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-[var(--theme-text)]">
              {t("wecom.enabled", "启用企业微信机器人")}
            </div>
            <p className="es-hint mt-0.5">
              {t("wecom.enabledDesc", "启用或禁用此渠道")}
            </p>
          </div>
          <button
            onClick={() => setEnabled(!enabled)}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50 ${
              enabled
                ? "bg-amber-500 shadow-sm shadow-amber-500/25"
                : "bg-stone-200 dark:bg-stone-700"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                enabled ? "translate-x-[18px]" : "translate-x-[3px]"
              }`}
            />
          </button>
        </div>
      </div>

      {/* Bot Credentials */}
      <div className="es-section">
        <div className="es-section-title">
          {t("wecom.credentials", "机器人凭证")}
        </div>
        <div className="es-field">
          <label className="es-label">
            {t("wecom.botId", "机器人 ID")}
            <span className="es-required">*</span>
          </label>
          <input
            type="text"
            value={botId}
            onChange={(e) => setBotId(e.target.value)}
            placeholder={t("wecom.botIdPlaceholder", "bot_xxxxxxxxxx")}
            className="glass-input es-input"
          />
        </div>
        <div className="es-field">
          <label className="es-label">
            {t("wecom.botSecret", "机器人密钥")}
            {hasExistingConfig ? (
              <span className="es-hint ml-1">
                {t("wecom.leaveEmpty", "留空保持当前值")}
              </span>
            ) : (
              <span className="es-required">*</span>
            )}
          </label>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={
              hasExistingConfig
                ? t("wecom.passwordMask", "••••••••••••")
                : ""
            }
            className="glass-input es-input"
          />
        </div>
      </div>

      {/* Behavior Settings */}
      <div className="es-section">
        <div className="es-section-title">
          {t("wecom.behavior", "行为设置")}
        </div>

        {/* Streaming */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3">
            <div>
              <label className="es-label">
                {t("wecom.streamReply", "流式回复")}
              </label>
              <p className="es-hint mt-0.5">
                {t(
                  "wecom.streamReplyDesc",
                  "通过 WebSocket 流式传输 Agent 回复",
                )}
              </p>
            </div>
            <WeComToggle
              checked={streamReply}
              onChange={setStreamReply}
              ariaLabel={t("wecom.streamReply", "流式回复")}
            />
          </div>
        </div>

        {/* Thinking Message */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3">
            <div>
              <label className="es-label">
                {t(
                  "wecom.sendThinkingMessage",
                  "发送思考占位消息",
                )}
              </label>
              <p className="es-hint mt-0.5">
                {t(
                  "wecom.sendThinkingMessageDesc",
                  "在 5 秒回调期限内发送占位消息",
                )}
              </p>
            </div>
            <WeComToggle
              checked={sendThinkingMessage}
              onChange={setSendThinkingMessage}
              ariaLabel={t(
                "wecom.sendThinkingMessage",
                "Thinking Placeholder",
              )}
            />
          </div>
        </div>

        {/* Audio */}
        <div className="es-field">
          <div className="flex items-center justify-between gap-3">
            <div>
              <label className="es-label">
                {t("wecom.autoTranscribeAudio", "自动转写语音")}
              </label>
              <p className="es-hint mt-0.5">
                {t(
                  "wecom.autoTranscribeAudioDesc",
                  "接收语音消息时作为附件传给 Agent，并提示转写",
                )}
              </p>
            </div>
            <WeComToggle
              checked={autoTranscribeAudio}
              onChange={setAutoTranscribeAudio}
              ariaLabel={t(
                "wecom.autoTranscribeAudio",
                "Audio Transcription",
              )}
            />
          </div>
          {autoTranscribeAudio && (
            <textarea
              value={audioTranscribePrompt}
              onChange={(e) => setAudioTranscribePrompt(e.target.value)}
              rows={3}
              className="glass-input es-input mt-3 min-h-[5rem] resize-y"
              placeholder={DEFAULT_AUDIO_TRANSCRIBE_PROMPT}
            />
          )}
        </div>

        {/* Group Policy */}
        <div className="es-field">
          <label className="es-label">
            {t("wecom.groupPolicy", "群聊消息策略")}
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setGroupPolicy("mention")}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-all ${
                groupPolicy === "mention"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)] shadow-sm shadow-[var(--theme-primary)]/10"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)] hover:border-[var(--theme-text-secondary)]"
              }`}
            >
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-md text-sm font-medium transition-colors ${
                  groupPolicy === "mention"
                    ? "bg-[var(--theme-primary)] text-white dark:text-[var(--theme-bg-card)]"
                    : "bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)]"
                }`}
              >
                @
              </div>
              <div className="min-w-0">
                <span className="block text-xs font-medium text-[var(--theme-text)]">
                  {t("wecom.groupPolicyMention", "仅@提及回复")}
                </span>
                <span className="text-[10px] text-[var(--theme-text-secondary)]">
                  {t("wecom.groupPolicyMentionDesc", "仅 @机器人时回复")}
                </span>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setGroupPolicy("open")}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-all ${
                groupPolicy === "open"
                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)] shadow-sm shadow-[var(--theme-primary)]/10"
                  : "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:bg-[var(--glass-bg-subtle)] hover:border-[var(--theme-text-secondary)]"
              }`}
            >
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-md text-sm transition-colors ${
                  groupPolicy === "open"
                    ? "bg-[var(--theme-primary)]"
                    : "bg-[var(--glass-bg-subtle)]"
                }`}
              >
                💬
              </div>
              <div className="min-w-0">
                <span className="block text-xs font-medium text-[var(--theme-text)]">
                  {t("wecom.groupPolicyOpen", "回复所有消息")}
                </span>
                <span className="text-[10px] text-[var(--theme-text-secondary)]">
                  {t("wecom.groupPolicyOpenDesc", "回复所有消息")}
                </span>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Agent & Model */}
      <div className="es-section">
        <ChannelAgentSelect value={agentId} onChange={setAgentId} />
      </div>
      <div className="es-section">
        <ChannelModelSelect value={modelId} onChange={setModelId} />
      </div>
      <div className="es-section">
        {agentId === "team" ? (
          <ChannelTeamSelect value={teamId} onChange={setTeamId} />
        ) : (
          <ChannelPersonaSelect
            value={personaPresetId}
            onChange={setPersonaPresetId}
          />
        )}
      </div>

      {/* Setup Guide */}
      <div className="es-callout">
        <div className="es-callout-body">
          <div className="es-callout-title">
            {t("wecom.setupGuide", "设置指南")}
          </div>
          <ol className="mt-1 list-decimal list-outside ml-4 space-y-0.5 text-[0.8rem] text-[var(--theme-text-secondary)]">
            <li>
              {t(
                "wecom.step1",
                "前往企业微信管理后台 (work.weixin.qq.com)",
              )}
            </li>
            <li>
              {t(
                "wecom.step2",
                "进入应用管理，创建智能机器人",
              )}
            </li>
            <li>
              {t(
                "wecom.step3",
                "从机器人设置中获取机器人 ID 和机器人密钥",
              )}
            </li>
            <li>
              {t(
                "wecom.step4",
                "启用 WebSocket 长连接（无需公网 IP）",
              )}
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
