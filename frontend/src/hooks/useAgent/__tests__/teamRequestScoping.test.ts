import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../../useAgent.ts", import.meta.url),
  "utf8",
);

test("submits team_id only when the current agent is team", () => {
  assert.match(
    source,
    /currentAgent\s*===\s*"team"\s*\?\s*selectedTeamId\s*:\s*null/,
  );
});

test("stores team_id in optimistic session metadata only for team agent", () => {
  assert.match(
    source,
    /if\s*\(\s*currentAgent\s*===\s*"team"\s*&&\s*selectedTeamId\s*\)\s*\{[\s\S]*conversationConfig\.team_id\s*=\s*selectedTeamId;/,
  );
});
