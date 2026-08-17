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
| Boot | `GET /health`, `GET /openapi.json` (7 paths), `GET /docs` |
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

Attendance refusals are HTTP **200 with `success: false`** plus a `reason`, same
convention as presence. After a run, assert the per-user event sequence strictly
alternates CHECK_IN/CHECK_OUT, and that `USED` challenges equal attendance events
(a consumed challenge with no event would mean the transaction boundary leaked).

Geofence maths for building coordinates: `lat + meters / 111194.93` moves that
many metres north of `(12.9716, 77.5946)` with a 150 m radius.

## Gotchas

- **Port 5432 is the native `postgresql-x64-18` service**, not Docker. `docker
  compose up` binds only IPv6 and connections silently hit the native server.
  For the container, set `POSTGRES_PORT=5433`.
- **`TIMESTAMPTZ` comes back as `+05:30` locally** (native PG uses the system
  zone) but `Z` under Docker. Same instant, two spellings — compare parsed
  datetimes, never string prefixes. This has bitten twice: `iso[11:16]` to read a
  clock time reads a *different* clock in the two environments. Parse and
  `.astimezone(UTC)` first.
- Same root cause on the server side: **never `date(event_timestamp)` or
  `::date`** in a query. The session TimeZone decides the answer, so days would
  bucket differently locally vs Docker. Filter on explicit UTC instants instead.
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
  lock. See `tests/test_presence_concurrency.py::interleave`.
- Pydantic lax mode coerces numeric **strings** (`"12.97"` is accepted for
  latitude). Out-of-range, `"nan"`, `"1e400"` and non-numeric strings still 422,
  so the bounds hold — don't mistake the coercion for a hole.
- Presence rejections are **200 with `verified: false`**, not 4xx. Only 401
  (unauthenticated) and 422 (malformed/smuggled) are error codes.
