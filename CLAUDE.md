# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

Two components: `backend/` (a FastAPI service) and `frontend/` (a React/Vite
PWA foundation). Each is independently runnable and has its own CLAUDE.md-style
guidance in this file, split into a Backend section and a Frontend section
below. Match whichever directory you're working in.

## Phased build — read before doing anything

Karya is built in strictly-scoped phases, each handed over and reviewed one at a
time. **Phases 1–11 are complete**: DB foundation → auth/RBAC → presence
verification → attendance check-in/out → attendance reads → user/tenant
management → production hardening → frontend/PWA architecture foundation →
staff attendance experience → manager/admin dashboards → tenant self-service
onboarding, email verification and office-display (kiosk) mode. A frontend
redesign (role-specific screens, a richer design system — see
`frontend/docs/design-system.md` once it lands) is in progress on top of
Phase 11; no phase past that is scoped yet.

(`backend/README.md`'s own phase table and `frontend/README.md` lag behind
the actual state of the tree in places neither has been updated yet — trust
this file and git history (`git log --oneline`) over either when they
disagree.)

**Do not start an unscoped future phase, or add anything from either backend's
or frontend's "not implemented yet" list, unless explicitly asked.** On the
backend: reports/CSV export, hours/overtime/analytics, leave/shift management,
per-tenant timezones, password reset by email, a Redis rate limiter,
`/metrics`/tracing, multiple attendance locations per tenant, or a
`refresh_tokens` cleanup sweeper. On the frontend: offline attendance queueing,
per-tenant configurable geofence UI, or anything else not already present in
`src/features/` and `src/pages/`. If a task sounds like it belongs to one of
these, confirm scope with the user before adding it — the project owner ends
each phase with an explicit stop instruction.

Within whatever is asked: match the existing depth of documentation (docstrings
and comments explain *why*, not just *what*) and the existing test style
(see each section's "Testing" below) rather than a lighter-weight approach.

---

# Backend (`backend/`)

## Commands

All run from `backend/`.

```bash
# Setup
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"     # installs dev deps (pytest, httpx) too
cp .env.example .env                                     # then edit; never commit .env

# Database (either works — the app only reads POSTGRES_*/DATABASE_URL)
docker compose up -d                # Postgres only, for local dev
docker compose ps                   # wait for "healthy"
# — or point .env at an existing local PostgreSQL 13+ and `CREATE DATABASE karya;`

# Migrations
alembic upgrade head
alembic current
alembic downgrade -1

# Run the app
uvicorn app.main:app --reload
curl http://127.0.0.1:8000/health   # liveness — never touches the DB
curl http://127.0.0.1:8000/ready    # readiness — SELECT 1

# Tests (against real PostgreSQL, not SQLite — see "Testing")
pytest
pytest tests/test_attendance.py                          # one file
pytest tests/test_attendance.py::test_check_in_success    # one test
```

Production container:

```bash
docker compose --profile api up -d --build
docker compose --profile api run --rm api alembic upgrade head   # migrations are a deploy step, not a startup step
```

## Environment gotchas on this dev machine

(See `docs/PRODUCTION.md` for the full env-var reference.)

- A **native PostgreSQL 18 service already owns port 5432**. `docker compose up`
  then binds only IPv6 `::5432`, and `localhost:5432` silently reaches the native
  server instead, failing with `password authentication failed`. Set
  `POSTGRES_PORT=5433` in `.env` if using the Docker database — it retargets both
  the published port and the app.
- **Python 3.11 is the only interpreter installed** (floor is 3.11, target is
  3.12+) — avoid 3.12-only syntax.
- PowerShell here is 5.1: `Set-Content -Encoding utf8` writes a BOM that
  corrupts `.env`'s first key for docker-compose. Write it with
  `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`.
- `JWT_SECRET_KEY` has no default; the app still boots without it in
  `local`/`test` but raises on any attempt to mint/verify a token. In any other
  `ENVIRONMENT` it fails to start.

## Architecture

**Composition root:** `app/main.py` — `create_app(config)` builds the FastAPI
app; the middleware order is deliberate and documented there (security headers
outermost → correlation-id/access-log → CORS → request-size limits →
routing). Business logic never lives in route handlers or ORM models — it lives
in `app/services/`.

```
app/
├── main.py            create_app(): middleware order, routers, lifespan
├── core/               config.py (env settings, prod fail-fast), context.py,
│                       logging.py (JSON/console + redaction), rate_limit.py
├── middleware/         security_headers, request_context (correlation id +
│                       access log), request_limits (body/query caps)
├── api/
│   ├── deps.py         get_current_user, tenant context, require_roles
│   ├── errors.py       exception handlers — 422 never echoes submitted input
│   ├── limits.py       rate-limit dependencies (the only wiring routes see)
│   ├── probes.py       GET /health, GET /ready
│   └── v1/             router.py + auth.py, presence.py, attendance.py,
│                       users.py, tenant.py  (route handlers only — thin)
├── db/                 base.py (DeclarativeBase), session.py (engine/pool),
│                       tenant_scope.py (tenant-scoped query helpers)
├── models/             the 7 SQLAlchemy entities
├── schemas/            Pydantic request/response contracts
└── services/            business logic, one package per domain:
    ├── auth/           password (Argon2id), jwt (access tokens),
    │                   refresh_tokens, service (login/refresh/logout)
    ├── presence/        gps, qr, results, service (combines both signals)
    ├── attendance/      service (check-in/out + row locking), queries (reads)
    └── users/           service (lifecycle/roles/password), errors
```

### Data model

Seven tables, UUID primary keys throughout, `TIMESTAMPTZ` everywhere:
`tenants`, `users`, `attendance_locations`, `qr_challenges`, `attendance_events`
(source of truth for attendance — never a derived status column),
`audit_logs` (append-only), `refresh_tokens` (hashed). Every tenant-owned table
carries `tenant_id`; deletion is governed per-FK (`RESTRICT`/`CASCADE`/`SET
NULL`, never `cascade="all, delete-orphan"`) — see `backend/README.md` §9.

### Load-bearing design decisions (do not casually "fix" these)

- **Tenant context is derived, never accepted.** `current_user.tenant_id` comes
  from re-reading the database on every request; no path/query/header/body
  field may influence it. New tenant-scoped endpoints must take `tenant_id`
  from `current_user`, never from a request parameter.
- **RBAC (`require_roles`) is an exact set match with no hierarchy.**
  `SUPER_ADMIN` is never implicitly granted anything and must be listed
  explicitly on every route that needs it.
- **The database, not the JWT, is authoritative** for user status/role/tenant —
  checked fresh on every request, so deactivation takes effect on the next call.
- **Cross-tenant lookups return 404, never 403** (no existence oracle).
- **Business refusals return HTTP 200** with `success: false` / `verified:
  false` + a machine-readable `reason` (presence checks, attendance
  check-in/out, etc.). 4xx is reserved for requests that could not be processed
  at all (401 auth, 422 validation/smuggled fields, 413/414 size, 429 rate
  limit).
- **`attendance_events` is the single source of truth** — no cached/derived
  status column anywhere; every read view computes state from events on each
  request.
- **Never bucket by day with `date(event_timestamp)` or `::date`** — PostgreSQL
  session TimeZone follows the host (`Asia/Calcutta` locally, `UTC` in Docker),
  so this buckets events into different days per environment. Filter on
  explicit UTC instants and bucket in Python via `astimezone(UTC).date()`.
- **`event_timestamp` defaults to `clock_timestamp()`, not `now()`** —
  `now()` is fixed at transaction start, which let a check-out that committed
  second get an earlier timestamp than the check-in it followed under lock
  contention (Phase 7 fixed this as a real bug; see README §8f).
- **Concurrency invariants are enforced by row locks (`SELECT ... FOR UPDATE`),
  not read-then-write.** QR single-use is one conditional `UPDATE ... WHERE
  status='ACTIVE' ...`; duplicate check-in/out is prevented by locking the
  *user* row (attendance rows may not exist yet); last-admin protection locks
  the tenant's admin rows. Lock order is always user → QR challenge, to avoid
  deadlock.
- **No dependency was added in Phase 7.** Structured logging, rate limiting,
  correlation ids, security headers and request-size limits are deliberately
  stdlib + what FastAPI already brings — don't reach for a third-party package
  for adjacent needs without a strong reason.
- **Nothing is ever deleted** — there is no `DELETE` route anywhere in the API.
  Users move between `ACTIVE`/`INACTIVE`; attendance events are immutable.

### Database access is synchronous, deliberately

A sync engine keeps Alembic and test fixtures simple; endpoints are short
transactional units, not long I/O fan-outs, so async wouldn't buy much, and
Starlette already runs each `def` endpoint in a worker thread.

## Testing

- The suite runs against **real PostgreSQL**, not SQLite — the schema relies on
  `JSONB`, `TIMESTAMPTZ`, `gen_random_uuid()`, multi-column unique constraints.
  Fixtures create `<POSTGRES_DB>_test` if missing, run `alembic downgrade
  base` → `alembic upgrade head` (proving both migration directions every run),
  and wrap each test in a rolled-back transaction.
- Rate limiting stays **enabled** throughout the suite (an autouse fixture
  clears counters between tests) — a limiter that blocks a legitimate flow is
  exactly the regression the suite exists to catch, and it can't catch that
  disabled.
- The three `*_concurrency.py` modules (`test_attendance_concurrency.py`,
  `test_presence_concurrency.py`, `test_users_concurrency.py`) are the only
  ones that commit to the database (real concurrency needs separate
  connections) and clean up their own rows. Each also contains a deliberately
  naive implementation asserted to *fail* under the same forced interleaving —
  so if the harness ever stops creating real contention, that test fails
  rather than the suite quietly passing. Follow this pattern for any new
  concurrency-sensitive invariant.
- `test_health.py` makes any DB access raise, to prove liveness never queries
  the database — a useful pattern if you add other infra-independent checks.
- To verify a change end-to-end over HTTP (not just unit tests), use the
  `backend:verify` skill — it documents how to drive the running app over a
  socket, seed data (there's no registration endpoint), and the specific flows
  worth checking (enumeration resistance, spoofing attempts, tenant isolation,
  header/log hygiene, etc.).

## Where to look for more detail

`backend/README.md` is long but exhaustive — it documents *why* behind every
phase's design decisions, full endpoint tables, request/response examples, and
the complete data model. `backend/docs/PRODUCTION.md` covers deployment,
secrets, backups, and every known residual risk (rate limiter is per-process
only, no access-token revocation, single attendance location per tenant, etc.).
Prefer grepping those before re-deriving an answer from the code.

---

# Frontend (`frontend/`)

React 19 + TypeScript (`strict: true`) + Vite. Phase 8 built the PWA
foundation — routing, auth, design system, API client; Phases 9 and 10 then
built the real product on top of it: the staff check-in/check-out experience
and the manager/admin dashboards. `frontend/README.md` still describes only
the Phase 8 foundation (see the phased-build note above) — prefer the code and
this section for anything about `features/attendance`, `features/team`, or
`features/users/admin`.

## Commands

All run from `frontend/`.

```bash
npm install
cp .env.example .env.local      # then edit if the backend isn't at the default URL
npm run dev                      # dev server; service worker disabled here on purpose
npm run build                    # tsc -b (5 project-reference configs) && vite build
npm run preview                  # serve the production build — the only way to see real PWA behaviour
npm run lint                     # oxlint
npm run typecheck                # tsc -b --force, everything
npm run test                     # vitest run (unit + component + accessibility)
npm run test:e2e                 # playwright test (Desktop Chrome + Mobile Chrome)
npm run generate:api-types       # regenerate src/types/api.generated.ts — see docs/api-types.md
```

Single test: `npx vitest run tests/unit/routing.test.tsx` /
`npx playwright test tests/e2e/smoke.spec.ts`.

## Architecture

**Composition root:** `src/app/App.tsx` → `providers.tsx` (QueryClient, auth
bootstrap, toaster) → `router.tsx` (role-gated, lazily-loaded route tree).
Business logic lives in `src/features/*` and `src/lib/*`, never in
`src/pages/*` (thin) or `src/components/ui/*` (no app logic at all).

```
src/
├── app/            App.tsx, router.tsx, providers.tsx
├── components/     ui/ (design-system primitives) · layout/ (shell) · feedback/
├── features/       auth/, tenant/ (+ tenant/'s own attendance-location
│                   self-service), users/ (+ users/admin/ for employee
│                   management), attendance/ (check-in/out flow, history),
│                   team/ (manager "who's working today" views), onboarding/
│                   (self-registration, email verification, setup checklist),
│                   display/ (office-display kiosk token management + the
│                   kiosk screen itself) — schemas, forms, API-backed hooks
├── hooks/          useGeolocation, useCameraStream, useOnlineStatus,
│                   useInstallPrompt, useDebouncedValue
├── lib/            api/ (client + typed endpoints) · auth/ (session/tokens) ·
│                   errors/ (describeError) · pwa/ · validation/ · utils/
├── pages/          auth/, staff/, manager/, admin/, onboarding/, display/ —
│                   one file per route, thin wrappers around the
│                   corresponding features/ module
├── routes/         guards.tsx (RequireAuth, RequireRole)
├── stores/         authStore.ts, toastStore.ts — the only two Zustand stores
├── types/          api.generated.ts (OpenAPI codegen — never hand-edited)
├── config/         env.ts, navigation.ts, pwaManifest.ts
└── service-worker.ts
```

### Load-bearing design decisions (do not casually "fix" these)

- **The frontend never decides whether presence is valid.** `useGeolocation`
  and `useCameraStream` (both in `src/hooks/`) collect evidence only — no
  geofence math, no QR validation, no verdict. The backend renders every
  decision; a hook or component that starts computing "am I close enough"
  is a regression, not a feature.
- **Frontend route guards are UX only, not the security boundary**
  (`src/routes/guards.tsx`). A STAFF token sent directly at an admin endpoint
  still gets a 403 from the backend regardless of what the router does.
- **One centralized HTTP client** (`src/lib/api/client.ts`) — no component or
  feature calls `fetch` directly. It knows nothing about React or the auth
  store; authenticated requests and token refresh are wired in from outside
  via `configureApiAuth`, which is what keeps it free of an import cycle with
  `src/lib/auth/session.ts`.
- **Access token in memory only; refresh token in `localStorage`** — a
  documented trade-off, not an oversight, because the backend returns the
  refresh token in the JSON body rather than an HttpOnly cookie and this
  phase doesn't change that contract. Full reasoning: `frontend/docs/auth.md`.
- **API types are generated from the backend's live OpenAPI schema**
  (`frontend/openapi/karya.openapi.json` → `src/types/api.generated.ts`), never
  hand-written. Regenerate both after any backend schema change — see
  `frontend/docs/api-types.md`.
- **The service worker never caches a backend response** — `NetworkOnly` for
  every `/api/...` request, `NetworkFirst`-with-shell-fallback for navigation
  only. No offline attendance queueing exists or should be added; see
  `frontend/docs/pwa.md`.
- **Every error funnels through `ApiError` → `describeError()` →
  `ErrorState`/inline alert** — no component reads an HTTP status code
  itself. The one deliberate exception (`LoginForm`'s 401 message) is
  explained in `frontend/docs/error-handling.md`.
- **Nothing here duplicates backend authority** — no client-side geofence
  radius, no client-side role hierarchy beyond display/navigation filtering,
  no tenant id ever sent to narrow a query (`src/config/navigation.ts`,
  `src/routes/guards.tsx`).

### Design system

Hand-built Radix UI wrappers under `src/components/ui/`, not the shadcn CLI
(a network-dependent generator that would have produced the same kind of file
this repo already has written directly) — see `frontend/README.md` §7 for the
full reasoning.

## Testing

Three layers — Vitest+RTL (unit/component), axe-core (accessibility, inside
the same Vitest run), Playwright (e2e smoke, backend mocked at the network
boundary so no live PostgreSQL is required to run it). Full breakdown of what
each test covers and why: `frontend/docs/testing.md`.

## Where to look for more detail

`frontend/README.md` for setup and project layout (Phase 8 state only — see
the phased-build note above for what it misses); `frontend/docs/*.md` for the
"why" behind auth, PWA/service-worker strategy, API codegen, error handling,
performance (`performance.md`, added in Phase 9/10, tracks real production
bundle sizes per route chunk), and testing — each referenced directly from the
code comments they document.
