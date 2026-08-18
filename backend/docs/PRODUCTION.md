# Karya - production readiness

What a real deployment of the Karya backend requires, and what it does **not** yet
provide. Nothing here is aspirational: where a capability is missing it says so.

Companion to `README.md`, which covers local development.

---

## 1. What Phase 7 hardened, and what it did not

| Area | Status |
| --- | --- |
| Configuration validation, production fail-fast | In the application |
| Security headers, CORS, request size limits | In the application |
| Structured JSON logging, correlation ids | In the application |
| Liveness `/health`, readiness `/ready` | In the application |
| Connection pooling, server-side timeouts, graceful shutdown | In the application |
| Rate limiting | **Per process only** - see section 6 |
| Reverse proxy, TLS termination | Deployment's job - see section 5 |
| Secret storage | Deployment's job - see section 4 |
| Automated backups, PITR | Infrastructure's job - see section 9 |
| Metrics, tracing, alerting | Not implemented - see section 10 |
| Orchestration, autoscaling, rolling deploys | Out of scope - see section 11 |

---

## 2. Required environment variables

`.env.example` documents every variable with its default. These are the ones a
production deployment **must** set; everything else has a safe default.

| Variable | Why it is required |
| --- | --- |
| `ENVIRONMENT=production` | Enables the fail-fast rules below. One of `local`, `test`, `staging`, `production` - an unrecognised value is refused at startup. |
| `JWT_SECRET_KEY` | No default exists. At least 32 characters, and not one of the placeholders published in `.env.example`. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `POSTGRES_PASSWORD` or `DATABASE_URL` | A production database must be authenticated. |
| `CORS_ALLOWED_ORIGINS` | Only if a browser client exists. Every entry must be https. Leave empty for a backend-only deployment; that is the safest setting, not an omission. |

**The application refuses to start** in production when: `JWT_SECRET_KEY` is
missing, too short, or a known placeholder; `DEBUG=true`; the database password is
empty or a placeholder and no `DATABASE_URL` is set; any CORS origin is not
https; or any limit, timeout or pool value is nonsensical. A configuration
mistake becomes a failed boot rather than a quiet weakness.

Rotating `JWT_SECRET_KEY` invalidates every issued access token immediately.
Refresh tokens are unaffected - they are opaque random values checked against the
database, not signed - so clients recover by refreshing. Plan a rotation for a
quiet window all the same.

---

## 3. Database

**Requirements**

- PostgreSQL 13 or newer. Developed and tested against **18.4** (native) and the
  `postgres:18-alpine` image. `gen_random_uuid()` is built in from 13; no
  extension is needed.
- The application role needs SELECT/INSERT/UPDATE on the seven tables and
  nothing more. It never issues DDL at runtime - schema changes are Alembic's job
  - so it does **not** need to own the schema. Grant DDL only to whatever runs
  migrations.
- `TIMESTAMPTZ` everywhere; the server's timezone does not matter, because the
  application never asks SQL to derive a date. Setting the server to UTC anyway
  makes logs and psql sessions easier to read.

**Migrations are a deploy step, not a startup step.**

    alembic upgrade head       # once, before the new version starts serving
    alembic current            # confirm the revision

The container does **not** migrate on boot, on purpose: two replicas starting
together would both try, and Alembic's version table is not a coordination
mechanism. Run it as a pre-deploy job (`docker compose --profile api run --rm api
alembic upgrade head`, a Kubernetes Job, an ECS one-off task).

Every migration so far is backwards-compatible with the previous application
version, so a rolling deploy is safe. That is a property to check per migration,
not a guarantee of the tool: a future column drop or rename would need the usual
expand/contract sequence (add, backfill, deploy code, drop in a later release).

**Rollback.** `alembic downgrade -1` reverses one revision, and each of the four
revisions has a tested `downgrade()`. Reversing a *schema* change does not reverse
a *data* change, and Karya has one migration whose downgrade is safe but
undesirable - `127b35de9c9f` restores `event_timestamp DEFAULT now()`, which
reintroduces a real ordering bug (see section 12). Prefer rolling the application
back and leaving the schema forward.

**Connection budget.** Each API process holds up to
`DB_POOL_SIZE + DB_MAX_OVERFLOW` connections (default 5 + 10 = 15). Size it
against the server:

    instances x workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW)  <  max_connections - headroom

With PostgreSQL's default `max_connections = 100`, reserving about 10 for
administration and migrations: 2 instances x 2 workers x 15 = 60. Comfortable.
Going to 4 instances x 4 workers at the same pool size needs 240 and will not fit
- raise `max_connections` (each backend costs memory), lower the pool, or put
PgBouncer in transaction mode in front. **Do not** simply raise the pool: a bigger
pool does not make a saturated database faster, it moves the queue from the
application, where it is bounded and observable, into the server, where it is
neither.

Two server-side ceilings are set per connection: `DB_STATEMENT_TIMEOUT_MS`
(default 15 s) bounds a runaway query, and `DB_LOCK_TIMEOUT_MS` (default 5 s)
bounds the `SELECT ... FOR UPDATE` waits the attendance and last-admin paths rely
on. The expected lock wait is milliseconds, so 5 s only fires when a transaction
is genuinely stuck - and then it fails one request instead of holding a pool slot
until the pool is exhausted and every request fails. Set either to 0 to disable
if the platform manages them globally.

---

## 4. Secrets

- `.env` is gitignored and must never be committed. Both `.gitignore` files
  exclude it, and no secret appears in any tracked file.
- **Do not ship `.env` to production.** Use the platform's secret store -
  Kubernetes Secret mounted as environment variables, AWS Secrets Manager or
  SSM Parameter Store, Docker Swarm secrets, systemd `EnvironmentFile` with mode
  0600. The application reads plain environment variables, so any of these works
  with no code change.
- Nothing sensitive is baked into the image: the Dockerfile copies no `.env`, and
  `.dockerignore` excludes it from the build context entirely.
- Secrets never reach the logs. Every credential is a `SecretStr`, the database
  URL is logged only in its password-free form, and the log formatter redacts any
  field whose name suggests a credential (password, token, secret, nonce,
  authorization, hash) as a second line of defence.
- SQLAlchemy runs with `hide_parameters=True`, because a `users` INSERT binds
  `password_hash` as a parameter and SQLAlchemy renders bound parameters into
  exception messages, which reach log files.

---

## 5. Reverse proxy and TLS

**HTTPS is mandatory.** Karya sends bearer tokens on every request and accepts
passwords on two endpoints. Terminate TLS at a load balancer or reverse proxy
(ALB, nginx, Caddy, Traefik) and never expose uvicorn directly to the internet.

**The proxy header configuration is load-bearing, not cosmetic.** Karya's
per-address rate limits key on `request.client.host`. Behind a proxy that address
is the *proxy's* unless uvicorn is told to trust its forwarding header:

    uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      --proxy-headers --forwarded-allow-ips=10.0.0.7 \
      --timeout-graceful-shutdown 30 --no-access-log

- **Omit these flags** and every client shares one per-address budget: one busy
  client can exhaust the login limit for everybody.
- **Set forwarded-allow-ips to a wildcard** and any client can spoof its own
  address by sending `X-Forwarded-For`, bypassing those limits entirely. Name the
  proxy's address instead. The shipped Dockerfile CMD deliberately omits both
  flags, so the insecure option is never the default.

The proxy should also: enforce its own request timeout (uvicorn has no global
one), cap request size as a second layer (the application caps at
`MAX_REQUEST_BODY_BYTES`, default 64 KiB), and set `X-Request-ID` if it already
generates one - Karya honours a safe inbound value (letters, digits, dot, dash,
underscore; 64 characters at most) and replaces anything else rather than logging a
caller-controlled string.

**Workers.** `WEB_CONCURRENCY` (or `--workers`) sets the count. Karya's endpoints
are synchronous, so each worker's throughput is bounded by its thread pool and by
the connection pool. Start with 2 per CPU core, then check the connection
arithmetic in section 3 before raising it. Uvicorn handles SIGTERM correctly: it
stops accepting connections, lets in-flight requests finish within
`--timeout-graceful-shutdown`, then runs the lifespan shutdown that disposes the
pool. Set the platform's termination grace period **above** that value (for
example 40 s for a 30 s uvicorn grace) or the orchestrator will SIGKILL
mid-request.

---

## 6. Rate limiting - read this before relying on it

The limiter is a **fixed-window counter in each process's memory**. Concretely:

- It **does** stop one client brute-forcing or flooding **one instance**, and it
  stops a mobile client stuck in a retry loop.
- Login failures are counted per (tenant, email) as well as per address, so
  guessing one account is throttled even from many addresses. Only failures count
  and a success clears the counter, so a person who mistypes their password twice
  is unaffected.
- It is **not** shared across instances. With N replicas an attacker effectively
  gets N times the budget, because each process only counts what it saw.
- Counters are **lost on restart**, so a deploy resets every window.
- A fixed window admits up to twice the limit across a window boundary.

**Therefore, for a multi-instance deployment, put a limiter at the edge too** -
ALB/WAF rate rules, nginx `limit_req`, Cloudflare - and treat the in-process one
as defence in depth. When shared state is wanted instead,
`app/core/rate_limit.py` exposes a three-method `RateLimiter` protocol (`consume`,
`peek`, `clear`) chosen to map onto Redis INCR+EXPIRE, GET and DEL; a Redis
backend is a second class plus one line in `get_rate_limiter()`. No route, schema
or handler changes.

Every limit is configurable (the `RATE_LIMIT_*` block in `.env.example`) and can
be turned off wholesale with `RATE_LIMIT_ENABLED=false` if the edge handles it.

**One trade-off stated plainly:** per-account failure counting means someone who
knows an email address can deliberately spend that account's failure budget and
throttle its logins for up to 15 minutes on that instance. That is inherent to
per-account throttling. It is mitigated by counting only failures, by a window in
minutes rather than hours, and by a limit (10) far above ordinary mistyping - but
it is a real trade, not an absence of one.

---

## 7. Health checks

| Endpoint | Checks | Use it for |
| --- | --- | --- |
| `GET /health` | Nothing external. Always 200 if the process is running. | **Liveness** - container restarts |
| `GET /ready` | `SELECT 1` against PostgreSQL. 200 or 503. | **Readiness** - load-balancer rotation, rollout gating |

Do **not** point liveness at `/ready`. An orchestrator *kills* what fails
liveness, so a database blip would restart every healthy API process - turning a
recoverable dependency failure into an outage, with a restart storm on top, at the
moment the database can least afford it. Readiness merely removes an instance from
rotation, which is the correct response.

Both are unauthenticated, because the infrastructure that needs them cannot hold a
credential, and both return a fixed one-word payload with no version, hostname,
driver, timing or error detail.

---

## 8. Logging

One JSON object per line on **stderr**; the container runtime or systemd collects
it. `LOG_FORMAT=console` gives human-readable lines for a terminal.

Every record carries `timestamp` (UTC ISO-8601), `level`, `logger`, `message` and,
inside a request, `request_id`. One access line per request adds `method`, `path`,
`route` (the template, for example `/attendance/users/{user_id}`), `status_code`,
`duration_ms`, `client_ip` and - once authentication has resolved - `user_id` and
`tenant_id`.

Deliberately absent: the **query string**, because a search term is user input that
has no business sitting in a log retained for months; the raw path is logged, the
query is not. Also absent: passwords, password hashes, access tokens, refresh
tokens, QR nonces, `Authorization` headers, request bodies, and email addresses on
failed logins (a log of attempted addresses is a list of accounts worth attacking -
the tenant slug is logged instead, which is what an operator correlates by).

Business events worth alerting on: `login_failed`, `login_throttled`,
`rate_limited`, `refresh_rejected`, `database_error`, `database_unreachable`,
`unhandled_exception`, `application_startup`, `application_shutdown`. 4xx logs at
WARNING and 5xx at ERROR, so an alert on ERROR fires for defects and not for a
mistyped password.

**Retention.** Access logs carry `client_ip`, `user_id` and `tenant_id`, which are
personal data in most jurisdictions. Set a retention period deliberately (30 to 90
days is typical) rather than keeping them forever by default.

---

## 9. Backup and recovery

**Not implemented by Karya, and required before production.** Attendance events
are the product's source of truth and are immutable by design; losing them cannot
be repaired by recomputation.

**Minimum viable**

- `pg_dump --format=custom` nightly, stored off-host (object storage), encrypted
  at rest.
- Retention with distinct tiers: for example 7 daily, 4 weekly, 12 monthly. One
  rolling backup is not a backup - it happily overwrites the last good copy with a
  corrupt one.

**Preferred - point-in-time recovery**

- Continuous WAL archiving (`archive_mode = on` plus an `archive_command`, or
  `pg_receivewal`), with a base backup from `pg_basebackup` or pgBackRest.
- Gives recovery to any instant within the retention window, which matters because
  the realistic disaster is an accidental bulk change, not a disk failure - and a
  nightly dump loses up to a day of attendance.
- Managed platforms (RDS, Cloud SQL, Azure Database, Neon, Supabase) provide this;
  **confirm the retention window and that it is switched on**, rather than
  assuming.

**Restore testing is the part that gets skipped, and it is the part that matters.**
Restore to a scratch database on a schedule (quarterly at least), then verify:
`alembic current` reports the expected revision; row counts for `attendance_events`
and `audit_logs` are plausible; and `GET /ready` against the restored database
returns 200. An untested backup is a hypothesis.

**Also back up** `JWT_SECRET_KEY` - in the secret store, not with the database.
Losing it does not lose data but signs every user out at once.

---

## 10. Monitoring

Phase 7 provides the primitives and stops there: structured logs, correlation ids,
per-request latency and status, and the two probes. There is **no** `/metrics`
endpoint, no Prometheus exposition and no tracing.

What to watch from what exists:

- **Availability** - `/ready` failure rate and duration.
- **Latency** - `duration_ms` percentiles grouped by `route`. The template makes
  per-endpoint aggregation possible without identifiers exploding the cardinality.
- **Errors** - count of `event=unhandled_exception` and of status 500 or above.
  Both should normally be zero; alert on any.
- **Abuse** - rates of `login_failed`, `login_throttled`, `rate_limited`.
- **Saturation** - pool exhaustion shows up as rising `duration_ms` with no
  matching database slowness. `SELECT count(*) FROM pg_stat_activity` against the
  connection budget in section 3 is the direct check.
- **Database** - connection count, replication lag if applicable, disk headroom,
  and `attendance_events` growth.

Extension points are deliberately clean: a metrics middleware would sit alongside
`app/middleware/request_context.py` and reuse the same timing, and OpenTelemetry
would consume the existing `request_id` as a span attribute.

---

## 11. Deployment topology

Docker Compose is **not** production orchestration - no rolling deploys, no
replicas, no secret store, no scheduling. It is here for local development and for
integration-testing the production image.

A production topology needs: a TLS-terminating load balancer routing on `/ready`;
two or more API replicas; a managed or replicated PostgreSQL with automated
backups; a secret store; log aggregation; and a migration step that runs once per
deploy, before the new version serves traffic. Kubernetes manifests, ECS task
definitions and Terraform are out of scope for Phase 7.

**Deploy checklist**

1. `ENVIRONMENT=production` and every variable in section 2 set from the secret
   store.
2. `alembic upgrade head` as a one-off job; confirm with `alembic current`.
3. Start the new version; wait for `/ready` to return 200 before adding it to the
   load balancer.
4. Confirm `application_startup` in the logs shows the expected `version`,
   `environment`, `auth_configured: true` and `rate_limit_enabled`.
5. Smoke test over HTTPS: `/health`, `/ready`, a login, and one authenticated
   read.
6. Check that a response carries `X-Request-ID` and the expected security headers.

---

## 12. Known residual risks

Recorded rather than hidden.

1. **Rate limiting is per process.** Section 6. The material gap for a
   multi-instance deployment; mitigate at the edge.
2. **`refresh_tokens` grows without bound.** Rows are revoked, never deleted, so
   the audit trail survives - but nothing prunes expired ones. The `expires_at`
   index exists for a sweeper that does not exist yet. Harmless at current scale;
   a periodic delete of rows whose `expires_at` is well in the past is the whole
   fix, and it is not implemented.
3. **No password reset.** An administrator can only create an account *with* a
   password and convey it out of band. Doing this properly needs email delivery,
   single-use expiring tokens, anti-enumeration and its own rate limit; a
   half-built version would be worse than none.
4. **GPS is evidence, not proof.** The server validates coordinates and accuracy
   rigorously but cannot detect a spoofed location on a rooted device. The
   single-use rotating QR is what raises the cost of that; device attestation
   would raise it further and is deferred.
5. **`/docs` loads Swagger UI from a CDN**, so it renders blank in an air-gapped
   network. The API is unaffected, and `DOCS_ENABLED=false` turns the page off.
6. **No access-token revocation.** Access tokens are valid until they expire
   (default 15 minutes). Deactivating a user or changing a role takes effect on
   the *next* request because the database is re-read every time, and every
   refresh session is revoked immediately - so the exposure is bounded by the
   access-token lifetime, which is the trade `ACCESS_TOKEN_EXPIRE_MINUTES`
   controls.
7. **Attendance event ordering depends on the server clock.** Phase 7 fixed the
   real bug here - `event_timestamp` now defaults to `clock_timestamp()`, so a
   check-out committed second can no longer be stamped before the check-in it
   followed (migration `127b35de9c9f`). A large **backwards** system-clock jump on
   the database host could still misorder events. NTP configured to slew rather
   than step addresses it; a monotonic sequence column would make it structural
   and is not implemented.
8. **Single attendance location per tenant.** The schema supports several and the
   QR is bound to a location, but the resolution logic picks the one active site.
9. **No supply-chain integrity.** `constraints.txt` pins versions but carries no
   hashes; see that file's own header for why, and for what it does not cover.
