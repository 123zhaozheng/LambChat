import test from "node:test";
import assert from "node:assert/strict";

import { buildApiUrl, buildWebSocketUrl, getFullUrl } from "../config.ts";

test("buildApiUrl keeps same-origin deployments relative", () => {
  assert.equal(buildApiUrl("/api/health", ""), "/api/health");
});

test("buildApiUrl prefixes relative backend paths for packaged apps", () => {
  assert.equal(
    buildApiUrl("/api/health", "https://chat.example.com/"),
    "https://chat.example.com/api/health",
  );
});

test("getFullUrl prefers the configured backend for relative file URLs", () => {
  assert.equal(
    getFullUrl("/api/upload/file/report.pdf", "https://chat.example.com"),
    "https://chat.example.com/api/upload/file/report.pdf",
  );
});

test("buildWebSocketUrl points packaged apps at the configured backend", () => {
  assert.equal(
    buildWebSocketUrl("/ws", "https://chat.example.com"),
    "wss://chat.example.com/ws",
  );
});

test("buildWebSocketUrl keeps same-origin browser deployments on window host", () => {
  assert.equal(
    buildWebSocketUrl("/ws", "", {
      protocol: "http:",
      host: "localhost:3001",
    }),
    "ws://localhost:3001/ws",
  );
});
