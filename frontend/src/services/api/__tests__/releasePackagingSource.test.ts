import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

function readRepoFile(path: string): string {
  const url = new URL(`../../../../../${path}`, import.meta.url);
  return readFileSync(url, "utf8");
}

test("release workflow publishes branded desktop and mobile artifacts", () => {
  const workflowPath = ".github/workflows/app-release.yml";
  assert.equal(
    existsSync(new URL(`../../../../../${workflowPath}`, import.meta.url)),
    true,
  );

  const workflow = readRepoFile(workflowPath);
  assert.match(workflow, /LambChat-/);
  assert.match(workflow, /package:desktop/);
  assert.match(workflow, /assembleRelease/);
  assert.match(workflow, /softprops\/action-gh-release/);
});

test("release workflow publishes a debug Android APK when signing secrets are missing", () => {
  const workflow = readRepoFile(".github/workflows/app-release.yml");

  assert.doesNotMatch(workflow, /LambChat-android-[^\n]*release-unsigned\.apk/);
  assert.doesNotMatch(workflow, /unsigned-xcarchive/);
  assert.match(workflow, /assembleDebug/);
  assert.match(workflow, /app-debug\.apk/);
  assert.match(workflow, /LambChat-android-\$\{RELEASE_TAG\}-debug\.apk/);
  assert.match(workflow, /LambChat-android-\$\{RELEASE_TAG\}-signed\.apk/);
});

test("mobile package scripts generate and validate branded native images", () => {
  const packageJson = JSON.parse(readRepoFile("frontend/package.json")) as {
    scripts: Record<string, string>;
  };
  const assetScript = readRepoFile(
    "frontend/scripts/generate-branded-assets.mjs",
  );

  assert.match(packageJson.scripts["mobile:sync"], /brand:assets/);
  assert.match(packageJson.scripts["mobile:build"], /brand:assets/);
  assert.match(packageJson.scripts["brand:assets"], /generate-branded-assets/);
  assert.match(packageJson.scripts["brand:assets:check"], /--check/);
  assert.match(assetScript, /LambChat/);
  assert.match(assetScript, /public\/icons\/icon-512\.png/);
});
