# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

The backend follows a pragmatic quality approach focused on type safety,
consistent patterns, and infrastructure reliability.

---

## Required Patterns

- **Type annotations** on all function signatures (args + return type)
- **Pydantic schemas** for all API request/response bodies — no raw dicts
- **Error handling** at route boundaries — domain exceptions → HTTPException
- **Async everywhere** — no synchronous DB calls or blocking I/O in route handlers
- **`get_logger(__name__)`** in every module that logs — not `print()` or raw `logging.getLogger()`
- **`Depends(get_current_user_required)`** for authenticated routes
- **`Depends(require_permissions("perm:name"))`** for RBAC checks
- **`run_blocking_io()`** for CPU-bound work that must not block the event loop
- **Storage classes** for all data access — no raw pymongo outside infra modules

---

## Forbidden Patterns

- ❌ Raw `pymongo` / motor calls outside Storage classes
- ❌ Synchronous I/O in async route handlers (use `run_blocking_io()`)
- ❌ `print()` for output — always use `logger`
- ❌ Raw dict returns from API routes — use Pydantic response models
- ❌ Hardcoded configuration — use `settings` from `src.kernel.config`
- ❌ Catching `Exception` and swallowing silently — at minimum log it

---

## Testing Requirements

### Current state

The project has **limited test coverage** on the backend. Codegraph reports ⚠️ no covering tests
for most API routes and services. Testing is an area for improvement.

### When tests are written

- **Agent event processing** — some coverage in `src/infra/agent/events/`
- **Task state machine** — `src/infra/task/` has local exceptions and transitions
- **Utility functions** — datetime, validation helpers

### Test patterns when writing

- Use `pytest` with `pytest-asyncio` for async tests
- Place tests alongside source or in a `tests/` directory at the same level
- Mock external services (LLM, MCP, MongoDB) — don't require live infrastructure

---

## Code Style

- **Python 3.12+** — use modern syntax (type unions `X | Y`, `list[str]` not `List[str]`)
- **Imports**: `from src.xxx import Yyy` — absolute imports from `src` root
- **Docstrings**: Chinese for module-level; English for method-level is acceptable
- **Line length**: ~120 chars practical limit (not enforced by linter)
- **Formatting**: no black/ruff formatter enforced, but match surrounding code style
- **Chinese error messages** in API responses (consistent with existing patterns)

---

## Environment & Dependency Management

- **uv** is the only allowed Python package manager — no `pip`, `poetry`, `conda`, or `pipenv`
- Install dependencies: `uv sync`
- Add dependencies: `uv add <package>`
- Run commands: `uv run python <script>` or `uv run <command>`
- Dependency declarations live in `pyproject.toml`

---

## Security Checklist

Before merging any route:

- [ ] Auth: `Depends(get_current_user_required)` or `get_current_user_optional`
- [ ] RBAC: `require_permissions()` for permission-gated endpoints
- [ ] Input validation: Pydantic schema on request body, no raw JSON
- [ ] No secrets in responses: use `mask_api_key()` for model configs
- [ ] No SQL/NoSQL injection: use parameterized queries via Storage classes
- [ ] Rate limiting: applied on auth endpoints via `rate_limiter.py`
- [ ] `TraceContext.clear_request_context()` in streaming endpoint `finally` blocks
