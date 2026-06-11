# Error Handling

> How errors are handled in this project.

---

## Overview

The backend uses a **two-layer error system**:
1. **Domain exceptions** in `src/kernel/exceptions.py` — for business logic errors
2. **HTTP exceptions** in route handlers — for API responses

Domain exceptions are caught at the route layer and converted to appropriate HTTP status codes.

---

## Custom Exception Hierarchy

All custom exceptions live in `src/kernel/exceptions.py`:

| Exception | HTTP Mapping | Use Case |
|-----------|-------------|----------|
| `AgentError` | 500 | Agent runtime failures |
| `ConfigurationError` | 500 | Invalid configuration |
| `ValidationError` | 400 | Input validation failures |
| `NotFoundError` | 404 | Resource not found |
| `AuthenticationError` | 401 | Invalid/missing credentials |
| `AuthorizationError` | 403 | Insufficient permissions |
| `StorageError` | 500 | Database/storage failures |
| `LLMError` | 502 | LLM provider errors |
| `ToolError` | 500 | Tool execution failures |
| `SkillError` | 500 | Skill execution failures |
| `SessionError` | 500 | Session management errors |
| `EmailNotVerifiedError` | 403 | Email verification required (has `.email` attribute) |
| `AccountNotActiveError` | 403 | Account not activated (has `.email` attribute) |

Some infra modules define local exceptions:
- `src/infra/mcp/encryption.py` → `DecryptionError`
- `src/infra/task/exceptions.py` → `TaskInterruptedError`
- `src/infra/task/state_machine.py` → `InvalidTaskTransitionError`

---

## Error Handling Patterns

### Route-level pattern

```python
@router.post("/{agent_id}/stream")
async def chat_stream(
    agent_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    try:
        await validate_agent_model_access(agent_options, user)
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        # ... main logic
    finally:
        TraceContext.clear_request_context()
```

Rules:
- **Catch domain exceptions explicitly** at the route boundary
- **Convert to HTTPException** with appropriate status code
- **Use `finally` blocks** for cleanup (TraceContext, connections)
- **Don't catch Exception broadly** — let unexpected errors propagate to the global handler

### Dependency-level pattern

Auth errors are raised directly in dependencies (`src/api/deps.py`):

```python
async def get_current_user_required(...) -> TokenPayload:
    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证信息")
    # ...
    except HTTPException:
        raise  # re-raise HTTPException without wrapping
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
```

---

## API Error Responses

All API errors follow FastAPI's standard format:

```json
{
  "detail": "Human-readable error message"
}
```

- 401 — `"未提供认证信息"`, `"无效的 Token"`, `"用户不存在"`
- 403 — `"缺少权限: <perm>"`, or str(AuthorizationError)
- 404 — `"<资源>不存在"` (e.g., `"会话不存在"`, `"角色预设不存在"`)
- 422 — FastAPI auto-generated validation errors

Chinese error messages are used in auth/domain errors. This is consistent across the codebase.

---

## SSE Error Handling

For streaming endpoints (chat), errors are sent as SSE events:

```python
async def event_generator():
    try:
        async for event in agent.stream(...):
            yield await run_blocking_io(_format_agent_sse_event, event)
    finally:
        TraceContext.clear_request_context()
```

The `Presenter.error()` method formats error events with trace_id for client-side debugging.

---

## Common Mistakes

- ❌ Don't catch `Exception` and swallow it silently — at minimum log it
- ❌ Don't raise custom exceptions directly from route handlers — convert to HTTPException
- ❌ Don't forget `except HTTPException: raise` before the generic `except Exception` handler
- ❌ Don't forget `TraceContext.clear_request_context()` in `finally` blocks for streaming endpoints
