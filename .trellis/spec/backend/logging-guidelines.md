# Logging Guidelines

> How logging works in this project.

---

## Overview

The backend uses Python's **stdlib `logging`** with a custom trace-context injection system.
Every log entry automatically includes `trace_id` and `span_id` from `TraceContext` (contextvars-based).

---

## Logger Setup

```python
from src.infra.logging import get_logger

logger = get_logger(__name__)
```

- **Always** use `get_logger(__name__)` — never `logging.getLogger()` directly
- The `__name__` convention ensures log records show the originating module path
- `get_logger` is a thin wrapper that returns `logging.getLogger(name)`

---

## Log Levels

| Level | When to Use | Example |
|-------|------------|---------|
| `DEBUG` | Detailed diagnostic info | `logger.debug(f"Cache hit for user {user_id}")` |
| `INFO` | Normal operation milestones | `logger.info(f"[API] Got {len(mcp_tools)} MCP tools")` |
| `WARNING` | Unexpected but recoverable | `logger.warning(f"[Tools API] Failed to get MCP tools: {e}")` |
| `ERROR` | Operation failures needing attention | `logger.error(f"[WebSocket] Auth error: {e}")` |

### Per-module level configuration

Set via `LOG_LEVELS` env var: `"src.infra.redis=DEBUG,src.agents=TRACE"`

Third-party loggers are silenced by default:
- `httpx`, `httpcore`, `urllib3`, `asyncio` → `WARNING`

---

## Log Message Format

Messages use a **bracket-tag prefix** convention to identify the subsystem:

```python
logger.info(f"[API] request.agent_options: {request_body.agent_options}")
logger.info(f"[Tools API] Got {len(mcp_tools)} MCP tools from global cache")
logger.warning(f"[MCP] Failed to connect: {e}")
logger.error(f"[WebSocket] Auth error: {e}")
```

Common prefixes: `[API]`, `[Tools API]`, `[MCP]`, `[WebSocket]`, `[Agent]`, `[Auth]`

---

## Trace Context

`TraceContext` (in `src/infra/logging/context.py`) uses Python contextvars to auto-inject
`trace_id` and `span_id` into every log record via `TraceFilter`.

```python
from src.infra.logging import TraceContext

# Set at request entry
TraceContext.set(trace_id="abc123", span_id="def456")

# Clear at request exit (important for streaming!)
TraceContext.clear_request_context()
```

**Critical**: Always clear TraceContext in `finally` blocks for SSE/streaming endpoints
to prevent contextvars leaking between requests.

---

## Log Formatting

Logs use `ColoredFormatter` (in `src/infra/logging/formatter.py`) with:
- Color-coded levels (DEBUG=gray, INFO=green, WARNING=yellow, ERROR=red)
- Trace context injection via `TraceFilter`
- Configurable format via `settings.LOG_FORMAT` and `settings.LOG_DATE_FORMAT`

Output goes to `stdout` only (no file logging in application code).

---

## Structured Event Logging

For agent SSE events, use the `Presenter` system (not raw logger):

```python
presenter.info("Processing message")
presenter.error("LLM call failed", error_type="LLMError", details={"provider": provider})
```

This produces structured SSE events sent to the frontend, not log lines.

---

## What NOT to Log

- ❌ API keys, passwords, JWT tokens — use `mask_api_key()` for model configs
- ❌ Full request bodies with file uploads
- ❌ User personal data in bulk (log user_id, not user object)

---

## Common Mistakes

- ❌ Don't use `print()` — always use `logger`
- ❌ Don't use `logging.getLogger()` directly — use `from src.infra.logging import get_logger`
- ❌ Don't forget the bracket-tag prefix (e.g., `[API]`, `[MCP]`)
- ❌ Don't forget `TraceContext.clear_request_context()` in streaming endpoint `finally` blocks
