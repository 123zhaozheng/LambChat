# Directory Structure

> How backend code is organized in this project.

---

## Overview

Backend is a Python / FastAPI application under `src/`. It follows a layered architecture:
- **kernel** — core types, schemas, config, exceptions (shared across all layers)
- **api** — FastAPI routes, middleware, dependencies (HTTP entry points)
- **infra** — infrastructure implementations (storage, auth, LLM, tools, MCP, etc.)
- **agents** — LangGraph-based agent implementations (fast_agent, search_agent, team_agent)

---

## Directory Layout

```
src/
├── kernel/                    # Core types, schemas, config, exceptions
│   ├── config/                # Settings and configuration (Pydantic BaseSettings)
│   ├── schemas/               # Pydantic schemas (model, session, user, etc.)
│   ├── types.py               # Enums, protocols, type definitions
│   └── exceptions.py          # Custom exception hierarchy
│
├── api/                       # HTTP layer (FastAPI)
│   ├── main.py                # App factory, middleware registration
│   ├── deps.py                # Shared FastAPI dependencies (auth, permissions)
│   ├── middleware/             # Auth, tracing, user-context middleware
│   └── routes/                # Route modules (one file per domain)
│       ├── agent/             # Agent + model config routes
│       ├── auth/              # Auth subpackage (core, oauth, profile, verification)
│       ├── chat.py            # Chat / session message routes
│       ├── session.py         # Session CRUD
│       ├── mcp.py             # MCP server management
│       ├── skill.py           # Skill CRUD
│       └── ...                # channels, feedback, marketplace, etc.
│
├── infra/                     # Infrastructure implementations
│   ├── agent/                 # Agent runtime (events, middleware, model storage)
│   ├── auth/                  # JWT, password hashing, OAuth
│   ├── chat/                  # Chat history, message processing
│   ├── llm/                   # LLM provider integrations
│   ├── logging/               # Structured logging with TraceContext
│   ├── mcp/                   # MCP client/server management
│   ├── memory/                # Memory store (client + storage)
│   ├── role/                  # RBAC role storage
│   ├── session/               # Session storage
│   ├── skill/                 # Skill execution and storage
│   ├── storage/               # Abstract storage base + MongoDB implementation
│   ├── tool/                  # Tool execution, human tool, deferred manager
│   ├── upload/                # File upload handling
│   ├── user/                  # User management + storage
│   └── ...                    # channel, email, envvar, feedback, etc.
│
└── agents/                    # LangGraph agent definitions
    ├── core/                  # Shared: base class, persona, thinking, tool_filter
    ├── fast_agent/            # Main chat agent (graph, nodes, state, context, prompt)
    ├── search_agent/          # Search agent (same structure as fast_agent)
    └── team_agent/            # Team coordination agent
```

---

## Module Organization

Each new feature/domain should follow the established pattern:

1. **Schema** in `src/kernel/schemas/` — Pydantic BaseModel for request/response types
2. **Route** in `src/api/routes/` — one file per domain (e.g., `feedback.py`, `mcp.py`)
3. **Storage/Service** in `src/infra/<domain>/` — business logic and data access
4. **Exception** in `src/kernel/exceptions.py` — domain-specific errors if needed

Agents follow a consistent internal structure:
- `graph.py` — LangGraph StateGraph definition
- `nodes.py` — Node functions
- `state.py` — TypedDict state definition
- `context.py` — AgentContext (tools, LLM, presenter setup)
- `prompt.py` — System prompt templates

---

## Naming Conventions

- **Files**: `snake_case.py` — e.g., `model_storage.py`, `chat_validation.py`
- **Classes**: `PascalCase` — e.g., `ModelConfig`, `SessionStorage`, `FastAgentContext`
- **Functions/methods**: `snake_case` — e.g., `get_logger()`, `list_available_models()`
- **Schemas**: `<Entity>Base`, `<Entity>Create`, `<Entity>Update`, `<Entity>Response` pattern
- **Storage classes**: `<Entity>Storage` (e.g., `MCPStorage`, `RoleStorage`)
- **Route modules**: one file per domain, named after the domain (e.g., `feedback.py`)
- **Agent subpackages**: `snake_case` directory (e.g., `fast_agent/`, `search_agent/`)

---

## Examples

- Well-organized agent: `src/agents/fast_agent/` (graph → nodes → state → context → prompt)
- Well-organized infra module: `src/infra/mcp/` (storage, client, encryption, config)
- Schema with CRUD variants: `src/kernel/schemas/model.py` (ModelConfig, ModelConfigCreate, ModelConfigUpdate, ModelResponse)
