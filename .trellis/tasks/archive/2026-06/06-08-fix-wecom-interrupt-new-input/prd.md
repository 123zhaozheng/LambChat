# fix: WeCom interrupted message resumes with new input

## Goal

When a WeCom user sends a new message while an agent run is still producing a response, LambChat should cancel the previous run and process the new WeCom message as the next user input in the same conversation. The user should see a normal new answer, not a blank WeCom bubble, and existing conversation context should be preserved.

## What I Already Know

* The user reproduced the issue in WeCom: first agent response is interrupted by a second user message, backend pauses/cancels the prior run, but the second message does not continue as the new agent input; WeCom shows a blank bubble.
* The current diff in `src/infra/channel/wecom/handler.py` changed prior behavior from "create a fresh session after cancel" to "keep the same session after cancel".
* Recent commits show the history of this area:
  * `595898b5 fix(channel): cancel previous WeCom run when user sends new message`
  * `b84935c5 fix(channel): prevent duplicate WeCom replies when run is superseded`
  * `efc1ac33 fix(channel): create fresh session after cancelling previous WeCom run`
* Web chat behaves correctly in the same stop-then-new-message scenario.
* Web chat submits new runs with `write_user_message_immediately=True` and `display_message=request.message`, so the new user message is persisted before the background run starts.
* WeCom currently calls `task_manager.submit(...)` without `write_user_message_immediately=True` and without `display_message=content`.
* WeCom also sends a stream thinking placeholder before the agent emits content. If no agent content is collected, `finalize_stream_message()` can finish the stream with `" "`, which presents as a blank bubble.

## Requirements

* Keep the same WeCom session ID when a new message interrupts an active run, so conversation context remains available.
* Cancel the previous active run before submitting the new WeCom message.
* Persist the new WeCom user message immediately, matching the Web chat submission path.
* Submit the new WeCom message as the agent input for the new run.
* Prevent the superseded old run from sending a duplicate or partial final reply.
* Prevent blank WeCom final stream bubbles when no assistant content was collected.
* Preserve existing WeCom features: `/new`, stream reply, thinking placeholder, segmented replies, persona preset, project resolution, team agent selection, and file reveal upload.

## Acceptance Criteria

* [ ] Given a WeCom run is streaming, when the same user sends a second message, the previous run is cancelled and a new run is submitted using the second message as `message`.
* [ ] The second WeCom message is persisted as a `user:message` event for the new `run_id` before the background run begins, matching Web behavior.
* [ ] The new run uses the same `session_id` as the existing WeCom chat unless the user explicitly sends `/new`.
* [ ] The old run does not finalize or send a duplicate response after it is superseded.
* [ ] The WeCom UI does not receive a blank final stream message for the new run.
* [ ] If the new run produces assistant chunks, those chunks are streamed/finalized normally.
* [ ] If the new run errors or is cancelled before assistant content exists, WeCom receives an explicit nonblank message or the open stream is closed without presenting an empty answer.
* [ ] Existing `/new` behavior still creates a fresh WeCom session and responds with the existing success text.
* [ ] Regression tests cover the WeCom interrupt-and-new-message path.

## Definition of Done

* Tests added or updated for the WeCom interrupted-message flow.
* Targeted tests pass locally.
* Ruff or project lint passes for touched files if available.
* No unrelated dirty files are reverted or included.
* The implementation does not create a fresh session for the normal interrupt path.

## Technical Approach

Use the Web chat submission flow as the behavioral source of truth. The recommended minimal fix is to update WeCom submission so it persists the new user message immediately:

* Add `display_message=content` to the WeCom `task_manager.submit(...)` call.
* Add `write_user_message_immediately=True` to the same call.
* Keep `session_id = await _get_wecom_session_id(chat_id)` unchanged after cancellation.
* Keep the superseded-run guard after `_process_events()`.
* Add blank-stream protection in `WeComResponseCollector.finalize_stream_message()` or adjacent logic so a stream started only by `WECOM_THINKING_MESSAGE` is not finalized as `" "`.

If the minimal fix still fails in tests or local reproduction, investigate LangGraph inner checkpoint state as a second phase. Do not reset or recreate the session unless proven necessary, because the user explicitly wants context preservation.

## Decision (ADR-lite)

**Context**: The Web path already supports stop-then-new-input without creating a new session. WeCom differs by submitting the new run without immediate user-message persistence and by managing its own WeCom stream placeholder.

**Decision**: First align WeCom run submission with Web chat by immediately persisting the new user message. Add nonblank stream finalization safeguards. Defer checkpoint reset/reseed unless the aligned submission path is insufficient.

**Consequences**: This keeps the fix small and preserves conversation continuity. It may not solve a deeper checkpointer corruption issue if one exists; tests should be structured so that a checkpoint-specific failure becomes visible.

## Implementation Plan

1. Inspect Web chat submit/cancel behavior:
   * Confirm `src/api/routes/chat.py` submit uses `write_user_message_immediately=True`.
   * Confirm cancel route does not create a new session.

2. Update WeCom submit behavior:
   * In `src/infra/channel/wecom/handler.py`, pass `display_message=content` and `write_user_message_immediately=True` to `task_manager.submit(...)`.
   * Preserve the existing cancel-before-submit flow.
   * Preserve the existing active-run supersession check.

3. Add blank-stream guard:
   * Find the path where `finalize_stream_message()` turns empty collected content into `" "`.
   * Ensure a WeCom stream that has only the thinking placeholder is not finalized into a blank visible answer.
   * Prefer a localized explicit fallback only for error/cancel/no-content cases; do not alter normal assistant content.

4. Add tests:
   * Unit test the WeCom handler submit call captures the second message with `write_user_message_immediately=True` and `display_message`.
   * Unit test a superseded old run does not send a final reply.
   * Unit test blank collected content does not finalize to an empty WeCom bubble.
   * Reuse existing Feishu/TaskManager fake patterns where possible.

5. Verify:
   * Run targeted WeCom/channel tests.
   * Run targeted TaskManager tests if touched.
   * Run lint on touched Python files if practical.

## Out of Scope

* Reworking LangGraph checkpoint storage globally.
* Changing Web chat behavior.
* Changing Feishu channel behavior.
* Creating a fresh WeCom session on every interrupt.
* Adding queueing or multi-message batching for WeCom.

## Technical Notes

* Main file likely impacted: `src/infra/channel/wecom/handler.py`.
* Web reference file: `src/api/routes/chat.py`.
* Task manager reference files:
  * `src/infra/task/manager.py`
  * `src/infra/task/executor.py`
  * `src/infra/task/cancellation.py`
* WeCom blank bubble likely comes from a stream placeholder being finalized with empty content.
* Treat user edits in the current diff as existing WIP. Do not revert them unless the implementer confirms with the user.

## Research References

* [`research/codebase-wecom-interrupt-flow.md`](research/codebase-wecom-interrupt-flow.md) — codebase comparison of Web chat and WeCom interrupt/new-message flow.
