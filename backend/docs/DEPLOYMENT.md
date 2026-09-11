# Karya - free-tier deployment and CI/CD

This documents one concrete, working deployment of Karya, distinct from
`PRODUCTION.md` (which stays provider-agnostic and covers what any
production deployment needs). This file covers the specific stack chosen
for the project's first public deployment, why, and exactly how the
pipeline moves a change from a push to a live update.

Cost: **$0/month**, on each provider's free tier as of when this was
written. Free-tier limits change over time and are not re-verified by this
document automatically - check each provider's own pricing page before
relying on a number here.

## 1. The stack, and why

| Layer | Provider | Why this one |
|---|---|---|
| Backend | [Render](https://render.com) | Runs `backend/Dockerfile` unmodified - no separate buildpack config to maintain. Free web service plan; sleeps after 15 min idle (see §5). |
| Database | [Neon](https://neon.tech) | Free serverless Postgres with no forced expiry (unlike some providers' free Postgres, which auto-deletes after a fixed window). Karya's sync SQLAlchemy engine manages its own connection pool, so this deployment uses Neon's *direct* endpoint, not its pgbouncer pooler. |
| Frontend | [Vercel](https://vercel.com) | Static Vite/PWA build, zero-config SPA routing for the framework preset, generous free tier, automatic HTTPS. |
| Email | [Brevo](https://brevo.com), via its **HTTP API**, not SMTP | `ENVIRONMENT=production` refuses to boot without an email transport configured (`app/core/config.py`, `_validate_production`) - this deployment runs fully hardened `production`, not the SMTP-skipping `staging` shortcut, so real users can self-register from day one. SMTP specifically does not work here: verified directly that Render's free tier blocks outbound SMTP connections (a real send attempt hung until timeout and never reached `smtp-relay.brevo.com`) - see §5 and `app/services/email/mailer.py`. |
| CI/CD | GitHub Actions | Free on public repos; gates every deploy on the real test suite passing first (see §3) - neither Render's nor Vercel's own auto-deploy runs `pytest` or `vitest`. |

## 2. Repository layout added for this

```
.github/workflows/backend.yml    test (pytest, real Postgres) -> migrate -> trigger Render
.github/workflows/frontend.yml   test (typecheck/lint/test/build) -> deploy via Vercel CLI
render.yaml                      Render Blueprint: service definition, env var list
frontend/vercel.json             build command, output dir, SPA fallback rewrite
```

Both workflows are path-filtered (`paths: ["backend/**"]` /
`["frontend/**"]`): a change to one half of the app never triggers a test
run or deploy of the other half.

## 3. How a change goes live

1. Push to `master`.
2. GitHub Actions runs the test job for whichever half changed:
   - Backend: `pytest` against a fresh `postgres:18-alpine` service
     container in the runner - the same real-database policy as local
     development (see the repository root `CLAUDE.md`'s Testing section).
   - Frontend: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
3. Only if that job is green, and only on a real push to `master` (never on
   a pull request build), the deploy job runs:
   - Backend: `alembic upgrade head` against the live Neon database, then
     `alembic current` to confirm, then a `POST` to Render's deploy hook
     URL. Migrations run here - in CI, as a distinct step - never inside the
     container at startup, matching the reasoning already in
     `PRODUCTION.md` §3 (two replicas starting together must never both
     attempt a migration; Render's free plan only ever runs one instance,
     but the pipeline doesn't rely on that to stay correct).
   - Frontend: `vercel pull` -> `vercel build --prod` -> `vercel deploy
     --prebuilt --prod`, using `VITE_API_BASE_URL` (a GitHub Actions
     *variable*, not a secret - it ends up in the public JS bundle either
     way) pointed at the Render URL.
4. Both Render's and Vercel's own Git auto-deploy are turned off
   (`render.yaml`'s `autoDeploy: false`; Vercel Project Settings -> Git ->
   Disconnect), so this pipeline is the *only* path to production for
   either half of the app - a red test run can never reach real users on
   either side.

   **This wasn't true for a while, and it's worth knowing the history**:
   Vercel's Git integration auto-builds on *every* push to `master`
   regardless of this repo's path filters, independent of this workflow -
   a real backend-only commit triggered one directly (`"source":"git"` in
   Vercel's own deployment history), and because that build never went
   through `typecheck`/`lint`/`test` or received `VITE_API_BASE_URL` from
   GitHub Actions, it crashed the whole app at boot (see §5's incident
   writeup). The fix was two layers: `VITE_API_BASE_URL`/`VITE_APP_ENV` are
   now also real Vercel **project** environment variables (§4), so even a
   stray build from a reconnected integration would work correctly rather
   than crash; and Vercel's Git integration is now disconnected entirely,
   closing the test-gating gap for real, not just working around its
   symptom. Verified after disconnecting: a `workflow_dispatch` run of
   `frontend.yml` still deployed successfully (`"source":"cli"` in Vercel's
   deployment history, confirming the CLI path doesn't depend on the Git
   integration being connected).

## 4. Environment variables, by where they live

**Render dashboard** (prompted once when the Blueprint is created, from
`render.yaml`'s `sync: false` entries - never stored in git):
`JWT_SECRET_KEY`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`, `PUBLIC_APP_URL`,
`BREVO_API_KEY`, `SMTP_FROM_ADDRESS` (still needed - it's the sender identity
for both transports, not an SMTP-only setting). See `backend/.env.example`
for what each one does, and §5 below for why this deployment uses
`BREVO_API_KEY` rather than `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD` even
though the app supports both.

**GitHub Actions secrets** (repo Settings -> Secrets and variables ->
Actions -> Secrets): `PROD_DATABASE_URL` (same Neon connection string as
Render's `DATABASE_URL`), `PROD_JWT_SECRET_KEY` (same value as Render's
`JWT_SECRET_KEY` - the CI migration step and the running app must agree
enough to both pass `Settings` validation, though the migration step
itself never mints a token), `RENDER_DEPLOY_HOOK_URL`, `VERCEL_TOKEN`,
`VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`.

**GitHub Actions variables** (same screen, "Variables" tab):
`VITE_API_BASE_URL` = the Render service's public URL.

**Vercel project environment variables** (Project Settings -> Environment
Variables, Production + Preview) - a deliberate duplicate of the two build
values above, not just the GitHub Actions copy: `VITE_API_BASE_URL`,
`VITE_APP_ENV=production`. See §5 for why this needs to exist twice.

## 5. Known trade-offs of this specific stack

These are additions to `PRODUCTION.md` §12's residual-risk list, specific to
running on free tiers rather than gaps in the application itself:

- **(Resolved) Vercel's Git integration used to deploy independently of
  this repo's own pipeline**, running neither `typecheck`/`lint`/`test`
  nor receiving `VITE_API_BASE_URL` from GitHub Actions. This produced a
  real incident: a backend-only commit triggered a Vercel-git build with
  no API URL configured, which crashed the whole app at boot
  (`src/config/env.ts` validates eagerly - see its module docstring) - a
  blank page in production, caught by hitting the live site directly
  rather than by any automated check. Fixed in two layers: `VITE_API_BASE_URL`/
  `VITE_APP_ENV` are now also real Vercel **project** environment
  variables (§4), and Vercel's Git integration is now disconnected
  entirely (§3 step 4) - so this workflow is the only path to a frontend
  deploy, the same guarantee `render.yaml`'s `autoDeploy: false` already
  gave the backend.
- **Cold starts.** Render's free web service sleeps after 15 minutes with
  no traffic; the first request after that takes on the order of 30-50
  seconds while it wakes. `/health`'s liveness check (no DB query) will be
  slow on that first hit too, not just user-facing requests.
- **Rate limiting stays correct, but only because this is one instance.**
  `PRODUCTION.md` §6 already documents that Karya's rate limiter is
  in-memory and per-process; Render's free plan runs exactly one instance,
  so that limitation doesn't compound here the way it would across
  replicas. If this ever moves to a paid multi-instance plan, revisit that
  section before relying on the limiter again.
- **`--proxy-headers --forwarded-allow-ips=*`** (set in `render.yaml`'s
  `dockerCommand`) trusts Render's edge proxy for the real client IP used
  by rate limiting. Render's container has no other public entry point, so
  the wildcard is scoped by Render's own network topology - but this is
  this deployment's judgment call, not a property the application itself
  enforces. Reconsider it if the app is ever deployed somewhere the
  container *is* directly reachable.
- **No backup automation.** `PRODUCTION.md` §9 already states Karya ships
  none; Neon's own free-tier backup/point-in-time-recovery window (check
  their current docs) is what this deployment relies on, not anything
  Karya or this pipeline adds.
- **Render's free tier blocks outbound SMTP.** Discovered by reproducing a
  live onboarding failure: `POST /api/v1/onboarding/tenants` returned 503
  with the log line `"error":"TimeoutError"` against `smtp-relay.brevo.com`,
  duration ~14s (Karya's own `SMTP_TIMEOUT_SECONDS` giving up, not Brevo
  refusing anything - the connection never completed at all). This is a
  common anti-spam-relay policy on free-tier PaaS hosts, not a Karya or
  Brevo bug. The fix was adding a second transport
  (`app/services/email/mailer.py`'s Brevo-HTTP-API path) rather than
  fighting the platform - plain HTTPS is not blocked the way SMTP ports
  are. If this deployment ever moves off Render, either transport still
  works; there was no need to remove SMTP support, only to stop relying on
  it *here*.
- **Brevo's free-tier sending limit** applies to every verification email
  Karya sends, regardless of which transport delivers it. If it's ever
  exceeded, `app/services/email/mailer.py` surfaces the delivery failure as
  a 5xx on the onboarding endpoint rather than silently dropping the
  email - it will be visible, not silent.

## 6. Rolling back

A bad backend deploy: revert the offending commit on `master` under
`backend/`, push - the pipeline redeploys the last-good code through the
same tested path. Render also keeps prior deploys in its dashboard for a
manual rollback if you need it faster than a revert-and-push.

A bad migration is the one step this pipeline can't automatically undo -
`alembic downgrade -1` against the Neon database is a manual, deliberate
action (same as `PRODUCTION.md`'s general guidance), not something to
script into the deploy path.
