import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("revealed file API uses the configured API base", () => {
  const source = readSource("../revealedFile.ts");

  assert.match(source, /import \{ API_BASE/);
  assert.doesNotMatch(source, /authFetch<[^>]+>\("\/api\/files/);
  assert.doesNotMatch(source, /authFetch<[^>]+>\(\s*`\/api\/files/);
});

test("WebSocket notifications use the configured backend base", () => {
  const source = readSource("../../../hooks/useWebSocket.ts");

  assert.match(source, /buildWebSocketUrl/);
  assert.doesNotMatch(source, /window\.location\.host/);
  assert.doesNotMatch(source, /`\$\{protocol\}\/\/\$\{host\}\/ws`/);
});

test("hooks with backend requests do not hardcode same-origin API roots", () => {
  const useMcp = readSource("../../../hooks/useMcp.ts");
  const useTools = readSource("../../../hooks/useTools.ts");
  const useApprovals = readSource("../../../hooks/useApprovals.ts");
  const profileTools = readSource(
    "../../../components/profile/tabs/ProfileToolsTab.tsx",
  );

  assert.match(useMcp, /import \{ API_BASE/);
  assert.match(useTools, /import \{ API_BASE/);
  assert.match(useApprovals, /import \{ API_BASE/);
  assert.match(profileTools, /import \{ API_BASE/);
  assert.doesNotMatch(useMcp, /const API_BASE = "\/api/);
  assert.doesNotMatch(useTools, /const API_BASE = "\/api/);
  assert.doesNotMatch(useApprovals, /const API_BASE =/);
  assert.doesNotMatch(profileTools, /const API_BASE = "\/api/);
  assert.doesNotMatch(useMcp, /"\s*\/api\/admin\/mcp/);
  assert.doesNotMatch(useTools, /"\s*\/api/);
  assert.doesNotMatch(useApprovals, /"\s*\/human/);
  assert.doesNotMatch(profileTools, /"\s*\/api/);
});

test("API modules share the normalized API base configuration", () => {
  const feedback = readSource("../feedback.ts");
  const notification = readSource("../notification.ts");

  assert.match(feedback, /import \{ API_BASE \} from "\.\/config"/);
  assert.match(notification, /import \{ API_BASE \} from "\.\/config"/);
  assert.doesNotMatch(feedback, /import\.meta\.env\.VITE_API_BASE/);
  assert.doesNotMatch(notification, /import\.meta\.env\.VITE_API_BASE/);
});
