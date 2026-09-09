# Error handling

One normalized shape (`ApiError`, in `src/lib/api/errors.ts`), one place that
turns it into words (`describeError`, in `src/lib/errors/describeError.ts`),
and one component that renders the result (`ErrorState`, in
`src/components/feedback/ErrorState.tsx`). No other file should need to
inspect an HTTP status code or a `fetch` rejection directly.

## The mapping

| Status | `ApiError.kind` | User sees | Retryable? |
| --- | --- | --- | --- |
| — (network failure) | `network` | "Can't reach Karya" | ✅ |
| — (client timeout) | `timeout` | "That took too long" | ✅ |
| — (aborted) | `cancelled` | (usually invisible — a superseded search/route change) | ❌ |
| 401 | `unauthorized` | "Your session has expired" *(except the login form and email verification — see below)* | ❌, redirect to `/login` |
| 403 | `forbidden` | "You don't have permission" | ❌ |
| 404 | `not_found` | "Not found" | ❌ |
| 409 | `conflict` | Backend's own message (already safe/specific — e.g. "A user with that email already exists") | ❌ |
| 422 | `validation` | Field-level errors, mapped back onto the form | ❌ — the input needs to change |
| 429 | `rate_limited` | "Too many attempts" + a wait time if `Retry-After` was present | ✅, after the wait |
| 500 | `server` | "Something went wrong" | ✅ |
| 503 | `unavailable` | "Service temporarily unavailable" | ✅ |
| anything else | `unknown` | Generic fallback | ✅ |

## The deliberate exceptions: login's and verification's 401

`describeError`'s generic 401 copy ("Your session has expired, sign in
again") is correct for an authenticated screen whose token died mid-session.
It is the wrong sentence for someone who just typed the wrong password on the
login form — they never had a session to expire. `LoginForm.tsx` special-cases
this one kind, on this one screen, to show the backend's own message
("Invalid credentials") verbatim instead — which is safe to show as-is,
because that message is *already* the deliberately generic, anti-enumeration
text the backend's own design requires (see backend README §8a: the same
401 for an unknown tenant, an unknown user, a wrong password, and a
deactivated account).

`VerifyEmailPage.tsx` makes the same exception for the same reason, one level
removed: a rejected onboarding verification link (missing, expired, or
already used — Phase 11) is a 401 too, but again never had a "session" to
expire. It shows the backend's own message ("This verification link is
invalid or has expired") verbatim, which is safe for the same
anti-enumeration reason (see backend `onboarding.py`).

These are the only two places in the frontend that override the shared
mapping, and each is called out explicitly at its own call site
(`src/features/auth/LoginForm.tsx`, `src/pages/onboarding/VerifyEmailPage.tsx`)
so neither looks like a copy-paste mistake later.

## Never surfaced to the user

- Raw backend internals (SQL, stack traces, table/constraint names) — the
  backend already refuses to leak these (see backend README §8f); the
  frontend adds no path that could re-expose one anyway, since it only ever
  reads `{"detail": ...}`.
- The 422 "input" field Pydantic would otherwise include — the backend
  strips it before the response leaves (backend §8f, "the 422 body echoed
  the submitted password" — a real bug found and fixed there), and the
  frontend's `ValidationIssue` type only has `type` / `loc` / `msg` to begin
  with, so there's nothing to accidentally render even if it appeared.
- A raw `X-Request-ID` in the main UI. It's carried on `ApiError.requestId`
  and shown only in `ErrorState`'s small "Reference: ..." line — useful for
  a support conversation, not a general-purpose detail.

## Retries

`describeError(...).retryable` decides whether `ErrorState` offers a "Try
again" button. It is `false` for 401/403/404/409/422/`cancelled` on
purpose — none of those change by simply repeating the request unmodified.
Nothing in this codebase auto-retries a mutation (attendance actions,
password changes, user edits): TanStack Query's mutation default is
`retry: false` (see `src/app/providers.tsx`), and `ConfirmationDialog`
requires an explicit second click for anything destructive. A query (GET)
may retry once automatically for retryable kinds (see the `retry` function
in `createQueryClient`) — reads are idempotent, writes are not, and the
codebase treats that distinction as load-bearing.
