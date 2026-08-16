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
| 4 | Attendance check-in / check-out | Not started |

Phase 2 adds the identity and authorization layer every later feature depends
on: Argon2id password hashing, JWT access tokens, revocable refresh tokens with
mandatory rotation, tenant isolation, and reusable role dependencies. It added
exactly one table (`refresh_tokens`) and changed no Phase 1 schema.

Phase 3 adds presence verification: server-side GPS geofencing plus single-use
dynamic QR challenges. It added **no tables and no migration** — it reuses the
Phase 1 `attendance_locations`, `qr_challenges` and `audit_logs` tables.

See [§10 — Not implemented yet](#10-what-is-intentionally-not-implemented-yet).

## 3. Technology stack

| Concern         | Choice                                    |
| --------------- | ----------------------------------------- |
| Language        | Python (target 3.12+; floor 3.11)         |
| Web framework   | FastAPI                                   |
| ORM             | SQLAlchemy 2.x (typed declarative models)  |
| Driver          | psycopg 3 (`postgresql+psycopg`)          |
| Database        | PostgreSQL 16                             |
| Migrations      | Alembic                                   |
| Validation      | Pydantic v2 / pydantic-settings           |
| Password hashing| Argon2id (`argon2-cffi`)                  |
| Access tokens   | JWT HS256 (`PyJWT`)                       |
| Containers      | Docker Compose                            |
| Tests           | pytest (against real PostgreSQL)          |

Database access is **synchronous**. Phase 1 has no request path that touches
the database, and a sync engine keeps Alembic and the test fixtures simple.

## 4. How to start PostgreSQL

Either database source works — the application only reads `POSTGRES_*` /
`DATABASE_URL`, so it does not care which one is running.

### Option A — Docker (recommended for a clean, disposable database)

From `backend/`:

```bash
docker compose up -d
docker compose ps          # wait for "healthy"
```

The compose file provisions PostgreSQL 18 only, with a named persistent volume
(`karya-postgres-data`), a `pg_isready` health check, and configurable
credentials, database name and host port. **Redis is deliberately not
included** — it arrives with QR challenges, sessions and rate limiting.

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

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Fail-safe behaviour.** `JWT_SECRET_KEY` has no fallback value. If it is
missing and `ENVIRONMENT` is anything other than `local`/`test`, the application
refuses to start. In `local`/`test` it still starts — so `GET /health` and the
database tooling work on a fresh checkout — but any attempt to mint or verify a
token raises instead of signing with a guessable default.

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
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Interactive docs: <http://127.0.0.1:8000/docs>.

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

`test_presence_concurrency.py` is the only module that commits to the database
(real concurrency needs separate connections); it deletes its own rows in
teardown. It also contains a deliberately naive implementation and asserts that
implementation *would* double-consume — so if the harness ever stops creating
real lock contention, that test fails rather than the suite quietly passing.

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
| `POST` | `/api/v1/auth/login` | — | Tenant-scoped login → token pair |
| `POST` | `/api/v1/auth/refresh` | refresh token in body | Rotate → new token pair |
| `POST` | `/api/v1/auth/logout` | refresh token in body | Revoke that session (204) |
| `GET`  | `/api/v1/auth/me` | Bearer access token | The caller's own profile |
| `POST` | `/api/v1/presence/qr/challenge` | MANAGER / TENANT_ADMIN | Issue a QR challenge (Phase 3) |
| `POST` | `/api/v1/presence/verify` | Any active user | Verify presence (Phase 3) |

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

**Deferred to Phase 4 (attendance):** check-in / check-out APIs · attendance
business logic · attendance history APIs · attendance reports.

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

Also deliberately absent: any endpoint that changes a user's role (so
self-escalation has no surface), and any access-token blacklist (access tokens
are short-lived; revocation lives at the refresh-token layer). The
`app/security/` and `app/middleware/` packages are still not needed — password
and token logic lives under `app/services/auth/`, and the only middleware so far
is CORS, configured in `main.py`.

## Project layout

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, router mount, GET /health
│   ├── core/config.py           # env-driven settings, SecretStr credentials
│   ├── api/
│   │   ├── deps.py              # get_current_user, tenant context, require_roles
│   │   └── v1/
│   │       ├── router.py        # aggregates v1 routers
│   │       ├── auth.py          # login / refresh / logout / me
│   │       └── presence.py      # qr/challenge / verify
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
│       └── presence/
│           ├── results.py       # shared enums + result dataclasses
│           ├── gps.py           # validation, haversine, geofence
│           ├── qr.py            # challenge lifecycle, atomic consume
│           └── service.py       # combines both signals, audit logging
├── alembic/                     # env.py, script.py.mako, versions/
├── tests/                       # conftest + model/schema/auth/rbac/tenant tests
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

Business logic lives in `services/`, not in route handlers or ORM models.
