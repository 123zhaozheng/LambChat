import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const toolbarSource = readFileSync(
  new URL("../ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);
const selectorsSource = readFileSync(
  new URL("../ChatInputSelectors.tsx", import.meta.url),
  "utf8",
);
const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const featureMenuSource = readFileSync(
  new URL("../../selectors/FeatureMenu.tsx", import.meta.url),
  "utf8",
);
const teamPickerSource = readFileSync(
  new URL("../../team/TeamPickerModal.tsx", import.meta.url),
  "utf8",
);

test("team toolbar chip only renders after a team is selected", () => {
  assert.doesNotMatch(toolbarSource, /TeamPickerModal/);
  assert.match(toolbarSource, /selectedPersonaName && currentAgent !== "team"/);
  assert.match(
    toolbarSource,
    /currentAgent === "team" && onSelectTeam && selectedTeamId/,
  );
  assert.match(toolbarSource, /onActivePanelChange\("team"\)/);
  assert.match(toolbarSource, /chat\.teamSelected/);
  assert.doesNotMatch(toolbarSource, /Select team/);
  assert.match(toolbarSource, /text-\[var\(--theme-primary\)\]/);
  assert.doesNotMatch(toolbarSource, /text-amber-500/);
  assert.match(selectorsSource, /TeamPickerModal/);
  assert.match(selectorsSource, /isOpen=\{activePanel === "team"\}/);
  assert.match(selectorsSource, /selectedTeamId=\{selectedTeamId \?\? null\}/);
  assert.match(
    chatInputSource,
    /selectedTeamId=\{selectedTeamId\}[\s\S]*onSelectTeam=\{onSelectTeam\}/,
  );
});

test("team selector uses the persona selector interaction surfaces", () => {
  assert.match(
    toolbarSource,
    /hasTeamSelector=\{currentAgent === "team" && !!onSelectTeam\}/,
  );
  assert.match(
    toolbarSource,
    /hasPersonaSelector=\{hasPersonaSelector && currentAgent !== "team"\}/,
  );
  assert.match(toolbarSource, /onSelectTeam\?\.\(null\)/);
  assert.match(toolbarSource, /group-hover:opacity-0/);
  assert.match(featureMenuSource, /hasTeamSelector/);
  assert.match(featureMenuSource, /label=\{t\("featureMenu\.team", "团队"\)\}/);
  assert.match(featureMenuSource, /onClick=\{\(\) => onOpen\("team"\)\}/);
  assert.match(
    teamPickerSource,
    /z-\[250\][\s\S]*sm:max-w-3xl[\s\S]*xl:max-w-6xl/,
  );
  assert.match(teamPickerSource, /grid auto-grid-cols gap-3/);
  assert.match(teamPickerSource, /pps-card__action/);
  assert.match(teamPickerSource, /handleSelect\(team\.id\)/);
  assert.match(teamPickerSource, /onSelect\(teamId\)/);
  assert.doesNotMatch(teamPickerSource, /sm:w-\[420px\]/);
});
