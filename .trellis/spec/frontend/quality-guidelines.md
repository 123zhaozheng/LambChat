# Quality Guidelines

> Linting, testing, and accessibility standards for the frontend.

---

## Overview

The frontend uses Vitest for testing and follows consistent patterns for
code quality, accessibility, and responsive design.

---

## Testing

### Framework

- **Vitest** — test runner (compatible with Vite)
- Tests are placed in `__tests__/` subdirectories next to the component/hook
- Test files follow `<name>.test.ts` or `<name>.test.tsx` naming

### Test patterns

```tsx
// Component test
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Checkbox } from "../Checkbox";

describe("Checkbox", () => {
  it("renders checked state", () => {
    render(<Checkbox checked={true} />);
    expect(screen.getByRole("checkbox")).toHaveAttribute("aria-checked", "true");
  });
});
```

### Coverage

- Critical UI flows have test coverage (auth, chat, PWA, routing)
- Panel stores have unit tests (`blockPreviewStore.test.ts`, `persistentToolPanelState.test.ts`)
- Utility functions have unit tests (`selectorPagination.test.ts`, `goalCommands.test.ts`)
- Many components lack tests — this is an area for improvement

---

## Accessibility

### ARIA attributes

Interactive elements use proper ARIA:

```tsx
<div role="checkbox" aria-checked={checked}>
<button aria-label={t("common.previous")}>
```

### Keyboard support

- `PanelSearchInput` handles composition events for CJK input
- Tab navigation works for all interactive elements
- Focus management for modals and panels

### Semantic HTML

- `<nav>` for navigation bars
- `<main>` / `<article>` where appropriate
- `<h1>`-`<h3>` hierarchy in panels

---

## Responsive Design

### Breakpoints

| Breakpoint | Min Width | Target |
|-----------|-----------|--------|
| default | 0 | Mobile |
| `sm:` | 640px | Small tablets |
| `lg:` | 1024px | Desktop |
| `xl:` | 1280px | Large desktop |
| `2xl:` | 1536px | Ultra-wide |

### Mobile-specific patterns

```tsx
// Safe area handling for native builds
<div className="safe-area-top safe-area-bottom">

// Dynamic viewport height
<div className="min-h-[100svh] min-h-[100dvh]">

// Keyboard-aware layout
const isKeyboardOpen = useMobileKeyboardAware();

// Mobile device detection
import { isMobileDevice } from "../../utils/mobile";
```

---

## Code Style

- **TypeScript strict mode** — no implicit any, strict null checks
- **Named exports** — avoid default exports
- **TailwindCSS** — no inline styles, no CSS modules
- **i18next** — all user-facing strings use `t("key")`, no hardcoded strings
- **`clsx`** for conditional class composition (not `classnames`)

---

## Common Mistakes

- ❌ Don't hardcode user-facing strings — use `t("key")` with i18next
- ❌ Don't forget `dark:` variants for dark mode support
- ❌ Don't use CSS modules or inline styles — use TailwindCSS
- ❌ Don't forget `aria-*` attributes on custom interactive elements
- ❌ Don't forget safe area classes for native builds (Capacitor/Tauri)
- ❌ Don't use `default` exports — use named exports
