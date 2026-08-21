# Authentication architecture

This documents the frontend's authentication design and, specifically, the one
place it deviates from an ideal it couldn't reach without a backend change —
per this phase's brief, that is documented here rather than made silently.

## The backend contract (Phase 2, unchanged)

`POST /api/v1/auth/login` and `POST /api/v1/auth/refresh` return:

```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 900 }
```

Both tokens are returned **in the JSON response body**. There is no
`Set-Cookie` header and no HttpOnly cookie involved anywhere in the backend's
design (see `backend/README.md` §8a). The refresh token is long-lived (30
days), single-use, and rotates on every use — presenting a used one is a 401,
never silently re-issued.

## What that means for the frontend

The textbook-safest pattern for a long-lived credential in a browser is an
HttpOnly, Secure cookie set by the server — JavaScript can never read it, so
XSS cannot exfiltrate it. **Karya's backend does not offer that** — cookies
were never part of the Phase 2 design, and adding one would be a backend
contract change, which this phase's brief says to document rather than
silently make. So the frontend has to hold both tokens in *some* JS-reachable
form. Given that constraint, the design here is:

| Token | Where it lives | Why |
| --- | --- | --- |
| Access token | `authStore` (Zustand, in-memory only) | Never written to any Storage API. A page reload starts with `accessToken: null` — see `src/stores/authStore.ts`. Short-lived (15 min default), so even a successful XSS read has a small window. |
| Refresh token | `localStorage`, under `karya.refresh_token` | The only Storage API that survives a PWA being closed and relaunched from a home-screen icon days later — `sessionStorage` does not survive that, and Karya's product needs "stays signed in" behaviour on a mobile attendance app. See `src/lib/auth/tokenStorage.ts`. |

**This is a real trade-off, not a solved problem.** `localStorage` is
readable by any script that runs in the page's origin, so a successful XSS
can steal the refresh token. Two things bound the damage:

1. The refresh token is **not a bearer credential for the API** — it can only
   be exchanged, once, at `/auth/refresh`, and every exchange **rotates** it.
   A stolen-and-used token invalidates the legitimate client's copy on its
   next refresh attempt, which surfaces as a forced logout — a detectable
   event, not a silent, permanent compromise.
2. Section 24 of this phase's brief ("frontend security") is honoured
   everywhere else: no `dangerouslySetInnerHTML` in this codebase, all user
   input is rendered through React (which escapes by default), and nothing
   the app does writes arbitrary HTML from a data source. XSS is the
   precondition for this specific risk to matter at all, and the codebase is
   built to make that precondition hard to reach.

**If a real HttpOnly-cookie refresh flow becomes available in a later backend
phase**, this is the one module to change: `src/lib/auth/tokenStorage.ts` and
the calls into it from `src/lib/auth/session.ts`. Nothing else in the app
touches a raw token — every component asks `useAuth()` for `isAuthenticated`
/ `user`, never for a token (§6).

## Request flow

```
apiFetch(path, { auth: true })
  → attach `Authorization: Bearer <access token>` from authStore
  → 200s and non-401 errors: return/throw normally
  → 401: try refreshOnce() (deduplicated — five simultaneous 401s trigger
    exactly one /auth/refresh call, not five racing to rotate the same
    refresh token)
      → success: retry the original request once with the new access token
      → failure: authHooks.onSessionExpired() → clears authStore +
        localStorage, notifies subscribers (query cache clear), and the
        next render of RequireAuth redirects to /login
```

See `src/lib/api/client.ts` for the implementation and `src/lib/auth/session.ts`
for the orchestration (`login`, `logout`, `bootstrapSession`, `performRefresh`).

## Session bootstrap

On every app load, `bootstrapSession()` (called once by `AuthBootstrap` in
`src/app/providers.tsx`) checks `localStorage` for a refresh token:

- **None found** → `unauthenticated` immediately, no network call.
- **Found** → exchange it via `/auth/refresh`, then fetch `/auth/me` to
  populate the user. Either step failing (expired, revoked, deactivated
  account) ends the session the same way a mid-app 401 does — no error is
  shown; "not signed in yet" isn't a failure.

Every route depends on this having already resolved (`RequireAuth` shows a
spinner while `status === 'loading'`), so this is genuinely a blocking
bootstrap step, not a background refresh.

## What every component actually sees

`useAuth()` (`src/features/auth/useAuth.ts`) is the only supported way to ask
about the session:

```ts
const { isAuthenticated, isLoading, user, hasRole, login, logout } = useAuth()
```

No component decodes a JWT, reads `authStore` directly, or touches
`localStorage`. That indirection is what makes the token-storage decision
above a one-file concern instead of a codebase-wide one.
