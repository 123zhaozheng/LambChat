# Technical Info

## Summary For Implementer

This is a targeted backend/channel fix. The product expectation is:

1. WeCom user sends message A.
2. Agent starts responding to A.
3. Before A finishes, WeCom user sends message B.
4. Backend cancels A's run.
5. Message B is immediately persisted and submitted as the input for a new run in the same session.
6. WeCom shows the response to B, not a blank bubble.

The Web chat path already has the desired behavior. Match it before considering deeper checkpoint changes.

## Recommended Minimal Patch

In `src/infra/channel/wecom/handler.py`, update the `task_manager.submit(...)` call in `create_wecom_message_handler()`:

```python
run_id, _ = await task_manager.submit(
    session_id=session_id,
    agent_id=agent_to_use,
    message=content,
    user_id=user_id,
    executor=executor,
    project_id=project_id,
    agent_options=wecom_agent_options,
    session_name=session_title,
    enabled_skills=enabled_skills,
    persona_system_prompt=persona_system_prompt,
    team_id=team_id if agent_to_use == "team" else None,
    display_message=content,
    write_user_message_immediately=True,
)
```

Do not create a new session after cancel for this normal interrupt path.

## Blank Bubble Guard

Investigate `WeComResponseCollector.finalize_stream_message()`.

Current behavior to watch for:

* `send_thinking_placeholder()` can start a WeCom stream before any assistant content exists.
* If no assistant chunks are appended, finalization may use `final_text = final_content.strip() or " "`.
* In WeCom this can appear as a blank bubble.

Suggested behavior:

* If assistant content exists, finalize normally.
* If the stream was superseded by a newer run, do not finalize/send.
* If a run ends with no assistant content and is not superseded, send a nonblank fallback or avoid finalizing as whitespace.

Pick the smallest change that prevents a visible blank bubble without disrupting normal stream replies.

## Test Guidance

Prefer focused unit tests over broad integration tests because WeCom SDK and live Redis/Mongo are external concerns.

Useful fakes:

* Fake task manager that records `cancel()` and `submit()` arguments.
* Fake `_process_events()` that either appends no assistant chunks or appends a chunk.
* Fake `WeComChannel` with `reply_stream()`, `reply_message()`, and `send_proactive_message()` call recording.
* Fake storage/session for `current_run_id` checks.

Recommended assertions:

* `submit_kwargs["message"] == second_message`
* `submit_kwargs["display_message"] == second_message`
* `submit_kwargs["write_user_message_immediately"] is True`
* `submit_kwargs["session_id"]` stays the same after cancel
* old/superseded run does not call final send
* empty collected content does not call `reply_stream(..., " ", finish=True)`

## Risks

* If the inner deep-agent checkpointer is already in a corrupted partial assistant state, immediate user-message persistence might not be enough. Only then consider a scoped checkpoint reset/reseed design.
* Overcorrecting by creating a fresh session loses context, which the user does not want.
* A too-aggressive blank-stream guard could leave an open WeCom stream unfinalized. Ensure the SDK contract is respected.

## Non-Goals

* Do not touch frontend.
* Do not change Feishu behavior unless tests reveal shared collector code needs it.
* Do not introduce new dependencies.
