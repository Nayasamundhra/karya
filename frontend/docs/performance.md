# Performance

Measured, not assumed. Numbers below are from an actual `npm run build` of
this codebase (§21/§43) — re-run it yourself if you want current numbers;
they will drift as pages are added in Phase 9/10.

## Bundle size (production build)

| Chunk | Raw | Gzipped | What's in it |
| --- | --- | --- | --- |
| `index-*.js` (main) | ~514 KB | ~161 KB | React 19, ReactDOM, React Router, TanStack Query, Zustand, the Radix primitives and design-system components the app shell (`AppShell`, `Header`, `Sidebar`, `BottomNav`, `Toaster`) needs on every authenticated screen |
| `Input-*.js` | ~36 KB | ~13 KB | React Hook Form + Zod + the `@hookform/resolvers` glue, split out because only screens with a real form pull it in |
| `ProfilePage-*.js` | ~10 KB | ~3.6 KB | |
| `createLucideIcon-*.js` | ~9.8 KB | ~3.9 KB | Shared Lucide icon runtime (each icon itself is a few hundred bytes more) |
| `LoginPage-*.js`, `HomePage-*.js`, `ForbiddenPage-*.js`, `NotFoundPage-*.js`, `ComingSoon-*.js`, `TeamPage-*.js`, `UsersPage-*.js`, `AttendancePage-*.js`, `Card-*.js` | 0.3–2.4 KB each | | Route-level code splitting working as intended — see below |
| CSS | ~23.5 KB | ~5.6 KB | Tailwind's generated utility CSS for every class actually used |
| Service worker | ~17.7 KB | ~5.8 KB | Workbox runtime + the three routing rules in `src/service-worker.ts` |

Vite/Rolldown warns that the main chunk exceeds its 500 KB default
threshold. That warning is noted, not chased: 161 KB gzipped of JS
(React + a real query/form/state stack + a component library) is an
ordinary weight for a production SPA, not an outlier, and this phase
explicitly says not to "obsess over arbitrary bundle-size targets" (§43).
The honest, unresolved next step if this ever needs to shrink is
`build.rollupOptions.output.manualChunks` (or Rolldown's equivalent —
Vite 8 defaults to the Rolldown bundler here, per the build warning's own
wording) to split React/Router/Query into a separately-cacheable vendor
chunk; not done in this phase to avoid destabilizing the build over a
threshold that is advisory, not a real user-facing problem at this size.

## What's confirmed NOT in the production bundle

- **`@tanstack/react-query-devtools`** — gated behind `import.meta.env.DEV`
  in `src/app/providers.tsx`. Verified by rebuilding after wiring it in and
  confirming the main chunk's size was unchanged (both builds: 514.49 KB).
- **Test tooling** — Vitest, Playwright, `@testing-library/*`, `axe-core`,
  are all `devDependencies`; nothing under `tests/` is imported from any file
  under `src/`.
- **The OpenAPI spec JSON** — lives under `openapi/`, imported by nothing at
  runtime (only by the `generate:api-types` script).

## Route-level code splitting

Every page under `src/pages/` is its own chunk (see the table above and
`src/app/router.tsx`'s `lazy()` wiring) — a STAFF user's browser never
requests `AdminUsersPage`'s or `TeamPage`'s JS, because no reachable code path
in their session ever imports it. This is the concrete answer to §21's "avoid
loading admin/dashboard code for a STAFF user if route-level splitting can
prevent it" — verified by reading the chunk list above rather than assumed
from the `lazy()` calls existing.

## Other measures already in place

- **TanStack Query caching** (§22) — `staleTime: 30_000` by default, so
  navigating back to a screen within 30s reuses cached data with no request;
  `useTenant` overrides this to 5 minutes for data that changes rarely.
- **Request deduplication** — TanStack Query dedupes identical in-flight
  queries by key automatically; the API client's own `refreshOnce()`
  (`src/lib/api/client.ts`) does the equivalent for concurrent 401s so five
  components hitting a stale token at once trigger one `/auth/refresh`, not
  five.
- **`AbortController` on every request** (§26) — `apiFetch` always combines a
  timeout with any caller-supplied `signal`; TanStack Query supplies that
  signal automatically and cancels it on unmount/query-key change, so an
  abandoned search or a fast route change never lets a stale response arrive
  late and overwrite newer state.
- **No premature optimization** — no `React.memo`/`useMemo` scattered
  speculatively; none of the current screens do enough rendering work to
  need it, and adding it without a measured reason would just be more code to
  maintain for no measured benefit.
