---
name: verify
description: Build, run and drive the Karya backend to observe changes at the HTTP surface. Use when verifying backend changes end to end.
---

# Verifying the Karya backend

The surface is **HTTP**. Drive `uvicorn` over a socket; don't import `app.*` to
check behaviour. (Importing `app.*` is fine for *seeding* — see below.)

## Handle

```powershell
# from the repo's backend/ directory
# venv setup (once): python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\alembic.exe current      # expect head
$p = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8040" `
  -PassThru -WindowStyle Hidden
# poll http://127.0.0.1:8040/health until 200, then drive
Stop-Process -Id $p.Id -Force
```

Use a port in the 804x range; the app itself has no default port. Any setting can
be overridden per-process with an env var before `Start-Process`, e.g.
`$env:QR_CHALLENGE_TTL_SECONDS = "3"` to watch a QR lapse on the real clock
in seconds instead of 30. That also proves the setting is genuinely wired.

**Capture stderr to a file.** Phase 7's logs are one JSON object per line and are
half the evidence — the privacy sweep and the access-log assertions both read
them. Redirect with `-RedirectStandardError` (PowerShell) or `2>` (bash).

## Seeding

**There is no registration endpoint by design**, so users cannot be created over
HTTP. Seed through the DB with the app's own services (this is setup, not
verification), then drive everything else over the socket:

```python
from app.services.auth.password import hash_password   # needed for a usable login
# Tenant -> AttendanceLocation -> User(role=...)   then commit
```

Teardown order matters — `users.tenant_id` and `attendance_locations.tenant_id`
are `ON DELETE RESTRICT`:

```
qr_challenges, audit_logs, refresh_tokens, attendance_events
  -> attendance_locations -> users -> tenants
```

Always tear down: the dev DB (`karya`) is not transactional per-run like the test
DB. Confirm `attendance_events` is still 0 afterwards.

## Flows worth driving

| Area | Sequence |
| --- | --- |
| Boot | `GET /health` (never queries the DB), `GET /ready` (200/503), `GET /openapi.json` (24 paths as of Phase 7 — print them, don't assert a count), `GET /docs` |
| Auth | login → `/auth/me` → refresh (rotate) → replay old refresh (401) → logout → refresh (401) |
| Enumeration | wrong password / unknown tenant / right user+wrong tenant must return byte-identical 401 |
| QR issuance | STAFF 403, MANAGER 201, TENANT_ADMIN 201, SUPER_ADMIN 403 (no hierarchy) |
| Presence | valid → `PRESENCE_VERIFIED`; replay → `QR_ALREADY_USED`; 350 m → `OUTSIDE_GEOFENCE`; then reuse that same QR from inside — **it must still work** (a failed attempt must not burn it) |
| Cross-tenant | tenant A submits tenant B's challenge → `QR_NOT_FOUND`, and B's challenge must still be usable by B |
| Spoofing | `gps_verified` / `qr_verified` / `presence_verified` / `distance_meters` / `tenant_id` / `user_id` in the body → 422 |
| DB authority | flip `users.status`/`role` from a second process; the *same unexpired token* must change behaviour on the next request |
| Attendance | check-in → duplicate check-in (`ALREADY_CHECKED_IN`) → check-out → duplicate check-out (`NOT_CHECKED_IN`) → check-in again; each success needs its **own fresh QR** |
| Attendance races | fire N simultaneous check-ins (each with its own challenge) → exactly one succeeds, the rest `ALREADY_CHECKED_IN`; same for check-out |
| Attendance reads | `/attendance/me`, `/me/history`, `/team/today`, `/users/{id}`, `/users/{id}/history`; STAFF gets 403 on the last three; cross-tenant ids give **404 identical to a random UUID** |
| Read-only proof | snapshot `count(*)` **and** a content hash of `attendance_events`, issue many GETs, re-check — catches UPDATEs a count alone would miss |
| User mgmt | create → login as the new user → promote → deactivate → reactivate → audit; STAFF **and MANAGER** get 403 on every admin route (managers have no user-management powers by design) |
| Credential cut-off | after deactivate *and* after a password change, the victim's **unexpired refresh token** must 401 too, not just their access token and login |
| Field smuggling | `role` / `status` / `password_hash` / `tenant_id` / `created_at` on `PATCH /users/{id}` or `/users/me` → 422; role and status have their own endpoints |
| Headers (P7) | read them from the raw response: `nosniff`, `no-referrer`, `DENY`, `no-store`, strict CSP. No HSTS locally. `/docs` must get the *relaxed* CSP and still render Swagger |
| Request id (P7) | generated when absent (32 hex), different every request, a safe inbound value honoured, a hostile one replaced, present on a 401 and on a 413 |
| Limits (P7) | 70 KB body → 413; 3 KB query → 414; both still carry the security headers and a request id |
| Error hygiene (P7) | `password` of 7 chars → 422 whose body does **not** contain it, and whose entries carry only `type`/`loc`/`msg` |
| Rate limits (P7) | hammer login → run of 401s then a run of 429s, `Retry-After` positive, body exactly `{"detail":"Too many requests"}`; an already-authenticated user unaffected |
| CORS (P7) | the configured origin echoed exactly (never `*`), `allow-credentials: true`, `X-Request-ID` in `expose-headers`; a foreign origin gets **no** `allow-origin` |
| Log sweep (P7) | every stderr line parses as JSON; no password, `$argon2`, `Bearer `, DB password, JWT secret, issued **QR nonce** or refresh-token hash appears; failed logins carry `tenant_slug` and **no email**; no access record contains a query string |

Attendance refusals are HTTP **200 with `success: false`** plus a `reason`, same
convention as presence. After a run, assert the per-user event sequence strictly
alternates CHECK_IN/CHECK_OUT, that every `event_timestamp` is **distinct**, and
that `USED` challenges are at least the number of attendance events (a consumed
challenge with no event would mean the transaction boundary leaked).

Geofence maths for building coordinates: `lat + meters / 111194.93` moves that
many metres north of `(12.9716, 77.5946)` with a 150 m radius.

## Verifying the container (Phase 7)

```bash
docker compose up -d                              # postgres only
docker compose --profile api up -d --build        # + the production image
docker inspect --format '{{.State.Health.Status}}' karya-api
```

Worth checking, because these are the properties the Dockerfile exists for:

- `docker exec karya-api id` → `uid=10001(karya)`, not root.
- `cat /proc/1/cmdline` → uvicorn *is* PID 1, so it gets SIGTERM directly.
- `touch /srv/karya/app/x.py` must be **refused** — root owns the code.
- No `.env`, no `gcc`, no `tests/`, no `pytest` in the image.
- `docker stop --timeout 40 karya-api` must exit **0 in well under 40 s**, and the
  logs must end `application_shutdown` → `database_pool_disposed`. A SIGKILL
  fallback would take the full timeout and skip both lines.

Then run the same HTTP driver against `:8000`. Migrations are a **deploy step**:
`docker compose --profile api run --rm api alembic upgrade head`.

## Gotchas

- **Port 5432 is the native `postgresql-x64-18` service**, not Docker. `docker
  compose up` binds only IPv6 and connections silently hit the native server.
  For the container, set `POSTGRES_PORT=5433`.
- **The `karya-postgres-data` volume outlives `docker compose down`**, and
  PostgreSQL only creates the role in `POSTGRES_USER` when it initialises an
  *empty* data directory. So changing `POSTGRES_USER`/`POSTGRES_PASSWORD` against
  an existing volume gives `password authentication failed`. Either match what the
  volume already has (`docker exec karya-postgres psql -U postgres -c "SELECT
  rolname FROM pg_roles"` to find out, then `ALTER USER ... PASSWORD` to set a
  known one) or `docker compose down -v` — which **destroys the data**.
- **`kill -TERM` from Git Bash is a hard terminate on Windows.** It does not run
  uvicorn's shutdown, so a local graceful-shutdown check proves nothing. Verify it
  with `docker stop` (a real SIGTERM to PID 1) or by exiting a `TestClient`
  context, which runs the ASGI lifespan.
- **`TIMESTAMPTZ` comes back as `+05:30` locally** (native PG uses the system
  zone) but `Z` under Docker. Same instant, two spellings — compare parsed
  datetimes, never string prefixes. This has bitten twice: `iso[11:16]` to read a
  clock time reads a *different* clock in the two environments. Parse and
  `.astimezone(UTC)` first.
- Same root cause on the server side: **never `date(event_timestamp)` or
  `::date`** in a query. The session TimeZone decides the answer, so days would
  bucket differently locally vs Docker. Filter on explicit UTC instants instead.
- **`now()` is the transaction start time, not "now".** Phase 7 found a real bug
  here: `event_timestamp DEFAULT now()` let a check-out committed *second* carry an
  *earlier* stamp than the check-in it followed, because its transaction began
  first and then blocked on the row lock. The column now defaults to
  `clock_timestamp()`. Two consequences for tests: bracket a server-generated
  instant with `clock_timestamp()` (a `now()` bracket cannot bound something that
  happens inside its own transaction), and never assume `now()` differs between two
  statements in one transaction — it does not.
- **Don't assert headers via `dict(response.headers)`** — that loses HTTP's
  case-insensitivity and made `www-authenticate: Bearer` look absent. Use the
  `HTTPMessage`/`httpx` mapping, or read the raw socket.
- **Writing `.env` from PowerShell 5.1**: `Set-Content -Encoding utf8` adds a BOM
  that corrupts the first key for docker-compose. Use
  `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`.
- **Concurrency can't be tested by starting N threads together** — each request
  is a sub-millisecond round trip and they serialise, so a knowingly broken
  implementation passes. Force the interleaving: transaction A acts and holds its
  transaction open, then B attempts the same thing and must block on the row
  lock. See `tests/test_presence_concurrency.py::interleave`. For *ordering*
  hazards the interleaving must be the other way round — B's transaction older
  than A's — see `interleave_with_older_second_transaction`.
- Pydantic lax mode coerces numeric **strings** (`"12.97"` is accepted for
  latitude). Out-of-range, `"nan"`, `"1e400"` and non-numeric strings still 422,
  so the bounds hold — don't mistake the coercion for a hole.
- Presence rejections are **200 with `verified: false`**, not 4xx. Only 401
  (unauthenticated), 413/414 (too large), 422 (malformed/smuggled) and 429
  (throttled) are error codes.
- **URL-encode query values in the driver.** A search term like `' OR 1=1 --`
  contains spaces, and `urllib` raises `InvalidURL` before the request is even
  sent — which looks like a server problem but is not. Use
  `urllib.parse.quote(term, safe='')`.
- **Not every response is JSON.** `/docs` is an HTML document, so a driver that
  unconditionally `json.loads` the body crashes there rather than reporting a
  failure. Parse defensively.
- **Rate limits are per process and shared across a driver run.** A check that
  asserts "exactly 20 succeed then 5 fail" breaks as soon as an earlier section of
  the same script has spent part of the budget from the same address. Assert the
  *shape* — a run of 401s, then a run of 429s, never interleaved — or restart the
  server first, since the counters are in memory.
- **Privacy sweeps must search for secret *values*, not the word "password".**
  `PASSWORD_CHANGED` is a required audit action, so a substring check for
  "password" false-positives on `GET /users/{id}/audit`. Assert the actual
  password strings, `$argon2` and `password_hash` are absent instead. For the log
  sweep, read the *issued* nonces and token hashes out of the DB and search for
  those exact values — a generic pattern will not catch a leak.
- The **last-admin 409 is unreachable over HTTP** and that is expected: demoting
  or deactivating an admin requires a *different* TENANT_ADMIN caller, which
  implies a second admin exists, and self-targeting is refused first. Verify the
  invariant at the service layer; over HTTP just confirm the tenant can never be
  stranded (every route returns 403/404 first).
- **`fileConfig` in `alembic/env.py` must keep `disable_existing_loggers=False`.**
  The default disables every logger that already exists, including all of Karya's,
  in any process that runs Alembic in-process — the test suite does, so without it
  the application logs silently vanish mid-run.
