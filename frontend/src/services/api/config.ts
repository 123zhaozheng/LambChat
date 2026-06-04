/**
 * API configuration and URL utilities
 */

const configuredApiBase =
  (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_API_BASE || "";

function normalizeApiBase(apiBase: string): string {
  return apiBase.replace(/\/+$/, "");
}

const API_BASE = normalizeApiBase(configuredApiBase);
export { API_BASE };

export interface BrowserLocationLike {
  protocol: string;
  host: string;
}

export function buildApiUrl(path: string, apiBase: string = API_BASE): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const normalizedBase = normalizeApiBase(apiBase);
  return normalizedBase ? `${normalizedBase}${normalizedPath}` : normalizedPath;
}

export function buildWebSocketUrl(
  path: string = "/ws",
  apiBase: string = API_BASE,
  locationLike?: BrowserLocationLike,
): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const normalizedBase = normalizeApiBase(apiBase);

  if (normalizedBase) {
    const url = new URL(normalizedPath, normalizedBase);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
  }

  const location =
    locationLike || (typeof window !== "undefined" ? window.location : null);
  if (!location) {
    return normalizedPath;
  }

  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${normalizedPath}`;
}

/**
 * 获取完整 URL（用于处理后端返回的相对路径）
 * @param url - 可能是相对路径或完整 URL
 * @returns 完整 URL
 */
export function getFullUrl(
  url: string | undefined | null,
  apiBase: string = API_BASE,
): string | undefined {
  if (!url) return undefined;
  // 如果已经是完整 URL（http:// 或 https://），直接返回
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  if (apiBase) {
    return buildApiUrl(url, apiBase);
  }
  // 如果是相对路径，拼接 base URL（优先使用当前 origin，否则使用 API_BASE）
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "";
  return baseUrl + url;
}
