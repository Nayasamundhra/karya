# Testing strategy

Three layers, each answering a different question:

| Layer | Tool | Question it answers | Run with |
| --- | --- | --- | --- |
| Unit / component | Vitest + React Testing Library | "Does this piece of logic/UI behave correctly in isolation?" | `npm run test` |
| Accessibility | axe-core, inside the Vitest run | "Does this markup have detectable a11y violations?" | part of `npm run test` |
| Browser / smoke | Playwright | "Does the real, built app behave correctly end to end in a real browser?" | `npm run test:e2e` |

Coverage is intentionally **behavioral, not exhaustive** (§30: "do not write
hundreds of superficial tests"). What's covered and why:

## Unit tests (`tests/unit/`)

- **`app-boot.test.tsx`** — the app renders with no persisted session and
  lands on the login page, with no error-boundary fallback. This is the
  simplest possible "does the whole tree mount without throwing" check, and
  it's real: it exercises `bootstrapSession`, the router, and lazy-loaded
  route chunks together, not mocked.
- **`routing.test.tsx`** — protected-route redirects, per-role access
  (STAFF blocked from `/admin/users`, MANAGER blocked from it too, TENANT_ADMIN
  allowed), the 404 catch-all, and that both the desktop sidebar and mobile
  bottom nav are present in the DOM (§10/§8 — CSS decides which is visible,
  not JS, so both existing is the thing worth asserting).
- **`login-form.test.tsx`** — client-side validation blocks a bad submission
  before the API is even called, a loading state disables the button and
  changes its label, a 401 shows the right (non-field-attributed) message,
  and a 429 shows the wait time from `Retry-After`.
- **`describeError.test.ts`** — every status → `ApiError.kind` mapping, that
  422 bodies are parsed into structured field errors, that `Retry-After` and
  `X-Request-ID` are read correctly, and that `retryable` is `false` for
  403/422 specifically (retrying doesn't fix either).
- **`useGeolocation.test.ts`** — success, `PERMISSION_DENIED` mapped to a
  `denied` permission state (not a generic error), an unsupported browser
  reported honestly, and — a negative assertion — that the hook's returned
  shape has no `isInsideGeofence`/`verified` field, because that decision is
  never the frontend's to make.
- **`navigation-config.test.ts`** — the role→nav-item mapping, including that
  `SUPER_ADMIN` gets nothing by default (mirrors the backend's
  no-implicit-hierarchy RBAC design) and that undefined/unknown roles produce
  an empty list rather than throwing.
- **`pwaManifest.test.ts`** — the manifest has the fields required for
  installability, declares a maskable icon, and — checked against the real
  filesystem, not just the config object — that every icon file it references
  actually exists in `public/`.
- **`accessibility.test.tsx`** — `axe-core` against the login form and a
  sample of core primitives (Button, Input, Badge, Alert), with
  `color-contrast` disabled (jsdom has no real paint engine, so that
  specific check is unreliable there — see the test file's own comment; real
  contrast is checked by hand against the token values in
  `src/styles/index.css`).

## E2E / smoke (`tests/e2e/`)

Runs against the real built app in real Chromium (`Desktop Chrome` and
`Mobile Chrome`/Pixel 7 projects — §31), with the **backend mocked at the
network boundary** via Playwright's `page.route()`. This was a deliberate
choice, not a shortcut:

- It needs no PostgreSQL instance running, no seeded tenant/user, and no
  Docker Compose — the suite is runnable anywhere Node and a browser are
  available, including CI.
- Every mocked response shape is drawn from the actual generated OpenAPI
  types (`frontend/openapi/karya.openapi.json` / `src/types/api.generated.ts`),
  not guessed — see each test's payloads.
- It complements, not replaces, a real integration pass against the live
  backend. That kind of run — seed real data, drive the UI, confirm it
  reaches PostgreSQL correctly — is exactly what the backend's own
  `backend:verify` skill is for on the API side; a full browser-driven
  version of that (real backend + real frontend together) is future work,
  not part of this phase's smoke suite.

Covers: unauthenticated redirect from `/`, unauthenticated redirect away from
an admin-only route *without the admin content ever rendering*, an empty
submission never calling the API, a real 401 shown verbatim, and a full
successful login landing on a role-correct home page with no admin nav
visible for a STAFF-equivalent flow.

## What's deliberately not tested yet

- Real GPS/camera hardware — `useGeolocation`/`useCameraStream` are tested
  by mocking `navigator.geolocation`/`navigator.mediaDevices`, per §31's "do
  not require real GPS/camera hardware in CI." The actual scanning/decoding
  UI that will consume these hooks is Phase 9's, and its tests belong there.
- Visual regression / pixel-diffing — not set up. Manual visual QA (§35) was
  done for this phase via ad-hoc Playwright screenshots at 375/768/1280px
  and in dark mode; a permanent visual-regression suite is a reasonable
  future addition once there are enough real screens to make one worth its
  maintenance cost.
- Load/performance testing — out of scope for a frontend foundation phase.
