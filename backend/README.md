# Karya — Backend

## 1. What Karya is

Karya is a **multi-tenant staff attendance and presence verification platform**.
Each customer company is a *tenant*; its staff record attendance from a
mobile-first client, and presence is verified rather than merely self-reported.

The verification model combines:

- **GPS presence** — is the device inside the site's geofence?
- **Dynamic QR presence** — did the device scan a short-lived, one-time nonce
  displayed at the site?

and, in future, additional signals (Wi-Fi, device integrity, risk scoring).

## 2. Current project phase

| Phase | Scope | Status |
| --- | --- | --- |
| **1** | Database & backend foundation — six entities, relationships, constraints, indexes, migration, Dockerised PostgreSQL, `GET /health` | ✅ Complete |
| **2** | Authentication, multi-tenant security, RBAC foundation | ✅ Complete |
| **3** | Presence verification — GPS + geofencing + dynamic QR | ✅ Complete |
| **4** | Attendance check-in / check-out | ✅ Complete |
| **5** | Attendance history, daily summary, tenant dashboard APIs | ✅ Complete |
| **6** | User, tenant and account management | ✅ Complete |
| **7** | Production hardening & API readiness | ✅ Complete |
| 8–10 | Frontend / PWA architecture, staff attendance experience, manager/admin dashboards | ✅ Complete (see `frontend/`; `frontend/README.md` still describes only Phase 8) |
| **11** | Tenant self-service onboarding, email verification, office-display (kiosk) mode | ✅ Complete |

Phase 2 adds the identity and authorization layer every later feature depends
on: Argon2id password hashing, JWT access tokens, revocable refresh tokens with
mandatory rotation, tenant isolation, and reusable role dependencies. It added
exactly one table (`refresh_tokens`) and changed no Phase 1 schema.

Phase 3 adds presence verification: server-side GPS geofencing plus single-use
dynamic QR challenges. It added **no tables and no migration** — it reuses the
Phase 1 `attendance_locations`, `qr_challenges` and `audit_logs` tables.

Phase 4 adds the attendance lifecycle — check-in and check-out — on top of that
verification. Also **no tables and no migration**: it writes to the Phase 1
`attendance_events` table, which already had every column needed.

Phase 5 makes attendance *readable*: self-service history, daily summaries and a
tenant dashboard. **No new tables** — every view is derived from
`attendance_events` on each request. It adds one migration, and only an index:
`(tenant_id, event_timestamp)`, measured as necessary for the team query.

Phase 6 lets a tenant administrator manage the people who use Karya: user
creation, profile and role management, activate/deactivate, self-service password
change, and a tenant profile. **No new tables and no migration** — the existing
`users`, `tenants` and `audit_logs` tables already carried everything needed.

Phase 7 hardens all of it for production without changing any business
behaviour: configuration that fails fast, security headers, CORS verification,
rate limiting, request size limits, structured logging with correlation ids,
liveness/readiness probes, connection-pool and timeout management, graceful
shutdown, a production container image, and error responses that cannot leak
internals. It adds **no table**, and one migration that changes a single column
*default* — see [§8f](#8f-production-hardening-phase-7).

Phases 8–10 build the frontend on top of this API (routing, auth, PWA shell;
the staff check-in/check-out experience; manager and admin dashboards) — see
`frontend/CLAUDE.md`'s Frontend section, since none of it changes the backend.

Phase 11 adds tenant self-service: an organization creates itself and its
first administrator through the one public, unauthenticated write endpoint in
the API (`POST /onboarding/tenants`), the administrator verifies by email
before the account is usable at all, and a tenant can then set up its own
attendance location and mint credentials for unattended office-display
kiosks that show a self-refreshing check-in QR code with no phone or login
involved. It adds four tables (`email_verification_tokens`, `display_tokens`,
plus the migrations that add them and an `attendance_locations.description`
column) and one dependency-free outbound-email mechanism (stdlib `smtplib`,
degrading to a structured log line when `SMTP_HOST` is unset — see
`app/services/email/mailer.py`).

See [§10 — Not implemented yet](#10-what-is-intentionally-not-implemented-yet).

## 3. Technology stack

| Concern         | Choice                                    |
| --------------- | ----------------------------------------- |
| Language        | Python (target 3.12+; floor 3.11)         |
| Web framework   | FastAPI                                   |
| ORM             | SQLAlchemy 2.x (typed declarative models)  |
| Driver          | psycopg 3 (`postgresql+psycopg`)          |
| Database        | PostgreSQL 18 (13+ supported)              |
| Migrations      | Alembic                                   |
| Validation      | Pydantic v2 / pydantic-settings           |
| Password hashing| Argon2id (`argon2-cffi`)                  |
| Access tokens   | JWT HS256 (`PyJWT`)                       |
| Containers      | Docker (multi-stage, non-root) + Compose   |
| Logging         | stdlib `logging` + a JSON formatter        |
| Tests           | pytest (against real PostgreSQL)          |

Database access is **synchronous**. A sync engine keeps Alembic and the test
fixtures simple, and Karya's endpoints are short transactional units rather than
long I/O fan-outs, so the concurrency an async driver buys would mostly be spent
waiting on the same connection pool. Starlette runs each `def` endpoint in a
worker thread, so the server stays concurrent regardless.

**No dependency was added in Phase 7.** Structured logging, rate limiting, the
correlation id, the security headers and the size limits are all stdlib plus what
FastAPI already brings - which is deliberate: each of those has a popular
third-party package, and each package would have been more code to audit than the
feature it provides.

## 4. How to start PostgreSQL

Either database source works — the application only reads `POSTGRES_*` /
`DATABASE_URL`, so it does not care which one is running.

### Option A — Docker (recommended for a clean, disposable database)

From `backend/`:

```bash
docker compose up -d
docker compose ps          # wait for "healthy"
```

`docker compose up -d` provisions **PostgreSQL only**, with a named persistent
volume (`karya-postgres-data`), a `pg_isready` health check, and configurable
credentials, database name and host port. That is what local development wants: the
application runs on the host with `--reload`.

To run the **production image** against it — non-root user, health check, signal
handling, pinned dependencies — start the API service, which is behind a profile so
the command above is unchanged:

```bash
docker compose --profile api up -d --build
docker compose --profile api run --rm api alembic upgrade head   # migrations are a
                                                                 # deploy step
curl http://127.0.0.1:8000/ready
```

**Redis is deliberately not included.** Phase 7's rate limiter is in-process, which
is honest about its limits (see [§8f](#8f-production-hardening-phase-7)); Redis
arrives when a shared limiter or session store actually needs it.

Compose is **not** production orchestration — no rolling deploys, replicas, secret
store or scheduling. See [`docs/PRODUCTION.md`](docs/PRODUCTION.md).

To stop, keeping data: `docker compose down`.
To stop and destroy data: `docker compose down -v`.

> **Port conflict.** If a native PostgreSQL service already owns 5432 (on this
> machine, `postgresql-x64-18` does), the container will start but connections
> to `localhost:5432` reach the *native* server and fail authentication. Set
> `POSTGRES_PORT=5433` in `.env` — the one variable retargets both the
> published container port and the application, so they cannot drift.

### Option B — An existing local PostgreSQL server

Point `.env` at it and create the database once:

```sql
CREATE DATABASE karya;
```

The test database (`karya_test`) is created automatically by the test suite.
No extension is needed: `gen_random_uuid()` is built into PostgreSQL 13+.

This is the configuration currently in `.env`: the local **PostgreSQL 18.4**
service on `localhost:5432`.

## 5. How to configure environment variables

Copy the template and edit it. **Never commit `.env`** — it is gitignored.

```bash
cp .env.example .env            # PowerShell: Copy-Item .env.example .env
```

| Variable            | Purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `POSTGRES_DB`       | Database name (compose **and** app)                   |
| `POSTGRES_USER`     | Role name                                            |
| `POSTGRES_PASSWORD` | Role password — set your own, no default is shipped   |
| `POSTGRES_HOST`     | `localhost` from the host, service name from a container |
| `POSTGRES_PORT`     | Host port to publish, default `5432`                 |
| `DATABASE_URL`      | *Optional.* Full URL; overrides the five above        |
| `TEST_DATABASE_URL` | *Optional.* Defaults to `<POSTGRES_DB>_test`          |
| `JWT_SECRET_KEY`    | **Required** for auth. No default; min 32 chars       |
| `JWT_ALGORITHM`     | Default `HS256`                                      |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Default `15`                               |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | Default `30`                               |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact origins; wildcard rejected  |
| `MAX_GPS_ACCURACY_METERS` | Worst accepted GPS accuracy. Default `100`     |
| `QR_CHALLENGE_TTL_SECONDS` | QR challenge lifetime. Default `30`          |
| `DOCS_ENABLED`      | Serve `/docs`, `/redoc`, `/openapi.json`. Default `true` |
| `LOG_LEVEL` / `LOG_FORMAT` | Default `INFO` / `json` (or `console`)      |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | Pool bounds. Default `5` / `10`      |
| `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS` | Default `30` / `1800` |
| `DB_CONNECT_TIMEOUT_SECONDS` | Default `10`                              |
| `DB_STATEMENT_TIMEOUT_MS`, `DB_LOCK_TIMEOUT_MS` | Server-side ceilings. Default `15000` / `5000`; `0` disables |
| `MAX_REQUEST_BODY_BYTES`, `MAX_QUERY_STRING_BYTES` | Default `65536` / `2048` |
| `HSTS_ENABLED`, `HSTS_MAX_AGE_SECONDS` | Unset ⇒ on in production only    |
| `RATE_LIMIT_ENABLED` and the eight `RATE_LIMIT_*` budgets | See `.env.example` |

The full annotated list — including which values production refuses to start
without — is in [`.env.example`](.env.example) and
[`docs/PRODUCTION.md`](docs/PRODUCTION.md).

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Fail-safe behaviour.** `JWT_SECRET_KEY` has no fallback value. If it is
missing and `ENVIRONMENT` is anything other than `local`/`test`, the application
refuses to start. In `local`/`test` it still starts — so `GET /health` and the
database tooling work on a fresh checkout — but any attempt to mint or verify a
token raises instead of signing with a guessable default.

`ENVIRONMENT` is a **closed set** (`local`, `test`, `staging`, `production`), not
a free string, so `prod` or a stray trailing space fails at startup instead of
silently landing in the permissive branch of a later `if`. With
`ENVIRONMENT=production` the application additionally refuses to start when
`DEBUG` is on, when the JWT secret or database password is still one of the
placeholders published in `.env.example`, or when any CORS origin is not
`https://` — because the values that are *convenient* locally are exactly the ones
that must never reach production.

The same `.env` drives both Docker Compose and the application, so the two can
never drift. `app/core/config.py` builds the SQLAlchemy URL from the discrete
variables and wraps every secret in `SecretStr`, so credentials cannot leak via
an accidental `repr()` or log line.

## 6. How to run Alembic migrations

```bash
alembic upgrade head       # apply everything
alembic current            # show the applied revision
alembic downgrade -1       # roll back one revision
alembic history            # list revisions
```

The URL is injected at runtime from the settings above — `alembic.ini` contains
no `sqlalchemy.url`, so no credential is ever committed. To target another
database ad hoc:

```bash
alembic -x db_url=postgresql+psycopg://user:pass@host:5432/db upgrade head
```

## 7. How to start FastAPI

```bash
uvicorn app.main:app --reload
```

Then:

```bash
curl http://127.0.0.1:8000/health   # {"status":"ok"}   liveness  — never queries the DB
curl http://127.0.0.1:8000/ready    # {"status":"ready"} readiness — SELECT 1
```

Interactive docs: <http://127.0.0.1:8000/docs>.

Every response carries an `X-Request-ID` header and the same id appears on every
log line the request produced, so a reported problem can be looked up directly.

For a production-shaped run, see
[`docs/PRODUCTION.md` §5](docs/PRODUCTION.md) — the flags are not optional
decoration: `--proxy-headers --forwarded-allow-ips=<proxy>` is what makes the
per-address rate limits see the real client rather than the load balancer.

## 8. How to run tests

```bash
pip install -e ".[dev]"
pytest
```

The suite runs against **real PostgreSQL**, not SQLite, because the schema
relies on PostgreSQL-specific behaviour (`JSONB`, `TIMESTAMPTZ`,
`gen_random_uuid()`, multi-column unique constraints). The fixtures:

1. create `<POSTGRES_DB>_test` if it does not exist,
2. run `alembic downgrade base` then `alembic upgrade head` — so **every test
   run also proves both migration directions**, and
3. wrap each test in a transaction that is rolled back, so tests never see each
   other's rows.

Coverage by area:

| File | What it covers |
| --- | --- |
| `test_models.py`, `test_schema.py` | Phase 1 entities, constraints, indexes, delete rules |
| `test_health.py` | `GET /health` |
| `test_password.py` | Argon2id hashing and verification |
| `test_jwt.py` | Token payload, expiry, tampering, wrong type, `alg:none` |
| `test_auth_login.py` | Login, generic 401, tenant-scoped lookup |
| `test_auth_me.py` | `/auth/me`, no credential leakage, DB-authoritative state |
| `test_refresh_tokens.py` | Issuance, rotation, replay, revocation, logout |
| `test_tenant_isolation.py` | Cross-tenant attacks via body/query/header/token |
| `test_rbac.py` | `require_roles`, no hierarchy, no escalation surface |
| `test_config.py` | Missing/short secret, CORS wildcard, lifetimes, presence thresholds |
| `test_presence_gps.py` | Coordinate validation, haversine correctness, geofencing, accuracy |
| `test_presence_qr.py` | Issuance authorization, nonce quality, expiry, replay, bindings |
| `test_presence_concurrency.py` | Forced-interleaving proof that only one caller consumes a QR |
| `test_presence_verify.py` | End-to-end presence, spoofing attempts, tenant isolation, no attendance events |
| `test_attendance.py` | Check-in/out lifecycle, state transitions, spoofing, QR single-use across endpoints |
| `test_attendance_concurrency.py` | Forced-interleaving proof that concurrent check-ins produce exactly one event |
| `test_attendance_read.py` | Self-service reads, session shaping, UTC boundaries, pagination, date limits |
| `test_attendance_team.py` | RBAC, tenant dashboard, summary arithmetic, cross-tenant 404s, N+1 guard |
| `test_users_admin.py` | Creation, listing, search escaping, profile, role, lifecycle, audit |
| `test_users_self.py` | Own profile, password change, self-escalation attempts |
| `test_users_security.py` | RBAC matrix, cross-tenant 404s, field smuggling, attendance preservation |
| `test_users_concurrency.py` | Last-admin invariant and duplicate-email race, forced interleaving |
| `test_config_production.py` | Environment enum, production fail-fast, operational limits |
| `test_security_headers.py` | Every header, on success/error/413, docs CSP exception, HSTS |
| `test_cors.py` | Allowed, disallowed and near-miss origins; preflight; wildcard refusal |
| `test_rate_limit.py` | The limiter (windows, `Retry-After`, capacity, thread safety), the wired endpoints, and a full working day that must never be throttled |
| `test_observability.py` | Request-id generation/validation, access-log fields, redaction, no secret in any log |
| `test_error_handling.py` | Validation errors that do not echo input, generic 500s, no traceback or SQL leakage |
| `test_request_limits.py` | Body and query caps, chunked-body evasion, existing bounds intact |
| `test_db_session.py` | Pool configuration, server-side timeouts, rollback-on-exception, disposal |
| `test_health.py` | Liveness independence from the database, readiness 200/503, read-only |

`test_health.py` proves liveness never queries the database by making any database
access raise, so the property fails loudly if `/health` ever grows a query.

The two `*_concurrency.py` modules are the only ones that commit to the database
(real concurrency needs separate connections); each deletes its own rows in
teardown. Both also contain a deliberately naive implementation and assert it
*would* break — double-consuming a QR, or double-inserting a CHECK_IN — so if the
harness ever stops creating real lock contention those tests fail rather than the
suite quietly passing. Phase 7 added a third pair in the same style, for event
*ordering* rather than event count: see
[§8f](#8f-production-hardening-phase-7).

Rate limiting stays **enabled** throughout the suite rather than being switched
off, because a limiter that blocks a legitimate flow is exactly the regression the
suite should catch — and it cannot catch it while disabled. An autouse fixture
clears the counters between tests, so each test behaves like a freshly started
process.

## 8a. Authentication architecture (Phase 2)

### The end-to-end flow

```
User
  ↓
Tenant-aware Login          POST /api/v1/auth/login  { tenant_slug, email, password }
  ↓
Password Verification       Argon2id, tenant-scoped user lookup
  ↓
Access Token + Refresh Token   JWT (15 min)  +  opaque random token (30 days)
  ↓
Authenticated Request       Authorization: Bearer <access_token>
  ↓
get_current_user()          verify signature / exp / type=access
  ↓
Database User               re-read from PostgreSQL — the authoritative record
  ↓
Tenant Context + Role       current_user.tenant_id, current_user.role
  ↓
Authorized Operation        require_roles(...) + tenant_scoped_select(...)
```

### Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | — | Liveness; never touches the database (Phase 1) |
| `GET` | `/ready` | — | Readiness; `SELECT 1`, 200 or 503 (Phase 7) |
| `POST` | `/api/v1/auth/login` | — | Tenant-scoped login → token pair |
| `POST` | `/api/v1/auth/refresh` | refresh token in body | Rotate → new token pair |
| `POST` | `/api/v1/auth/logout` | refresh token in body | Revoke that session (204) |
| `GET`  | `/api/v1/auth/me` | Bearer access token | The caller's own profile |
| `POST` | `/api/v1/presence/qr/challenge` | MANAGER / TENANT_ADMIN | Issue a QR challenge (Phase 3) |
| `POST` | `/api/v1/presence/verify` | Any active user | Verify presence (Phase 3) |
| `POST` | `/api/v1/attendance/check-in` | Any active user | Check in (Phase 4) |
| `POST` | `/api/v1/attendance/check-out` | Any active user | Check out (Phase 4) |
| `GET` | `/api/v1/attendance/me` | Any active user | Own attendance for a day (Phase 5) |
| `GET` | `/api/v1/attendance/me/history` | Any active user | Own daily history (Phase 5) |
| `GET` | `/api/v1/attendance/team/today` | MANAGER / TENANT_ADMIN | Tenant dashboard (Phase 5) |
| `GET` | `/api/v1/attendance/users/{user_id}` | MANAGER / TENANT_ADMIN | One user's day (Phase 5) |
| `GET` | `/api/v1/attendance/users/{user_id}/history` | MANAGER / TENANT_ADMIN | One user's history (Phase 5) |
| `GET`/`PATCH` | `/api/v1/users/me` | Any active user | Own profile (Phase 6) |
| `POST` | `/api/v1/users/me/password` | Any active user | Change own password (Phase 6) |
| `GET`/`PATCH` | `/api/v1/tenant/me` | Any active user / TENANT_ADMIN | Tenant profile (Phase 6) |
| `POST`/`GET` | `/api/v1/users` | TENANT_ADMIN | Create / list users (Phase 6) |
| `GET`/`PATCH` | `/api/v1/users/{user_id}` | TENANT_ADMIN | Read / update a user (Phase 6) |
| `PATCH` | `/api/v1/users/{user_id}/role` | TENANT_ADMIN | Change a role (Phase 6) |
| `POST` | `/api/v1/users/{user_id}/activate` | TENANT_ADMIN | Reactivate (Phase 6) |
| `POST` | `/api/v1/users/{user_id}/deactivate` | TENANT_ADMIN | Deactivate (Phase 6) |
| `GET` | `/api/v1/users/{user_id}/audit` | TENANT_ADMIN | Lifecycle audit (Phase 6) |
| `POST` | `/api/v1/onboarding/tenants` | — (public) | Create a tenant + its first (unverified) admin (Phase 11) |
| `POST` | `/api/v1/onboarding/verify-email` | — (public, token in body) | Activate the admin and sign in (Phase 11) |
| `POST` | `/api/v1/onboarding/resend-verification` | — (public) | Issue a fresh verification link (Phase 11) |
| `GET`/`POST`/`PATCH` | `/api/v1/tenant/me/location` | Any active user / TENANT_ADMIN | Read / set up / update the tenant's attendance location (Phase 11) |
| `POST`/`GET` | `/api/v1/tenant/display-tokens` | MANAGER / TENANT_ADMIN | Mint / list office-display kiosk credentials (Phase 11) |
| `POST` | `/api/v1/tenant/display-tokens/{id}/revoke` | MANAGER / TENANT_ADMIN | Revoke a kiosk's credential (Phase 11) |
| `POST` | `/api/v1/display/revoke-self` | — (display token, not a user) | A kiosk revokes its own credential (Phase 11) |
| `POST` | `/api/v1/presence/qr/challenge/display` | — (display token, not a user) | A kiosk mints its own QR challenge (Phase 11) |

All appear in the OpenAPI docs at `/docs`.

### Login flow

1. Validate the request body (`extra="forbid"` — a smuggled `role` or
   `tenant_id` is a 422, not a silently ignored field).
2. Resolve the tenant **by slug**, and constrain the user lookup to that tenant:
   `users.tenant_id = tenants.id AND tenants.slug = :slug`. A user is never
   looked up by email alone.
3. Verify the password with Argon2id.
4. Require `status = ACTIVE`.
5. Issue an access token and a refresh token, storing only the latter's hash.

**No user enumeration.** An unknown tenant, an unknown user, a wrong password
and a deactivated account all return the byte-identical response:

```
HTTP 401  {"detail": "Invalid credentials"}
```

The unknown-user path also performs one throwaway Argon2 verification, so it
costs the same wall-clock time as a wrong password and cannot be distinguished
by timing either.

### Access token lifecycle

Short-lived (default 15 min) HS256 JWT carrying exactly:

```json
{ "sub": "<user_uuid>", "tenant_id": "<tenant_uuid>", "role": "STAFF",
  "type": "access", "iat": …, "exp": …, "jti": "<unique_token_id>" }
```

No email, password hash, secret or database detail is ever placed in a token.
Access tokens are **not** blacklisted — they are short-lived by design, and
revocation happens at the refresh-token layer.

### Refresh token lifecycle

Refresh tokens are **not JWTs**. Each is 256 bits from `secrets.token_urlsafe`,
so it can be revoked server-side:

- The raw value is returned to the client **once** and never stored or logged.
- PostgreSQL holds only its **SHA-256 digest** in `refresh_tokens.token_hash`.
- SHA-256 rather than Argon2 here on purpose: the input is high-entropy random
  (no dictionary to slow down), and a deterministic digest is what allows lookup
  by a single indexed equality query.

**Rotation is mandatory.** On `POST /auth/refresh` the presented token is
verified (exists, not expired, `revoked_at IS NULL`, user exists, user ACTIVE,
stored tenant still matches), then **revoked** before a replacement is issued.
Rows are revoked rather than deleted, so a replayed token is identifiable as
revoked instead of merely absent. Replaying a rotated token returns 401 — it is
never silently exchanged for a new one. A rejected rotation rolls back, leaving
no half-applied state.

### Tenant isolation model

This is the load-bearing security property of the phase.

- **Context is derived, never accepted.** `get_current_user` reads the user row
  from PostgreSQL; `current_user.tenant_id` is the only tenant context. No path,
  query, header or body value can influence it.
- **The token identifies; the database decides.** Status, role and tenant
  membership are re-read on every request, so deactivating a user or changing
  their role takes effect on the *next* request rather than when their token
  expires.
- **Consistency check.** If a token's `tenant_id` no longer matches the user's
  row, the request is refused rather than trusting either side.
- **Reusable query helpers.** `app/db/tenant_scope.py` provides
  `tenant_scoped_select(Model, tenant_id)` and `get_tenant_owned(...)`; the
  latter returns `None` for both "missing" and "another tenant's", so a caller
  can answer either with an identical 404 and never confirm a foreign id exists.

Future tenant-owned endpoints must take the shape `GET /users` using
`current_user.tenant_id` internally — **never** `GET /users?tenant_id=…`.

### RBAC model

Roles (unchanged from Phase 1): `SUPER_ADMIN`, `TENANT_ADMIN`, `MANAGER`,
`STAFF`.

```python
@router.get("/staff", dependencies=[Depends(require_roles(UserRole.MANAGER))])
...
user: Annotated[User, Depends(require_roles(UserRole.TENANT_ADMIN, UserRole.MANAGER))]
```

- Membership is an **exact set match with no hierarchy**: MANAGER does not
  satisfy a TENANT_ADMIN requirement, and `SUPER_ADMIN` is **not** implicitly
  granted — a platform-level role must be listed explicitly. Silent inheritance
  is how over-broad access creeps in.
- The role is read from the database row, never from the token claim.
- `401` for unauthenticated, `403 {"detail": "Insufficient permissions"}` for
  authenticated-but-not-permitted. The refusal names no role.
- **No role-management endpoint exists**, so self-escalation has no surface. A
  test asserts the API exposes only the five paths above and no `PUT`/`PATCH`/
  `DELETE` at all.

## 8b. Presence verification architecture (Phase 3)

Phase 3 answers exactly one question: **"is this authenticated staff member
physically at their tenant's attendance location right now?"**

> **Phase 3 does NOT create attendance events.** It never writes to
> `attendance_events`. Deciding what attendance action verified presence should
> cause — a check-in or a check-out — is Phase 4's job. Keeping the two apart
> means presence can be re-evaluated, audited or refused with no attendance side
> effect, and a failed attempt leaves no attendance record to undo.

```
Staff Phone
    │
    ├── GPS evidence
    │
    └── QR challenge
           │
           ▼
       Karya Server
           │
      ┌────┴────┐
      ▼         ▼
     GPS       QR
   verify    verify
      │         │
      └────┬────┘
           ▼
    Presence Decision
           │
           ▼
    PRESENCE_VERIFIED
```

### Why two signals, and why both are mandatory

| Signal | What it proves | How it can fail alone |
| --- | --- | --- |
| **GPS** | The device *reports* coordinates inside the geofence | Coordinates can be faked on a rooted or developer-mode device |
| **Dynamic QR** | Someone read a code that existed for ~30 s on the office display | A photographed code could be shared — but only for seconds, and only once |

Neither is sufficient. GPS is an **evidence signal, not proof**: this codebase
performs rigorous server-side validation but cannot detect a spoofed location,
and it does not claim to. The QR compensates by requiring physical proximity to
a rotating display at the moment of the attempt. Conversely a shared QR code is
useless without also being inside the geofence. Requiring both means an attacker
must defeat two independent mechanisms at the same instant.

**Wi-Fi is deliberately not implemented.** It was specified as optional, and a
third signal adds real cost — SSID/BSSID collection is platform-restricted,
easily spoofed, and needs per-site configuration — for little gain over the two
above. Device attestation, which *would* raise the cost of GPS spoofing
materially, is intentionally deferred to a later security phase rather than
half-done here.

### How GPS distance is calculated

Server-side, always. The request carries coordinates and accuracy; it cannot
carry a distance (the field is rejected outright).

Distance uses the **haversine formula** on a sphere of radius 6 371 008.8 m
(IUGG mean). A naive Euclidean distance over raw latitude/longitude would be
wrong twice over: degrees are not metres, and a degree of longitude shrinks with
`cos(latitude)` — about 111 km at the equator but only 55.6 km at 60° — so flat
arithmetic would silently distort every geofence away from the equator. A test
asserts exactly that ratio.

The spherical model carries up to ~0.5 % error versus a true ellipsoid; at
geofence scale that is well under a metre, far below consumer GPS accuracy, so it
is not the limiting factor.

### How geofencing works

```
GPS valid  ⟺  coordinates well-formed
           ∧  accuracy_meters ≤ MAX_GPS_ACCURACY_METERS
           ∧  distance_meters ≤ attendance_locations.geofence_radius_meters
```

- The radius comes from **the tenant's own location row**, never a constant, so
  each tenant sets its own tolerance. `150` appears only as the column default.
- The boundary is inclusive (`distance <= radius`).
- Invalid coordinates are **rejected, never clamped** — silently pulling a bad
  coordinate into range would fabricate evidence.
- Poor accuracy fails even when the reported point is dead centre: a reading that
  only says "somewhere within 400 m" cannot evidence presence inside a 150 m
  geofence. The threshold is configurable, not hardcoded.
- The distance is returned even on failure, so a rejection is diagnosable
  ("you were 350 m away") rather than an opaque no.

### How dynamic QR challenges work

```
Server                                   Office display        Staff phone
  │ POST /presence/qr/challenge (MANAGER/TENANT_ADMIN)
  │──── nonce = secrets.token_urlsafe(32) ─────►│
  │     expires_at = now() + TTL               │ renders QR
  │                                            │  {challenge_id, nonce}
  │                                            │◄──── scan ──────│
  │◄──── POST /presence/verify {gps, challenge_id, nonce} ────────│
  │ atomic single-use consume
```

- **Nonce**: 32 bytes from the OS CSPRNG (`secrets`), url-safe encoded to 43
  characters. Not a timestamp, counter, sequence or bare UUID — the code is
  displayed publicly, so a predictable generator would be forgeable. `random` is
  unsuitable: its entire future output is recoverable from a few observed values.
- **Payload**: only `challenge_id` and `nonce`. No JWT, no credentials, no
  personal data, no coordinates. A signed token would be self-validating and so
  could not be revoked or marked used without a server record anyway — and the
  record is what gives replay protection, so the token would add only size.
- **Only MANAGER and TENANT_ADMIN may issue challenges.** STAFF cannot: anyone
  who can mint a code could mint one away from the office and redeem it
  themselves, defeating the second signal entirely.
- Previous challenges are **not** revoked on issue. The display fetches the next
  code slightly before the current one lapses, so they overlap briefly; revoking
  eagerly would break anyone mid-scan. Old codes simply expire.

### QR expiration

`expires_at = server_now() + QR_CHALLENGE_TTL_SECONDS` (default 30 s). The client
neither sends nor influences it. A challenge is rejected once
`server_time >= expires_at`; the server's UTC clock is authoritative and no
client-supplied time is read anywhere.

Expiration is **lazy**: when a request notices a lapsed-but-still-`ACTIVE` row it
flips the status to `EXPIRED` as bookkeeping. No background worker is required,
because the authoritative gate is the timestamp comparison — in the read check
*and* inside the consuming `UPDATE` — never the status column.

### QR replay protection

A challenge is strictly single-use, enforced by one statement:

```sql
UPDATE qr_challenges SET status='USED', used_at=now()
WHERE id=… AND tenant_id=… AND location_id=… AND nonce=…
  AND status='ACTIVE' AND used_at IS NULL AND expires_at > now()
```

Every precondition is re-checked *inside the write*, so the check and the claim
cannot be separated by another transaction — a compare-and-swap. Under
PostgreSQL's default **READ COMMITTED** isolation two concurrent such statements
serialise: the second blocks until the first commits, re-evaluates its `WHERE`
against the newly committed row, sees `status='USED'` and matches zero rows.
Exactly one caller can ever win.

A read-then-write (`SELECT` … then `UPDATE`) would leave both transactions
believing the challenge was `ACTIVE`. The test suite proves this is not
theoretical: it forces the interleaving and asserts a deliberately naive
implementation double-consumes while the real one does not.

Rows are **revoked/used rather than deleted**, so a replayed code is reported as
`QR_ALREADY_USED` instead of indistinguishable from a code that never existed.

### Ordering: why the QR is consumed last

```
1. resolve the tenant's active location
2. evaluate GPS
3. evaluate the QR  (read-only — nothing consumed)
4. if BOTH passed → atomically consume the QR
```

If the QR were spent before the GPS check, someone standing 500 m away would
destroy the office's current code on every attempt — a trivial denial of service
against everyone legitimately present. So a rejected attempt leaves the challenge
untouched and still usable. A test asserts exactly this.

### Tenant isolation

Unchanged from Phase 2 and extended to every new query:

- The attendance location is resolved by a tenant-scoped query using
  `current_user.tenant_id`.
- A challenge is validated against both `tenant_id` **and** `location_id`.
  Location binding is enforced even though V1 has one site per tenant, so a code
  cannot cross sites once multiple locations exist.
- Neither endpoint accepts a tenant or user identifier. `POST /presence/verify`
  takes no identity fields at all, and `extra="forbid"` turns an attempt to send
  one into a 422.
- **Cross-tenant reasons are collapsed in responses.** Internally the service
  distinguishes `QR_TENANT_MISMATCH` from `QR_NOT_FOUND`; the API reports both as
  `QR_NOT_FOUND`, because confirming "that id belongs to another tenant" is a
  cross-tenant existence oracle. The precise reason *is* recorded in the audit
  log, where repeated mismatches are a genuine signal that someone is probing.

### Presence verification flow

```
POST /api/v1/presence/verify        Authorization: Bearer <access token>
{ "latitude": 12.9723, "longitude": 77.5946,
  "accuracy_meters": 12.5, "challenge_id": "…", "nonce": "…" }
```

Rejections return **200 with `verified: false`**, not a 4xx: the request was
well-formed and processed, and the body carries a per-signal verdict. HTTP errors
are reserved for requests that could not be processed at all — 401
unauthenticated, 422 malformed or smuggled fields.

```json
{ "verified": true, "status": "PRESENCE_VERIFIED",
  "gps": {"verified": true, "distance_meters": 73.0, "accuracy_meters": 12.5},
  "qr":  {"verified": true}, "reason": null }
```

```json
{ "verified": false, "status": "PRESENCE_REJECTED",
  "gps": {"verified": false, "distance_meters": 350.0, "accuracy_meters": 12.5},
  "qr":  {"verified": true}, "reason": "OUTSIDE_GEOFENCE" }
```

Both signals are always reported, so one round trip tells the user everything
that is wrong. Failure reasons: `NO_ACTIVE_ATTENDANCE_LOCATION`, `GPS_INVALID`,
`GPS_ACCURACY_TOO_LOW`, `OUTSIDE_GEOFENCE`, `QR_NOT_FOUND`, `QR_EXPIRED`,
`QR_ALREADY_USED`, `QR_REVOKED`, `QR_NONCE_MISMATCH`.

**The office's stored coordinates are never returned** — a distance is all the
client needs, and revealing the exact position would help someone spoof it.

### What the client can never do

| Attempt | Outcome |
| --- | --- |
| `gps_verified` / `qr_verified` / `presence_verified` in the body | 422 |
| `distance_meters` in the body | 422 — the server computes its own |
| `tenant_id` / `user_id` in body, query or header | 422 or ignored |
| Choose `expires_at` for a challenge | Ignored; server sets it |
| Reuse a consumed challenge | `QR_ALREADY_USED` |
| Redeem another tenant's challenge | `QR_NOT_FOUND` |

### Audit logging

- `QR_CHALLENGE_CREATED` — on every issue, with `challenge_id`, `location_id`,
  `expires_at`, `ttl_seconds`. **The nonce is never logged**: it is the secret
  the challenge protects, and the id is enough to correlate issue with redemption.
- `PRESENCE_VERIFICATION_FAILED` — on every rejection, with the internal failure
  reason, distance and accuracy.

Successes are *not* audited: a rejection is the security-relevant event, whereas a
success will be recorded by Phase 4 as an attendance event carrying the same
metadata. Logging both would duplicate the record and bury the signal in noise.

### Designed for Phase 4

`PresenceDecision.to_verification_metadata()` renders a decision in exactly the
shape documented for `attendance_events.verification_metadata`, so Phase 4 can
persist it without reshaping — and the JSONB layout is fixed by one function
rather than restated at each call site. Phase 3 itself never writes that column.

```json
{"gps": {"verified": true, "distance_meters": 73.0, "accuracy_meters": 12.5},
 "qr":  {"verified": true, "challenge_id": "…"}}
```

## 8c. Attendance lifecycle (Phase 4)

Phase 3 asks *"is Rahul physically present?"*. Phase 4 asks the next question:
*"given that, should Karya record an attendance event?"* — and it is the only
code that writes to `attendance_events`.

```
CHECK-IN                             CHECK-OUT
Authentication                       Authentication
      ↓                                    ↓
Attendance state  (must be            Attendance state  (must be
  NOT_CHECKED_IN)                       CHECKED_IN)
      ↓                                    ↓
GPS verification                     GPS verification
      ↓                                    ↓
QR verification                      QR verification
      ↓                                    ↓
Atomic QR consumption                Atomic QR consumption
      ↓                                    ↓
Attendance event (CHECK_IN)          Attendance event (CHECK_OUT)
      ↓                                    ↓
Commit                               Commit
```

### Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/v1/attendance/check-in` | Any active user | Record a CHECK_IN |
| `POST` | `/api/v1/attendance/check-out` | Any active user | Record a CHECK_OUT |

Both take the **same body as `/presence/verify`** — coordinates, accuracy,
challenge id, nonce — because the schema is literally inherited from it.

```json
{ "success": true, "event_type": "CHECK_IN", "status": "CHECKED_IN",
  "attendance_event_id": "…", "event_timestamp": "2026-08-16T16:13:37.071390+05:30",
  "presence": {"verified": true,
               "gps": {"verified": true, "distance_meters": 73.0, "accuracy_meters": 12.5},
               "qr": {"verified": true}},
  "reason": null }
```

A refusal is `success: false` with HTTP 200 and a `reason`, matching
`/presence/verify`: the request was processed, and the presence breakdown is
what lets a client say *"you are 350 m away"* rather than just *"failed"*.

### Why attendance cannot be created without presence verification

**The server re-runs verification as part of the action.** A client cannot call
`/presence/verify`, get `PRESENCE_VERIFIED`, and then tell the server "I was
verified, check me in" — there is no field in which to say it. Every check-in
and check-out calls the Phase 3 service itself.

Even replaying the *same challenge* fails: `/presence/verify` consumes it, so
presenting it again to check-in returns `QR_ALREADY_USED`. There is no path from
an earlier verification to an attendance event.

`app/services/attendance/service.py` contains **no GPS or QR logic at all** — it
calls `presence_service.verify_presence`, which calls the GPS and QR modules.
One implementation, so the two entry points cannot drift apart in their security
behaviour:

```
attendance service → presence service → gps service
                                      → qr service
```

### Why the server controls timestamps

`event_timestamp` is omitted from the INSERT so PostgreSQL's `now()` server
default fills it, then it is read back to return to the client. The device clock
never reaches the column, and `event_timestamp` is one of the fields
`extra="forbid"` rejects outright. The QR's issue time is not used either — only
the moment the event was actually recorded.

### Why the client cannot choose `user_id` or `tenant_id`

Both come from `current_user`, resolved from the bearer token against the
database on every request. Neither appears in any attendance schema, so sending
one is a 422 rather than a silently ignored field. Query parameters and headers
are equally inert — a test fires `?user_id=…` plus an `X-User-Id` header at
check-in and asserts the row still belongs to the caller.

### Attendance state

Derived from the user's most recent event — there is deliberately **no
`current_status` column**. A denormalised status is a second source of truth that
can drift from the events, and the events are the audit record that matters.

```
no events            → NOT_CHECKED_IN
latest = CHECK_IN    → CHECKED_IN
latest = CHECK_OUT   → NOT_CHECKED_IN
```

The lookup is scoped by `(tenant_id, user_id)` ordered by `event_timestamp DESC`,
which is exactly the Phase 1 composite index. Because `CHECK_OUT` returns the
user to `NOT_CHECKED_IN`, day-after-day cycles work with no reset step.

### Transaction boundaries

One transaction per request, committed once in the route:

```
BEGIN
  lock the user row          ← SELECT … FOR UPDATE
  derive + validate state
  verify presence            ← GPS, then QR
  consume the QR challenge   ← atomic conditional UPDATE
  INSERT the attendance event
  INSERT the audit row
COMMIT
```

Nothing is committed separately, so the database can never hold **a consumed
challenge with no attendance event**. If anything raises, the session closes
without a commit and PostgreSQL discards the lot — including the consumption. A
live run confirmed the invariant: 8 attendance events, exactly 8 challenges in
`USED`.

### How duplicate check-ins and check-outs are prevented

The naive approach — read the latest event, then insert — races. Two concurrent
check-ins both read `NOT_CHECKED_IN` and both insert, giving `CHECK_IN,
CHECK_IN`: a state machine broken by timing rather than by logic.

Phase 4 takes a **row lock on the user** (`SELECT id FROM users WHERE id=… AND
tenant_id=… FOR UPDATE`) before reading the state. That serialises every
attendance operation for one user: the second transaction blocks there until the
first commits, then reads the state, sees the new event and refuses with
`ALREADY_CHECKED_IN` (or `NOT_CHECKED_IN` for check-out). Different users lock
different rows, so unrelated staff never contend.

The *user* row is locked rather than the attendance rows because at check-in time
there may be no attendance rows to lock, and PostgreSQL offers no gap lock under
READ COMMITTED. The user row always exists, so it is a reliable mutex keyed by
exactly the right thing.

**Lock order is always user → QR challenge**, so two transactions can never hold
each other's next lock and deadlock.

### How QR replay stays prevented

Untouched from Phase 3 — the same atomic conditional UPDATE, reached through the
same service. Two extra guarantees hold across the new endpoints:

- A challenge spent on a check-in **cannot** be reused for the check-out; each
  action needs its own fresh code.
- A challenge spent by `/presence/verify` cannot then authorise attendance.

### State is validated before evidence is examined

The order matters. A duplicate check-in is refused **before** the QR is looked
at, so it does not consume the office's current challenge — the same reasoning
Phase 3 applies to GPS failures. Otherwise a user tapping the button twice would
destroy the code for everyone queuing behind them. A test asserts the challenge
survives a rejected duplicate and still works for the legitimate next action.

### Verification metadata

Every event stores the evidence that justified it, in the existing
`verification_metadata` JSONB column, built from the presence decision rather
than restated:

```json
{"presence": {"verified": true},
 "gps": {"verified": true, "distance_meters": 73.0, "accuracy_meters": 12.5},
 "qr":  {"verified": true, "challenge_id": "…"},
 "attendance_state": "CHECKED_IN"}
```

The `challenge_id` is recorded, **never the nonce** — the id is enough to
correlate an event with the challenge that authorised it, whereas the nonce is
the secret that challenge protects.

### Audit

`ATTENDANCE_CHECK_IN` / `ATTENDANCE_CHECK_OUT` on success, carrying the event id,
challenge id, distance and accuracy. `ATTENDANCE_CHECK_IN_FAILED` /
`ATTENDANCE_CHECK_OUT_FAILED` on refusal, carrying the failure reason and the
state at the time.

One rejected action writes **one** audit row: attendance passes
`audit_failures=False` to the presence service and writes its own richer entry,
rather than leaving a presence row and an attendance row describing the same
event. As in Phase 3 the audit keeps the *internal* reason — a cross-tenant
attempt is recorded as `QR_TENANT_MISMATCH` even though the client is told
`QR_NOT_FOUND`.

### Not in Phase 4

No attendance history or reporting endpoint, no hours/overtime/late-arrival
calculation, no overnight-shift handling, no admin override, correction,
approval or deletion. Attendance events are treated as immutable audit records;
administrative correction is a later phase and needs its own explicit trail.

## 8d. Attendance reads (Phase 5)

Phase 4 made Karya able to *record* attendance securely. Phase 5 makes it able to
*read* it — and every one of these endpoints is strictly read-only.

> **`attendance_events` remains the single source of truth.** Phase 5 adds no
> `daily_attendance`, no `attendance_status`, no `current_attendance` and no
> cached status column anywhere. Every state below is computed from the events on
> each request. A denormalised copy would be a second source of truth that can
> drift from the record that actually matters.

### Endpoints and who may call them

| Method | Path | STAFF | MANAGER | TENANT_ADMIN |
| --- | --- | :-: | :-: | :-: |
| `GET` | `/api/v1/attendance/me` | ✅ | ✅ | ✅ |
| `GET` | `/api/v1/attendance/me/history` | ✅ | ✅ | ✅ |
| `GET` | `/api/v1/attendance/team/today` | 403 | ✅ | ✅ |
| `GET` | `/api/v1/attendance/users/{user_id}` | 403 | ✅ | ✅ |
| `GET` | `/api/v1/attendance/users/{user_id}/history` | 403 | ✅ | ✅ |

Staff see **only their own** attendance — a colleague's movements are not their
business. Managers and tenant admins have identical read access across their own
tenant; Karya's administration is tenant-scoped, and `TENANT_ADMIN` is not a
platform-wide role. As in Phase 2, `SUPER_ADMIN` is **not** implicitly granted
tenant data: it must be listed explicitly, and it is not.

Authorization reuses the Phase 2 `require_roles` dependency — no route compares
role strings by hand.

### How state is derived

```
no events that day        → NO_RECORD
last event is CHECK_IN    → CHECKED_IN
last event is CHECK_OUT   → COMPLETED
```

`NO_RECORD` is named deliberately. It says only that **no attendance event was
recorded** — it is *not* a claim that the person was absent from work. They may
have been on leave, travelling, working elsewhere, or simply unable to reach the
QR display. Karya cannot tell the difference, and leave and shift management do
not exist yet, so "ABSENT" would assert something the data does not support.

### Sessions

A day is returned as a list of check-in/check-out **sessions**, so multiple
cycles in one day are never collapsed:

```json
{ "date": "2026-08-15", "status": "COMPLETED",
  "sessions": [
    {"check_in": "…T09:00:00Z", "check_out": "…T12:00:00Z",
     "check_in_event_id": "…", "check_out_event_id": "…"},
    {"check_in": "…T13:00:00Z", "check_out": "…T18:00:00Z",
     "check_in_event_id": "…", "check_out_event_id": "…"}],
  "first_check_in": "…T09:00:00Z", "last_check_out": "…T18:00:00Z" }
```

Either side of a session may be `null`:

- `check_out: null` — the session is still open.
- `check_in: null` — the session opened on an **earlier day** and closed on this
  one. Phase 4 guarantees events alternate per *user*, not per calendar day, so a
  night shift legitimately produces a day whose first event is a CHECK_OUT.
  Discarding it would lose a real event.

Event ids are always included, so any figure on a dashboard can be traced back to
the exact rows behind it.

### Dates and timezones

Karya has no per-tenant timezone yet, so **UTC is the canonical calendar** and is
applied explicitly rather than inherited.

That distinction matters more than it sounds. PostgreSQL's session `TimeZone`
follows its host — `Asia/Calcutta` on this development machine, `UTC` in the
Docker image. A bare `date(event_timestamp)` or `::date` would therefore file an
event recorded at 23:30 UTC under *different days* in the two environments. So
this code never asks SQL to derive a date: it filters on explicit UTC instants
and buckets in Python via `astimezone(UTC).date()`. The test suite pins the
behaviour and passes identically against both servers.

Ranges are **half-open**, `[start, end)`, so an event at exactly midnight belongs
to the day starting then and no event can fall into two buckets.

Per-tenant timezones are a later phase; they would slot in by replacing
`day_bounds()` and `utc_date_of()` in `app/services/attendance/queries.py`.

### Pagination and range limits

History is paginated **by day**, newest first.

| Guard | Value |
| --- | --- |
| Default page size | 30 days |
| Maximum page size | 100 days |
| Maximum date range | 366 days |
| Default range | the last 30 days ending today |

Anything outside those is a 422. Without them a caller could ask for every event
a tenant has ever recorded in one request.

**Every date in the range is returned**, including days with no events, as
`NO_RECORD`. A calendar needs the gaps — otherwise it cannot distinguish "nothing
recorded" from "outside the range". `pagination.total` therefore counts *days*,
not events, and needs no COUNT query: the range is known arithmetic.

### Tenant isolation

Every query is constrained by `current_user.tenant_id`, taken from the
authenticated user's database row. There is no parameter, header or body field
that can widen it — a test fires `?tenant_id=…` plus `X-Tenant-Id` at the team
endpoint and asserts the roster is unchanged.

**Cross-tenant lookups return 404, never 403.** A 403 would confirm the id exists
somewhere and turn the endpoint into a tenant-wide enumeration oracle, so
"belongs to another tenant" and "does not exist" produce byte-identical
responses:

```
GET /api/v1/attendance/users/<a Tenant-B user>   → 404 {"detail": "User not found"}
GET /api/v1/attendance/users/<random UUID>       → 404 {"detail": "User not found"}
```

`/attendance/me` takes no identity input at all, so there is nothing to spoof.

### Avoiding N+1 on the team dashboard

`/attendance/team/today` runs **exactly two queries regardless of headcount** —
one for the tenant roster, one for the day's events — and joins them in memory.
The obvious alternative (fetch users, then query each user's events) would issue
one statement per employee on the endpoint most likely to be polled.

A test counts statements at the driver, grows the tenant from 3 to 28 employees,
and asserts the count does not move.

Everyone active appears, **including people with no events today** — they are
precisely who a manager is looking for. Inactive users are excluded from the live
dashboard (a departed employee is noise there) but their history stays fully
queryable through the history endpoints. Phase 5 hides and deletes nothing.

Summary counts always reconcile:

```
no_record + checked_in + completed == total_staff
```

### What the read APIs deliberately do not expose

Attendance is sensitive operational data, so responses carry the minimum:
timestamps, event ids, derived status, and — for the team view — name and
employee code.

Never returned: `verification_metadata`, GPS coordinates, distance, accuracy, QR
challenge ids, nonces, email addresses, roles, password hashes or tokens. The
verification evidence is retained on the event row for audit; a history screen has
no use for it, and every field exposed is a field that can leak. Tests assert the
absence of each by scanning the raw response text.

### Example responses

`GET /api/v1/attendance/me`

```json
{ "user_id": "…", "state": "CHECKED_IN",
  "day": { "date": "2026-08-17", "status": "CHECKED_IN",
           "sessions": [{"check_in": "2026-08-17T09:00:00Z", "check_out": null,
                         "check_in_event_id": "…", "check_out_event_id": null}],
           "first_check_in": "2026-08-17T09:00:00Z", "last_check_out": null } }
```

`GET /api/v1/attendance/me/history?from_date=2026-08-15&to_date=2026-08-17`

```json
{ "user_id": "…", "from_date": "2026-08-15", "to_date": "2026-08-17",
  "items": [ { "date": "2026-08-17", "status": "COMPLETED", "sessions": [ … ] },
             { "date": "2026-08-16", "status": "NO_RECORD", "sessions": [] },
             { "date": "2026-08-15", "status": "COMPLETED", "sessions": [ … ] } ],
  "pagination": {"page": 1, "page_size": 30, "total": 3, "total_pages": 1} }
```

`GET /api/v1/attendance/team/today`

```json
{ "date": "2026-08-17",
  "summary": {"total_staff": 4, "no_record": 2, "checked_in": 1, "completed": 1},
  "employees": [
    {"user_id": "…", "name": "Rahul Sharma", "employee_code": "EMP-1",
     "status": "COMPLETED", "check_in": "…", "check_out": "…", "sessions": [ … ]},
    {"user_id": "…", "name": "Arun Das", "employee_code": "ADM-1",
     "status": "NO_RECORD", "check_in": null, "check_out": null, "sessions": []}] }
```

`GET /api/v1/attendance/users/{user_id}` returns the same shape as
`/attendance/me`, for one user in the caller's own tenant.

### Not in Phase 5

Read-only means read-only: no editing, no deletion, no manual correction, no
admin check-in. Also absent — working hours, overtime, late arrival, absence
trends or any other analytics; CSV/Excel/PDF export; leave, holidays and
weekends; shifts and grace periods; and any frontend. Attendance events remain
immutable audit records.

## 8e. User, tenant and account management (Phase 6)

Phases 1–5 assumed the people using Karya already existed. Phase 6 is how they
get created, managed and retired — and it adds **no tables and no migration**.

### Endpoints and who may call them

| Method | Path | STAFF | MANAGER | TENANT_ADMIN |
| --- | --- | :-: | :-: | :-: |
| `GET` | `/api/v1/users/me` | ✅ | ✅ | ✅ |
| `PATCH` | `/api/v1/users/me` | ✅ | ✅ | ✅ |
| `POST` | `/api/v1/users/me/password` | ✅ | ✅ | ✅ |
| `GET` | `/api/v1/tenant/me` | ✅ | ✅ | ✅ |
| `PATCH` | `/api/v1/tenant/me` | 403 | 403 | ✅ |
| `POST` | `/api/v1/users` | 403 | 403 | ✅ |
| `GET` | `/api/v1/users` | 403 | 403 | ✅ |
| `GET` | `/api/v1/users/{user_id}` | 403 | 403 | ✅ |
| `PATCH` | `/api/v1/users/{user_id}` | 403 | 403 | ✅ |
| `PATCH` | `/api/v1/users/{user_id}/role` | 403 | 403 | ✅ |
| `POST` | `/api/v1/users/{user_id}/activate` | 403 | 403 | ✅ |
| `POST` | `/api/v1/users/{user_id}/deactivate` | 403 | 403 | ✅ |
| `GET` | `/api/v1/users/{user_id}/audit` | 403 | 403 | ✅ |

**MANAGER deliberately gets no user-management powers.** Managers see attendance;
tenant admins own identity and lifecycle. That separation matters because manager
accounts are handed out far more freely — a manager who could create logins or
change roles would widen the blast radius of one compromised account to the whole
tenant. `SUPER_ADMIN` is not granted anything here either: it is a platform role,
and Karya's administration is tenant-scoped.

### User lifecycle

```
            ┌──────────── created by TENANT_ADMIN ─────────────┐
            ▼                                                  │
        ACTIVE  ──── deactivate ────►  INACTIVE ──── activate ──┘
            │                             │
   can log in, refresh,          cannot log in, refresh,
   check in / check out          check in or check out
            │                             │
            └───── attendance history and audit trail persist ──┘
```

**Nothing is ever deleted.** Karya is an attendance and audit system: a deleted
identity would leave historical events pointing at nobody. There is no `DELETE`
route anywhere in the API, and a test asserts that.

Deactivation takes effect immediately — the authentication dependency re-reads
`users.status` on every request, so an unexpired access token stops working at
once — and **revokes every refresh session**, so a 30-day refresh token cannot
outlive the access it represents. Reactivation restores the ability to
authenticate and deliberately **does not** touch the password: silently clearing a
credential would lock the person out rather than help them.

### Roles

Assignable within a tenant: `TENANT_ADMIN`, `MANAGER`, `STAFF`. `SUPER_ADMIN` is
rejected with a 422 — tenant administration must not be a route to platform
access.

Role changes live on their own endpoint rather than in the generic profile update,
so a privilege change is never indistinguishable from a typo correction in the
audit trail. Two rules apply:

- **Nobody changes their own role**, including a tenant admin. That closes the
  most direct escalation path: the one role permitted to edit roles could
  otherwise edit its own.
- **A tenant never loses its last active administrator** — see below.

### Last-admin protection

Before demoting or deactivating a `TENANT_ADMIN`, the operation verifies another
active one exists. A tenant that loses its final administrator cannot manage its
own users again without operator intervention.

This is concurrency-safe, which a `SELECT COUNT(*)` would not be: two
simultaneous demotions would both observe "there are two admins" and both
proceed, leaving zero. Instead a single statement locks the tenant's active admin
rows **and** the target row `FOR UPDATE`, ordered by id so no two transactions
can deadlock. The second transaction blocks, then re-evaluates against committed
state, sees the admin the first one removed, and refuses with a 409.

A test forces that interleaving; a companion test asserts the naive
count-then-update version *does* leave the tenant with zero admins under the same
harness, so the guarantee cannot quietly become untested.

### Password security

Argon2id throughout, reusing the Phase 2 hashing utility — no second algorithm was
introduced. Passwords are never logged, never returned in a response and never
written to an audit row.

**Policy:** 8–128 characters, length only. No composition rules, following NIST
SP 800-63B: requiring an upper-case letter and a digit pushes people towards
predictable substitutions without adding real entropy. A new password must also
differ from the current one and must not be the account's own email or employee
code. The bounds now live in `app/schemas/fields.py` so login and user management
cannot drift apart.

`POST /users/me/password` verifies the current password **before** looking at the
new one, so a caller who has not proven ownership gets no feedback about the new
value. A wrong current password is a generic `401 Invalid credentials`. The
current-password field is only required to be non-empty — applying the length
policy to it would let a short guess return 422 instead of 401, distinguishing
"malformed" from "wrong". On success **every refresh session is revoked**: a
changed password usually means the old one is suspect.

### Email normalisation

Emails are trimmed and lower-cased on the way in — for login as well as user
management. `users` enforces `UNIQUE(tenant_id, email)` on the *stored* value,
which PostgreSQL compares case-sensitively, so without this `Rahul@acme.com` and
`rahul@acme.com` would be two accounts in one tenant and the casing someone typed
would decide whether they got in.

Normalising every write makes that constraint effectively case-insensitive with
**no migration**: if every stored value is lower-case, uniqueness of the stored
value *is* uniqueness of the address. (Verified safe: the database contained no
mixed-case addresses.) Uniqueness stays **per tenant** — the same person may hold
an account in two tenants.

### Tenant isolation

`tenant_id` is a required argument on every service function and always comes from
`current_user.tenant_id`. It appears in no request schema, so sending one is a
422. A grep across the API layer confirms all nine call sites read it from the
authenticated user and none from a request.

**Cross-tenant operations return 404**, byte-identical to an id that exists
nowhere — for read, update, role change, activate, deactivate and audit alike.
Distinguishing them would confirm the id is real and enable tenant enumeration.

### Duplicate handling

Uniqueness is the database's job. A `SELECT` first would still let two concurrent
creations both pass and both insert, so the `UNIQUE(tenant_id, email)` violation
is caught inside a `SAVEPOINT` and translated to a clean **409** — the client
never sees an `IntegrityError`, a constraint name or a table name. Five concurrent
creations of one email over HTTP produce exactly one 201 and four 409s.

### Search safety

The user search binds its term as a parameter *and* escapes `LIKE`
metacharacters. Unescaped, a search for `%` becomes the pattern `%%%` and returns
the entire tenant, and `_` silently means "any single character" — a search box
that leaks the whole user list. Escaped, the term matches what was typed.

### Audit

Every administrative mutation writes an audit row **in the same transaction** as
the change, so the two commit together or neither does: `USER_CREATED`,
`USER_UPDATED`, `USER_ROLE_CHANGED`, `USER_ACTIVATED`, `USER_DEACTIVATED`,
`PASSWORD_CHANGED`. The actor is always the authenticated caller; the target is
always the affected user. A failed creation leaves neither a user nor an audit row.

Metadata carries identifiers and before/after values only — for example
`{"old_role": "STAFF", "new_role": "MANAGER"}`. Never a password, hash, token or
nonce. `GET /users/{id}/audit` is scoped to the tenant, to `target_type='User'`
and to that user, so it is not a window onto the tenant's whole audit log.

### Deliberate limitations

- **No password reset by email**, because Karya has no email infrastructure. Doing
  it properly needs delivery, single-use expiring tokens, anti-enumeration and
  rate limiting; a half-built version would be worse than none. An administrator
  can currently only create an account *with* a password, which they must convey
  out of band.
- **No email invitations**, for the same reason.
- **No rate limiting** on login or password change. This is a **production
  deployment requirement**, not something Phase 6 fakes: it belongs at the edge
  (or with Redis, which arrives later) rather than as an in-process counter that
  resets on restart.
- **No tenant creation, suspension or deletion** — operator concerns, not
  self-service ones. `PATCH /tenant/me` changes only `name`; `slug` is excluded
  because it is the identifier every employee types at login, so renaming it would
  lock out the whole company at once.
- **Users cannot change their own email**; it is the login identity, and it
  belongs to tenant administration.

## 8f. Production hardening (Phase 7)

Phases 1–6 built the product. Phase 7 makes it safe to run, and **changes no
business behaviour**: no endpoint URL moved, no response shape changed, no rule
about attendance, presence, roles or tenancy was altered. The full-suite count went
from 443 to 659 tests, with no existing test rewritten except where Phase 7 fixed a
real defect (two, described below).

### The request pipeline

```
                    ┌────────────────────────────────────────────┐
  client  ───────►  │ SecurityHeadersMiddleware                  │  outermost
                    │  nosniff · Referrer-Policy · CSP           │
                    │  X-Frame-Options · Cache-Control · HSTS    │
                    ├────────────────────────────────────────────┤
                    │ RequestContextMiddleware                   │
                    │  X-Request-ID in/out · access log          │
                    │  last-resort 500                           │
                    ├────────────────────────────────────────────┤
                    │ CORSMiddleware (only if origins configured)│
                    ├────────────────────────────────────────────┤
                    │ RequestLimitsMiddleware                    │
                    │  body <= 64 KiB · query <= 2 KiB           │
                    ├────────────────────────────────────────────┤
                    │ rate-limit dependency -> auth -> schema    │
                    │ -> route -> service -> PostgreSQL          │  innermost
                    └────────────────────────────────────────────┘
```

The order is load-bearing, not incidental:

- **Security headers outermost**, so *every* response carries them — including the
  413 the size limiter generates and the 500 the context middleware generates. One
  layer lower would miss both.
- **Correlation id outside CORS**, so a rejected preflight is still logged and still
  traceable.
- **CORS outside the size limits**, so a 413 still carries CORS headers and a
  browser reports the real status instead of an opaque CORS failure.
- **Size limits still ahead of routing**, so an oversized body is refused before it
  is buffered or JSON-decoded.

All four are plain ASGI middleware rather than `BaseHTTPMiddleware`, which runs the
downstream app in a separate task connected by a queue — an extra task switch per
request, plus known trouble with streaming and background tasks, for behaviour these
do not need.

### Two real defects this phase found and fixed

**1. The 422 body echoed the submitted password.** FastAPI's default validation
handler includes Pydantic's `input` field, which is the offending value:

```
POST /api/v1/auth/login   {"password": "hunter2", ...}
-> 422 {"detail":[{"type":"too_short", ..., "input":"hunter2"}]}
```

That is a credential in a response body, and from there in browser consoles,
client-side error reporting, and any proxy that logs bodies. `app/api/errors.py` now
builds the response from an **allowlist** of `{type, loc, msg}`, so a future Pydantic
error field cannot leak by default either. The client still learns exactly what to
fix: `loc` names the field and `msg` states the rule.

**2. A check-out could be stamped before the check-in it followed.**
`attendance_events.event_timestamp` defaulted to `now()`, which in PostgreSQL is the
**transaction start** time, not the moment of insertion. Under lock contention:

```
t=0.00  transaction B begins                    (B's now() is fixed here)
t=0.50  transaction A begins, locks the user row,
        inserts CHECK_IN stamped 0.50, commits
t=0.51  B finally gets the lock, correctly sees CHECKED_IN,
        inserts a valid CHECK_OUT — stamped 0.00
```

Ordering by `event_timestamp` then reports `[CHECK_OUT, CHECK_IN]`, so the derived
state is `CHECKED_IN` for someone who has checked out: they show as present on the
team dashboard and the day's sessions mis-pair. Reproduced against PostgreSQL 18.4
with a 0.536 s inversion before the fix.

The Phase 4 row lock serialises the *decision* correctly; it cannot serialise a
timestamp that was fixed before the lock was taken. Migration `127b35de9c9f` changes
the default to **`clock_timestamp()`**, which reads the wall clock at insertion, so
stored order always matches commit order. That is the phase's only migration, it
touches one column default, and it is reversible.

It also removed a second symptom: `now()` is constant *within* a transaction, so two
events written in one transaction shared a timestamp and the "latest event" query
broke the tie arbitrarily — differently depending on whether the planner chose a
sequential or an index scan, which is why this surfaced as an order-dependent test
failure rather than a consistent one.

`test_attendance_concurrency.py` now carries the regression test **and** its guard, in
the house style: a companion test stamps events with `now()` explicitly under the
identical interleaving and asserts the pair *does* invert, so the guarantee cannot
quietly become untested.

### Configuration

`ENVIRONMENT` is a closed set — `local`, `test`, `staging`, `production` — so a typo
like `prod` fails at startup rather than behaving like development. Production
additionally refuses to boot on a development-shaped configuration: `DEBUG=true`, a
placeholder secret or database password, or a non-`https://` CORS origin. Every
operational limit (pool sizes, timeouts, body caps, rate budgets) is validated in
every environment, because a zero in any of them silently disables a protection.

### Security headers

| Header | Why |
| --- | --- |
| `X-Content-Type-Options: nosniff` | A JSON body containing attacker-influenced text must never be sniffed as HTML and executed |
| `Referrer-Policy: no-referrer` | Karya URLs contain user and tenant UUIDs, which a `Referer` would leak to the next site visited |
| `X-Frame-Options: DENY` + `frame-ancestors 'none'` | `/docs` is a real HTML page and a clickjacking surface; both are sent because one is the modern control and one is what older browsers honour |
| `Content-Security-Policy` | Makes "this response is data" browser-enforced: `default-src 'none'` |
| `Cache-Control: no-store` | Every response is authenticated data or an error; neither belongs in a shared cache or on a laptop disk |
| `Strict-Transport-Security` | Production only. Meaningless without HTTPS, and actively harmful on `localhost`, where it would pin the whole browser profile to a scheme that host cannot serve |

Deliberately **not** set: `X-XSS-Protection` (removed from every current browser, and
it introduced vulnerabilities of its own), the `Cross-Origin-*` isolation headers
(they govern document contexts, which an API has none of), and `Permissions-Policy`
(it constrains browser features a JSON response cannot use).

`/docs` and `/redoc` get a **separate, looser CSP** — Swagger UI loads its script from
a CDN, applies inline styles, and mounts itself via a second, inline script FastAPI's
default docs HTML embeds directly, so the strict policy would render a blank page (the
CDN script loads, but the inline one that actually renders the UI into the page gets
silently blocked without `'unsafe-inline'` on `script-src` too). Both relaxations are
scoped to exactly those paths, so they cost nothing on any route that carries data.
`DOCS_ENABLED=false` turns the docs page and the schema off together, since they are
one decision.

### Rate limiting, and what it honestly protects

An in-memory fixed-window counter, per process. Stated plainly, because it decides
what the thing is worth:

- ✅ Stops one client brute-forcing or flooding **one instance**, and stops a mobile
  client stuck in a retry loop.
- ❌ **Not** shared across instances — with N replicas an attacker effectively gets N
  times the budget. Counters are also lost on restart, and a fixed window admits up
  to twice the limit across a boundary.

So a multi-instance deployment needs an edge limiter as well. The seam for replacing
it is deliberate: routes only ever declare *which* limit applies
(`dependencies=[LOGIN_RATE_LIMIT]`), and the three-method `RateLimiter` protocol
(`consume`, `peek`, `clear`) was chosen to map onto Redis `INCR`+`EXPIRE`, `GET` and
`DEL`. A Redis backend is a second class plus one line in `get_rate_limiter()` — no
route, schema or handler change.

Login gets **two** limits, because they bound different things. Per address (20/min)
bounds request volume; per `(tenant, email)` (10 failures / 15 min) bounds *guessing*,
which addresses are too cheap to bound. Only failures count and a success clears the
counter, so mistyping a password twice leaves no trace. The identifier is stored as a
SHA-256 digest, never the address itself, so the limiter's keyspace is not a list of
who has been trying to log in.

| Endpoint | Key | Budget |
| --- | --- | --- |
| `POST /auth/login` | client address | 20 / min |
| `POST /auth/login` (failures only) | `(tenant, email)` digest | 10 / 15 min |
| `POST /auth/refresh`, `POST /auth/logout` | client address | 60 / min |
| `POST /users/me/password` | user | 5 / 15 min |
| `POST /presence/qr/challenge` | user | 60 / min |
| `POST /presence/verify` | user | 30 / min |
| `POST /attendance/check-in`, `/check-out` | user | 20 / min |
| Tenant-admin mutations, `PATCH /tenant/me` | user | 120 / min |

Budgets are set so a real person never meets one: someone checks in twice a day
against 20/min, and the office QR display refreshes about twice a minute against
60/min. A test walks a full working day — login, presence check, check in, out for
lunch, back in, out for the day, each with its own fresh QR, plus ten dashboard
reads — and asserts nothing is throttled.

Read endpoints are **not** limited. They are already bounded by pagination and range
caps, and throttling a dashboard a manager refreshes would be user-visible for no
security gain.

A 429 carries `Retry-After` and a body of exactly `{"detail": "Too many requests"}` —
no remaining count and no rule name, which would tell a script how to pace itself.
Throttling is byte-identical for accounts that exist and accounts that do not, so the
Phase 2 anti-enumeration property holds for 429 as well as for 401.

### Error handling

Every error is still `{"detail": ...}` — unchanged from Phases 1–6, which several
existing tests assert byte-for-byte. The correlation id therefore lives in the
`X-Request-ID` **header**, not in the body: that keeps the envelope identical for two
callers hitting the same error, so a cross-tenant 404 stays indistinguishable from a
fictional one.

An unhandled exception returns `500 {"detail": "Internal server error"}` and the
traceback goes only to the log. It is caught in the correlation middleware rather than
by a handler on Starlette's `ServerErrorMiddleware`, which sits *outside* every
application middleware — a response produced there would carry no correlation id, no
security headers and no access-log line, which is precisely the case an operator most
needs to trace. A `SQLAlchemyError` is likewise a generic 500: its string form can
carry the statement, the table and constraint names, and for some drivers the bound
parameters.

### Structured logging

One JSON object per line on stderr (`LOG_FORMAT=console` for a terminal). Every record
inside a request carries `request_id`; the access line adds `method`, `path`, `route`,
`status_code`, `duration_ms`, `client_ip` and — once authentication has resolved —
`user_id` and `tenant_id`.

- **`route`, not just `path`.** The template (`/attendance/users/{user_id}`) is what
  makes "how slow is this endpoint" answerable; the expanded path alone would put a
  distinct value on every line.
- **The query string is never logged.** `?search=<someone's name>` is user input, and
  a log line may be retained for months.
- **Never logged at all:** passwords, password hashes, access tokens, refresh tokens,
  QR nonces, `Authorization` headers, request bodies. A failed login records the
  *tenant slug* — public, and what an operator correlates by — and not the email,
  because a log of attempted addresses is a list of accounts worth attacking.
- **Key-based redaction as a net**, not as the plan: any field whose name suggests a
  credential is replaced before serialisation, so one careless `extra=` in a future
  phase cannot leak.
- 4xx logs at WARNING and 5xx at ERROR, so an alert on ERROR fires for defects and not
  for a mistyped password.

An inbound `X-Request-ID` is honoured only if it matches `[A-Za-z0-9._-]{1,64}`;
anything else is replaced with a generated id rather than failing the request. Without
that check a caller could embed newlines and forge whole log entries.

`alembic/env.py` gained `disable_existing_loggers=False`, which is load-bearing rather
than tidy: `fileConfig` defaults to `True` and would disable every logger that already
existed — including all of Karya's — in any process that runs Alembic in-process. The
test suite does exactly that, which is how this was found.

### Liveness and readiness

| Endpoint | Checks | For |
| --- | --- | --- |
| `GET /health` | nothing external; always 200 while the process runs | **liveness** — restarts |
| `GET /ready` | `SELECT 1` against PostgreSQL; 200 or 503 | **readiness** — load-balancer rotation |

The split is the point. An orchestrator *kills* what fails liveness, so if liveness
touched PostgreSQL a database blip would restart every healthy API process — turning a
recoverable dependency failure into an outage, with a restart storm on top, exactly
when the database can least afford it. Readiness merely removes an instance from
rotation. Both are unauthenticated and return a fixed one-word payload: no version,
hostname, driver, timing or error detail.

They sit **outside** `/api/v1`, because they describe the process rather than the API
contract, so a future `/api/v2` must not move them.

### Database connections

`DB_POOL_SIZE` (5) + `DB_MAX_OVERFLOW` (10) per process, with `pool_pre_ping` and a
30-minute recycle — both defending against the same failure, a connection that looks
open and is not. `docs/PRODUCTION.md` works through sizing against PostgreSQL's
`max_connections`; the short version is that a bigger pool does not make a saturated
database faster, it just moves the queue somewhere less visible.

Two server-side ceilings are applied per connection: `statement_timeout` (15 s) bounds
a runaway query, and `lock_timeout` (5 s) bounds the `FOR UPDATE` waits the attendance
and last-admin paths rely on. The expected wait there is milliseconds, so 5 s only
fires when a transaction is genuinely stuck — and then it fails one request instead of
holding a pool slot until the pool is exhausted and *every* request fails.

`hide_parameters=True` is a requirement rather than a preference: a `users` INSERT
binds `password_hash` as a parameter, and SQLAlchemy renders bound parameters into
exception messages, which reach log files.

`get_db` now rolls back explicitly on exception. `close()` happens to roll back too,
but explicitness matters here — a request that raises mid-transaction must not return
its connection to the pool with uncommitted work for the next request to inherit.

### Graceful shutdown

Four lines, because there is nothing else to stop: Karya runs no background tasks,
timers or workers. Uvicorn stops accepting connections and drains in-flight requests
within `--timeout-graceful-shutdown`, then the lifespan handler disposes the
connection pool. Startup deliberately does **not** touch the database — a container
that refuses to start cannot report anything, whereas one that starts and reports
itself unready can.

### Container

Multi-stage `python:3.12-slim-bookworm`: the runtime stage carries no compiler, no pip
cache and no build metadata. It runs as a non-root user (uid 10001) that only *reads*
its own code, so a compromised process cannot rewrite its source. Dependencies come
from `constraints.txt`, a pinned closure produced by resolving the runtime
dependencies in a clean virtualenv — `pyproject.toml`'s ranges are right for a library
and wrong for a deployment.

The `HEALTHCHECK` hits liveness, not readiness, for the reason above. The `CMD` is
exec-form so uvicorn is PID 1 and receives `SIGTERM` directly, and it deliberately
**omits** `--proxy-headers` / `--forwarded-allow-ips`: those make uvicorn rewrite the
client address from `X-Forwarded-For`, which the per-address rate limits key on, so
trusting that header from any peer would let any client spoof its address. A deployment
behind a load balancer must add both, naming the balancer.

Compose still starts PostgreSQL and nothing else; the API is behind a profile
(`docker compose --profile api up -d --build`), so the existing development workflow is
untouched. Compose is not production orchestration and does not pretend to be.

### Frontend readiness (for Phase 8)

Reviewed from a consumer's perspective, with no endpoint redesigned for aesthetics.
What a client can rely on: every error is `{"detail": ...}`; validation failures are
422 with `{type, loc, msg}` and never echo the submitted value; a 429 carries
`Retry-After`; every response carries `X-Request-ID`, exposed through CORS so a browser
can read it and report it; business refusals stay **200** with `success: false` /
`verified: false` plus a machine-readable `reason`; no identity field is ever accepted
from the client; and `/openapi.json` documents authentication, roles, statuses and
pagination across all 24 paths.

## 9. Current database entities

Seven tables — the six Phase 1 entities plus one for Phase 2:

| Table                  | Purpose                                             |
| ---------------------- | --------------------------------------------------- |
| `tenants`              | One customer company                                |
| `users`                | A person within a tenant                            |
| `attendance_locations` | The tenant's single attendance site (V1)             |
| `qr_challenges`        | Short-lived, one-time-use QR nonces                 |
| `attendance_events`    | **Source of truth** for attendance                  |
| `audit_logs`           | Append-only trail of privileged actions             |
| `refresh_tokens`       | Hashed refresh tokens (authentication state)         |

### Relationships

```
Tenant ─┬─< User ─┬─< AttendanceEvent
        │         ├─< AuditLog          (as actor)
        │         └─< RefreshToken
        ├─< AttendanceLocation ─< QRChallenge
        ├─< AttendanceEvent
        ├─< QRChallenge
        ├─< AuditLog
        └─< RefreshToken
```

### Deletion policy

`cascade="all, delete-orphan"` is used **nowhere**. Deletion is governed by
foreign keys, chosen per relationship:

| Foreign key                          | `ON DELETE` | Why                                       |
| ------------------------------------ | ----------- | ----------------------------------------- |
| `users.tenant_id`                    | `RESTRICT`  | never lose staff records silently          |
| `attendance_locations.tenant_id`     | `RESTRICT`  | site config is business data                |
| `attendance_events.tenant_id`        | `RESTRICT`  | source of truth — must not vanish           |
| `attendance_events.user_id`          | `RESTRICT`  | as above                                   |
| `qr_challenges.tenant_id`            | `CASCADE`   | disposable, short-lived artefact            |
| `qr_challenges.location_id`          | `CASCADE`   | as above                                   |
| `audit_logs.tenant_id`               | `SET NULL`  | the trail must outlive its subject          |
| `audit_logs.actor_user_id`           | `SET NULL`  | as above                                   |
| `refresh_tokens.user_id`             | `CASCADE`   | a session is not history; drop it with the user |
| `refresh_tokens.tenant_id`           | `CASCADE`   | as above                                   |

### Conventions

- **UUID primary keys** everywhere; no auto-increment integers. Generated by
  the application (`uuid.uuid4`), with `gen_random_uuid()` as a server default
  so raw SQL inserts are also safe.
- **All timestamps are `TIMESTAMPTZ`**, stored in UTC. No naive timestamps
  exist; a test asserts this against `information_schema`.
- `attendance_events.event_timestamp` is **server-generated** (`now()`). The
  client is never trusted for the authoritative attendance time.
- `verification_metadata` and `audit_logs.metadata` are **JSONB** and remain
  intentionally schema-less, so new verification signals need no migration.
- Passwords exist only as `users.password_hash`, holding an Argon2id PHC string.
  There is no plain-text password column, and a test enforces that.
- Refresh tokens exist only as `refresh_tokens.token_hash` (SHA-256 hex). A test
  asserts the table has no column that could hold a usable raw token.
- On `AuditLog` the Python attribute is `log_metadata` because `metadata` is
  reserved by SQLAlchemy's declarative API; the **column** is still `metadata`.

### Tenant isolation

Every tenant-owned table carries `tenant_id`. As of Phase 2 this is enforced at
runtime as well as in the schema — see
[§8a — Tenant isolation model](#tenant-isolation-model).

## 10. What is intentionally NOT implemented yet

**Delivered in Phase 7:** rate limiting (in-process; see §8f for what that does
and does not protect), security headers, CORS verification, request size limits,
structured logging, correlation ids, readiness probe, pool and timeout management,
graceful shutdown, a production container image, and production configuration
fail-fast.

**Still not implemented, and now scheduled after the frontend:** attendance reports ·
CSV / Excel / PDF export · hours, overtime, late-arrival and absence analytics ·
overnight-shift rules · leave, holidays and weekends · admin check-in/out,
correction, approval or deletion · per-tenant timezones · password reset by email ·
email invitations.

**Explicitly out of scope for Phase 7, and documented rather than half-built:** a
distributed (Redis) rate limiter · a `/metrics` endpoint, Prometheus exposition or
tracing · automated database backups and point-in-time recovery · Kubernetes / ECS
manifests · a `refresh_tokens` cleanup sweeper · supply-chain hash pinning. Each is
stated with its consequences in
[`docs/PRODUCTION.md`](docs/PRODUCTION.md) — §12 lists every known residual risk.

**Deliberately not implemented in Phase 3:** Wi-Fi verification (specified as
optional) · device fingerprinting / attestation · face recognition · the office
display frontend · rate limiting (endpoints are structured so it can be added;
Redis arrives with it) · a public QR-revocation endpoint (revocation exists at
service level only, so there is no route to abuse).

**Deferred to later phases:** registration · password reset · user-management
and tenant-management APIs · super-admin endpoints · role-management API ·
notifications · React frontend · PWA · admin & staff dashboards · reports ·
analytics · multiple attendance locations per tenant · payroll · leave
management · shift management · Redis · background workers.

Also deliberately absent: any access-token blacklist. Access tokens are
short-lived by design and the database is re-read on every request, so a
deactivation or role change takes effect on the *next* call; revocation lives at the
refresh-token layer. `app/security/` is still not needed — password and token logic
lives under `app/services/auth/`. `app/middleware/` now exists, because Phase 7
genuinely needed it (see §8f).

## 11. Operations

The full operational reference is [`docs/PRODUCTION.md`](docs/PRODUCTION.md). The
short version:

### Health and readiness

```bash
curl -fsS http://host:8000/health   # liveness  — restart on failure
curl -fsS http://host:8000/ready    # readiness — remove from rotation on failure
```

Point liveness at `/health` and readiness at `/ready`, never the reverse: `/health`
never queries the database precisely so that a database blip cannot make an
orchestrator restart every healthy process.

### Production configuration

Set `ENVIRONMENT=production` and the application enforces the rest — it refuses to
start without a real `JWT_SECRET_KEY`, with `DEBUG=true`, with a placeholder
database password, or with a non-`https://` CORS origin. `.env.example` annotates
every variable; `docs/PRODUCTION.md` §2 lists the required ones.

### Security considerations

- **HTTPS is mandatory** — bearer tokens on every request, passwords on two
  endpoints.
- Behind a load balancer, run uvicorn with
  `--proxy-headers --forwarded-allow-ips=<proxy address>`. Omit it and every client
  shares one rate-limit budget; use a wildcard and any client can spoof its address.
  Name the proxy.
- The in-process rate limiter is **per process**. A multi-instance deployment needs
  an edge limiter too.
- Never ship `.env`; use the platform's secret store. Nothing sensitive is baked
  into the image.
- Set a retention period for access logs — they carry `client_ip`, `user_id` and
  `tenant_id`.

### Deployment prerequisites

PostgreSQL 13+ (18 recommended) with automated backups · a TLS-terminating proxy ·
a secret store · log aggregation · `alembic upgrade head` as a one-off step **before**
the new version serves traffic. The checklist is `docs/PRODUCTION.md` §11.

### Backup and recovery

**Not implemented by Karya, and required before production.** Attendance events are
the source of truth and are immutable, so losing them cannot be repaired by
recomputation. Minimum: nightly `pg_dump --format=custom`, off-host, encrypted,
with tiered retention. Preferred: continuous WAL archiving for point-in-time
recovery, because the realistic disaster is an accidental bulk change rather than a
disk failure. **Test the restore on a schedule** — an untested backup is a
hypothesis. Details and the verification steps are in `docs/PRODUCTION.md` §9.

### Monitoring

Structured JSON logs on stderr are the interface; there is no `/metrics` endpoint
and no tracing yet. Alert on `event=unhandled_exception` and on 5xx (both should be
zero), watch `duration_ms` percentiles grouped by `route`, and watch the rates of
`login_failed`, `login_throttled` and `rate_limited`.

## Project layout

```
backend/
├── app/
│   ├── main.py                  # create_app(): middleware order, routers, lifespan
│   ├── core/
│   │   ├── config.py            # env-driven settings, SecretStr, production fail-fast
│   │   ├── context.py           # request-scoped contextvars + logging filter
│   │   ├── logging.py           # JSON/console formatters, key-based redaction
│   │   └── rate_limit.py        # RateLimiter protocol + in-memory fixed window
│   ├── middleware/
│   │   ├── security_headers.py  # hardening headers; docs CSP exception
│   │   ├── request_context.py   # correlation id, access log, last-resort 500
│   │   └── request_limits.py    # body and query size caps
│   ├── api/
│   │   ├── deps.py              # get_current_user, tenant context, require_roles
│   │   ├── errors.py            # exception handlers; 422 never echoes input
│   │   ├── limits.py            # rate-limit dependencies (the only wiring routes see)
│   │   ├── probes.py            # GET /health, GET /ready
│   │   └── v1/
│   │       ├── router.py        # aggregates v1 routers; owns API_V1_PREFIX
│   │       ├── auth.py          # login / refresh / logout / me
│   │       ├── presence.py      # qr/challenge / verify
│   │       ├── attendance.py    # check-in / check-out / reads
│   │       ├── users.py         # user management + self-service
│   │       └── tenant.py        # tenant profile
│   ├── db/
│   │   ├── base.py              # DeclarativeBase, naming convention, mixins
│   │   ├── session.py           # engine + session factory + get_db()
│   │   └── tenant_scope.py      # tenant-scoped query helpers
│   ├── models/                  # the seven entities
│   ├── schemas/                 # auth.py, user.py, presence.py (API contract)
│   └── services/
│       ├── auth/
│       │   ├── password.py      # Argon2id only
│       │   ├── jwt.py           # access-token mint/verify only
│       │   ├── refresh_tokens.py# the refresh-token store only
│       │   └── service.py       # login / refresh / logout flows
│       ├── presence/
│       │   ├── results.py       # shared enums + result dataclasses
│       │   ├── gps.py           # validation, haversine, geofence
│       │   ├── qr.py            # challenge lifecycle, atomic consume
│       │   └── service.py       # combines both signals, audit logging
│       ├── attendance/
│       │   ├── results.py       # state machine enums, outcome, read models
│       │   ├── service.py       # check-in/out, row lock, audit logging
│       │   └── queries.py       # read-only history / daily / team views
│       └── users/
│           ├── errors.py        # domain errors, mapped to codes by the API
│           └── service.py       # lifecycle, roles, password, last-admin lock
├── alembic/                     # env.py, script.py.mako, versions/ (4 revisions)
├── tests/                       # conftest + 24 test modules
├── docs/PRODUCTION.md           # deployment, secrets, backups, residual risks
├── alembic.ini
├── Dockerfile                   # multi-stage, non-root, healthcheck
├── .dockerignore
├── constraints.txt              # pinned runtime closure for reproducible builds
├── docker-compose.yml           # postgres always; api behind the "api" profile
├── pyproject.toml
└── .env.example
```

Business logic lives in `services/`, not in route handlers or ORM models.
