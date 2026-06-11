# Type Safety

> TypeScript conventions and type organization in this project.

---

## Overview

The frontend uses **strict TypeScript** with explicit type annotations on exports.
Types mirror backend Pydantic schemas where API contracts are shared.

---

## Type Organization

### Location by purpose

| Directory | What Goes Here |
|-----------|---------------|
| `types/` | Global/shared type definitions (session.ts, index.ts, env.d.ts) |
| `services/api/*.ts` | API-specific types co-located with the API module |
| `hooks/useAgent/types.ts` | Hook-specific types in a subpackage |
| `components/**/` | Component props interfaces defined inline or at top of file |

### Backend-mirroring types

Types that mirror backend schemas are defined in the corresponding API service:

```typescript
// services/api/session.ts — mirrors src/kernel/schemas/session.py
export interface BackendSession {
  id: string;
  user_id?: string;
  agent_id: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  name?: string;
  metadata: Record<string, unknown>;
  unread_count?: number;
}
```

Note: frontend types use **snake_case** to match the API response format,
even though TypeScript convention is normally camelCase.

---

## Type Definition Patterns

### CRUD type families

Following the backend pattern, API types come in families:

```typescript
// Full type
export interface ModelConfig { id?: string; value: string; label: string; enabled: boolean; ... }
// Create type (omit generated fields)
export interface ModelConfigCreate { value: string; label: string; enabled?: boolean; ... }
// Update type (all optional)
export interface ModelConfigUpdate { label?: string; enabled?: boolean; ... }
// List response
export interface ModelListResponse { models: ModelConfig[]; count: number; enabled_count: number; }
```

### Union / discriminated types

```typescript
export type FrontendGoalCommand =
  | { action: "run"; goal: ActiveGoalSpec; prompt: string }
  | { action: "clear" }
  | { action: "invalid" };
```

### Generic utility types

```typescript
export type LoadingSize = "xs" | "sm" | "md" | "lg" | "xl";
export type AttachmentPreviewSource = "chat-input" | "user-message";
export type AuthMode = "login" | "register";
```

### Singleton store type

```typescript
export interface SingletonStore<T> {
  get: () => T;
  set: (next: T) => void;
  subscribe: (listener: () => void) => () => void;
}
```

---

## Naming Conventions

- **Interfaces**: `PascalCase` — `BackendSession`, `ModelConfig`, `ActiveGoalSpec`
- **Type aliases**: `PascalCase` — `LoadingSize`, `AuthMode`, `ProviderType`
- **Props types**: `<Component>Props` — `PanelHeaderProps`, `ChatInputProps`
- **Response types**: `<Entity>Response` / `<Entity>ListResponse`
- **Create/Update types**: `<Entity>Create` / `<Entity>Update`

---

## Type Safety Rules

- **Always type API responses**: `authFetch<ModelListResponse>(url)`
- **Prefer `interface` over `type`** for object shapes (extendable)
- **Use `type`** for unions, intersections, and utility types
- **Avoid `any`** — use `unknown` when type is truly unknown
- **Use `as const`** for literal types when needed
- **Prefer optional chaining** (`?.`) over non-null assertions (`!`)

---

## Common Mistakes

- ❌ Don't use `any` — use `unknown` or a specific type
- ❌ Don't define backend-mirroring types in `types/` — co-locate with the API module
- ❌ Don't use `snake_case` for type names — use `PascalCase`
- ❌ Don't forget to type `authFetch<T>()` calls — always specify the response type
- ❌ Don't use non-null assertions (`!`) when optional chaining works
