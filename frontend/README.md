# Karya — Frontend

## 1. What this is

The frontend foundation for Karya — a multi-tenant staff attendance and
presence-verification platform. This is **Phase 8** of the project: the
architectural foundation (auth, routing, design system, PWA shell, API
client, error/loading/empty states, testing setup) that Phase 9 (the real
staff attendance experience — check-in/check-out, GPS + QR) and Phase 10
(manager/admin dashboards) will build on. See `CLAUDE.md` at the repo root
for the full phase history and what is/isn't in scope right now.

**The backend remains authoritative for everything security-sensitive.** This
frontend collects evidence (GPS coordinates, a scanned QR payload) and
displays decisions; it never computes a geofence, never validates a QR
challenge, and never decides whether presence is verified. See
`src/hooks/useGeolocation.ts` and `src/hooks/useCameraStream.ts` for where
that line is drawn in code.

## 2. Technology stack

| Concern | Choice |
| --- | --- |
| Language | TypeScript, `strict: true` |
| Build tool | Vite |
| UI | React 19 |
| Routing | React Router (data router / `createBrowserRouter`) |
| Server state | TanStack Query |
| Client state | React state/context by default; Zustand for the two things that are genuinely global (`authStore`, `toastStore`) |
| Styling | Tailwind CSS v4 (CSS-first config, see `src/styles/index.css`) |
| Components | Hand-built, Radix UI primitives underneath (Dialog, Select, Tabs, DropdownMenu, Toast, Label, Slot) — see §9 below for why not the shadcn CLI |
| Icons | lucide-react |
| Forms | React Hook Form + Zod (`@hookform/resolvers/zod`) |
| PWA | vite-plugin-pwa (`injectManifest` strategy, hand-written service worker) |
| Testing | Vitest + React Testing Library + axe-core (unit/a11y), Playwright (e2e) |
| Linting | oxlint (the Vite scaffold's default — kept rather than adding a second linter) |

## 3. Getting started

```bash
npm install
cp .env.example .env.local     # then edit if your backend isn't at the default URL
npm run dev
```

Requires the backend running (see `backend/README.md`) for anything past the
login screen. `.env.local` is gitignored; see `.env.example` for every
variable and `src/config/env.ts` for how they're validated at startup — a
missing/malformed value fails loudly before the app renders anything, rather
than failing confusingly the first time a component reaches for it.

## 4. Commands

```bash
npm run dev             # start the dev server (PWA service worker disabled — see docs/pwa.md)
npm run build           # tsc -b (typechecks app + node + service-worker configs) && vite build
npm run preview         # serve the production build locally — this is how to see real PWA behaviour
npm run lint            # oxlint
npm run typecheck       # tsc -b --force across every tsconfig (app, node, service-worker, unit tests, e2e tests)
npm run test            # vitest run (unit + component + accessibility)
npm run test:watch      # vitest, watch mode
npm run test:coverage   # vitest run --coverage
npm run test:e2e        # playwright test (starts its own dev server; see playwright.config.ts)
npm run generate:api-types   # regenerate src/types/api.generated.ts from openapi/karya.openapi.json — see docs/api-types.md
npm run generate:icons       # regenerate the placeholder PWA icons — see docs/pwa.md
```

Single test file / single test: `npx vitest run tests/unit/routing.test.tsx`,
or `npx playwright test tests/e2e/smoke.spec.ts --project="Desktop Chrome"`.

## 5. Project layout

```
frontend/
├── src/
│   ├── app/                 App.tsx, router.tsx (route tree), providers.tsx
│   ├── components/
│   │   ├── ui/               Design-system primitives (Button, Input, Dialog, Select,
│   │   │                     Tabs, DropdownMenu, Table, Card, Badge, Alert, Skeleton,
│   │   │                     Spinner, Toaster, ConfirmationDialog, Label)
│   │   ├── layout/            AppShell, Sidebar, BottomNav, Header, UserMenu,
│   │   │                     OfflineBanner, ErrorBoundary, FullScreenSpinner
│   │   └── feedback/          EmptyState, ErrorState, ComingSoon
│   ├── features/              One folder per domain; each owns its schemas, forms
│   │   ├── auth/               and API-backed hooks (useAuth, useOwnProfile, ...) —
│   │   ├── users/               never imported by an unrelated feature.
│   │   └── tenant/
│   ├── hooks/                useGeolocation, useCameraStream, useOnlineStatus,
│   │                         useInstallPrompt — infrastructure Phase 9 will use
│   ├── lib/
│   │   ├── api/                client.ts (the one HTTP client), errors.ts, types.ts,
│   │   │                       endpoints/ (one file per backend router)
│   │   ├── auth/                session.ts (login/logout/refresh orchestration),
│   │   │                        tokenStorage.ts — see docs/auth.md
│   │   ├── errors/              describeError.ts — see docs/error-handling.md
│   │   ├── pwa/                 register.ts
│   │   ├── validation/          shared Zod field bounds, mirrored from the backend
│   │   └── utils/                cn.ts
│   ├── pages/                One file per route; thin, compose from features/components
│   │   ├── auth/, staff/, manager/, admin/
│   ├── routes/                guards.tsx (RequireAuth, RequireRole, RedirectIfAuthenticated)
│   ├── stores/                authStore.ts, toastStore.ts — the only two Zustand stores
│   ├── types/                 api.generated.ts (never hand-edited — see docs/api-types.md)
│   ├── config/                env.ts, navigation.ts, pwaManifest.ts, validation constants
│   ├── styles/                index.css — design tokens, light/dark
│   ├── service-worker.ts      hand-written SW source (injectManifest) — see docs/pwa.md
│   └── main.tsx
├── tests/
│   ├── unit/                  Vitest + RTL + axe-core
│   └── e2e/                   Playwright
├── openapi/                    karya.openapi.json — regenerated from the backend, checked in
├── scripts/                    generate-placeholder-icons.mjs
├── docs/                       auth.md, pwa.md, api-types.md, error-handling.md,
│                                performance.md, testing.md — read these for "why"
├── vite.config.ts, vitest.config.ts, playwright.config.ts
├── tsconfig.json + tsconfig.{app,node,sw,test,e2e}.json  (project references — see §6)
└── .env.example
```

## 6. Why five `tsconfig.*.json` files

Five genuinely different execution contexts exist in this repo, each needing
a different `lib`/`types`/`module` setting, and TypeScript project references
let all five stay `strict: true` and get checked by one `npm run typecheck`
without any of them fighting the others' globals:

- **`tsconfig.app.json`** — the app itself: `DOM` lib, React JSX.
- **`tsconfig.node.json`** — `vite.config.ts`: Node types, no DOM.
- **`tsconfig.sw.json`** — `src/service-worker.ts`: `WebWorker` lib
  (`self`, `ServiceWorkerGlobalScope`), explicitly **not** `DOM` — a service
  worker has no `window`, and typing it as if it did would hide real bugs.
- **`tsconfig.test.json`** — `tests/unit/`: adds `vitest/globals` and
  `@testing-library/jest-dom`'s matcher types.
- **`tsconfig.e2e.json`** — `tests/e2e/`: `@playwright/test`'s types instead
  (a different `test`/`expect` than Vitest's, deliberately not mixed
  together in one config).

## 7. Design system — why hand-built Radix wrappers, not the shadcn CLI

The brief said "shadcn/ui or another accessible, composable component
system." The shadcn CLI itself is a code generator that fetches component
source from a registry and writes it into the repo — functionally, once
run, the result *is* "hand-written Radix + Tailwind wrapper components living
in your repo," which is exactly what `src/components/ui/` contains. Writing
them directly:

- avoids a network-dependent generator step in an environment where that
  dependency wasn't necessary,
- means every primitive's source was actually read while writing this
  phase, rather than trusted sight-unseen from a registry, and
- adds zero extra tooling dependency beyond the underlying `@radix-ui/*`
  packages the CLI would have installed anyway.

Composable primitives only (§9: "do not create custom components for every
tiny element") — thirteen primitives cover every design-system item the
brief listed (Button, Input, Select, Dialog/Modal, Card, Badge, Table, Tabs,
Dropdown, Toast, Alert, Skeleton/Spinner, EmptyState/ErrorState,
ConfirmationDialog).

## 8. Further reading

- [`docs/auth.md`](docs/auth.md) — the authentication architecture, and the
  one documented trade-off (refresh-token storage) this phase couldn't avoid
  without a backend change.
- [`docs/pwa.md`](docs/pwa.md) — service-worker caching strategy, offline
  behaviour, Android/iOS platform differences.
- [`docs/api-types.md`](docs/api-types.md) — the OpenAPI codegen pipeline.
- [`docs/error-handling.md`](docs/error-handling.md) — the status→message
  mapping every error in the app goes through.
- [`docs/performance.md`](docs/performance.md) — measured bundle sizes and
  what's confirmed excluded from production.
- [`docs/testing.md`](docs/testing.md) — what each test layer covers and why.

## 9. What's intentionally not here yet

The actual staff check-in/check-out flow, attendance history UI, manager
team dashboard, and admin user-management UI are Phase 9 and Phase 10 —
see `CLAUDE.md`. Placeholder pages exist at their eventual routes
(`/attendance`, `/team`, `/admin/users`) so navigation and role-gating are
real and testable now, without building the features themselves early.
