/**
 * The one centralized HTTP client. Every request Karya's frontend makes to
 * the backend goes through `apiFetch` — no component or feature module calls
 * `fetch` directly. That is what keeps base URL, JSON handling, auth headers,
 * timeouts, cancellation and error normalization defined in exactly one place.
 *
 * This module deliberately knows nothing about React, TanStack Query or the
 * auth store. Authenticated requests, token refresh and "what happens when a
 * session expires" are wired in from outside via `configureApiAuth` — see
 * `src/lib/auth/session.ts`, which is the only caller. That seam is what lets
 * this file be tested and reasoned about with no auth state at all, and is
 * what stops an import cycle between "the client that needs a token" and
 * "the auth module that needs the client to fetch one".
 */
import { env } from '@/config/env'
import { apiErrorFromResponse, cancelledApiError, networkApiError, timeoutApiError } from '@/lib/api/errors'

const DEFAULT_TIMEOUT_MS = 15_000

export interface AuthHooks {
  /** Synchronous — the access token lives in memory (a store), never storage. */
  getAccessToken: () => string | null
  /**
   * Called on a 401 for an `auth: true` request. Must resolve with a fresh
   * access token or reject. `client.ts` deduplicates concurrent calls to this
   * itself (see `refreshOnce` below) — the hook does not need its own guard.
   */
  refreshAccessToken: () => Promise<string>
  /** Called once refreshing has failed — the session is over. */
  onSessionExpired: () => void
}

let authHooks: AuthHooks | null = null

/** Wired once at app bootstrap by `src/lib/auth/session.ts`. */
export function configureApiAuth(hooks: AuthHooks): void {
  authHooks = hooks
}

// Deduplicates concurrent refreshes: five components hitting a stale access
// token at once must trigger exactly one `/auth/refresh` call, not five
// (which would race the Phase 2 rotate-on-use refresh token and fail four of
// them outright).
let inFlightRefresh: Promise<string> | null = null

function refreshOnce(): Promise<string> {
  if (!authHooks) return Promise.reject(new Error('Auth hooks not configured'))
  if (!inFlightRefresh) {
    inFlightRefresh = authHooks
      .refreshAccessToken()
      .finally(() => {
        inFlightRefresh = null
      })
  }
  return inFlightRefresh
}

export interface ApiFetchOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  /** Attach `Authorization: Bearer <access token>` and auto-refresh-and-retry once on 401. Default true. */
  auth?: boolean
  /**
   * Attach `Authorization: Bearer <token>` verbatim instead of the signed-in
   * user's access token - for the one caller that authenticates as
   * something other than a user session: the office-display kiosk's own
   * display token (see `src/lib/api/endpoints/display.ts`). Implies no
   * refresh-and-retry on 401 - a display token isn't a session, there is
   * nothing to refresh it into, a 401 just means "revoked or wrong".
   * Mutually exclusive with `auth` in practice, though nothing enforces that.
   */
  token?: string
  /** Caller-supplied cancellation (e.g. TanStack Query's queryFn signal). */
  signal?: AbortSignal
  timeoutMs?: number
  /** @internal set on the retried request after a refresh, to prevent a refresh loop. */
  _retried?: boolean
}

function buildUrl(path: string, query?: ApiFetchOptions['query']): string {
  const url = new URL(env.apiBaseUrl + path)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

/** Combine the caller's cancellation with an internal timeout into one signal. */
function combineSignals(external: AbortSignal | undefined, timeoutMs: number) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), timeoutMs)
  external?.addEventListener('abort', () => controller.abort(external.reason))
  return {
    signal: controller.signal,
    cleanup: () => clearTimeout(timer),
  }
}

async function readJsonBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/**
 * Perform one request against the Karya API.
 *
 * `path` is the API path only (e.g. `/api/v1/auth/login`), never a full URL —
 * that keeps the base URL swappable per environment with zero call-site
 * changes. Throws `ApiError` for every failure mode; never returns a
 * partially-parsed or ambiguous result.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const {
    method = 'GET',
    body,
    query,
    auth = true,
    token: explicitToken,
    signal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    _retried = false,
  } = options

  const headers = new Headers({ Accept: 'application/json' })
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  // A random per-request id, sent so a network failure with no response can
  // still be correlated against client-side logs; the server may keep it or
  // replace it (see backend `RequestContextMiddleware`), and either value is
  // read back off the response, never assumed.
  headers.set('X-Request-ID', crypto.randomUUID())

  if (explicitToken) {
    headers.set('Authorization', `Bearer ${explicitToken}`)
  } else if (auth) {
    const token = authHooks?.getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  const { signal: combinedSignal, cleanup } = combineSignals(signal, timeoutMs)

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: combinedSignal,
      // Karya's backend uses bearer tokens, not cookies, for authentication —
      // there is nothing for the browser to send or store as a credential.
      credentials: 'omit',
    })
  } catch (cause) {
    cleanup()
    if (signal?.aborted) throw cancelledApiError()
    if (combinedSignal.aborted) throw timeoutApiError()
    throw networkApiError(cause)
  }
  cleanup()

  if (response.status === 401 && auth && !explicitToken && !_retried && authHooks) {
    try {
      await refreshOnce()
    } catch {
      authHooks.onSessionExpired()
      const errorBody = await readJsonBody(response)
      throw apiErrorFromResponse(response, errorBody)
    }
    return apiFetch<T>(path, { ...options, _retried: true })
  }

  const responseBody = await readJsonBody(response)

  if (!response.ok) {
    if (response.status === 401 && auth && !explicitToken) {
      // Refresh itself did not throw above only because `_retried` was
      // already true — i.e. the retried request is *also* unauthorized.
      // That is a genuinely dead session, not a transient race. Excluded
      // for `explicitToken` requests: a rejected display token must never
      // tear down whatever unrelated user session happens to be signed in
      // (normally none — the kiosk route needs no login at all — but
      // nothing here should assume that).
      authHooks?.onSessionExpired()
    }
    throw apiErrorFromResponse(response, responseBody)
  }

  return responseBody as T
}
