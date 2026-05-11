import test from "node:test";
import assert from "node:assert/strict";

import { buildOAuthLoginUrl } from "../auth.ts";

test("buildOAuthLoginUrl uses API base for split frontend/backend deployments", () => {
  assert.equal(
    buildOAuthLoginUrl("github", "https://api.lambchat.com"),
    "https://api.lambchat.com/api/auth/oauth/github",
  );
});

test("buildOAuthLoginUrl keeps same-origin deployments relative", () => {
  assert.equal(buildOAuthLoginUrl("google", ""), "/api/auth/oauth/google");
});
