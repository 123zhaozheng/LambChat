# Codebase Research: WeCom Interrupt/New Input Flow

## Question

Why does Web chat handle stop-then-new-message correctly while WeCom can show a blank response and fail to continue with the new input?

## Findings

### Web Chat Path

Relevant file: `src/api/routes/chat.py`

* Web submit creates or receives a `run_id`, then calls `task_manager.submit(...)` or `submit_arq(...)`.
* Web submit passes `write_user_message_immediately=True`.
* Web submit also passes `display_message=request.message`.
* `BackgroundTaskManager.submit()` writes the user message immediately via `_persist_initial_user_message()` when this flag is true.
* Web SSE reads events by `(session_id, run_id)`, so the frontend attaches to the new run and receives the already-written `user:message`.

### WeCom Path

Relevant file: `src/infra/channel/wecom/handler.py`

* WeCom gets the current session via `_get_wecom_session_id(chat_id)`.
* WeCom calls `task_manager.cancel(session_id, user_id=user_id)` before submitting the new run.
* Current WIP keeps the same session after cancel, which matches the product expectation of preserving context.
* WeCom `task_manager.submit(...)` currently does not pass `write_user_message_immediately=True`.
* WeCom `task_manager.submit(...)` currently does not pass `display_message=content`.
* WeCom sends a thinking placeholder with `collector.send_thinking_placeholder()` before processing the agent events.

### Task Manager Behavior

Relevant files:

* `src/infra/task/manager.py`
* `src/infra/task/executor.py`

`BackgroundTaskManager.submit()` supports two relevant flags:

* `write_user_message_immediately`: writes the user message before background execution starts.
* `user_message_written`: prevents duplicate `user:message` emission inside `TaskExecutor.run_task()`.

When `write_user_message_immediately` is false, the user message is emitted later inside `TaskExecutor.run_task()`. If cancellation, scheduling, stream reads, or placeholder finalization race around this point, channel behavior can diverge from Web.

### Blank Bubble Risk

Relevant file: `src/infra/channel/wecom/handler.py`

`WeComResponseCollector` can start a stream with `WECOM_THINKING_MESSAGE`. Later, if no assistant chunks were collected, finalization can fall back to whitespace. This likely explains the visible blank bubble in WeCom.

## Recommended Direction

First align WeCom with Web chat:

* Pass `display_message=content`.
* Pass `write_user_message_immediately=True`.
* Keep same session after cancel.
* Keep superseded-run guard to avoid duplicate old replies.
* Add a blank-stream guard so no collected assistant content becomes a whitespace-only WeCom final message.

Only investigate checkpoint reset/reseed if the aligned submit path still cannot process the new user input.
