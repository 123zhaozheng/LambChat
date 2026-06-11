# Directory Structure

> How frontend code is organized in this project.

---

## Overview

Frontend is a React 18 / TypeScript / TailwindCSS application under `frontend/src/`.
It supports **three deployment targets**: web (Vite SPA), Android (Capacitor), and desktop (Tauri).
Uses `react-router` for routing, `i18next` for localization, and `lucide-react` for icons.

---

## Directory Layout

```
frontend/src/
├── App.tsx                   # Root app component with routing
│
├── components/               # React components organized by domain
│   ├── agent/                # Agent/model selectors and icons
│   ├── auth/                 # Login, register, OAuth, password reset
│   ├── chat/                 # Chat input, messages, tool result panels
│   │   ├── ChatMessage/      # Message rendering (markdown, tool calls, items)
│   │   │   └── items/       # Tool result items (EditFile, Execute, Glob, Grep, etc.)
│   ├── common/               # Shared UI primitives (Loading, Pagination, Checkbox, etc.)
│   │   └── ImageViewer/     # Image preview component
│   ├── documents/            # File/document preview (PDF, PPTX, images)
│   │   ├── previews/         # Format-specific preview renderers
│   │   └── utils/           # Document utility functions
│   ├── fileLibrary/          # File library management
│   ├── landing/              # Landing/marketing page sections
│   ├── layout/               # App shell, header, sidebar, content area
│   │   └── AppContent/      # Chat vs non-chat content routing
│   ├── mcp/                  # MCP server configuration UI
│   ├── notification/         # Notification preferences
│   ├── panels/               # Admin/settings panel pages
│   │   ├── AgentModelPanel/  # Agent model configuration
│   │   ├── AgentPanel/       # Agent configuration
│   │   ├── ModelPanel/       # Model management with tabs
│   │   ├── SkillsHubPanel/   # Skills marketplace
│   │   ├── SkillsPanel/      # Skills management
│   │   ├── MemoryPanel/      # Memory management
│   │   ├── MarketplacePanel/ # Marketplace browsing
│   │   └── channel/         # Channel management
│   ├── persona/              # Persona preset UI
│   ├── profile/              # User profile settings
│   ├── pwa/                  # PWA-specific components
│   ├── selectors/            # Reusable selector components (SkillSelector, ToolSelector)
│   ├── share/                # Session sharing
│   ├── sidebar/              # Sidebar session list
│   ├── skeletons/            # Loading skeleton components
│   ├── skill/                # Skill detail/editing
│   ├── team/                 # Team management
│   └── pages/               # Route-level page components
│
├── contexts/                 # React contexts (SettingsContext, AuthContext)
├── hooks/                    # Custom hooks
│   └── useAgent/            # Agent interaction hook (streaming, goal tracking)
├── i18n/                     # Internationalization
│   └── locales/             # Language JSON files
├── services/                 # Service layer (API calls, notifications)
│   ├── api/                 # API client modules (agent, session, model, auth, etc.)
│   └── notifications/       # Push notification service
├── styles/                   # Global CSS / Tailwind config
├── types/                    # TypeScript type definitions
├── utils/                    # Utility functions
├── workers/                  # Web workers
├── constants/                # App constants
└── __tests__/                # Integration/smoke tests (Vitest)
```

---

## Module Organization

### Component organization

Each domain folder contains:
- Main component file (e.g., `ChatInput.tsx`)
- Sub-components if needed
- `__tests__/` folder with `.test.ts(x)` files (Vitest)

### API service organization

`services/api/` mirrors backend routes:
- `agent.ts` — agent listing and chat
- `session.ts` — session CRUD and events
- `model.ts` — model config and listing
- `auth.ts` — authentication
- `fetch.ts` — authFetch wrapper with token injection
- `config.ts` — API_BASE URL resolution
- `token.ts` — access token management

---

## Naming Conventions

- **Files**: `PascalCase.tsx` for components, `camelCase.ts` for utilities/hooks
- **Components**: `export function ComponentName()` — named exports, not default exports
- **Hooks**: `use<Name>` prefix (e.g., `useAgent`, `useSessionSync`, `useMobileKeyboardAware`)
- **Types**: `PascalCase` interface/type (e.g., `BackendSession`, `ModelOption`, `ActiveGoalSpec`)
- **API modules**: `camelCase` API object (e.g., `agentApi`, `sessionApi`, `modelApi`)
- **Stores**: `camelCase` store variable (e.g., `panelStore`, `agentListCache`)
- **Test files**: `<Component>.test.tsx` in `__tests__/` subdirectory

---

## Examples

- Well-organized component domain: `components/chat/` (input, messages, attachments, stores)
- Well-organized API service: `services/api/model.ts` (types, cache, API object)
- Well-organized hook: `hooks/useAgent/` (types, goalCommands, main hook)
- Panel with tabs: `components/panels/ModelPanel/tabs/` (config tab, roles tab, form modal)
